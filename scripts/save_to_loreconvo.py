"""
Direct LoreConvo query tool -- fallback when MCP tools are unavailable.

Provides save_session, get_recent_sessions, search_sessions, and read_by_id
operations directly against the LoreConvo SQLite database. Use this when the
LoreConvo MCP server is not reachable (e.g., in scheduled tasks or batch scripts).

Usage (save a session):
    python scripts/save_to_loreconvo.py \
        --title "Daily QA run 2026-04-02" \
        --surface "qa" \
        --summary "Ran full test suite. 286 tests passing..." \
        --tags '["qa", "automated"]' \
        --artifacts '["reports/qa_report_2026_04_02.md"]'

Usage (read recent sessions):
    python scripts/save_to_loreconvo.py --read --limit 5
    python scripts/save_to_loreconvo.py --read --surface qa --limit 3

Usage (read one session by ID):
    python scripts/save_to_loreconvo.py --read-id e55cac21-4471-4991-bf1d-17b2883f28dc

Usage (search sessions):
    python scripts/save_to_loreconvo.py --search "test suite"
"""

import argparse
import json
import os
import sqlite3
import sys
import uuid
from datetime import datetime


# -- DB discovery --

def _find_loreconvo_db():
    """Find the LoreConvo sessions.db, checking common locations."""
    candidates = [
        os.path.expanduser("~/.loreconvo/sessions.db"),
    ]
    # Cowork VM mount paths
    import glob
    candidates += sorted(glob.glob("/sessions/*/mnt/.loreconvo/sessions.db"))

    for path in candidates:
        if os.path.isfile(path):
            return path
    return None


def _connect(db_path=None):
    """Connect to LoreConvo DB, auto-discovering if no path given."""
    path = db_path or _find_loreconvo_db()
    if not path:
        print("ERROR: Could not find LoreConvo sessions.db", file=sys.stderr)
        sys.exit(1)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn, path


# -- Save session --

