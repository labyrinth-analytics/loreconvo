#!/usr/bin/env python3
"""pipeline_tracker.py - Unified task/item tracking for all agents.

Replaces ad-hoc PipelineDB with a structured SQLite database and CLI.
All agents read/write through this script. No raw SQL.

Usage:
    python scripts/pipeline_tracker.py add --type opportunity \
        --desc "New product idea" --agent scout
    python scripts/pipeline_tracker.py add --type opportunity \
        --desc "New product idea" --agent scout --ref OPP-025
    python scripts/pipeline_tracker.py update --ref OPP-022 --status approved \
        --agent debbie --note "Approved for architecture review"
    python scripts/pipeline_tracker.py list [--status new] [--type bug] [--agent ron]
    python scripts/pipeline_tracker.py show --ref SEC-014
    python scripts/pipeline_tracker.py block --ref OPP-016 --blocker "No local SQL Server"
    python scripts/pipeline_tracker.py depend --ref GINA-001 --blocks RON-TODO-1
    python scripts/pipeline_tracker.py next --agent ron
    python scripts/pipeline_tracker.py types
    python scripts/pipeline_tracker.py statuses

Reference ID formats (auto-generated if --ref is omitted):
    OPP-NNN    Pipeline opportunities (Scout)
    SEC-NNN    Security findings (Brock)
    MEG-NNN    QA findings (Meg)
    GINA-NNN   Architecture findings (Gina)
    RON-NNN    Ron build tasks
    DEBBIE-NNN Debbie action items
    PROD-NNN   Product-level items
"""

import argparse
import json
import os
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

# DB location strategy:
# 1. If PIPELINE_DB env var is set, use that (explicit override)
# 2. If running from repo (scripts/ dir exists), use data/pipeline.db in repo
# 3. Fallback: ~/.loreconvo/pipeline.db (Debbie's Mac default)
# 4. Last resort for Cowork VM: /tmp/pipeline.db

def _find_db_path():
    # Explicit override
    if os.environ.get("PIPELINE_DB"):
        p = Path(os.environ["PIPELINE_DB"])
        return p.parent, p

    # Try repo-relative: walk up from this script to find repo root
    script_dir = Path(__file__).resolve().parent
    repo_root = script_dir.parent
    repo_data = repo_root / "data"

    # Test if we can actually write SQLite here (FUSE mounts may block it)
    if repo_root.exists():
        repo_data.mkdir(parents=True, exist_ok=True)
        test_db = repo_data / ".write_test.db"
        try:
            _conn = sqlite3.connect(str(test_db))
            _conn.execute("CREATE TABLE IF NOT EXISTS _test (x INTEGER)")
            _conn.close()
            test_db.unlink(missing_ok=True)
            return repo_data, repo_data / "pipeline.db"
        except (sqlite3.OperationalError, OSError):
            pass  # FUSE or read-only filesystem, fall through

    # Debbie's Mac default
    home_dir = Path(os.path.expanduser("~/.loreconvo"))
    if home_dir.exists():
        return home_dir, home_dir / "pipeline.db"

    # Cowork VM fallback -- /tmp is always writable
    tmp_dir = Path("/tmp/pipeline")
    tmp_dir.mkdir(parents=True, exist_ok=True)
    return tmp_dir, tmp_dir / "pipeline.db"

DB_DIR, DB_PATH = _find_db_path()

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    ref_id TEXT PRIMARY KEY,
    type TEXT NOT NULL,           -- opportunity, bug, security, architecture, task, product
    description TEXT NOT NULL,
    initial_date TEXT NOT NULL,   -- ISO 8601
    status_date TEXT NOT NULL,    -- ISO 8601
    updated_by TEXT NOT NULL,     -- agent name or 'debbie'
    status TEXT NOT NULL DEFAULT 'new',
    priority TEXT,                -- P1-P5 or HIGH/MEDIUM/LOW
    blockers TEXT DEFAULT '[]',   -- JSON array of ref_ids that block this item
    blocks TEXT DEFAULT '[]',     -- JSON array of ref_ids this item blocks
    notes TEXT DEFAULT '[]',      -- JSON array of {date, agent, text} entries
    product TEXT                  -- loreconvo, loredocs, sql_optimizer, etc.
);

