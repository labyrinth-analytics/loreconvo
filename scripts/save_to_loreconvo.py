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
    python scripts/save_to_loreconvo.py --read --tag-filter agent:ron-builder --limit 5

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
from datetime import datetime, timezone
from pathlib import Path

# Bootstrap: resolve storage_core for non-package callers.
# save_to_loreconvo.py lives in ron_skills/loreconvo/scripts/;
# _bootstrap.py lives in ron_skills/loreconvo/hooks/scripts/.
# Load _bootstrap by explicit file location -- no sys.path mutation.
import importlib.util
_BOOTSTRAP_PATH = (
    Path(__file__).resolve().parent.parent / "hooks" / "scripts" / "_bootstrap.py"
)
_bootstrap_spec = importlib.util.spec_from_file_location(
    "_loreconvo_bootstrap", str(_BOOTSTRAP_PATH)
)
_bootstrap = importlib.util.module_from_spec(_bootstrap_spec)
_bootstrap_spec.loader.exec_module(_bootstrap)

try:
    _storage = _bootstrap.resolve_storage_core(Path(__file__))
except _bootstrap.BootstrapError as exc:
    print(f"ERROR: {exc}", file=sys.stderr)
    sys.exit(1)

_open_conn = _storage._open_conn
ensure_schema = _storage.ensure_schema
sanitize_fts_query = _storage.sanitize_fts_query


# -- Tier enforcement (SH-100324: parity with MCP server's save_session) --

FREE_SESSION_LIMIT = 50


def _is_pro_licensed():
    """Check whether LoreConvo Pro is active.

    Mirrors the Config.is_pro check that the MCP server's save_session
    performs. Tries the full license module first (installed package
    or source-tree fallback). If neither is importable, does a
    lightweight env-var check for dev bypass mode.
    """
    # Path 1: installed package
    try:
        from loreconvo.core.license import is_pro_licensed
        return is_pro_licensed()
    except ImportError:
        pass

    # Path 2: source-tree fallback via importlib
    try:
        import importlib.util
        product_root = Path(__file__).resolve().parent.parent
        license_path = product_root / "src" / "core" / "license.py"
        if license_path.is_file():
            # Add the core directory to sys.path so license.py's
            # fallback `import license_store` can resolve.
            core_dir = license_path.parent
            if str(core_dir) not in sys.path:
                sys.path.insert(0, str(core_dir))
            spec = importlib.util.spec_from_file_location(
                "_loreconvo_license", str(license_path)
            )
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod.is_pro_licensed()
    except Exception:
        pass

    # Path 3: lightweight dev-bypass check (no import needed).
    # This covers the case where neither the package nor the source
    # tree is fully importable (e.g., missing transitive deps).
    dev_mode = os.environ.get("LAB_DEV_MODE", "").strip() == "1"
    env_value = os.environ.get("LORECONVO_PRO", "").strip()
    if dev_mode and env_value and not env_value.startswith("LAB-"):
        return True

    # Path 4: check durable license store directly
    try:
        import importlib.util
        product_root = Path(__file__).resolve().parent.parent
        store_path = product_root / "src" / "core" / "license_store.py"
        if store_path.is_file():
            core_dir = store_path.parent
            if str(core_dir) not in sys.path:
                sys.path.insert(0, str(core_dir))
            spec = importlib.util.spec_from_file_location(
                "_loreconvo_license_store", str(store_path)
            )
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            key = mod.read_key("loreconvo")
            if key:
                # Re-try full validation via license module
                try:
                    from loreconvo.core.license import validate_license_key
                    validate_license_key(key)
                    return True
                except Exception:
                    pass
    except Exception:
        pass

    return False


def _check_session_tier_limit(conn):
    """Check LoreConvo Free-tier session limit before saving.

    Returns True if the operation is allowed, False if rejected.
    Mirrors the check in database.py:save_session().
    """
    if _is_pro_licensed():
        return True

    # The source column may not exist in older schemas; fall back to
    # counting all sessions if the column is missing.
    try:
        row = conn.execute(
            "SELECT COUNT(*) as c FROM sessions "
            "WHERE source IS NULL OR source != 'file_memory'"
        ).fetchone()
    except sqlite3.OperationalError:
        row = conn.execute(
            "SELECT COUNT(*) as c FROM sessions"
        ).fetchone()
    current_count = row[0] if row else 0

    if current_count >= FREE_SESSION_LIMIT:
        print(
            f"Error: Free tier limit reached: {current_count} of "
            f"{FREE_SESSION_LIMIT} sessions stored. "
            "Upgrade at https://buy.stripe.com/9B65kv1VOgk3ekr7VD7N600 "
            "to unlock unlimited sessions, then set your LORECONVO_PRO "
            "license key."
        )
        return False

    return True


# -- DB discovery --

def _find_loreconvo_db():
    """Find the LoreConvo sessions.db, checking common locations.

    Mounted paths are checked FIRST. In Cowork VMs, os.path.expanduser("~")
    resolves to the ephemeral VM home (e.g. /sessions/sharp-adoring-dijkstra/),
    NOT Debbie's Mac home. Writing to VM ~ loses all data when the session ends.
    Checking /sessions/*/mnt/.loreconvo/ first ensures we find the Mac-backed
    mount when running in a Cowork VM.
    """
    # Cowork VM mount paths FIRST -- VM ~ is ephemeral, mount is Debbie's Mac
    import glob
    candidates = sorted(glob.glob("/sessions/*/mnt/.loreconvo/sessions.db"))
    # VM home fallback (used in Claude Code on Debbie's Mac where ~ IS the Mac home)
    candidates += [os.path.expanduser("~/.loreconvo/sessions.db")]

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
    conn = _open_conn(path, busy_timeout_ms=2000)
    return conn, path


