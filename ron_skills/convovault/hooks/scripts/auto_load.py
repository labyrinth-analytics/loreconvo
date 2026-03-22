"""ConvoVault SessionStart auto-load hook.

Receives session metadata via stdin JSON from Claude Code's SessionStart hook.
Queries the ConvoVault SQLite database for recent sessions matching the current
working directory (project), then outputs a context summary to stdout.

Claude Code injects stdout content into the session as system context.
Designed to run within the hook timeout window.
"""

import json
import os
import sys
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path


def get_db_path():
    """Get database path, matching core/config.py logic."""
    return os.environ.get("CONVOVAULT_DB", os.path.expanduser("~/.convovault/sessions.db"))


def query_recent_sessions(db_path, cwd, days_back=7, limit=5):
    """Query ConvoVault for recent sessions, optionally filtered by project/cwd.

    Returns a list of session dicts with id, title, summary, decisions,
    start_date, end_date, and tags.
    """
    if not os.path.exists(db_path):
        return []

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        cutoff = (datetime.now() - timedelta(days=days_back)).isoformat()

        # Try project-filtered query first (match cwd against project field)
        # ConvoVault stores project as the working directory path
        sessions = []

        if cwd:
            # Match sessions from the same project directory
            # Use LIKE for partial matching (subprojects, etc.)
            cursor = conn.execute(
                """SELECT id, title, summary, decisions, artifacts, tags,
                          start_date, end_date
                   FROM sessions
                   WHERE project LIKE ?
                     AND start_date >= ?
                   ORDER BY start_date DESC
                   LIMIT ?""",
                (f"%{cwd}%", cutoff, limit),
            )
            sessions = [dict(row) for row in cursor.fetchall()]

        # If no project-specific sessions, fall back to most recent across all projects
        if not sessions:
            cursor = conn.execute(
                """SELECT id, title, summary, decisions, artifacts, tags,
                          start_date, end_date
                   FROM sessions
                   ORDER BY start_date DESC
                   LIMIT ?""",
                (limit,),
            )
            sessions = [dict(row) for row in cursor.fetchall()]

        return sessions

    except Exception as e:
        sys.stderr.write(f"ConvoVault auto-load query error: {e}\n")
        return []
    finally:
        conn.close()


def format_context(sessions, cwd):
    """Format session data into a concise context block for Claude.

    Output is plain text that Claude Code injects into the session.
    Keep it focused and scannable -- this goes into the system prompt area.
    """
    if not sessions:
        return ""

    lines = []
    lines.append("# ConvoVault: Recent Session Context")
    lines.append("")

    # Indicate if results are project-specific or global
    if cwd:
        project_name = os.path.basename(cwd) if cwd else "unknown"
        lines.append(f"Recent sessions for project: {project_name}")
    else:
        lines.append("Recent sessions (no project filter):")
    lines.append("")

    for i, session in enumerate(sessions, 1):
        title = session.get("title", "Untitled")
        start = session.get("start_date", "")
        end = session.get("end_date", "")

        # Format date nicely
        date_str = ""
        if start:
            try:
                dt = datetime.fromisoformat(start)
                date_str = dt.strftime("%b %d, %Y %I:%M %p")
            except (ValueError, TypeError):
                date_str = start[:19] if start else ""

        lines.append(f"## Session {i}: {title}")
        if date_str:
            lines.append(f"Date: {date_str}")

        # Summary (truncated for context window efficiency)
        summary = session.get("summary", "")
        if summary:
            # Take first 500 chars of summary to keep context lean
            truncated = summary[:500]
            if len(summary) > 500:
                truncated += "..."
            lines.append(f"Summary: {truncated}")

        # Decisions are high-signal, always include
        decisions_raw = session.get("decisions", "[]")
        try:
            decisions = json.loads(decisions_raw) if isinstance(decisions_raw, str) else decisions_raw
        except (json.JSONDecodeError, TypeError):
            decisions = []

        if decisions:
            lines.append("Key decisions:")
            for d in decisions[:5]:  # Cap at 5 decisions per session
                lines.append(f"  - {d}")

        # Artifacts (file paths created/modified)
        artifacts_raw = session.get("artifacts", "[]")
        try:
            artifacts = json.loads(artifacts_raw) if isinstance(artifacts_raw, str) else artifacts_raw
        except (json.JSONDecodeError, TypeError):
            artifacts = []

        if artifacts:
            lines.append("Artifacts: " + ", ".join(artifacts[:5]))

        lines.append("")

    lines.append("---")
    lines.append("Use this context to avoid re-asking questions or repeating work from prior sessions.")
    lines.append("If a prior session is directly relevant, you can query ConvoVault MCP tools for full details.")

    return "\n".join(lines)


def main():
    """Main entry point for SessionStart hook."""
    try:
        # Read hook input from stdin
        stdin_data = sys.stdin.read()
        if not stdin_data:
            sys.exit(0)

        hook_input = json.loads(stdin_data)
        session_id = hook_input.get("session_id", "unknown")
        cwd = hook_input.get("cwd", "")

        # Query ConvoVault for recent sessions
        db_path = get_db_path()

        # Configuration via environment variables
        days_back = int(os.environ.get("CONVOVAULT_DAYS_BACK", "7"))
        limit = int(os.environ.get("CONVOVAULT_LIMIT", "5"))

        sessions = query_recent_sessions(db_path, cwd, days_back=days_back, limit=limit)

        if not sessions:
            sys.stderr.write(f"ConvoVault auto-load: No recent sessions found for {cwd or 'any project'}\n")
            sys.exit(0)

        # Format and output context to stdout
        # Claude Code captures stdout from SessionStart hooks and injects it
        context = format_context(sessions, cwd)
        if context:
            print(context)
            sys.stderr.write(
                f"ConvoVault auto-load: Injected context from {len(sessions)} recent session(s) "
                f"for session {session_id}\n"
            )

    except json.JSONDecodeError:
        sys.exit(0)
    except Exception as e:
        sys.stderr.write(f"ConvoVault auto-load error: {e}\n")
        sys.exit(0)


if __name__ == "__main__":
    main()
