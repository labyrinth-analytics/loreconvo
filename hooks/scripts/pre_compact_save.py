"""LoreConvo PreCompact auto-save hook.

Receives PreCompact hook input via stdin JSON from Claude Code.
Saves the current session transcript to the vault before context compaction
occurs, so no context is lost when Claude Code compresses the session.

Fires on both manual (/compact) and auto (context limit) compaction triggers.
"""

import json
import os
import sys
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

# Reuse transcript parsing and DB save logic from auto_save.py
# Both scripts live in the same directory -- import by manipulating sys.path.
_SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPT_DIR))
from auto_save import parse_transcript, ensure_tables


def get_db_path():
    """Get database path, matching core/config.py logic."""
    return os.environ.get("LORECONVO_DB", os.path.expanduser("~/.loreconvo/sessions.db"))


def save_pre_compact(db_path, session_id, parsed, trigger):
    """Save parsed session data before compaction.

    If the session already exists in the DB (e.g., from a prior pre-compact
    or session-end save), update it. Otherwise insert a new record.
    Tags include 'pre-compact' and the trigger type ('manual' or 'auto').
    """
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    tags = ["pre-compact", trigger]

    conn = sqlite3.connect(db_path)
    try:
        ensure_tables(conn)

        cursor = conn.execute("SELECT id FROM sessions WHERE id = ?", (session_id,))
        now = datetime.now().isoformat()

        if cursor.fetchone():
            conn.execute(
                """UPDATE sessions SET summary = ?, decisions = ?, artifacts = ?,
                   tags = ?, end_date = ?, updated_at = ?
                   WHERE id = ?""",
                (
                    parsed["summary"],
                    json.dumps(parsed["decisions"]),
                    json.dumps(parsed["artifacts"]),
                    json.dumps(tags),
                    now,
                    now,
                    session_id,
                ),
            )
            conn.commit()
            return True

        conn.execute(
            """INSERT INTO sessions (id, title, surface, summary, decisions, artifacts,
               open_questions, tags, start_date, end_date)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                session_id,
                parsed["title"],
                "code",
                parsed["summary"],
                json.dumps(parsed["decisions"]),
                json.dumps(parsed["artifacts"]),
                json.dumps([]),
                json.dumps(tags),
                now,
                now,
            ),
        )

        try:
            conn.execute(
                """INSERT INTO sessions_fts(rowid, title, summary, decisions)
                   SELECT rowid, title, summary, decisions
                   FROM sessions WHERE id = ?""",
                (session_id,),
            )
        except sqlite3.OperationalError:
            pass

        for tool in parsed.get("tools_used", []):
            try:
                conn.execute(
                    "INSERT INTO session_skills (session_id, skill_name) VALUES (?, ?)",
                    (session_id, tool),
                )
            except sqlite3.IntegrityError:
                pass

        conn.commit()
        return True
    except Exception as e:
        sys.stderr.write(f"LoreConvo pre-compact save DB error: {e}\n")
        return False
    finally:
        conn.close()


def main():
    """Main entry point for PreCompact hook."""
    try:
        stdin_data = sys.stdin.read()
        if not stdin_data:
            sys.exit(0)

        hook_input = json.loads(stdin_data)
        session_id = hook_input.get("session_id", "unknown")
        transcript_path = hook_input.get("transcript_path", "")
        trigger = hook_input.get("trigger", "auto")

        parsed = parse_transcript(transcript_path)
        if not parsed:
            sys.exit(0)

        if parsed["message_count"] < 2:
            sys.exit(0)

        db_path = get_db_path()
        saved = save_pre_compact(db_path, session_id, parsed, trigger)

        if saved:
            sys.stderr.write(
                f"LoreConvo: Pre-compact save ({trigger}) -- '{parsed['title']}'\n"
            )

    except json.JSONDecodeError:
        sys.exit(0)
    except Exception as e:
        sys.stderr.write(f"LoreConvo pre-compact save error: {e}\n")
        sys.exit(0)


if __name__ == "__main__":
    main()
