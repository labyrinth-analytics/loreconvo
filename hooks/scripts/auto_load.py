"""LoreConvo SessionStart auto-load hook.

Receives session metadata via stdin JSON from Claude Code's SessionStart hook.
Queries the LoreConvo SQLite database for recent sessions matching the current
working directory (project), then outputs a context summary to stdout.

Claude Code injects stdout content into the session as system context.
Designed to run within the hook timeout window.

Scoring logic (higher = shown first):
  +3  session has open questions (most actionable context)
  +2  session has >= 2 decisions
  +1  session has artifacts
  +2  started within last 24 hours
  +1  started within last 3 days
  +1  session is pinned (keep_forever=1, user-curation signal)
  -2  no summary, no decisions, no open questions, no artifacts (noise)

Sessions that score <= 0 and are not the only results are filtered out.
Total formatted context is capped at _MAX_CONTEXT_TOKENS to avoid bloat.
"""

import json
import os
import sys
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Robust sibling import (SH-13436 r5): resolve this script's own directory
# explicitly rather than relying on sys.path[0], which is invocation-path
# dependent and could be set to something else by a future launcher/wrapper.
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
import trust_framing


# Token-based soft cap (replaces char-based MAX_CONTEXT_CHARS).
# Default 1000 tokens = today's 4000 chars (len // 4), behavior-preserving.
# Configurable via LORECONVO_AUTO_LOAD_MAX_TOKENS env var.
_MAX_CONTEXT_TOKENS = int(os.environ.get("LORECONVO_AUTO_LOAD_MAX_TOKENS", "1000"))


MEMORY_MD_NAMESPACE = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")  # URL namespace
MEMORY_MD_MAX_LINES = 200  # match Claude Code's startup line limit


def get_db_path():
    """Get database path, matching core/config.py logic."""
    return os.environ.get("LORECONVO_DB", os.path.expanduser("~/.loreconvo/sessions.db"))


def score_session(session, now):
    """Compute a signal quality score for a session dict.

    Higher scores = more actionable context for the incoming session.
    """
    score = 0

    # Open questions are highest signal -- unanswered items the user may continue
    open_q_raw = session.get("open_questions", "[]")
    try:
        open_questions = json.loads(open_q_raw) if isinstance(open_q_raw, str) else (open_q_raw or [])
    except (json.JSONDecodeError, TypeError):
        open_questions = []
    if open_questions:
        score += 3

    # Decisions (>= 2 means a substantive work session)
    decisions_raw = session.get("decisions", "[]")
    try:
        decisions = json.loads(decisions_raw) if isinstance(decisions_raw, str) else (decisions_raw or [])
    except (json.JSONDecodeError, TypeError):
        decisions = []
    if len(decisions) >= 2:
        score += 2
    elif len(decisions) == 1:
        score += 1

    # Artifacts indicate something was produced
    artifacts_raw = session.get("artifacts", "[]")
    try:
        artifacts = json.loads(artifacts_raw) if isinstance(artifacts_raw, str) else (artifacts_raw or [])
    except (json.JSONDecodeError, TypeError):
        artifacts = []
    if artifacts:
        score += 1

    # Recency bonus
    start_raw = session.get("start_date", "")
    if start_raw:
        try:
            start_dt = datetime.fromisoformat(start_raw)
            age = now - start_dt
            if age <= timedelta(hours=24):
                score += 2
            elif age <= timedelta(days=3):
                score += 1
        except (ValueError, TypeError):
            pass

    # Noise penalty: short/empty sessions add clutter
    summary = session.get("summary", "") or ""
    if not summary and not decisions and not open_questions and not artifacts:
        score -= 2

    # User-curation signal: pinned sessions are explicitly valued by the user
    if session.get("keep_forever"):
        score += 1

    return score


