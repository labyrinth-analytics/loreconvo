"""LoreConvo PreCompact auto-save hook.

Receives PreCompact hook input via stdin JSON from Claude Code.
Saves the current session transcript to the vault before context compaction
occurs, so no context is lost when Claude Code compresses the session.

Fires on both manual (/compact) and auto (context limit) compaction triggers.
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

from loreconvo.src.core.timeutil import utc_now_iso

# Bootstrap: resolve storage_core for non-package callers.
from _bootstrap import resolve_storage_core, BootstrapError

try:
    _storage = resolve_storage_core(Path(__file__))
except BootstrapError as exc:
    from _bootstrap import _write_breadcrumb
    _write_breadcrumb("pre_compact_save", str(exc), [])
    sys.stderr.write(f"LoreConvo pre-compact bootstrap error: {exc}\n")
    sys.exit(1)

_open_conn = _storage._open_conn
ensure_schema = _storage.ensure_schema
upsert_session = _storage.upsert_session

# Reuse transcript parsing from auto_save.py
_SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPT_DIR))
from auto_save import parse_transcript


def get_db_path():
    """Get database path, matching core/config.py logic."""
    return os.environ.get("LORECONVO_DB", os.path.expanduser("~/.loreconvo/sessions.db"))


def save_pre_compact(db_path, session_id, parsed, trigger, project=None):
    """Save parsed session data before compaction.

    If the session already exists in the DB (e.g., from a prior pre-compact
    or session-end save), update it. Otherwise insert a new record.
    Tags include 'pre-compact' and the trigger type ('manual' or 'auto').

    project is derived from the hook cwd (mirrors auto_save.py) so pre-compact
    saves are namespaced like every other save. On UPDATE we only fill project
    when it is currently NULL (COALESCE) -- a pre-compact firing after an agent
    or SessionEnd save must not clobber an already-stamped project.
    """
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    tags = ["pre-compact", trigger]

    # Stamp the owning agent when this save fires inside a scheduled-agent run.
    agent = os.environ.get("LORECONVO_AGENT", "").strip()
    if agent:
        tags.append(f"agent:{agent}")

    conn = _open_conn(db_path, busy_timeout_ms=2000)
    try:
        ensure_schema(conn)

        cursor = conn.execute("SELECT id FROM sessions WHERE id = ?", (session_id,))
        now = utc_now_iso()
        tags_json = json.dumps(tags)
        decisions_json = json.dumps(parsed["decisions"])
        artifacts_json = json.dumps(parsed["artifacts"])

        if cursor.fetchone():
            conn.execute(
                """UPDATE sessions SET summary = ?, decisions = ?, artifacts = ?,
                   tags = ?, end_date = ?,
                   project = COALESCE(project, ?)
                   WHERE id = ?""",
                (
                    parsed["summary"],
                    decisions_json,
                    artifacts_json,
                    tags_json,
                    now,
                    project,
                    session_id,
                ),
            )
            return True

        upsert_session(
            conn,
            session_id=session_id,
            title=parsed["title"],
            surface="code",
            project=project,
            start_date=now,
            end_date=now,
            summary=parsed["summary"],
            decisions=decisions_json,
            artifacts=artifacts_json,
            open_questions=json.dumps([]),
            tags=tags_json,
        )

        try:
            conn.execute(
                """INSERT INTO sessions_fts(rowid, title, summary, decisions)
                   SELECT rowid, title, summary, decisions
                   FROM sessions WHERE id = ?""",
                (session_id,),
            )
        except Exception:
            pass

        for tool in parsed.get("tools_used", []):
            try:
                conn.execute(
                    "INSERT INTO session_skills (session_id, skill_name) VALUES (?, ?)",
                    (session_id, tool),
                )
            except Exception:
                pass

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
        cwd = hook_input.get("cwd", "")
        project = os.path.basename(cwd.rstrip("/")) if cwd else None

        parsed = parse_transcript(transcript_path)
        if not parsed:
            sys.exit(0)

        if parsed["message_count"] < 2:
            sys.exit(0)

        db_path = get_db_path()
        saved = save_pre_compact(db_path, session_id, parsed, trigger, project)

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