def save_session(args):
    """Save a session to LoreConvo, matching the MCP tool's behavior exactly."""
    conn, db_path = _connect(args.db_path)

    session_id = str(uuid.uuid4())
    now = datetime.now().isoformat()

    # Parse JSON list args (accept both JSON strings and plain strings)
    def parse_list(val):
        if not val:
            return []
        try:
            parsed = json.loads(val)
            if isinstance(parsed, list):
                return parsed
        except (json.JSONDecodeError, TypeError):
            pass
        return [val]

    decisions = parse_list(args.decisions)
    artifacts = parse_list(args.artifacts)
    open_questions = parse_list(args.open_questions)
    tags = parse_list(args.tags)

    conn.execute(
        """INSERT INTO sessions
           (id, title, surface, project, start_date, end_date, summary,
            decisions, artifacts, open_questions, tags, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            session_id,
            args.title,
            args.surface,
            args.project,
            args.start_date or now,
            args.end_date,
            args.summary,
            json.dumps(decisions),
            json.dumps(artifacts),
            json.dumps(open_questions),
            json.dumps(tags),
            now,
        )
    )
    conn.commit()
    conn.close()

    print(f"Saved session {session_id} to {db_path}")
    print(f"  title: {args.title}")
    print(f"  surface: {args.surface}")
    return session_id


# -- Read recent sessions --

def read_sessions(args):
    """Read recent sessions from LoreConvo DB."""
    conn, db_path = _connect(args.db_path)

    query = "SELECT id, surface, title, substr(summary, 1, 300) as summary_preview, datetime(created_at) as created FROM sessions"
    params = []
    conditions = []

    if args.surface:
        conditions.append("surface = ?")
        params.append(args.surface)

    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(args.limit)

    rows = conn.execute(query, params).fetchall()
    conn.close()

    if not rows:
        print("No sessions found.")
        return

    for row in rows:
        print(f"[{row['created']}] ({row['surface']}) {row['title']}")
        print(f"  ID: {row['id']}")
        print(f"  {row['summary_preview']}")
        print()


# -- Read one session by ID --

def read_session_by_id(args):
    """Fetch the full content of a single session by UUID."""
    conn, db_path = _connect(args.db_path)

    row = conn.execute(
        """SELECT id, surface, project, title, summary, decisions, artifacts,
                  open_questions, tags, datetime(created_at) as created
           FROM sessions WHERE id = ?""",
        (args.read_id,)
    ).fetchone()
    conn.close()

    if not row:
        print(f"No session found with ID: {args.read_id}", file=sys.stderr)
        sys.exit(1)

    print(f"[{row['created']}] ({row['surface']}) {row['title']}")
    print(f"  ID: {row['id']}")
    if row['project']:
        print(f"  Project: {row['project']}")
    print()
    print("Summary:")
    print(row['summary'])
    print()

    for field in ("decisions", "artifacts", "open_questions", "tags"):
        raw = row[field]
        if raw:
            try:
                items = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                items = [raw]
            if items:
                print(f"{field.replace('_', ' ').title()}:")
                for item in items:
                    print(f"  - {item}")
                print()


# -- Search sessions --

def search_sessions(args):
    """Search sessions by keyword in title/summary."""
    conn, db_path = _connect(args.db_path)

    query = """SELECT id, surface, title, substr(summary, 1, 300) as summary_preview,
               datetime(created_at) as created
               FROM sessions
               WHERE title LIKE ? OR summary LIKE ?
               ORDER BY created_at DESC LIMIT ?"""
    pattern = f"%{args.search}%"
    rows = conn.execute(query, (pattern, pattern, args.limit)).fetchall()
    conn.close()

    if not rows:
        print(f"No sessions matching '{args.search}'.")
        return

    print(f"Found {len(rows)} session(s) matching '{args.search}':")
    print()
    for row in rows:
        print(f"[{row['created']}] ({row['surface']}) {row['title']}")
        print(f"  ID: {row['id']}")
        print(f"  {row['summary_preview']}")
        print()


# -- CLI --

def main():
    parser = argparse.ArgumentParser(
        description="Direct LoreConvo query tool (fallback for MCP tools)"
    )
    parser.add_argument("--db-path", help="Explicit path to sessions.db (auto-discovers if omitted)")

    # Mode flags
    parser.add_argument("--read", action="store_true", help="Read recent sessions instead of saving")
    parser.add_argument("--read-id", type=str, dest="read_id",
                        help="Read full content of one session by UUID")
    parser.add_argument("--search", type=str, help="Search sessions by keyword")

    # Save args
    parser.add_argument("--title", type=str, help="Session title")
    parser.add_argument("--surface", type=str,
                        help="Surface: cowork, code, chat, qa, security, pm, marketing, pipeline, error")
    parser.add_argument("--summary", type=str, help="Session summary (2-3 paragraphs)")
    parser.add_argument("--project", type=str, help="Project name")
    parser.add_argument("--decisions", type=str, help="JSON list of decisions")
    parser.add_argument("--artifacts", type=str, help="JSON list of artifacts")
    parser.add_argument("--open-questions", type=str, dest="open_questions", help="JSON list of open questions")
    parser.add_argument("--tags", type=str, help="JSON list of tags")
    parser.add_argument("--start-date", type=str, dest="start_date", help="ISO 8601 start time")
    parser.add_argument("--end-date", type=str, dest="end_date", help="ISO 8601 end time")

    # Read/search args
    parser.add_argument("--limit", type=int, default=5, help="Max sessions to return (default: 5)")

    args = parser.parse_args()

    if args.read_id:
        read_session_by_id(args)
    elif args.search:
        search_sessions(args)
    elif args.read:
        read_sessions(args)
    else:
        # Save mode -- require title, surface, summary
        if not args.title or not args.surface or not args.summary:
            parser.error("Save mode requires --title, --surface, and --summary")
        save_session(args)


if __name__ == "__main__":
    main()
