"""LoreConvo SessionEnd auto-save hook.

Receives session metadata via stdin JSON from Claude Code's SessionEnd hook.
Parses the transcript JSONL to extract a summary, then saves via storage_core.

Designed to run within the 3-5 second timeout window.
"""

import json
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path

# Bootstrap: resolve storage_core and timeutil for non-package callers.
from _bootstrap import resolve_storage_core, resolve_timeutil, BootstrapError

try:
    _storage = resolve_storage_core(Path(__file__))
    utc_now_iso = resolve_timeutil(Path(__file__)).utc_now_iso
except BootstrapError as exc:
    # Write breadcrumb before exiting so the MCP server can surface it.
    from _bootstrap import _write_breadcrumb
    _write_breadcrumb("auto_save", str(exc), [])
    sys.stderr.write(f"LoreConvo auto-save bootstrap error: {exc}\n")
    sys.exit(1)

_open_conn = _storage._open_conn
ensure_schema = _storage.ensure_schema
upsert_session = _storage.upsert_session


_MAX_DECISION_LENGTH = 500
_MAX_SUMMARY_LENGTH = 8000


def _truncate_if_needed(value, max_length, field_name):
    """Truncate value to max_length chars, adding [TRUNCATED] marker if needed."""
    if not value or len(value) <= max_length:
        return value
    marker = f" [TRUNCATED: {field_name} exceeds {max_length} chars]"
    max_content_length = max(0, max_length - len(marker))
    return value[:max_content_length] + marker


def auto_save_tags():
    """Tags for an auto-saved session.

    Always includes 'auto-captured'. When the environment provides LORECONVO_AGENT
    and/or AGENT_RUN_SESSION_ID (set by the scheduled-agent launcher), also tag
    the agent and run so agent-tagged recall can find these stubs. Ordinary
    interactive sessions, which set neither var, are unchanged: just
    ['auto-captured'].
    """
    tags = ["auto-captured"]
    agent = os.environ.get("LORECONVO_AGENT")
    if agent:
        tags.append("agent:" + agent)
    run_id = os.environ.get("AGENT_RUN_SESSION_ID")
    if run_id:
        tags.append("run:" + run_id)
    return tags


def get_db_path():
    """Get database path, matching core/config.py logic."""
    return os.environ.get("LORECONVO_DB", os.path.expanduser("~/.loreconvo/sessions.db"))


