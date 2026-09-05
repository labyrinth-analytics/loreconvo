"""Detect clobbered LoreConvo sessions (SH-101571). [SKIP-TEST-GATE]

Scans for sessions that have the 'auto-captured' tag but lack any 'role:' tag,
indicating they were overwritten by shallow auto-capture/pre-compact hooks
instead of preserving explicit (rich) saves. Tested by manual invocation.

Usage:
    python3 detect_clobbered_sessions.py --db-path ~/.loreconvo/sessions.db --days 30
    python3 detect_clobbered_sessions.py --db-path ~/.loreconvo/sessions.db --days 30 --agent madison-marketing
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

try:
    from loreconvo.src.core.database import SessionDatabase
    from loreconvo.src.core.config import Config
except ImportError:
    try:
        from src.core.database import SessionDatabase
        from src.core.config import Config
    except ImportError:
        sys.stderr.write(
            "Error: Cannot import SessionDatabase from loreconvo package. "
            "Ensure loreconvo is installed or PYTHONPATH is set correctly.\n"
        )
        sys.exit(1)


def detect_clobbered_sessions(db_path, days_back=30, agent_filter=None):
    """Find sessions with 'auto-captured' tag but no 'role:' tag.

    Returns list of (session_id, end_date, tags, summary) tuples.
    Uses SessionDatabase accessor to respect DDL invariants.
    """
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"Database not found: {db_path}")

    config = Config(db_path=db_path)
    db = SessionDatabase(config)

    try:
        cutoff_date = (datetime.now() - timedelta(days=days_back)).isoformat()

        query = """
            SELECT id, end_date, tags, summary
            FROM sessions
            WHERE end_date >= ?
            AND tags LIKE '%auto-captured%'
            AND tags NOT LIKE '%role:%'
            ORDER BY end_date DESC
        """
        cursor = db.conn.execute(query, (cutoff_date,))
        results = cursor.fetchall()

        if not results:
            return []

        fetched = []
        for row in results:
            session_id, end_date, tags_json, summary = row
            fetched.append((session_id, end_date, tags_json, summary))

        if agent_filter:
            filtered = []
            for session_id, end_date, tags_json, summary in fetched:
                try:
                    tags = json.loads(tags_json) if tags_json else []
                    if any(t == f"agent:{agent_filter}" for t in tags):
                        filtered.append((session_id, end_date, tags_json, summary))
                except (json.JSONDecodeError, TypeError):
                    pass
            return filtered

        return fetched

    finally:
        db.close()


def format_tags_readable(tags_json):
    """Parse and format tags for readability."""
    try:
        tags = json.loads(tags_json) if tags_json else []
        return ", ".join(str(t) for t in tags)
    except (json.JSONDecodeError, TypeError):
        return tags_json or "(no tags)"


def main():
    parser = argparse.ArgumentParser(
        description="Detect clobbered LoreConvo sessions (SH-101571)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 detect_clobbered_sessions.py --days 30
  python3 detect_clobbered_sessions.py --days 30 --agent madison-marketing
  python3 detect_clobbered_sessions.py --db-path /custom/path.db --days 7
        """,
    )
    parser.add_argument(
        "--db-path",
        default=os.path.expanduser("~/.loreconvo/sessions.db"),
        help="Path to LoreConvo database (default: ~/.loreconvo/sessions.db)",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=30,
        help="Days back to scan (default: 30)",
    )
    parser.add_argument(
        "--agent",
        help="Filter by agent name (optional)",
    )

    args = parser.parse_args()

    try:
        results = detect_clobbered_sessions(args.db_path, args.days, args.agent)
    except FileNotFoundError as e:
        sys.stderr.write(f"Error: {e}\n")
        sys.exit(1)

    if not results:
        print(f"[OK] No clobbered sessions found in last {args.days} days")
        if args.agent:
            print(f"     (agent filter: {args.agent})")
        return 0

    print(f"[WARN] Found {len(results)} potentially clobbered sessions in last {args.days} days:")
    if args.agent:
        print(f"       (agent filter: {args.agent})")
    print()

    for i, (session_id, end_date, tags_json, summary) in enumerate(results, 1):
        tags_readable = format_tags_readable(tags_json)
        print(f"{i}. {session_id}")
        print(f"   End Date:  {end_date}")
        print(f"   Tags:      {tags_readable}")
        if summary:
            summary_preview = summary[:80].replace("\n", " ")
            if len(summary) > 80:
                summary_preview += "..."
            print(f"   Summary:   {summary_preview}")
        print()

    return 1 if results else 0


if __name__ == "__main__":
    sys.exit(main())