def query_recent_sessions(db_path, cwd, days_back=14, limit=10):
    """Query LoreConvo for recent sessions, optionally filtered by project/cwd.

    Fetches a wider window than the old hook (days_back=14, limit=10) so the
    scoring pass has enough candidates to work with.  The caller then scores,
    filters, and caps before formatting.

    Returns a list of session dicts.
    """
    if not os.path.exists(db_path):
        return []

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        cutoff = (datetime.now() - timedelta(days=days_back)).isoformat()

        sessions = []

        exclusion_enabled = os.environ.get("LORECONVO_EXTERNAL_TOOL_EXCLUSION", "1") != "0"
        col_names = {row[1] for row in conn.execute("PRAGMA table_info(sessions)").fetchall()}
        # Only add the filter if the column exists (older DBs may not have it yet)
        has_ext_col = "external_tool_session" in col_names
        ext_filter = (
            " AND (external_tool_session IS NULL OR external_tool_session = 0)"
            if (exclusion_enabled and has_ext_col) else ""
        )
        # SH-10248: exclude expired sessions from auto-load context
        expiry_filter = (
            " AND (expires_at IS NULL OR expires_at > strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))"
            if "expires_at" in col_names else ""
        )
        # Keep-forever user-curation signal (v0.8.1)
        kf_col = ", keep_forever" if "keep_forever" in col_names else ""
        # summary_source drives provenance labeling (SH-13436); older DBs
        # predating the async-summarization migration may not have it yet.
        summary_source_col = ", summary_source" if "summary_source" in col_names else ""

        if cwd:
            project = os.path.basename(cwd.rstrip("/"))
            cursor = conn.execute(
                "SELECT id, title, summary, decisions, artifacts,"
                " open_questions, tags, start_date, end_date, source"
                + summary_source_col + kf_col +
                " FROM sessions"
                " WHERE project = ?"
                " AND start_date >= ?"
                " AND (source IS NULL OR source = 'session')"
                + ext_filter + expiry_filter +
                " ORDER BY start_date DESC LIMIT ?",
                (project, cutoff, limit),
            )
            sessions = [dict(row) for row in cursor.fetchall()]

        return sessions

    except Exception as e:
        sys.stderr.write(f"LoreConvo auto-load query error: {e}\n")
        return []
    finally:
        conn.close()


def index_memory_md(db_path, project_dir):
    """Index MEMORY.md from project_dir into the sessions table as source='file_memory'.

    Idempotent: uses a deterministic UUID5 keyed on the absolute file path so
    repeated calls upsert rather than accumulate duplicates.

    First 200 lines only (matches Claude Code's SessionStart load limit).
    Returns True if a MEMORY.md was found and indexed, False otherwise.
    """
    memory_path = Path(project_dir) / "MEMORY.md"
    if not memory_path.is_file():
        return False

    try:
        lines = memory_path.read_text(encoding="utf-8", errors="ignore").splitlines()
        content = "\n".join(lines[:MEMORY_MD_MAX_LINES])
        if not content.strip():
            return False

        abs_path = str(memory_path.resolve())
        session_id = str(uuid.uuid5(MEMORY_MD_NAMESPACE, abs_path))
        project_name = Path(project_dir).name
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        conn = sqlite3.connect(db_path)
        try:
            # Ensure source column exists (migration may not have run yet)
            try:
                conn.execute(
                    "ALTER TABLE sessions ADD COLUMN source TEXT DEFAULT 'session'"
                )
                conn.commit()
            except sqlite3.OperationalError:
                pass  # column already exists

            conn.execute(
                """INSERT INTO sessions
                   (id, title, surface, project, start_date, end_date,
                    summary, decisions, artifacts, open_questions, tags,
                    created_at, source)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET
                   title = excluded.title,
                   surface = excluded.surface,
                   project = excluded.project,
                   start_date = excluded.start_date,
                   end_date = excluded.end_date,
                   summary = excluded.summary,
                   decisions = excluded.decisions,
                   artifacts = excluded.artifacts,
                   open_questions = excluded.open_questions,
                   tags = excluded.tags,
                   created_at = excluded.created_at,
                   source = excluded.source""",
                (
                    session_id,
                    f"MEMORY.md: {project_name}",
                    "file",
                    project_name,
                    now,
                    now,
                    content,
                    "[]",
                    "[]",
                    "[]",
                    '["memory_md"]',
                    now,
                    "file_memory",
                ),
            )
            conn.commit()
        finally:
            conn.close()

        return True

    except Exception as e:
        sys.stderr.write(f"LoreConvo auto-load: MEMORY.md index error: {e}\n")
        return False


def select_sessions(sessions, max_count=5):
    """Score, filter, and rank sessions. Returns up to max_count best ones."""
    if not sessions:
        return []

    now = datetime.now()
    scored = [(score_session(s, now), s) for s in sessions]

    # Sort by score desc, then recency desc for ties
    scored.sort(key=lambda x: (x[0], x[1].get("start_date", "")), reverse=True)

    # Filter out noise sessions as long as we still have enough good ones
    good = [(sc, s) for sc, s in scored if sc > 0]
    if not good:
        # All sessions scored <= 0 -- keep top few rather than returning nothing
        good = scored[:max_count]

    return [s for _, s in good[:max_count]]