def parse_transcript(transcript_path):
    """Parse a Claude Code JSONL transcript into structured session data.

    Extracts: title (from first user message), surface, summary of key exchanges,
    decisions (lines starting with decision-like language), and artifacts.
    """
    if not transcript_path or not os.path.exists(transcript_path):
        return None

    messages = []
    try:
        with open(transcript_path, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    messages.append(entry)
                except json.JSONDecodeError:
                    continue
    except (IOError, PermissionError):
        return None

    if not messages:
        return None

    # Extract user and assistant messages
    user_messages = []
    assistant_messages = []
    tool_uses = []

    for msg in messages:
        # Real Claude Code transcripts wrap messages: {"type":"user", "message": {"role":..., "content":...}}
        inner = msg.get("message", msg)
        role = inner.get("role", "") if isinstance(inner, dict) else msg.get("role", "")
        content = inner.get("content", "") if isinstance(inner, dict) else msg.get("content", "")

        # Handle content that's a list of blocks
        if isinstance(content, list):
            text_parts = []
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "text":
                        text_parts.append(block.get("text", ""))
                    elif block.get("type") == "tool_use":
                        tool_name = block.get("name", "unknown")
                        if tool_name == "Skill":
                            # Extract the actual skill name from the input parameter
                            # so skill-history shows e.g. "skill:langgraph-finance-workflow"
                            # instead of the raw string "Skill"
                            input_val = block.get("input") or {}
                            skill_name = input_val.get("skill") if isinstance(input_val, dict) else None
                            if skill_name:
                                tool_uses.append(f"skill:{skill_name}")
                            else:
                                tool_uses.append("Skill")
                        else:
                            tool_uses.append(tool_name)
                elif isinstance(block, str):
                    text_parts.append(block)
            content = " ".join(text_parts)

        if role == "user" and content:
            user_messages.append(content[:500])  # Truncate long messages
        elif role == "assistant" and content:
            assistant_messages.append(content[:500])

    if not user_messages:
        return None

    # Title: first user message, truncated
    first_msg = user_messages[0]
    title = first_msg[:80].replace("\n", " ").strip()
    if len(first_msg) > 80:
        title += "..."

    # Summary: combine first few exchanges
    summary_parts = []
    for i, msg in enumerate(user_messages[:3]):
        summary_parts.append(f"User: {msg[:200]}")
        if i < len(assistant_messages):
            summary_parts.append(f"Assistant: {assistant_messages[i][:200]}")
    summary = "\n".join(summary_parts)
    summary = _truncate_if_needed(summary, _MAX_SUMMARY_LENGTH, "summary")

    decisions = []
    decision_keywords = ["decided", "agreed", "confirmed", "chose", "will use", "going with", "settled on"]
    for msg in assistant_messages:
        msg_lower = msg.lower()
        for keyword in decision_keywords:
            if keyword in msg_lower:
                for sentence in msg.split("."):
                    if keyword in sentence.lower():
                        clean = sentence.strip()
                        if clean and len(clean) > 10:
                            truncated = _truncate_if_needed(clean, _MAX_DECISION_LENGTH, "decision")
                            decisions.append(truncated)
                break

    # Detect artifacts (file paths, URLs)
    artifacts = []
    for msg in assistant_messages:
        # Look for file paths
        for word in msg.split():
            if "/" in word and ("." in word.split("/")[-1]) and len(word) > 5:
                clean = word.strip("(),\"'`")
                if clean not in artifacts and len(artifacts) < 10:
                    artifacts.append(clean)

    # Detect open questions (simple heuristic)
    open_questions = []
    oq_trigger_phrases = [
        "should we", "what about", "unclear", "not sure",
        "need to decide", "open question", "tbd", "to be determined",
    ]
    for msg in assistant_messages + user_messages:
        # Explicit prefix markers (line-level): "Open question: ..." or "Q: ..."
        for line in msg.split("\n"):
            stripped = line.strip()
            lower = stripped.lower()
            if lower.startswith("open question:") or lower.startswith("q:"):
                clean = stripped[:200]
                if clean and len(clean) > 10 and clean not in open_questions and len(open_questions) < 10:
                    open_questions.append(clean)
        # Sentence-level: trigger phrase + "?" in the same sentence
        msg_lower = msg.lower()
        for phrase in oq_trigger_phrases:
            if phrase in msg_lower:
                for sentence in msg.split("."):
                    sentence_stripped = sentence.strip()
                    if phrase in sentence_stripped.lower() and "?" in sentence_stripped:
                        clean = sentence_stripped[:200]
                        if clean and len(clean) > 10 and clean not in open_questions and len(open_questions) < 10:
                            open_questions.append(clean)
                break

    # Unique tools used
    unique_tools = list(set(tool_uses))[:20]

    return {
        "title": title,
        "summary": summary,
        "decisions": decisions[:10],
        "artifacts": artifacts[:10],
        "open_questions": open_questions[:10],
        "tools_used": unique_tools,
        "message_count": len(user_messages) + len(assistant_messages),
    }


def ensure_tables(conn):
    """Backward-compatible wrapper -- delegates to ensure_schema.

    Deprecated: use ensure_schema(conn) directly. Kept for existing
    test compatibility during the consolidation transition.
    """
    ensure_schema(conn)


def _has_explicit_save_signature(tags_json: str | None) -> bool:
    """True if the stored tags indicate an explicit agent_session_end.py save.

    Explicit saves always carry role:<team> (agent_session_end.py adds it from
    AGENT_ROLE). auto_save's own tags -- ['auto-captured'] plus optional
    agent:/run: copied from the launcher environment -- never include a role:
    tag, so role: is the reliable discriminator between a rich explicit save
    and a shallow hook parse (SH-100589).
    """
    if not tags_json:
        return False
    try:
        tags = json.loads(tags_json)
    except Exception:
        return False
    if not isinstance(tags, list):
        return False
    return any(str(t).startswith("role:") for t in tags)


def save_to_db(db_path, session_id, parsed, project=None, source="session"):
    """Save parsed session data via storage_core.

    source: 'session' for final SessionEnd saves, 'periodic' for mid-session snapshots.
    Periodic saves use the same session_id so the final SessionEnd save overwrites them.
    """
    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    conn = _open_conn(db_path, busy_timeout_ms=2000)
    try:
        ensure_schema(conn)

        # Use Claude's session_id as our primary key so dedup actually works.
        session_uuid = session_id

        # Check if session already exists (e.g., resumed session or duplicate hook fire)
        cursor = conn.execute("SELECT id, tags FROM sessions WHERE id = ?", (session_uuid,))
        row = cursor.fetchone()
        exists = row is not None
        existing_tags_json = row[1] if row else None

        now = utc_now_iso()
        tags_json = json.dumps(auto_save_tags())
        decisions_json = json.dumps(parsed["decisions"])
        artifacts_json = json.dumps(parsed["artifacts"])
        open_questions_json = json.dumps(parsed.get("open_questions", []))

        if exists:
            # SH-100589: never regress an explicit (rich) save to a shallower
            # hook parse. agent_session_end.py's save always carries
            # role:<team>; auto_save's tags never do. If the existing row
            # already has an explicit save, leave it untouched.
            if _has_explicit_save_signature(existing_tags_json):
                sys.stderr.write(
                    "LoreConvo auto-save: skipping update -- existing session "
                    f"{session_uuid} has an explicit save; nothing overwritten\n"
                )
                return True
            # Already saved -- update instead of duplicate.
            conn.execute(
                """UPDATE sessions SET summary = ?, decisions = ?, artifacts = ?,
                   open_questions = ?, tags = ?, end_date = ?, project = ?, source = ?
                   WHERE id = ?""",
                (
                    parsed["summary"],
                    decisions_json,
                    artifacts_json,
                    open_questions_json,
                    tags_json,
                    now,
                    project,
                    source,
                    session_uuid,
                ),
            )
        else:
            upsert_session(
                conn,
                session_id=session_uuid,
                title=parsed["title"],
                surface="code",
                project=project,
                start_date=now,
                end_date=now,
                summary=parsed["summary"],
                decisions=decisions_json,
                artifacts=artifacts_json,
                open_questions=open_questions_json,
                tags=tags_json,
                source=source,
            )

        # Update FTS index
        try:
            conn.execute(
                """INSERT INTO sessions_fts(rowid, title, summary, decisions)
                   SELECT rowid, title, summary, decisions
                   FROM sessions WHERE id = ?""",
                (session_uuid,),
            )
        except Exception:
            pass  # FTS table might not exist in older DBs

        # Save skill/tool usage
        for tool in parsed.get("tools_used", []):
            try:
                conn.execute(
                    "INSERT INTO session_skills (session_id, skill_name) VALUES (?, ?)",
                    (session_uuid, tool),
                )
            except Exception:
                pass

        return True
    except Exception as e:
        sys.stderr.write(f"LoreConvo auto-save DB error: {e}\n")
        return False
    finally:
        conn.close()


def main():
    """Main entry point for SessionEnd hook."""
    try:
        # Read hook input from stdin
        stdin_data = sys.stdin.read()
        if not stdin_data:
            sys.exit(0)

        hook_input = json.loads(stdin_data)
        session_id = hook_input.get("session_id", "unknown")
        transcript_path = hook_input.get("transcript_path", "")
        cwd = hook_input.get("cwd", "")
        project = os.path.basename(cwd.rstrip("/")) if cwd else None

        # Parse transcript
        parsed = parse_transcript(transcript_path)
        if not parsed:
            sys.exit(0)

        # Skip very short sessions (less than 2 messages)
        if parsed["message_count"] < 2:
            sys.exit(0)

        # Save to database
        db_path = get_db_path()
        saved = save_to_db(db_path, session_id, parsed, project)

        if saved:
            sys.stderr.write(f"LoreConvo: Auto-saved session '{parsed['title']}'\n")
            if _is_valid_transcript_path(transcript_path):
                _dispatch_async_summarizer(session_id, transcript_path)
            # Dispatch proactive consolidation trigger (SH-12693 r5)
            signal_count = len(parsed.get("decisions", [])) + len(parsed.get("open_questions", []))
            message_count = parsed.get("message_count", 0)
            _dispatch_proactive_consolidation(project, "code", signal_count, message_count)

    except json.JSONDecodeError:
        sys.exit(0)
    except Exception as e:
        sys.stderr.write(f"LoreConvo auto-save error: {e}\n")
        sys.exit(0)


def _is_valid_transcript_path(transcript_path):
    """Validate that transcript_path is within expected Claude directory (SH-10880).

    Returns True if path is under ~/.claude, False otherwise.
    Logs a warning if validation fails.
    """
    if not transcript_path:
        return False
    try:
        normalized = Path(transcript_path).resolve()
        expected_base = Path.home() / ".claude"
        if normalized.is_relative_to(expected_base):
            return True
        sys.stderr.write(
            f"LoreConvo: transcript_path outside expected directory boundaries: "
            f"{transcript_path}; skipping async summarizer dispatch\n"
        )
        return False
    except Exception as e:
        sys.stderr.write(
            f"LoreConvo: transcript_path validation failed: {e}; skipping dispatch\n"
        )
        return False


def _dispatch_async_summarizer(session_id, transcript_path):
    """Fire-and-forget background subprocess to upgrade session to LLM summary.

    Only dispatched when LORECONVO_ANTHROPIC_API_KEY is set. The hook
    returns immediately; summarization happens asynchronously.
    """
    import subprocess
    if not os.environ.get("LORECONVO_ANTHROPIC_API_KEY"):
        return
    try:
        # Locate session_summarizer.py relative to this hook's src directory.
        hook_dir = os.path.dirname(os.path.abspath(__file__))
        src_dir = os.path.join(hook_dir, "..", "..", "src")
        summarizer = os.path.join(src_dir, "session_summarizer.py")
        if not os.path.exists(summarizer):
            return
        args = [sys.executable, summarizer, session_id]
        if transcript_path:
            args.append(transcript_path)
        # Pass current env so API key + LORECONVO_DB are inherited.
        subprocess.Popen(
            args,
            env=os.environ.copy(),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except Exception as exc:
        sys.stderr.write(f"LoreConvo: async summarizer dispatch failed (non-fatal): {exc}\n")


def _dispatch_proactive_consolidation(project, surface, signal_count, message_count):
    """Fire-and-forget proactive consolidation trigger (SH-12693 r5).

    Spawns the proactive_consolidate.py runner if LORECONVO_PROACTIVE_MIN_SIGNALS is set.
    The hook returns immediately; consolidation happens asynchronously.
    """
    import subprocess
    if not os.environ.get("LORECONVO_PROACTIVE_MIN_SIGNALS"):
        return  # default off; no import, no work, no cost
    try:
        hook_dir = os.path.dirname(os.path.abspath(__file__))
        runner = os.path.join(hook_dir, "..", "..", "src", "proactive_consolidate.py")
        if not os.path.exists(runner):
            return  # half-shipped release -> inert, not a crash
        args = [
            sys.executable, runner,
            "--signals", str(signal_count),
            "--messages", str(message_count),
            "--project", project or "",
            "--surface", surface
        ]
        # Pass current env so LORECONVO_* vars are inherited
        def _log_path():
            return str(os.path.join(os.path.expanduser("~"), ".loreconvo", "consolidate.log"))

        subprocess.Popen(
            args,
            env=os.environ.copy(),
            stdout=subprocess.DEVNULL,
            stderr=open(_log_path(), "a"),  # stderr to log file, not DEVNULL
            start_new_session=True,
        )
    except Exception as exc:
        sys.stderr.write(f"LoreConvo: proactive consolidation dispatch failed (non-fatal): {exc}\n")


if __name__ == "__main__":
    main()
