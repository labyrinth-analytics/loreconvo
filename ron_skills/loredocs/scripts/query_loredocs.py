"""
Direct LoreDocs query tool -- fallback when MCP tools are unavailable.

Provides vault_list, vault_info (inject_summary), vault_search, and
vault_add_document operations directly against the LoreDocs SQLite database.
Use this when the LoreDocs MCP server is not reachable (e.g., in scheduled
tasks or batch scripts).

Usage:
    # List all vaults (equivalent to vault_list)
    python scripts/query_loredocs.py --list

    # Show vault details + document manifest (equivalent to vault_inject_summary)
    python scripts/query_loredocs.py --info "My Project Docs"

    # Search documents across all vaults
    python scripts/query_loredocs.py --search "architecture"

    # Add a text/markdown document to a vault
    python scripts/query_loredocs.py --add-doc \
        --vault "My Project Docs" \
        --name "Architecture Overview" \
        --file docs/architecture.md \
        --tags '["architecture", "design"]' \
        --category "architecture"

    # Add a document from stdin (pipe content in)
    echo "# My Doc" | python scripts/query_loredocs.py --add-doc \
        --vault "My Project Docs" \
        --name "Quick Note" \
        --stdin
"""

import argparse
import glob
import json
import os
import sqlite3
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path


# -- DB discovery --

def _find_loredocs_db():
    """Find the LoreDocs database, checking common locations.

    Mounted paths are checked FIRST. In Cowork VMs, os.path.expanduser("~")
    resolves to the ephemeral VM home (e.g. /sessions/sharp-adoring-dijkstra/),
    NOT Debbie's Mac home. Writing to VM ~ loses all data when the session ends.
    Checking /sessions/*/mnt/.loredocs/ first ensures we find the Mac-backed
    mount when running in a Cowork VM.
    """
    # Cowork VM mount paths FIRST -- VM ~ is ephemeral, mount is Debbie's Mac
    candidates = sorted(glob.glob("/sessions/*/mnt/.loredocs/loredocs.db"))
    # VM home fallback (used in Claude Code on Debbie's Mac where ~ IS the Mac home)
    candidates += [os.path.expanduser("~/.loredocs/loredocs.db")]

    for path in candidates:
        if os.path.isfile(path):
            return path
    return None


def _find_loredocs_root(db_path):
    """Derive the LoreDocs root dir from the DB path."""
    return str(Path(db_path).parent)


def _connect(db_path=None):
    """Connect to LoreDocs DB, auto-discovering if no path given."""
    path = db_path or _find_loredocs_db()
    if not path:
        print("ERROR: Could not find LoreDocs loredocs.db", file=sys.stderr)
        sys.exit(1)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn, path


