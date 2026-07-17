"""LoreConvo Stop hook auto-capture.

Receives session metadata via stdin JSON when the user halts execution mid-session.
Parses the transcript JSONL to extract a summary, then saves directly to SQLite.

This provides feature parity with claude-mem's Stop hook auto-capture, enabling
intermediate session saves before SessionEnd fires. Useful for long-running sessions.

Designed to run within the 3-5 second timeout window.
"""

import json
import os
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPT_DIR))
from auto_save import (
    auto_save_tags,
    get_db_path,
    parse_transcript,
    save_to_db,
)


def main():
    """Capture session state when user stops execution mid-session."""
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

        # Parse transcript using existing function
        parsed = parse_transcript(transcript_path)
        if not parsed or parsed["message_count"] < 1:
            sys.exit(0)

        # Save to database with source='stop'
        # SessionEnd will overwrite this to source='session' on normal exit
        db_path = get_db_path()
        saved = save_to_db(db_path, session_id, parsed, project, source="stop")

        if saved:
            sys.stderr.write(
                f"LoreConvo: Stop auto-captured '{parsed['title']}'\n"
            )

        sys.exit(0)

    except json.JSONDecodeError:
        sys.exit(0)
    except Exception:
        sys.exit(0)


if __name__ == "__main__":
    main()