# -- Save session --

def save_session(args):
    """Save a session to LoreConvo, matching the MCP tool's behavior exactly.

    SH-12871: when args.session_id is provided (Claude Code's native session
    ID, e.g. threaded through by agent_session_end.py from the transcript
    file), upsert by that ID instead of always minting a fresh UUID. Without
    this, a PreCompact-hook stub for the same real session (which DOES key by
    that native ID) gets permanently orphaned the moment SessionEnd inserts an
    unrelated row under a random UUID -- the stub's truncated content is all
    that's ever findable. getattr() with a default keeps every existing caller
    (none of which pass session_id) on today's behavior unchanged.
    """
    conn, db_path = _connect(args.db_path)

    provided_id = getattr(args, "session_id", None)
    now = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')

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

    if provided_id:
        existing = conn.execute(
            "SELECT id FROM sessions WHERE id = ?", (provided_id,)
        ).fetchone()
        if existing:
            # Merge into the existing row (e.g. a PreCompact stub). start_date
            # and created_at are the true session start -- left untouched.
            conn.execute(
                """UPDATE sessions SET title = ?, surface = ?, project = ?,
                   end_date = ?, summary = ?, decisions = ?, artifacts = ?,
                   open_questions = ?, tags = ?
                   WHERE id = ?""",
                (
                    args.title,
                    args.surface,
                    args.project,
                    args.end_date or now,
                    args.summary,
                    json.dumps(decisions),
                    json.dumps(artifacts),
                    json.dumps(open_questions),
                    json.dumps(tags),
                    provided_id,
                )
            )
            conn.commit()
            conn.close()

            print(f"Saved session {provided_id} to {db_path}")
            print(f"  title: {args.title}")
            print(f"  surface: {args.surface}")
            return provided_id
        session_id = provided_id
    else:
        session_id = str(uuid.uuid4())

    # SH-100324: Enforce Free-tier session limit before INSERT
    # (parity with MCP server's save_session path). Skipped for
    # upserts of existing sessions (the UPDATE path above).
    if not _check_session_tier_limit(conn):
        conn.close()
        return None

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

    conditions = []
    params = []

    if args.surface:
        conditions.append("surface = ?")
        params.append(args.surface)

    tag_filter = getattr(args, "tag_filter", None)
    if tag_filter:
        # LIKE match against the JSON-serialised tags array.
        # Tags are stored as json.dumps(list) so a quoted exact token like
        # '"agent:ron-builder"' appears verbatim in the stored string.
        # This is robust against NULL and malformed-JSON rows (those won't match).
        conditions.append("tags LIKE ?")
        params.append(f'%"{tag_filter}"%')

    base = (
        "SELECT id, surface, title, substr(summary, 1, 300) as summary_preview, "
        "datetime(created_at) as created FROM sessions"
    )
    if conditions:
        base += " WHERE " + " AND ".join(conditions)
    base += " ORDER BY created_at DESC LIMIT ?"
    params.append(args.limit)

    rows = conn.execute(base, params).fetchall()
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

def search_rows(args):
    """Search sessions by keyword in title/summary. Returns rows.

    Raw input is never passed to MATCH: FTS5 reads bare hyphens and colons
    as query syntax, so "SH-100406" raises "no such column: 100406". The
    sanitizer (shared with the MCP/CLI search path via storage_core) quotes
    each token, which is what makes ticket refs searchable at all.
    """
    conn, db_path = _connect(args.db_path)

    try:
        # Use FTS5 MATCH for performance and relevance
        rows = conn.execute(
            """SELECT s.id, s.surface, s.title,
                      substr(s.summary, 1, 300) as summary_preview,
                      datetime(s.created_at) as created
               FROM sessions_fts f
               JOIN sessions s ON s.rowid = f.rowid
               WHERE sessions_fts MATCH ?
               ORDER BY s.created_at DESC LIMIT ?""",
            (sanitize_fts_query(args.search), args.limit)
        ).fetchall()
    except sqlite3.OperationalError:
        # Sanitized input should always parse. If MATCH still fails (corrupt
        # or missing FTS index), degrade to a per-term AND over LIKE.
        #
        # NOT a substring match on the raw query: "SH-100406 substack" never
        # appears verbatim in any summary, so matching the whole string
        # returned zero rows and read as "never saved". Adding a term must
        # narrow results, never erase them.
        terms = [t for t in (args.search or "").split() if t]
        if not terms:
            conn.close()
            return []
        where = " AND ".join(["(title LIKE ? OR summary LIKE ?)"] * len(terms))
        params = []
        for term in terms:
            params.extend([f"%{term}%", f"%{term}%"])
        params.append(args.limit)
        rows = conn.execute(
            f"""SELECT id, surface, title,
                       substr(summary, 1, 300) as summary_preview,
                       datetime(created_at) as created
                FROM sessions
                WHERE {where}
                ORDER BY created_at DESC LIMIT ?""",
            params
        ).fetchall()
    conn.close()
    return rows


def search_sessions(args):
    """Search sessions and print the results."""
    rows = search_rows(args)

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
    parser.add_argument("--session-id", type=str, dest="session_id",
                        help="Claude Code's native session ID. When provided and a row "
                             "already exists under it (e.g. a PreCompact-hook stub), this "
                             "save updates that row instead of inserting a disconnected "
                             "duplicate under a fresh UUID.")

    # Read/search args
    parser.add_argument("--limit", type=int, default=5, help="Max sessions to return (default: 5)")
    parser.add_argument("--tag-filter", type=str, dest="tag_filter",
                        help="Filter --read results to sessions containing this tag (e.g. agent:ron-builder)")

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
