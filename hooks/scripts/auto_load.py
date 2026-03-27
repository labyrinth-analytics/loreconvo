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
  -2  no summary, no decisions, no open questions, no artifacts (noise)

Sessions that score <= 0 and are not the only results are filtered out.
Total formatted context is capped at MAX_CONTEXT_CHARS to avoid bloat.
"""

import json
import os
import sys
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path


MAX_CONTEXT_CHARS = 4000  # Soft cap on total output length


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

        if cwd:
            cursor = conn.execute(
                """SELECT id, title, summary, decisions, artifacts,
                          open_questions, tags, start_date, end_date
                   FROM sessions
                   WHERE project LIKE ?
                     AND start_date >= ?
                   ORDER BY start_date DESC
                   LIMIT ?""",
                (f"%{cwd}%", cutoff, limit),
            )
            sessions = [dict(row) for row in cursor.fetchall()]

        # Fall back to most recent across all projects if no project matches
        if not sessions:
            cursor = conn.execute(
                """SELECT id, title, summary, decisions, artifacts,
                          open_questions, tags, start_date, end_date
                   FROM sessions
                   ORDER BY start_date DESC
                   LIMIT ?""",
                (limit,),
            )
            sessions = [dict(row) for row in cursor.fetchall()]

        return sessions

    except Exception as e:
        sys.stderr.write(f"LoreConvo auto-load query error: {e}\n")
        return []
    finally:
        conn.close()


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


def format_context(sessions, cwd):
    """Format session data into a concise context block for Claude.

    Output is plain text that Claude Code injects into the session.
    Includes open_questions (missing from old version) as they are highest-signal.
    Enforces MAX_CONTEXT_CHARS soft cap to prevent system prompt bloat.
    """
    if not sessions:
        return ""

    lines = []
    lines.append("# LoreConvo: Recent Session Context")
    lines.append("")

    if cwd:
        project_name = os.path.basename(cwd) if cwd else "unknown"
        lines.append(f"Recent sessions for project: {project_name}")
    else:
        lines.append("Recent sessions (no project filter):")
    lines.append("")

    total_chars = sum(len(l) for l in lines)

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
        if total_chars + block_chars > MAX_CONTEXT_CHARS and i > 1:
            # Soft cap reached -- stop adding more sessions
            break

        lines.extend(block)
        total_chars += block_chars

    lines.append("---")
    lines.append("Use this context to avoid re-asking questions or repeating work from prior sessions.")
    lines.append("If a prior session is directly relevant, query LoreConvo MCP tools for full details.")

    return "\n".join(lines)


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

        context = format_context(sessions, cwd)
        if context:
            print(context)
            sys.stderr.write(
                f"LoreConvo auto-load: Injected context from {len(sessions)} session(s) "
                f"(scored from {len(raw_sessions)} candidates) for session {session_id}\n"
            )

    except json.JSONDecodeError:
        sys.exit(0)
    except Exception as e:
        sys.stderr.write(f"LoreConvo auto-load error: {e}\n")
        sys.exit(0)


if __name__ == "__main__":
    main()