def _fmt_size(size_bytes):
    """Format bytes into human-readable size."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"


def _resolve_vault(conn, vault_ref):
    """Resolve a vault by ID or name (case-insensitive). Returns row dict or None."""
    # Try exact ID match first
    row = conn.execute("SELECT * FROM vaults WHERE id = ?", (vault_ref,)).fetchone()
    if row:
        return dict(row)

    # Try case-insensitive name match
    row = conn.execute(
        "SELECT * FROM vaults WHERE LOWER(name) = LOWER(?)", (vault_ref,)
    ).fetchone()
    if row:
        return dict(row)

    return None


# -- vault_list --

def cmd_list(args):
    """List all vaults with summary stats."""
    conn, db_path = _connect(args.db_path)

    query = "SELECT * FROM vaults"
    if not args.include_archived:
        query += " WHERE archived = 0"
    query += " ORDER BY updated_at DESC"

    rows = conn.execute(query).fetchall()

    if not rows:
        print("No vaults found.")
        return

    print("# Your Vaults\n")
    for row in rows:
        vault_id = row["id"]
        stats = conn.execute(
            """SELECT COUNT(*) as doc_count, COALESCE(SUM(file_size_bytes), 0) as total_size
               FROM documents WHERE vault_id = ? AND deleted = 0""",
            (vault_id,)
        ).fetchone()

        status = " [ARCHIVED]" if row["archived"] else ""
        print(f"## {row['name']}{status} (`{vault_id}`)")
        if row["description"]:
            print(f"  {row['description']}")
        print(f"  - Documents: {stats['doc_count']} | Size: {_fmt_size(stats['total_size'])}")
        try:
            tags = json.loads(row["tags"]) if row["tags"] else []
        except (json.JSONDecodeError, TypeError):
            tags = []
        if tags:
            print(f"  - Tags: {', '.join(tags)}")
        try:
            linked = json.loads(row["linked_projects"]) if row["linked_projects"] else []
        except (json.JSONDecodeError, TypeError):
            linked = []
        if linked:
            print(f"  - Linked projects: {', '.join(linked)}")
        print(f"  - Last updated: {row['updated_at'][:10]}")
        print()

    conn.close()


# -- vault_info / vault_inject_summary --

def cmd_info(args):
    """Show vault details and full document manifest."""
    conn, db_path = _connect(args.db_path)

    vault = _resolve_vault(conn, args.info)
    if not vault:
        print(f"Error: Vault '{args.info}' not found.")
        conn.close()
        return

    vault_id = vault["id"]
    stats = conn.execute(
        """SELECT COUNT(*) as doc_count, COALESCE(SUM(file_size_bytes), 0) as total_size
           FROM documents WHERE vault_id = ? AND deleted = 0""",
        (vault_id,)
    ).fetchone()

    docs = conn.execute(
        """SELECT id, name, category, priority, tags, notes, updated_at, file_size_bytes
           FROM documents WHERE vault_id = ? AND deleted = 0
           ORDER BY updated_at DESC""",
        (vault_id,)
    ).fetchall()

    print(f"# {vault['name']} (`{vault_id}`)")
    if vault["description"]:
        print(f"\n{vault['description']}")
    print(f"\nDocuments: {stats['doc_count']} | Total size: {_fmt_size(stats['total_size'])}")
    print(f"Created: {vault['created_at'][:10]} | Updated: {vault['updated_at'][:10]}")

    tags = json.loads(vault["tags"]) if vault["tags"] else []
    if tags:
        print(f"Tags: {', '.join(tags)}")

    if docs:
        print(f"\n## Documents ({len(docs)})\n")
        for d in docs:
            dtags = json.loads(d["tags"]) if d["tags"] else []
            tag_str = f" [{', '.join(dtags)}]" if dtags else ""
            print(f"- **{d['name']}** ({d['category']}, {d['priority']}){tag_str}")
            print(f"  ID: {d['id']} | Size: {_fmt_size(d['file_size_bytes'])} | Updated: {d['updated_at'][:10]}")
            if d["notes"]:
                print(f"  Notes: {d['notes'][:100]}")
    else:
        print("\nNo documents in this vault.")

    conn.close()


# -- vault_search --

def cmd_search(args):
    """Search documents across all vaults by keyword."""
    conn, db_path = _connect(args.db_path)

    # Use FTS if available, fall back to LIKE
    try:
        rows = conn.execute(
            """SELECT d.id, d.vault_id, d.name, d.category, d.tags, d.notes,
                      d.updated_at, d.file_size_bytes, v.name as vault_name
               FROM doc_fts f
               JOIN documents d ON f.doc_id = d.id
               JOIN vaults v ON d.vault_id = v.id
               WHERE doc_fts MATCH ? AND d.deleted = 0
               ORDER BY d.updated_at DESC LIMIT ?""",
            (args.search, args.limit)
        ).fetchall()
    except sqlite3.OperationalError:
        # FTS match failed, fall back to LIKE
        pattern = f"%{args.search}%"
        rows = conn.execute(
            """SELECT d.id, d.vault_id, d.name, d.category, d.tags, d.notes,
                      d.updated_at, d.file_size_bytes, v.name as vault_name
               FROM documents d
               JOIN vaults v ON d.vault_id = v.id
               WHERE d.deleted = 0 AND (d.name LIKE ? OR d.notes LIKE ?)
               ORDER BY d.updated_at DESC LIMIT ?""",
            (pattern, pattern, args.limit)
        ).fetchall()

    conn.close()

    if not rows:
        print(f"No documents matching '{args.search}'.")
        return

    print(f"Found {len(rows)} document(s) matching '{args.search}':\n")
    for d in rows:
        dtags = json.loads(d["tags"]) if d["tags"] else []
        tag_str = f" [{', '.join(dtags)}]" if dtags else ""
        print(f"- **{d['name']}** in vault '{d['vault_name']}'{tag_str}")
        print(f"  ID: {d['id']} | Category: {d['category']} | Size: {_fmt_size(d['file_size_bytes'])}")
        if d["notes"]:
            print(f"  Notes: {d['notes'][:100]}")
        print()


# -- vault_add_document --

def cmd_add_doc(args):
    """Add a document to a vault."""
    conn, db_path = _connect(args.db_path)
    root = _find_loredocs_root(db_path)

    vault = _resolve_vault(conn, args.vault)
    if not vault:
        print(f"Error: Vault '{args.vault}' not found.")
        conn.close()
        return

    vault_id = vault["id"]

    # Read content
    if args.stdin:
        content = sys.stdin.buffer.read()
        filename = args.name.replace(" ", "_").lower() + ".md"
    elif args.file:
        filepath = Path(args.file)
        if not filepath.is_file():
            print(f"Error: File '{args.file}' not found.")
            conn.close()
            return
        content = filepath.read_bytes()
        filename = filepath.name
    else:
        print("Error: Must specify --file or --stdin for document content.")
        conn.close()
        return

    # Validate filename
    if not filename or '..' in filename or '\x00' in filename or os.path.isabs(filename):
        print("Error: Invalid filename.")
        conn.close()
        return

    # Parse tags
    tags = []
    if args.tags:
        try:
            parsed = json.loads(args.tags)
            if isinstance(parsed, list):
                tags = parsed
        except (json.JSONDecodeError, TypeError):
            tags = [args.tags]

    doc_id = str(uuid.uuid4())[:12]
    now = datetime.now(timezone.utc).isoformat()
    ext = Path(filename).suffix.lower()
    category = args.category or "general"
    priority = args.priority or "normal"
    notes = args.notes or ""

    # Write file to disk
    vaults_dir = Path(root) / "vaults"
    doc_dir = vaults_dir / vault_id / "docs" / doc_id
    doc_dir.mkdir(parents=True, exist_ok=True)
    (doc_dir / "history").mkdir(exist_ok=True)

    current_file = doc_dir / f"current{ext}"
    current_file.write_bytes(content)

    # Extract text for search (simple: just decode if text-like)
    try:
        extracted = content.decode("utf-8")
    except UnicodeDecodeError:
        extracted = ""

    (doc_dir / "extracted.txt").write_text(extracted, encoding="utf-8")

    # Write metadata
    meta = {
        "id": doc_id,
        "vault_id": vault_id,
        "name": args.name,
        "original_filename": filename,
        "file_extension": ext,
        "category": category,
        "priority": priority,
        "tags": tags,
        "notes": notes,
        "created_at": now,
        "updated_at": now,
        "file_size_bytes": len(content),
        "version_count": 1,
    }
    (doc_dir / "metadata.json").write_text(
        json.dumps(meta, indent=2), encoding="utf-8"
    )

    # Insert into database
    conn.execute(
        """INSERT INTO documents
           (id, vault_id, name, original_filename, file_extension,
            category, priority, tags, notes, created_at, updated_at,
            file_size_bytes, version_count, deleted)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)""",
        (doc_id, vault_id, args.name, filename, ext, category, priority,
         json.dumps(tags), notes, now, now, len(content), 1)
    )

    # Index in FTS
    conn.execute(
        """INSERT INTO doc_fts (doc_id, vault_id, name, content, tags, notes)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (doc_id, vault_id, args.name, extracted, " ".join(tags), notes)
    )

    # Update vault timestamp
    conn.execute(
        "UPDATE vaults SET updated_at = ? WHERE id = ?", (now, vault_id)
    )
    conn.commit()
    conn.close()

    print(f"Added document '{args.name}' to vault '{vault['name']}'")
    print(f"  doc_id: {doc_id}")
    print(f"  filename: {filename}")
    print(f"  size: {_fmt_size(len(content))}")


