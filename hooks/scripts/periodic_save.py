"""LoreConvo periodic capture hook (PostToolUse).

Saves a rolling snapshot of the current session at configurable tool-call intervals.
Controlled by LORECONVO_CAPTURE_INTERVAL env var (number of tool calls between saves;
0 or unset = disabled).

State file: ~/.loreconvo/periodic_state.json
  {session_id: {"count": N, "last_save_at": ISO, "last_seen": ISO}}

The snapshot uses the same session_id as the final SessionEnd save, so the final
save always overwrites the periodic one (source changes from 'periodic' to 'session').
Periodic saves are hidden from auto-load context (source='periodic' is filtered out).
"""

import json
import os
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPT_DIR))
from auto_save import get_db_path, parse_transcript, save_to_db


STATE_FILE = os.path.expanduser("~/.loreconvo/periodic_state.json")
STATE_TTL_HOURS = 24


def _load_state():
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE) as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def _save_state(state):
    state_dir = os.path.dirname(STATE_FILE)
    os.makedirs(state_dir, exist_ok=True)
    tmp_fd, tmp_path = tempfile.mkstemp(dir=state_dir, suffix=".tmp")
    try:
        with os.fdopen(tmp_fd, "w") as f:
            json.dump(state, f)
        os.replace(tmp_path, STATE_FILE)
    except Exception:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


def _purge_old_state(state):
    """Remove entries for sessions not seen in the last STATE_TTL_HOURS hours."""
    cutoff = (datetime.now() - timedelta(hours=STATE_TTL_HOURS)).isoformat()
    return {
        sid: data for sid, data in state.items()
        if data.get("last_seen", "") >= cutoff
    }


def main():
    interval_str = os.environ.get("LORECONVO_CAPTURE_INTERVAL", "0")
    try:
        interval = int(interval_str)
    except ValueError:
        interval = 0

    if interval <= 0:
        sys.exit(0)

    try:
        stdin_data = sys.stdin.read()
        if not stdin_data:
            sys.exit(0)

        hook_input = json.loads(stdin_data)
        session_id = hook_input.get("session_id", "unknown")
        transcript_path = hook_input.get("transcript_path", "")
        cwd = hook_input.get("cwd", "")
        project = os.path.basename(cwd.rstrip("/")) if cwd else None

        if not transcript_path:
            sys.exit(0)

        now = datetime.now().isoformat()

        state = _load_state()
        state = _purge_old_state(state)

        session_state = state.get(session_id, {"count": 0})
        session_state["count"] = session_state.get("count", 0) + 1
        session_state["last_seen"] = now
        state[session_id] = session_state
        _save_state(state)

        if session_state["count"] < interval:
            sys.exit(0)

        # Interval reached -- take a snapshot
        parsed = parse_transcript(transcript_path)
        if not parsed or parsed["message_count"] < 2:
            sys.exit(0)

        db_path = get_db_path()
        saved = save_to_db(db_path, session_id, parsed, project, source="periodic")

        if saved:
            sys.stderr.write(
                f"LoreConvo: Periodic snapshot at tool call {session_state['count']}"
                f" -- '{parsed['title']}'\n"
            )

        # Reset counter after snapshot
        session_state["count"] = 0
        session_state["last_save_at"] = now
        state[session_id] = session_state
        _save_state(state)

        # Re-queue sweep: retry pending/heuristic sessions from prior saves.
        if os.environ.get("LORECONVO_ANTHROPIC_API_KEY"):
            _requeue_pending_summaries(db_path)

    except json.JSONDecodeError:
        sys.exit(0)
    except Exception as e:
        sys.stderr.write(f"LoreConvo periodic save error: {e}\n")
        sys.exit(0)


def _requeue_pending_summaries(db_path):
    """Dispatch async summarizer for sessions stuck in summary_pending or heuristic state.

    Only processes sessions with summary_retry_count < MAX_SUMMARY_RETRIES.
    Explicitly excludes 'pre_migration_unknown' (pre-v0.7.0 quality indeterminate;
    user can upgrade explicitly via save_session(summarize=True)).
    Fire-and-forget -- periodic_save returns immediately.
    """
    import sqlite3
    import subprocess
    MAX_REQUEUE = 3  # max sessions to requeue per periodic sweep
    try:
        conn = sqlite3.connect(db_path, timeout=5.0)
        rows = conn.execute(
            """SELECT id FROM sessions
               WHERE summary_source IN ('summary_pending', 'heuristic')
               AND (summary_retry_count IS NULL OR summary_retry_count < 5)
               AND source != 'periodic'
               ORDER BY end_date DESC
               LIMIT ?""",
            (MAX_REQUEUE,),
        ).fetchall()
        conn.close()
    except Exception:
        return

    if not rows:
        return

    hook_dir = Path(__file__).resolve().parent
    src_dir = hook_dir / ".." / ".." / "src"
    summarizer = (src_dir / "session_summarizer.py").resolve()
    if not summarizer.exists():
        return

    for (sid,) in rows:
        try:
            subprocess.Popen(
                [sys.executable, str(summarizer), sid],
                env=os.environ.copy(),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except Exception:
            pass


if __name__ == "__main__":
    main()