def format_context(sessions, cwd, db_path=None, session_nonce=None):
    """Format session data into a concise context block for Claude.

    Output is plain text that Claude Code injects into the session.
    Includes open_questions (missing from old version) as they are highest-signal.
    If project instructions exist, includes them after project name (project
    instructions are user-authored config, not recalled content, so they stay
    outside the untrusted-content wrapper below).
    The session/digest block (but not the header or project instructions) is
    wrapped in an explicit untrusted-data boundary (SH-13436) before being
    returned, so Claude Code's injected context is never bare recalled text.
    Enforces _MAX_CONTEXT_TOKENS soft cap to prevent system prompt bloat.
    """
    if not sessions:
        return ""

    if session_nonce is None:
        session_nonce = trust_framing.derive_session_nonce(None)

    lines = []
    lines.append("# LoreConvo: Recent Session Context")
    lines.append("")

    if cwd:
        project_name = os.path.basename(cwd) if cwd else "unknown"
        lines.append(f"Recent sessions for project: {project_name}")

        # Query and include project instructions if available
        if db_path and os.path.exists(db_path):
            try:
                conn = sqlite3.connect(db_path)
                row = conn.execute(
                    "SELECT instructions FROM projects WHERE name = ?",
                    (project_name,)
                ).fetchone()
                conn.close()
                if row and row[0]:
                    lines.append("")
                    lines.append(f"<!-- LoreConvo project instructions (user-authored, project: {project_name}) -->")
                    lines.append(row[0])
                    lines.append("<!-- end project instructions -->")
            except (sqlite3.OperationalError, sqlite3.DatabaseError):
                pass  # Ignore DB errors; instructions are optional
    else:
        lines.append("Recent sessions (no project filter):")
    lines.append("")

    # Wrapper overhead is subtracted from the budget once, up front, so the
    # per-block cap check below still reflects the real total context size
    # after wrapping (SH-13436).
    budget_tokens = _MAX_CONTEXT_TOKENS - trust_framing.WRAPPER_OVERHEAD_TOKENS

    body_lines = []
    total_chars = 0
    total_tokens = 0

    for i, session in enumerate(sessions, 1):
        block = []
        title = session.get("title") or "Untitled"
        start = session.get("start_date", "")

        date_str = ""
        if start:
            try:
                dt = datetime.fromisoformat(start)
                date_str = dt.strftime("%b %d, %Y %I:%M %p")
            except (ValueError, TypeError):
                date_str = start[:19] if start else ""

        block.append(f"## Session {i}: {title}")
        if date_str:
            block.append(f"Date: {date_str}")
        block.append(
            "Provenance: "
            + trust_framing.convo_provenance_tag(
                session.get("source"), session.get("summary_source")
            )
        )

        # Summary (truncated)
        summary = session.get("summary") or ""
        if summary:
            truncated = summary[:400]
            if len(summary) > 400:
                truncated += "..."
            block.append(f"Summary: {truncated}")

        # Open questions -- highest signal, always include when present
        open_q_raw = session.get("open_questions", "[]")
        try:
            open_questions = json.loads(open_q_raw) if isinstance(open_q_raw, str) else (open_q_raw or [])
        except (json.JSONDecodeError, TypeError):
            open_questions = []
        if open_questions:
            block.append("Open questions:")
            for q in open_questions[:4]:
                block.append(f"  ? {q}")

        # Decisions
        decisions_raw = session.get("decisions", "[]")
        try:
            decisions = json.loads(decisions_raw) if isinstance(decisions_raw, str) else (decisions_raw or [])
        except (json.JSONDecodeError, TypeError):
            decisions = []
        if decisions:
            block.append("Key decisions:")
            for d in decisions[:4]:
                block.append(f"  - {d}")

        # Artifacts
        artifacts_raw = session.get("artifacts", "[]")
        try:
            artifacts = json.loads(artifacts_raw) if isinstance(artifacts_raw, str) else (artifacts_raw or [])
        except (json.JSONDecodeError, TypeError):
            artifacts = []
        if artifacts:
            block.append("Artifacts: " + ", ".join(artifacts[:5]))

        block.append("")

        block_chars = sum(len(l) for l in block)
        block_tokens = block_chars // 4
        if total_tokens + block_tokens > budget_tokens and i > 1:
            # Soft cap reached -- stop adding more sessions
            break

        body_lines.extend(block)
        total_chars += block_chars
        total_tokens += block_tokens

    if body_lines:
        body_text = "\n".join(body_lines).rstrip("\n")
        lines.append(trust_framing.wrap_untrusted(body_text, session_nonce=session_nonce))
        lines.append("")

    # A genuine system-authored hint, not recalled content -- stays outside
    # the untrusted-content wrapper above. The prior free-floating imperative
    # sentence directly instructing action on the wrapped content ("Use this
    # context to avoid re-asking questions...") is deleted; that role is now
    # played by the wrapper's own standing note (SH-13436).
    lines.append("If a prior session is directly relevant, query LoreConvo MCP tools for full details.")

    return "\n".join(lines)


