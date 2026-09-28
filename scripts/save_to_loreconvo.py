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

Usage (semantic search; Pro, degrades to keyword search if unavailable):
    python scripts/save_to_loreconvo.py --search "how did we fix the flaky test" --semantic
"""

import argparse
import json
import os
import sqlite3
import sys
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
    """DEPRECATED shim -- the fallback save path no longer performs its own
    limit check (SH-101932 Phase B: save_session is a SessionDatabase caller,
    and SessionDatabase.save_session enforces the canonical tier limit
    itself). Kept as a pass-through so legacy callers (e.g. tests that
    imported the name) keep working; the duplicate count query, FREE_SESSION_LIMIT,
    and the 4-path _is_pro_licensed license resolution below are retained for
    read-path Pro gating (--semantic) and are NOT reimplementing save logic."""
    return True


# -- DB discovery --

def _find_loreconvo_db():
    """Find the LoreConvo sessions.db, checking common locations.

    `LORECONVO_DB`, when set, is the highest-precedence *discovery*
    candidate (below the `--db-path` flag, which callers check before this
    function runs). Resolution delegates to Config itself (the optional-
    import pattern already used elsewhere in this file for the license
    module) rather than duplicating its env-check -- one implementation, not
    two. An explicitly-set-but-unresolvable LORECONVO_DB is a hard error,
    never a silent fall-through to a different corpus (SH-101500).

    Mounted paths are checked next. In Cowork VMs, os.path.expanduser("~")
    resolves to the ephemeral VM home (e.g. /sessions/sharp-adoring-dijkstra/),
    NOT Debbie's Mac home. Writing to VM ~ loses all data when the session ends.
    Checking /sessions/*/mnt/.loreconvo/ first ensures we find the Mac-backed
    mount when running in a Cowork VM.
    """
    if os.environ.get("LORECONVO_DB"):
        try:
            from loreconvo.core.config import Config
            resolved = Config().db_path
        except ImportError:
            # Package absent. Config's set-case resolution is the env var
            # verbatim, so this is the same value, not a second derivation.
            resolved = os.environ["LORECONVO_DB"]
        if not os.path.isfile(resolved):
            print(
                f"ERROR: LORECONVO_DB is set but no database exists at "
                f"{resolved}. Refusing to fall back to a different corpus. "
                f"Fix the path, unset LORECONVO_DB, or pass --db-path.",
                file=sys.stderr,
            )
            sys.exit(1)
        return resolved

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
    """Save a session to LoreConvo via the canonical SessionDatabase.save_session.

    SH-101932 Phase B: the fallback is a second caller of the MCP server's
    own save path, never a second implementation. Removes the duplicated
    Free-tier limit check, the 4-path license resolution, and the raw
    INSERT/UPDATE that had drifted from the canonical write (content_hash,
    origin_machine, previous_summary, digest invalidation, truncation, and
    the source column all now flow through the same code the MCP server
    uses).

    Preserved fallback-specific semantics:
      - SH-12871 merge: when --session-id names an EXISTING row, the true
        session start (start_date/created_at) is read from that row and
        passed through on Session construction, so the canonical upsert
        does not overwrite it with 'now'.
      - Free-tier rejection still prints the canonical upgrade message on
        stdout and returns None (not an uncaught exception) -- callers
        like agent_session_end.py rely on exit 0 with no row.
    """

    try:
        core = _bootstrap.resolve_session_core(Path(__file__))
        SessionDatabase = core.SessionDatabase
        SessionLimitReachedError = core.SessionLimitReachedError
        Config = core.Config
        Session = core.Session
    except _bootstrap.BootstrapError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    db_path = args.db_path or _find_loreconvo_db()
    if not db_path:
        print("ERROR: Could not find LoreConvo sessions.db", file=sys.stderr)
        sys.exit(1)

    provided_id = getattr(args, "session_id", None)
    now = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')

    # Parse JSON list args (accept both JSON strings and plain strings)
    def parse_list(val, flag_name=None):
        if not val:
            return []
        try:
            parsed = json.loads(val)
            if isinstance(parsed, list):
                return parsed
        except (json.JSONDecodeError, TypeError):
            pass
        # Non-JSON fallback: warn but keep exit code 0
        if flag_name:
            truncated = val[:80] + ("..." if len(val) > 80 else "")
            print(
                f"WARNING: --{flag_name} value is not valid JSON. "
                f"Expected format: '[\"item1\",\"item2\"]'. "
                f"Received (truncated): {truncated!r}. "
                f"Stored as single list element.",
                file=sys.stderr,
            )
        return [val]

    decisions = parse_list(args.decisions, flag_name="decisions")
    artifacts = parse_list(args.artifacts, flag_name="artifacts")
    open_questions = parse_list(args.open_questions, flag_name="open-questions")
    tags = parse_list(args.tags, flag_name="tags")

    db = SessionDatabase(Config(db_path=db_path))
    try:
        existing = db.get_session(provided_id) if provided_id else None

        if existing is not None:
            # SH-12871 merge: the true session start survives the upsert.
            start_date = existing.start_date or args.start_date or now
            created_at = existing.created_at or now
            session_id = provided_id
        else:
            start_date = args.start_date or now
            created_at = now
            session_id = provided_id  # None -> Session mints a UUID

        session = Session(
            title=args.title,
            surface=args.surface,
            project=args.project,
            start_date=start_date,
            end_date=args.end_date,
            summary=args.summary,
            decisions=decisions,
            artifacts=artifacts,
            open_questions=open_questions,
            tags=tags,
            created_at=created_at,
        )
        if session_id is not None:
            session.id = session_id

        try:
            saved_id = db.save_session(session)
        except SessionLimitReachedError as exc:
            print(str(exc))
            return None
    finally:
        db.close()

    print(f"Saved session {saved_id} to {db_path}")
    print(f"  title: {args.title}")
    print(f"  surface: {args.surface}")
    return saved_id


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
        """SELECT id, surface, project, title, summary, previous_summary, decisions,
                  artifacts, open_questions, tags, datetime(created_at) as created
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

    if row['previous_summary']:
        print("Previous Summary:")
        print(row['previous_summary'])
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


def _cmd_search_semantic(args):
    """Attempt Pro semantic search via SessionDatabase.search_sessions(semantic=True).

    Reuses the exact call the MCP search_sessions tool makes rather than
    re-implementing ranking/fusion -- a second caller, never a second
    implementation.

    Returns True if semantic results were printed to stdout (caller is
    done). Returns False after printing a degrade tip to stderr; the
    caller should then run the ordinary keyword search on stdout, never a
    mix of tip and result text on the same stream.
    """
    tip = (
        "Semantic search requires LoreConvo Pro. Returning keyword results "
        "instead. Set your LORECONVO_PRO license key to activate."
    )
    if not _is_pro_licensed():
        print(tip, file=sys.stderr)
        return False

    try:
        core = _bootstrap.resolve_session_core(Path(__file__))
    except _bootstrap.BootstrapError as exc:
        print(tip, file=sys.stderr)
        print(f"ERROR: {exc}", file=sys.stderr)
        return False

    db_path = args.db_path or _find_loreconvo_db()
    if not db_path:
        print("ERROR: Could not find LoreConvo sessions.db", file=sys.stderr)
        sys.exit(1)

    db = core.SessionDatabase(core.Config(db_path=db_path))
    try:
        results = db.search_sessions(args.search, limit=args.limit, semantic=True)
    finally:
        db.close()

    if not results:
        print(f"No sessions matching '{args.search}' (semantic).")
        return True

    print(f"Found {len(results)} session(s) matching '{args.search}' (semantic):")
    print()
    for r in results:
        s = r.session
        preview = s.summary[:300] + "..." if len(s.summary) > 300 else s.summary
        print(f"[{s.start_date}] ({s.surface}) {s.title}")
        print(f"  ID: {s.id}")
        print(f"  {preview}")
        print()
    return True


def search_sessions(args):
    """Search sessions and print the results (or semantically with --semantic)."""
    if getattr(args, "semantic", False) and _cmd_search_semantic(args):
        return

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


# -- Skill history / inspect / stats / graph / dream-log / export (SH-101927/101928) --

def _session_database(args):
    """Open a SessionDatabase for shared-core operations.

    The fallback is a second caller of the MCP server's own
    SessionDatabase methods -- never a second implementation. Resolution
    goes through _bootstrap.resolve_session_core (installed package first,
    then synthesis from a sibling src/ checkout) because the fallback must
    work from BOTH interpreters the fleet invokes it with: .venv python
    (editable loreconvo install) and a bare system python (no loreconvo
    distribution -- the Hermes ceremony path).
    """
    try:
        core = _bootstrap.resolve_session_core(Path(__file__))
    except _bootstrap.BootstrapError as exc:
        print(
            f"ERROR: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)

    db_path = args.db_path or _find_loreconvo_db()
    if not db_path:
        print("ERROR: Could not find LoreConvo sessions.db", file=sys.stderr)
        sys.exit(1)

    return core.SessionDatabase(core.Config(db_path=db_path))


def skill_history(args):
    """List sessions that used a specific skill (get_skill_history)."""
    db = _session_database(args)
    try:
        sessions = db.get_skill_history(args.skill_name, args.days)
    finally:
        db.close()

    if not sessions:
        print(f'No sessions found using skill "{args.skill_name}"')
        return
    for s in sessions:
        print(f"  {s.start_date[:10]}  {s.surface:6s}  {s.title}")
    print(f"\n{len(sessions)} session(s) used '{args.skill_name}'")


def cmd_inspect(args):
    """List stored sessions with optional filters (inspect_sessions)."""
    db = _session_database(args)
    try:
        sessions = db.inspect_sessions(
            search=getattr(args, "search", None),
            tag=getattr(args, "tag_filter", None),
            surface=getattr(args, "surface", None),
            since=getattr(args, "since", None),
            limit=args.limit,
        )
        stats = db.get_inspect_stats() if getattr(args, "show_stats", False) else None
    finally:
        db.close()

    if stats:
        print(json.dumps(stats, indent=2))
    for s in sessions:
        print(f"  {s.start_date[:10]}  {s.surface:6s}  {s.title}")
    print(f"\n{len(sessions)} session(s)")


def cmd_stats(args):
    """Usage dashboard (get_stats): counts, storage, hook failure status."""
    db = _session_database(args)
    try:
        stats = db.usage_stats_with_hook_status()
    finally:
        db.close()
    print(json.dumps(stats, indent=2))


def cmd_graph(args):
    """Mermaid knowledge-graph around a session or project (graph_session_map)."""
    db = _session_database(args)
    try:
        result = db.build_graph_map_payload(
            session_id=args.graph_session_id,
            project=args.graph_project,
            depth=args.depth,
            max_nodes=args.max_nodes,
        )
    finally:
        db.close()

    if "error" in result:
        err = result["error"]
        print(
            f"ERROR: {err.get('code')}: {err.get('message')}",
            file=sys.stderr,
        )
        sys.exit(1)
    print(result["mermaid"])


def cmd_dream_log(args):
    """Consolidation log entries with digest status (get_dream_log)."""
    db = _session_database(args)
    try:
        entries, digest = db.get_dream_log_entries(
            project=getattr(args, "project", None),
            surface=getattr(args, "surface", None),
            limit=args.limit,
        )
    finally:
        db.close()
    print(json.dumps({
        "status": "ok",
        "project": getattr(args, "project", None),
        "surface": getattr(args, "surface", None),
        "entries": entries,
        "digest_status": digest,
    }, indent=2))


def cmd_export(args):
    """Export sessions as JSON/JSONL (export_sessions)."""
    raw_tags = getattr(args, "tags", None)
    if isinstance(raw_tags, str):
        try:
            raw_tags = json.loads(raw_tags)
        except json.JSONDecodeError:
            raw_tags = [raw_tags]

    db = _session_database(args)
    try:
        payload = db.export_payload(
            project=getattr(args, "project", None),
            tags=raw_tags,
            days_back=args.days_back,
            limit=args.export_limit,
            fmt=args.format,
        )
    finally:
        db.close()

    data = payload["data"]
    if args.output:
        Path(args.output).expanduser().write_text(data, encoding="utf-8")
        print(
            f"Exported {payload['session_count']} session(s) to "
            f"{args.output} ({args.format})"
        )
    else:
        print(data)


def cmd_import(args):
    """Import sessions from an export file (import_sessions)."""
    db = _session_database(args)
    try:
        result = db.import_export_file(
            file_path=args.import_file,
            on_conflict=args.on_conflict,
            dry_run=args.dry_run,
        )
    finally:
        db.close()

    if "error" in result:
        print(f"ERROR: {result['error']}", file=sys.stderr)
        sys.exit(1)
    print(json.dumps(result, indent=2))


def cmd_anthropic_export(args):
    """Export to Anthropic managed-agents format (export_for_anthropic, Pro)."""
    db = _session_database(args)
    try:
        payload = db.anthropic_export_payload(
            project=getattr(args, "project", None),
            days_back=args.days_back,
        )
    finally:
        db.close()

    if "error" in payload:
        print(f"ERROR: {payload['error']}", file=sys.stderr)
        sys.exit(1)

    data = payload["data"]
    if args.output:
        Path(args.output).expanduser().write_text(data, encoding="utf-8")
        print(
            f"Exported {payload['entry_count']} session(s) to "
            f"{args.output} (anthropic-memory-v1)"
        )
    else:
        print(data)


# -- Related sessions / consolidation / digest / context (SH-101929/101930) --


def cmd_related(args):
    """Related-session discovery (get_related_sessions, Pro only)."""
    db = _session_database(args)
    try:
        result = db.related_sessions_payload(
            session_id=args.related_session_id,
            limit=args.related_limit,
            min_shared_terms=args.min_shared_terms,
        )
    finally:
        db.close()

    if "error" in result:
        print(f"ERROR: {result['error']}", file=sys.stderr)
        sys.exit(1)

    sessions = result.get("related", [])
    if not sessions:
        print(f"No related sessions found for {args.related_session_id}.")
        return
    print(
        f"{result['related_count']} related session(s) for "
        f"{args.related_session_id}:"
    )
    print()
    for s in sessions:
        print(f"[{s.get('start_date')}] ({s.get('surface', '')}) {s.get('title')}")
        print(f"  ID: {s.get('session_id')}")
        print(f"  link: {s.get('link_type')} (shared terms: {s.get('shared_term_count')})")
        preview = s.get("summary_preview") or ""
        if preview:
            print(f"  {preview}")
        print()


def cmd_consolidate(args):
    """Run memory consolidation for a project (consolidate_memories)."""
    db = _session_database(args)
    try:
        result = db.consolidate_memories_payload(
            project=args.project,
            surface=getattr(args, "surface", None),
            max_sessions=args.max_sessions,
            dedup=args.dedup,
        )
    finally:
        db.close()
    print(json.dumps(result, indent=2))


def cmd_digest(args):
    """Print the current memory digest (get_memory_digest)."""
    db = _session_database(args)
    try:
        disable = True if args.digest_disable else (False if args.digest_enable else None)
        result = db.memory_digest_payload(
            project=args.project,
            surface=getattr(args, "surface", None),
            disable=disable,
            max_tokens=args.max_tokens,
        )
    finally:
        db.close()
    if result["status"] == "no_digest":
        print(f"No memory digest for project '{args.project}' "
              f"(surface {getattr(args, 'surface', None)}).", file=sys.stderr)
        sys.exit(1)
    print(result["digest_markdown"])


def cmd_context_for(args):
    """Print session context for a topic (get_context_for)."""
    db = _session_database(args)
    try:
        results = db.context_for_payload(
            topic=args.context_topic,
            max_results=args.max_results,
            include_external=args.include_external,
            semantic=args.semantic,
        )
    finally:
        db.close()

    if not results:
        print(f"No context found for topic '{args.context_topic}'.")
        return
    print(f"{len(results)} context result(s) for '{args.context_topic}':")
    print()
    for r in results:
        print(f"[{r['date']}] {r['session_title']}")
        print(f"  match: {r['match_score']:.2f}")
        if r["summary"]:
            print(f"  {r['summary']}")
        for d in (r["decisions"] or []):
            print(f"  decision: {d}")
        for q in (r["open_questions"] or []):
            print(f"  open: {q}")
        print()


# -- Structured memory items: decisions/questions/artifacts (SH-102285) --

# -- Session lifecycle ops (SH-102688) --


def cmd_link_session(args):
    """Link two related sessions (link_sessions)."""
    db = _session_database(args)
    try:
        db.link_sessions(args.link_from, args.link_to, args.link_type)
    finally:
        db.close()
    print(f"Linked: {args.link_from} -> {args.link_to} (type: {args.link_type})")


def cmd_set_session_expiry(args):
    """Set or clear session expiry (set_session_expiry)."""
    db = _session_database(args)
    try:
        result = db.set_session_expiry(args.expiry_session_id, args.expires_at)
    finally:
        db.close()
    if not result.get("ok"):
        print(
            f"ERROR: {result.get('code')}: {result.get('message')}",
            file=sys.stderr,
        )
        sys.exit(1)
    print(json.dumps(result, indent=2))


def cmd_pin_session(args):
    """Pin a session to exclude it from cleanup (set_keep_forever True)."""
    db = _session_database(args)
    try:
        found = db.set_keep_forever(args.pin_session_id, keep_forever=True)
    finally:
        db.close()
    if not found:
        print(f"ERROR: session not found: {args.pin_session_id}", file=sys.stderr)
        sys.exit(1)
    print(f"Pinned: {args.pin_session_id}")


def cmd_unpin_session(args):
    """Remove pin from a session (set_keep_forever False)."""
    db = _session_database(args)
    try:
        found = db.set_keep_forever(args.unpin_session_id, keep_forever=False)
    finally:
        db.close()
    if not found:
        print(f"ERROR: session not found: {args.unpin_session_id}", file=sys.stderr)
        sys.exit(1)
    print(f"Unpinned: {args.unpin_session_id}")


def cmd_tag_as_anti_pattern(args):
    """Mark a session as an anti-pattern (mark_anti_pattern)."""
    db = _session_database(args)
    try:
        result = db.mark_anti_pattern(
            args.anti_pattern_session_id,
            source=args.anti_pattern_source,
            reason=args.anti_pattern_reason,
        )
    finally:
        db.close()
    print(json.dumps({"status": result, "session_id": args.anti_pattern_session_id}))


def cmd_untag_anti_pattern(args):
    """Remove an anti-pattern tag (remove_anti_pattern)."""
    db = _session_database(args)
    try:
        result = db.remove_anti_pattern(
            args.anti_pattern_session_id,
            source=args.anti_pattern_source,
            reason=args.anti_pattern_reason,
        )
    finally:
        db.close()
    print(json.dumps({"status": result, "session_id": args.anti_pattern_session_id}))


def cmd_get_anti_patterns(args):
    """Retrieve anti-pattern sessions (get_anti_patterns)."""
    db = _session_database(args)
    try:
        result = db.get_anti_patterns(
            topic=getattr(args, "anti_pattern_topic", None),
            limit=args.limit,
            project=getattr(args, "project", None),
        )
    finally:
        db.close()
    print(json.dumps(result, indent=2))


def _parse_json_arg(raw, expected_type, flag_name):
    """Parse a JSON CLI argument, exiting with a clear error on failure.

    Returns None when raw is None (flag omitted) so callers can pass the
    result straight through to a SessionDatabase method's Optional param.
    """
    if raw is None:
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        print(f"ERROR: {flag_name} value is not valid JSON.", file=sys.stderr)
        sys.exit(1)
    if not isinstance(parsed, expected_type):
        print(f"ERROR: {flag_name} must be a JSON {expected_type.__name__}.", file=sys.stderr)
        sys.exit(1)
    return parsed


def _print_memory_item_result(result):
    """Print a memory-item op's dict result, hard-failing on ok=False."""
    if not result.get("ok", False):
        print(f"ERROR: {result.get('code')}: {result.get('message')}", file=sys.stderr)
        sys.exit(1)
    print(json.dumps(result, indent=2))


def cmd_save_memory_item(args):
    """Save a structured memory item: decision, open_question, or artifact (save_memory_item)."""
    tags = _parse_json_arg(args.memory_item_tags, list, "--memory-item-tags")
    metadata = _parse_json_arg(args.memory_item_metadata, dict, "--memory-item-metadata")

    db = _session_database(args)
    try:
        result = db.save_memory_item(
            item_type=args.memory_item_type,
            title=args.memory_item_title,
            body=args.memory_item_body,
            session_id=getattr(args, "session_id", None),
            project=args.project or "unspecified",
            tags=tags,
            metadata=metadata,
            external_id=args.memory_item_external_id,
            artifact_type=args.memory_item_artifact_type,
        )
    finally:
        db.close()
    _print_memory_item_result(result)


def cmd_query_memory_items(args):
    """Query structured memory items by type, project, status, and recency (query_memory_items)."""
    db = _session_database(args)
    try:
        result = db.query_memory_items(
            item_type=args.memory_item_type,
            project=args.project,
            status=args.memory_item_status,
            artifact_type=args.memory_item_artifact_type,
            days=args.memory_item_days,
            limit=args.memory_item_limit,
        )
    finally:
        db.close()
    _print_memory_item_result(result)


def cmd_transition_memory_item(args):
    """Move a memory item through its lifecycle (transition_memory_item)."""
    db = _session_database(args)
    try:
        result = db.transition_memory_item(
            item_id=args.memory_item_id,
            transition=args.memory_item_transition,
            reason=args.memory_item_reason,
            closing_session_id=args.closing_session_id,
        )
    finally:
        db.close()
    _print_memory_item_result(result)


def cmd_update_memory_item(args):
    """Correct a memory item's fields, or move it between projects (update_memory_item)."""
    tags = _parse_json_arg(args.memory_item_tags, list, "--memory-item-tags")
    metadata = _parse_json_arg(args.memory_item_metadata, dict, "--memory-item-metadata")

    db = _session_database(args)
    try:
        result = db.update_memory_item(
            item_id=args.memory_item_id,
            title=args.memory_item_title,
            body=args.memory_item_body,
            tags=tags,
            metadata=metadata,
            new_project=args.new_project,
            allow_project_change=args.allow_project_change,
        )
    finally:
        db.close()
    _print_memory_item_result(result)


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
    parser.add_argument("--semantic", action="store_true",
                        help="Use semantic (hybrid vector+keyword) search with --search. "
                             "Pro tier only; degrades to keyword search if unavailable.")

    # Observability mode flags (SH-101927)
    parser.add_argument("--skill-history", action="store_true",
                        help="List sessions that used --skill-name (get_skill_history)")
    parser.add_argument("--skill-name", type=str, dest="skill_name",
                        help="Skill name for --skill-history (e.g. 'hermes-agent')")
    parser.add_argument("--inspect", action="store_true",
                        help="List stored sessions with optional filters (inspect_sessions)")
    parser.add_argument("--since", type=str, dest="since",
                        help="With --inspect: only sessions on/after this date (YYYY-MM-DD)")
    parser.add_argument("--show-stats", action="store_true", dest="show_stats",
                        help="With --inspect: include aggregate counts")
    parser.add_argument("--stats", action="store_true",
                        help="Print the usage dashboard (get_stats)")
    parser.add_argument("--graph", action="store_true",
                        help="Print a Mermaid knowledge-graph (graph_session_map)")
    parser.add_argument("--graph-session-id", type=str, dest="graph_session_id",
                        help="With --graph: seed session UUID")
    parser.add_argument("--graph-project", type=str, dest="graph_project",
                        help="With --graph: seed project name")
    parser.add_argument("--depth", type=int, default=1,
                        help="With --graph: BFS depth (clamped 0-3, default 1)")
    parser.add_argument("--max-nodes", type=int, dest="max_nodes", default=60,
                        help="With --graph: node budget (clamped 1-200, default 60)")
    parser.add_argument("--dream-log", action="store_true",
                        help="Print consolidation log entries (get_dream_log)")
    parser.add_argument("--days", type=int, default=90,
                        help="With --skill-history: look-back window in days (default 90)")

    # Export/import mode flags (SH-101928)
    parser.add_argument("--export", action="store_true",
                        help="Export sessions as JSON/JSONL (export_sessions)")
    parser.add_argument("--import-file", type=str, dest="import_file",
                        help="Import sessions from an export file (import_sessions)")
    parser.add_argument("--on-conflict", type=str, dest="on_conflict",
                        choices=["skip", "replace"], default="skip",
                        help="With --import-file: 'skip' (default) or 'replace'")
    parser.add_argument("--dry-run", action="store_true", dest="dry_run",
                        help="With --import-file: validate without DB changes")
    parser.add_argument("--anthropic-export", action="store_true",
                        help="Export to Anthropic managed-agents format, Pro only "
                             "(export_for_anthropic)")
    parser.add_argument("--output", type=str, dest="output",
                        help="With --export/--anthropic-export: write to this file "
                             "instead of stdout")
    parser.add_argument("--format", type=str, dest="format",
                        choices=["json", "jsonl"], default="json",
                        help="With --export: output format (default json)")
    parser.add_argument("--days-back", type=int, dest="days_back", default=None,
                        help="With --export/--anthropic-export: limit to last N days")
    parser.add_argument("--export-limit", type=int, dest="export_limit", default=1000,
                        help="With --export: max sessions (default 1000)")

    # Related sessions / consolidation / digest / context flags (SH-101929/101930)
    parser.add_argument("--related", action="store_true",
                        help="Find sessions related to --related-session-id "
                             "(get_related_sessions, Pro only)")
    parser.add_argument("--related-session-id", type=str, dest="related_session_id",
                        help="With --related: seed session UUID")
    parser.add_argument("--related-limit", type=int, dest="related_limit", default=10,
                        help="With --related: max results (default 10, max 50)")
    parser.add_argument("--min-shared-terms", type=int, dest="min_shared_terms", default=3,
                        help="With --related: minimum shared keywords (default 3)")
    parser.add_argument("--consolidate", action="store_true",
                        help="Run memory consolidation for --project (consolidate_memories)")
    parser.add_argument("--max-sessions", type=int, dest="max_sessions", default=50,
                        help="With --consolidate: max sessions to analyze (default 50)")
    parser.add_argument("--dedup", type=str, dest="dedup", default=None,
                        choices=["off", "conservative", "balanced"],
                        help="With --consolidate: semantic dedup pass mode "
                             "(off default, conservative, balanced)")
    parser.add_argument("--digest", action="store_true",
                        help="Print the current memory digest for --project "
                             "(get_memory_digest)")
    parser.add_argument("--digest-disable", action="store_true", dest="digest_disable",
                        help="With --digest: set disabled=True on the digest")
    parser.add_argument("--digest-enable", action="store_true", dest="digest_enable",
                        help="With --digest: set disabled=False on the digest")
    parser.add_argument("--max-tokens", type=int, dest="max_tokens", default=2000,
                        help="With --digest: truncate markdown to this token "
                             "estimate (default 2000)")
    parser.add_argument("--context-for", action="store_true", dest="context_for",
                        help="Print session context for --context-topic "
                             "(get_context_for)")
    parser.add_argument("--context-topic", type=str, dest="context_topic",
                        help="With --context-for: the topic to find context for")
    parser.add_argument("--include-external", action="store_true", dest="include_external",
                        help="With --context-for: include external-tool sessions")
    parser.add_argument("--max-results", type=int, dest="max_results", default=5,
                        help="With --context-for: max excerpts (default 5)")

    # Structured memory item flags (SH-102285)
    parser.add_argument("--save-memory-item", action="store_true", dest="save_memory_item",
                        help="Save a decision/open_question/artifact (save_memory_item)")
    parser.add_argument("--query-memory-items", action="store_true", dest="query_memory_items",
                        help="Query structured memory items (query_memory_items)")
    parser.add_argument("--transition-memory-item", action="store_true", dest="transition_memory_item",
                        help="Move a memory item through its lifecycle (transition_memory_item)")
    parser.add_argument("--update-memory-item", action="store_true", dest="update_memory_item",
                        help="Correct a memory item's fields or move project (update_memory_item)")
    parser.add_argument("--memory-item-type", type=str, dest="memory_item_type",
                        choices=["decision", "open_question", "artifact"],
                        help="Item type for --save-memory-item/--query-memory-items")
    parser.add_argument("--memory-item-id", type=str, dest="memory_item_id",
                        help="Item id for --transition-memory-item/--update-memory-item")
    parser.add_argument("--memory-item-title", type=str, dest="memory_item_title",
                        help="Title for --save-memory-item/--update-memory-item")
    parser.add_argument("--memory-item-body", type=str, dest="memory_item_body",
                        help="Body text for --save-memory-item/--update-memory-item")
    parser.add_argument("--memory-item-tags", type=str, dest="memory_item_tags",
                        help="JSON list of tags for --save-memory-item/--update-memory-item")
    parser.add_argument("--memory-item-metadata", type=str, dest="memory_item_metadata",
                        help="JSON object of metadata for --save-memory-item/--update-memory-item")
    parser.add_argument("--memory-item-external-id", type=str, dest="memory_item_external_id",
                        help="Caller dedup key for --save-memory-item")
    parser.add_argument("--memory-item-artifact-type", type=str, dest="memory_item_artifact_type",
                        help="Artifact type for --save-memory-item (item_type=artifact), or "
                             "an artifact_type filter for --query-memory-items")
    parser.add_argument("--memory-item-status", type=str, dest="memory_item_status",
                        help="Status filter for --query-memory-items (e.g. active, open, retired)")
    parser.add_argument("--memory-item-days", type=int, dest="memory_item_days", default=None,
                        help="With --query-memory-items: only items created in the last N days")
    parser.add_argument("--memory-item-limit", type=int, dest="memory_item_limit", default=50,
                        help="With --query-memory-items: max rows to return (default 50, max 200)")
    parser.add_argument("--memory-item-transition", type=str, dest="memory_item_transition",
                        choices=["retire", "answer", "wont-answer"],
                        help="Transition for --transition-memory-item")
    parser.add_argument("--memory-item-reason", type=str, dest="memory_item_reason",
                        help="Optional reason recorded on close, with --transition-memory-item")
    parser.add_argument("--closing-session-id", type=str, dest="closing_session_id",
                        help="Session performing the transition, with --transition-memory-item")
    parser.add_argument("--new-project", type=str, dest="new_project",
                        help="Destination project, with --update-memory-item")
    parser.add_argument("--allow-project-change", action="store_true", dest="allow_project_change",
                        help="Required to actually move a memory item between projects, "
                             "with --update-memory-item")

    # Session lifecycle flags (SH-102688)
    parser.add_argument("--link-session", action="store_true", dest="link_session",
                        help="Link two sessions (link_sessions)")
    parser.add_argument("--link-from", type=str, dest="link_from",
                        help="With --link-session: source session ID")
    parser.add_argument("--link-to", type=str, dest="link_to",
                        help="With --link-session: target session ID")
    parser.add_argument("--link-type", type=str, dest="link_type", default="continues",
                        help="With --link-session: relationship type (default continues)")
    parser.add_argument("--set-session-expiry", action="store_true", dest="set_session_expiry",
                        help="Set or clear session expiry (set_session_expiry)")
    parser.add_argument("--expiry-session-id", type=str, dest="expiry_session_id",
                        help="With --set-session-expiry: session ID")
    parser.add_argument("--expires-at", type=str, dest="expires_at", default=None,
                        help="With --set-session-expiry: ISO 8601 timestamp or 'clear' to remove")
    parser.add_argument("--pin-session", action="store_true", dest="pin_session",
                        help="Pin a session to exclude from cleanup (set_keep_forever True)")
    parser.add_argument("--pin-session-id", type=str, dest="pin_session_id",
                        help="With --pin-session: session ID")
    parser.add_argument("--unpin-session", action="store_true", dest="unpin_session",
                        help="Remove pin from a session (set_keep_forever False)")
    parser.add_argument("--unpin-session-id", type=str, dest="unpin_session_id",
                        help="With --unpin-session: session ID")
    parser.add_argument("--tag-as-anti-pattern", action="store_true", dest="tag_as_anti_pattern",
                        help="Mark a session as anti-pattern (mark_anti_pattern)")
    parser.add_argument("--untag-anti-pattern", action="store_true", dest="untag_anti_pattern",
                        help="Remove anti-pattern tag (remove_anti_pattern)")
    parser.add_argument("--get-anti-patterns", action="store_true", dest="get_anti_patterns",
                        help="Retrieve anti-pattern sessions (get_anti_patterns)")
    parser.add_argument("--anti-pattern-session-id", type=str, dest="anti_pattern_session_id",
                        help="With --tag-as-anti-pattern/--untag-anti-pattern: session ID")
    parser.add_argument("--anti-pattern-source", type=str, dest="anti_pattern_source",
                        default="unknown",
                        help="With --tag-as-anti-pattern/--untag-anti-pattern: attribution source")
    parser.add_argument("--anti-pattern-reason", type=str, dest="anti_pattern_reason",
                        default="",
                        help="With --tag-as-anti-pattern/--untag-anti-pattern: reason")
    parser.add_argument("--anti-pattern-topic", type=str, dest="anti_pattern_topic",
                        default=None,
                        help="With --get-anti-patterns: optional topic filter")

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

    if args.skill_history:
        if not args.skill_name:
            parser.error("--skill-history requires --skill-name")
        skill_history(args)
    elif args.inspect:
        cmd_inspect(args)
    elif args.stats:
        cmd_stats(args)
    elif args.graph:
        cmd_graph(args)
    elif args.dream_log:
        cmd_dream_log(args)
    elif args.export:
        cmd_export(args)
    elif args.import_file:
        cmd_import(args)
    elif args.anthropic_export:
        cmd_anthropic_export(args)
    elif args.related:
        if not args.related_session_id:
            parser.error("--related requires --related-session-id")
        cmd_related(args)
    elif args.consolidate:
        if not args.project:
            parser.error("--consolidate requires --project")
        cmd_consolidate(args)
    elif args.digest:
        if not args.project:
            parser.error("--digest requires --project")
        cmd_digest(args)
    elif args.context_for:
        if not args.context_topic:
            parser.error("--context-for requires --context-topic")
        cmd_context_for(args)
    elif args.save_memory_item:
        if not args.memory_item_type or not args.memory_item_title:
            parser.error("--save-memory-item requires --memory-item-type and --memory-item-title")
        cmd_save_memory_item(args)
    elif args.query_memory_items:
        cmd_query_memory_items(args)
    elif args.transition_memory_item:
        if not args.memory_item_id or not args.memory_item_transition:
            parser.error("--transition-memory-item requires --memory-item-id and --memory-item-transition")
        cmd_transition_memory_item(args)
    elif args.update_memory_item:
        if not args.memory_item_id:
            parser.error("--update-memory-item requires --memory-item-id")
        cmd_update_memory_item(args)
    elif args.link_session:
        if not args.link_from or not args.link_to:
            parser.error("--link-session requires --link-from and --link-to")
        cmd_link_session(args)
    elif args.set_session_expiry:
        if not args.expiry_session_id:
            parser.error("--set-session-expiry requires --expiry-session-id")
        cmd_set_session_expiry(args)
    elif args.pin_session:
        if not args.pin_session_id:
            parser.error("--pin-session requires --pin-session-id")
        cmd_pin_session(args)
    elif args.unpin_session:
        if not args.unpin_session_id:
            parser.error("--unpin-session requires --unpin-session-id")
        cmd_unpin_session(args)
    elif args.tag_as_anti_pattern:
        if not args.anti_pattern_session_id:
            parser.error("--tag-as-anti-pattern requires --anti-pattern-session-id")
        cmd_tag_as_anti_pattern(args)
    elif args.untag_anti_pattern:
        if not args.anti_pattern_session_id:
            parser.error("--untag-anti-pattern requires --anti-pattern-session-id")
        cmd_untag_anti_pattern(args)
    elif args.get_anti_patterns:
        cmd_get_anti_patterns(args)
    elif args.read_id:
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