CREATE TABLE IF NOT EXISTS history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ref_id TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    agent TEXT NOT NULL,
    field TEXT NOT NULL,
    old_value TEXT,
    new_value TEXT,
    FOREIGN KEY (ref_id) REFERENCES items(ref_id)
);
"""

VALID_STATUSES = [
    "new",                  # Just created, not yet triaged
    "approved",             # Debbie approved, ready for work
    "approved-for-review",  # Approved, needs architecture review first
    "in-progress",          # Actively being worked on
    "completed",            # Done
    "needs-info",           # Needs more information
    "on-hold",              # Blocked or deferred
    "deferred",             # Pushed to later
    "rejected",             # Not doing this
    "acknowledged",         # Debbie has seen it, pending assignment
    "fix-scheduled",        # Fix is planned
    "wont-fix",             # Accepted risk
]

VALID_TYPES = [
    "opportunity",   # Scout pipeline items
    "enhancement",   # Feature improvements to existing products (Debbie-direct or any agent)
    "bug",           # Meg QA findings
    "security",      # Brock security findings
    "architecture",  # Gina architecture findings
    "task",          # Ron build tasks
    "debbie-action", # Things only Debbie can do
    "product",       # Product-level tracking
]

# Map item type -> ref_id prefix for auto-generation
TYPE_PREFIX = {
    "opportunity":   "OPP",
    "enhancement":   "ENH",
    "bug":           "MEG",
    "security":      "SEC",
    "architecture":  "GINA",
    "task":          "RON",
    "debbie-action": "DEBBIE",
    "product":       "PROD",
}


def get_db():
    DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)
    return conn


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def log_change(conn, ref_id, agent, field, old_val, new_val):
    conn.execute(
        "INSERT INTO history (ref_id, timestamp, agent, field, old_value, new_value) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (ref_id, now_iso(), agent, field, str(old_val), str(new_val)),
    )


def next_ref_id(conn, item_type):
    """Auto-generate the next ref ID for a given type (e.g., OPP-025, MEG-041)."""
    prefix = TYPE_PREFIX.get(item_type, item_type.upper()[:4])
    pattern = f"{prefix}-%"
    rows = conn.execute(
        "SELECT ref_id FROM items WHERE ref_id LIKE ?", (pattern,)
    ).fetchall()
    max_num = 0
    for r in rows:
        m = re.search(r"-(\d+)$", r["ref_id"])
        if m:
            max_num = max(max_num, int(m.group(1)))
    return f"{prefix}-{max_num + 1:03d}"


def cmd_add(args):
    conn = get_db()
    ts = now_iso()

    # Auto-generate ref_id if not provided
    ref = args.ref
    if not ref:
        ref = next_ref_id(conn, args.type)

    try:
        conn.execute(
            "INSERT INTO items (ref_id, type, description, initial_date, status_date, "
            "updated_by, status, priority, product) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (ref, args.type, args.desc, ts, ts, args.agent, "new", args.priority, args.product),
        )
        log_change(conn, ref, args.agent, "status", None, "new")
        conn.commit()
        print(f"  [OK] Added {ref}: {args.desc}")
    except sqlite3.IntegrityError:
        print(f"  [WARN] {ref} already exists. Use 'update' to modify.")
    conn.close()


def cmd_update(args):
    conn = get_db()
    row = conn.execute("SELECT * FROM items WHERE ref_id = ?", (args.ref,)).fetchone()
    if not row:
        print(f"  [ERROR] {args.ref} not found.")
        conn.close()
        return 1

    updates = []
    params = []

    if args.status:
        if args.status not in VALID_STATUSES:
            print(f"  [ERROR] Invalid status '{args.status}'. Valid: {', '.join(VALID_STATUSES)}")
            conn.close()
            return 1
        log_change(conn, args.ref, args.agent, "status", row["status"], args.status)
        updates.append("status = ?")
        params.append(args.status)

    if args.priority:
        log_change(conn, args.ref, args.agent, "priority", row["priority"], args.priority)
        updates.append("priority = ?")
        params.append(args.priority)

    if args.desc:
        updates.append("description = ?")
        params.append(args.desc)

    if args.note:
        notes = json.loads(row["notes"] or "[]")
        notes.append({"date": now_iso(), "agent": args.agent, "text": args.note})
        updates.append("notes = ?")
        params.append(json.dumps(notes))

    if updates:
        updates.append("status_date = ?")
        params.append(now_iso())
        updates.append("updated_by = ?")
        params.append(args.agent)
        params.append(args.ref)
        conn.execute(f"UPDATE items SET {', '.join(updates)} WHERE ref_id = ?", params)
        conn.commit()
        print(f"  [OK] Updated {args.ref}")
    else:
        print("  [WARN] Nothing to update.")
    conn.close()


def cmd_block(args):
    conn = get_db()
    row = conn.execute("SELECT * FROM items WHERE ref_id = ?", (args.ref,)).fetchone()
    if not row:
        print(f"  [ERROR] {args.ref} not found.")
        conn.close()
        return 1

    blockers = json.loads(row["blockers"] or "[]")
    if args.blocker not in blockers:
        blockers.append(args.blocker)
    conn.execute(
        "UPDATE items SET blockers = ?, status = 'on-hold', status_date = ?, updated_by = ? WHERE ref_id = ?",
        (json.dumps(blockers), now_iso(), args.agent or "system", args.ref),
    )
    log_change(conn, args.ref, args.agent or "system", "blockers", row["blockers"], json.dumps(blockers))
    conn.commit()
    print(f"  [OK] {args.ref} blocked by: {args.blocker}")
    conn.close()


def cmd_depend(args):
    """Mark that args.ref blocks args.blocks (downstream dependency)."""
    conn = get_db()

    # Update the upstream item's 'blocks' list
    row = conn.execute("SELECT * FROM items WHERE ref_id = ?", (args.ref,)).fetchone()
    if not row:
        print(f"  [ERROR] {args.ref} not found.")
        conn.close()
        return 1
    blocks = json.loads(row["blocks"] or "[]")
    if args.blocks not in blocks:
        blocks.append(args.blocks)
    conn.execute("UPDATE items SET blocks = ? WHERE ref_id = ?", (json.dumps(blocks), args.ref))

    # Update the downstream item's 'blockers' list
    downstream = conn.execute("SELECT * FROM items WHERE ref_id = ?", (args.blocks,)).fetchone()
    if downstream:
        blockers = json.loads(downstream["blockers"] or "[]")
        if args.ref not in blockers:
            blockers.append(args.ref)
        conn.execute("UPDATE items SET blockers = ? WHERE ref_id = ?", (json.dumps(blockers), args.blocks))

    conn.commit()
    print(f"  [OK] {args.ref} blocks {args.blocks}")
    conn.close()


def cmd_list(args):
    # Handle bare --type or --status (no value given) -> show valid choices
    if args.status == "__list__":
        cmd_statuses(args)
        return 0
    if args.type == "__list__":
        cmd_types(args)
        return 0

    conn = get_db()
    query = "SELECT * FROM items WHERE 1=1"
    params = []

    if args.status:
        if args.status not in VALID_STATUSES:
            print(f"  [ERROR] Invalid status '{args.status}'. Valid statuses:")
            for s in VALID_STATUSES:
                print(f"    {s}")
            conn.close()
            return 1
        query += " AND status = ?"
        params.append(args.status)
    if args.type:
        if args.type not in VALID_TYPES:
            print(f"  [ERROR] Invalid type '{args.type}'. Valid types:")
            for t in VALID_TYPES:
                print(f"    {t}")
            conn.close()
            return 1
        query += " AND type = ?"
        params.append(args.type)
    if args.agent:
        query += " AND updated_by = ?"
        params.append(args.agent)
    if args.product:
        query += " AND product = ?"
        params.append(args.product)

    query += " ORDER BY initial_date DESC"
    rows = conn.execute(query, params).fetchall()

    if not rows:
        print("No items found.")
        conn.close()
        return

    # Table output
    print(f"{'Ref ID':<14} {'Type':<14} {'Status':<18} {'Priority':<8} {'Updated By':<12} {'Status Date':<12} Description")
    print("-" * 120)
    for r in rows:
        desc = (r["description"][:50] + "...") if len(r["description"]) > 50 else r["description"]
        sd = r["status_date"][:10] if r["status_date"] else ""
        print(f"{r['ref_id']:<14} {r['type']:<14} {r['status']:<18} {r['priority'] or '':<8} {r['updated_by']:<12} {sd:<12} {desc}")

    print(f"\n{len(rows)} item(s)")
    conn.close()


def cmd_show(args):
    conn = get_db()
    row = conn.execute("SELECT * FROM items WHERE ref_id = ?", (args.ref,)).fetchone()
    if not row:
        print(f"  [ERROR] {args.ref} not found.")
        conn.close()
        return 1

    print(f"Ref ID:      {row['ref_id']}")
    print(f"Type:        {row['type']}")
    print(f"Description: {row['description']}")
    print(f"Status:      {row['status']}")
    print(f"Priority:    {row['priority'] or 'unset'}")
    print(f"Product:     {row['product'] or 'unset'}")
    print(f"Created:     {row['initial_date']}")
    print(f"Updated:     {row['status_date']} by {row['updated_by']}")

    blockers = json.loads(row["blockers"] or "[]")
    if blockers:
        print(f"Blocked by:  {', '.join(blockers)}")

    blocks = json.loads(row["blocks"] or "[]")
    if blocks:
        print(f"Blocks:      {', '.join(blocks)}")

    notes = json.loads(row["notes"] or "[]")
    if notes:
        print(f"\nNotes ({len(notes)}):")
        for n in notes:
            print(f"  [{n['date'][:10]}] ({n['agent']}): {n['text']}")

    # History
    history = conn.execute(
        "SELECT * FROM history WHERE ref_id = ? ORDER BY timestamp", (args.ref,)
    ).fetchall()
    if history:
        print(f"\nHistory ({len(history)} changes):")
        for h in history:
            print(f"  [{h['timestamp'][:10]}] ({h['agent']}): {h['field']} {h['old_value']} -> {h['new_value']}")

    conn.close()


def cmd_next(args):
    """What should this agent work on next? Returns highest-priority unblocked items."""
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM items WHERE status IN ('approved', 'in-progress', 'fix-scheduled', 'acknowledged') "
        "AND blockers = '[]' ORDER BY priority, initial_date",
    ).fetchall()

    if not rows:
        print("No actionable items found.")
        conn.close()
        return

    print(f"Actionable items for {args.agent or 'any agent'}:")
    print(f"{'Ref ID':<14} {'Status':<18} {'Priority':<8} Description")
    print("-" * 80)
    for r in rows:
        desc = (r["description"][:50] + "...") if len(r["description"]) > 50 else r["description"]
        print(f"{r['ref_id']:<14} {r['status']:<18} {r['priority'] or '':<8} {desc}")

    conn.close()


def cmd_types(args):
    """Show all valid item types."""
    print("Valid item types:")
    print(f"  {'Type':<16} {'Ref Prefix':<12} Description")
    print("  " + "-" * 60)
    descs = {
        "opportunity":   "Pipeline opportunities (Scout finds these)",
        "enhancement":   "Feature improvements to existing products (Debbie-direct)",
        "bug":           "QA findings (Meg)",
        "security":      "Security findings (Brock)",
        "architecture":  "Architecture findings (Gina)",
        "task":          "Build tasks (Ron)",
        "debbie-action": "Things only Debbie can do",
        "product":       "Product-level tracking",
    }
    for t in VALID_TYPES:
        prefix = TYPE_PREFIX.get(t, "???")
        print(f"  {t:<16} {prefix + '-NNN':<12} {descs.get(t, '')}")


def cmd_statuses(args):
    """Show all valid statuses."""
    print("Valid statuses:")
    descs = {
        "new":                "Just created, not yet triaged",
        "approved":           "Debbie approved, ready for work",
        "approved-for-review":"Approved, needs architecture review first",
        "in-progress":        "Actively being worked on",
        "completed":          "Done",
        "needs-info":         "Needs more information before proceeding",
        "on-hold":            "Blocked or paused",
        "deferred":           "Pushed to later",
        "rejected":           "Not doing this",
        "acknowledged":       "Debbie has seen it, pending assignment",
        "fix-scheduled":      "Fix is planned for a future session",
        "wont-fix":           "Accepted risk, not fixing",
    }
    for s in VALID_STATUSES:
        print(f"  {s:<22} {descs.get(s, '')}")


def main():
    parser = argparse.ArgumentParser(
        description="Pipeline item tracker for all agents",
        epilog="Use 'types' or 'statuses' to see valid values. "
               "Ref IDs are auto-generated if --ref is omitted on 'add'."
    )
    sub = parser.add_subparsers(dest="command")

    # add
    p_add = sub.add_parser("add", help="Add a new pipeline item (ref ID auto-generated if omitted)")
    p_add.add_argument("--ref", help="Reference ID (e.g., OPP-025). Auto-generated if omitted.")
    p_add.add_argument("--type", required=True, choices=VALID_TYPES,
                       help="Item type. Run 'types' to see all options.")
    p_add.add_argument("--desc", required=True, help="Description")
    p_add.add_argument("--agent", required=True, help="Who created this (e.g., scout, meg, debbie)")
    p_add.add_argument("--priority", help="Priority (P1-P5 or HIGH/MEDIUM/LOW)")
    p_add.add_argument("--product", help="Product (loreconvo, loredocs, etc.)")

    # update
    p_upd = sub.add_parser("update", help="Update an existing item")
    p_upd.add_argument("--ref", required=True, help="Reference ID")
    p_upd.add_argument("--status", choices=VALID_STATUSES,
                        help="New status. Run 'statuses' to see all options.")
    p_upd.add_argument("--agent", required=True, help="Who is updating")
    p_upd.add_argument("--priority", help="New priority")
    p_upd.add_argument("--desc", help="Updated description")
    p_upd.add_argument("--note", help="Add a note")

    # block
    p_blk = sub.add_parser("block", help="Mark an item as blocked")
    p_blk.add_argument("--ref", required=True, help="Reference ID to block")
    p_blk.add_argument("--blocker", required=True, help="What is blocking it (text or ref_id)")
    p_blk.add_argument("--agent", help="Who is reporting the block")

    # depend
    p_dep = sub.add_parser("depend", help="Set a dependency (X blocks Y)")
    p_dep.add_argument("--ref", required=True, help="Upstream item (the blocker)")
    p_dep.add_argument("--blocks", required=True, help="Downstream item (the blocked)")

    # list
    status_hint = "Filter by status (run 'statuses' to see all). Omit value to see choices."
    type_hint = "Filter by type (run 'types' to see all). Omit value to see choices."
    p_lst = sub.add_parser("list", help="List items (use --type/--status/--agent/--product to filter)")
    p_lst.add_argument("--status", nargs="?", const="__list__", help=status_hint)
    p_lst.add_argument("--type", nargs="?", const="__list__", help=type_hint)
    p_lst.add_argument("--agent", help="Filter by last updated_by")
    p_lst.add_argument("--product", help="Filter by product")

    # show
    p_shw = sub.add_parser("show", help="Show full details for an item")
    p_shw.add_argument("--ref", required=True, help="Reference ID")

    # next
    p_nxt = sub.add_parser("next", help="Show next actionable items")
    p_nxt.add_argument("--agent", help="Filter for a specific agent")

    # types
    sub.add_parser("types", help="Show all valid item types and their ref ID prefixes")

    # statuses
    sub.add_parser("statuses", help="Show all valid statuses and their meanings")

    args = parser.parse_args()

    if args.command == "add":
        return cmd_add(args)
    elif args.command == "update":
        return cmd_update(args)
    elif args.command == "block":
        return cmd_block(args)
    elif args.command == "depend":
        return cmd_depend(args)
    elif args.command == "list":
        return cmd_list(args)
    elif args.command == "show":
        return cmd_show(args)
    elif args.command == "next":
        return cmd_next(args)
    elif args.command == "types":
        return cmd_types(args)
    elif args.command == "statuses":
        return cmd_statuses(args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main() or 0)