# -- CLI --

def main():
    parser = argparse.ArgumentParser(
        description="Direct LoreDocs query tool (fallback for MCP tools)"
    )
    parser.add_argument("--db-path", help="Explicit path to loredocs.db (auto-discovers if omitted)")

    # Mode flags
    parser.add_argument("--list", action="store_true", help="List all vaults (equivalent to vault_list)")
    parser.add_argument("--info", type=str, help="Show vault details by name or ID (equivalent to vault_inject_summary)")
    parser.add_argument("--search", type=str, help="Search documents by keyword")
    parser.add_argument("--add-doc", action="store_true", dest="add_doc", help="Add a document to a vault")
    parser.add_argument("--include-archived", action="store_true", dest="include_archived",
                        help="Include archived vaults in --list")

    # Search/list args
    parser.add_argument("--limit", type=int, default=10, help="Max results for search (default: 10)")

    # Add-doc args
    parser.add_argument("--vault", type=str, help="Vault name or ID (for --add-doc)")
    parser.add_argument("--name", type=str, help="Document name (for --add-doc)")
    parser.add_argument("--file", type=str, help="Path to file to add (for --add-doc)")
    parser.add_argument("--stdin", action="store_true", help="Read document content from stdin (for --add-doc)")
    parser.add_argument("--tags", type=str, help="JSON list of tags (for --add-doc)")
    parser.add_argument("--category", type=str, help="Document category (for --add-doc, default: general)")
    parser.add_argument("--priority", type=str, help="Document priority (for --add-doc, default: normal)")
    parser.add_argument("--notes", type=str, help="Document notes (for --add-doc)")

    args = parser.parse_args()

    if args.add_doc:
        if not args.vault or not args.name:
            parser.error("--add-doc requires --vault and --name")
        cmd_add_doc(args)
    elif args.info:
        cmd_info(args)
    elif args.search:
        cmd_search(args)
    elif args.list:
        cmd_list(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