def query_digest_for_injection(db_path: str, project: str, surface: str) -> "str | None":
    """Return the digest_markdown for injection if eligible, or None.

    Eligibility rules:
    - LORECONVO_DREAM_INJECT env var must not be 'false'
    - A memory_digests row must exist for (project, surface)
    - disabled flag must be 0
    - updated_at must be within 7 days (freshness check)
    """
    if os.environ.get("LORECONVO_DREAM_INJECT", "true").lower() == "false":
        return None

    if not os.path.exists(db_path):
        return None

    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            # Check if memory_digests table exists (may not on older installs)
            tables = {row[0] for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()}
            if "memory_digests" not in tables:
                return None

            row = conn.execute(
                "SELECT digest_markdown, disabled, updated_at "
                "FROM memory_digests WHERE project=? AND surface IS ?",
                (project, surface)
            ).fetchone()

            if row is None:
                return None
            if row["disabled"]:
                return None

            # Freshness: updated_at must be within 7 days
            updated_raw = row["updated_at"] or ""
            if updated_raw:
                try:
                    updated_dt = datetime.fromisoformat(updated_raw.replace("Z", "+00:00"))
                    age = datetime.now(timezone.utc) - updated_dt
                    if age > timedelta(days=7):
                        return None
                except (ValueError, TypeError):
                    return None

            md = row["digest_markdown"] or ""
            return md if md.strip() else None

        finally:
            conn.close()
    except Exception as exc:
        sys.stderr.write(f"LoreConvo auto-load: digest query error: {exc}\n")
        return None


def main():
    """Main entry point for SessionStart hook."""
    try:
        stdin_data = sys.stdin.read()
        if not stdin_data:
            sys.exit(0)

        hook_input = json.loads(stdin_data)
        session_id = hook_input.get("session_id", "unknown")
        cwd = hook_input.get("cwd", "")

        db_path = get_db_path()

        # Index MEMORY.md from the project directory (idempotent upsert).
        project_dir = os.environ.get("LORECONVO_PROJECT_PATH", cwd)
        if project_dir and os.path.exists(db_path):
            index_memory_md(db_path, project_dir)

        days_back = int(os.environ.get("LORECONVO_DAYS_BACK", "14"))
        limit = int(os.environ.get("LORECONVO_LIMIT", "10"))
        max_count = int(os.environ.get("LORECONVO_MAX_SESSIONS", "5"))

        raw_sessions = query_recent_sessions(db_path, cwd, days_back=days_back, limit=limit)

        if not raw_sessions:
            sys.stderr.write(
                f"LoreConvo auto-load: No recent sessions found for {cwd or 'any project'}\n"
            )
            sys.exit(0)

        sessions = select_sessions(raw_sessions, max_count=max_count)

        session_nonce = trust_framing.derive_session_nonce(session_id)

        context = format_context(sessions, cwd, db_path, session_nonce=session_nonce)

        # Additive digest injection: prepend memory digest if eligible.
        # Wrapped separately (own untrusted-boundary + CONSOLIDATED DIGEST
        # provenance tag, SH-13436) rather than prepended raw -- order is
        # preserved as before: digest first, then sessions.
        project_name = os.path.basename(cwd) if cwd else ""
        surface = os.environ.get("LORECONVO_SURFACE", "code")
        digest_md = query_digest_for_injection(db_path, project_name, surface)
        if digest_md:
            digest_body = f"Provenance: {trust_framing.DIGEST_PROVENANCE_LABEL}\n\n{digest_md}"
            wrapped_digest = trust_framing.wrap_untrusted(digest_body, session_nonce=session_nonce)
            context = f"{wrapped_digest}\n\n{context}" if context else wrapped_digest

        if context:
            print(context)
            sys.stderr.write(
                f"LoreConvo auto-load: Injected context from {len(sessions)} session(s) "
                f"(scored from {len(raw_sessions)} candidates) for session {session_id} "
                f"(trust-wrapped)\n"
            )

    except json.JSONDecodeError:
        sys.exit(0)
    except Exception as e:
        sys.stderr.write(f"LoreConvo auto-load error: {e}\n")
        sys.exit(0)


if __name__ == "__main__":
    main()
