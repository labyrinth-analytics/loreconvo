"""One-shot migration: rewrite non-standard session surface values to "code".

SH-107094 (decision from SH-106851, option 1). SH-106842 made surface
validation live, so sessions whose surface is not in ALLOWED_SURFACES can no
longer be updated. This rewrites every such value to "code". Values already
valid are never touched. Agent attribution is lossy by design: sessions carry
agent:<name> tags.

Usage (dry run is the default and writes nothing):
    python scripts/migrate_surfaces.py [--db PATH]
    python scripts/migrate_surfaces.py --apply --backup-dir DIR [--db PATH]

The allowed set is imported from storage_core.ALLOWED_SURFACES, never restated.
A real run takes a timestamped backup first and refuses to write if the
backup is missing or does not verify.
"""

import argparse
import importlib.util
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

# Resolve storage_core through the single hook bootstrap -- no sys.path
# mutation and no importing the FastMCP server module. ALLOWED_SURFACES and
# the connection opener both come from storage_core, the same source the MCP
# server validates against (SH-107153).
_BOOTSTRAP_PATH = (
    Path(__file__).resolve().parent.parent / "hooks" / "scripts" / "_bootstrap.py"
)
_bootstrap_spec = importlib.util.spec_from_file_location(
    "_loreconvo_bootstrap", str(_BOOTSTRAP_PATH)
)
_bootstrap = importlib.util.module_from_spec(_bootstrap_spec)
_bootstrap_spec.loader.exec_module(_bootstrap)

# clear_breadcrumb=False: a one-shot migration command must not erase the
# hook_failure.json marker that records a broken HOOK save (SH-105345).
try:
    _storage = _bootstrap.resolve_storage_core(Path(__file__), clear_breadcrumb=False)
except _bootstrap.BootstrapError as exc:
    print("ERROR: %s" % exc, file=sys.stderr)
    sys.exit(1)

_open_conn = _storage._open_conn
ALLOWED_SURFACES = _storage.ALLOWED_SURFACES

TARGET_SURFACE = "code"
DEFAULT_DB = os.path.join(os.path.expanduser("~"), ".loreconvo", "sessions.db")


def count_nonstandard(conn):
    """Return {old_surface: row_count} for every surface outside ALLOWED_SURFACES."""
    marks = ",".join("?" for _ in ALLOWED_SURFACES)
    rows = conn.execute(
        "SELECT surface, COUNT(*) FROM sessions "
        "WHERE surface IS NULL OR surface NOT IN (%s) "
        "GROUP BY surface ORDER BY COUNT(*) DESC" % marks,
        tuple(ALLOWED_SURFACES),
    ).fetchall()
    return {r[0]: r[1] for r in rows}


def backup_database(db_path, backup_dir):
    """Write a timestamped, verified copy of db_path into backup_dir. Return its path."""
    os.makedirs(backup_dir, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = os.path.join(backup_dir, "sessions_pre_surface_migrate_%s.db" % stamp)
    src = _open_conn(db_path)
    # The online backup needs a plain destination handle, not a WAL-mode
    # store (same rationale as database.py's backfill backup).
    dst = sqlite3.connect(dest)  # ddl-guard: allow
    try:
        os.chmod(dest, 0o600)
        src.backup(dst)
        n_src = src.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        n_dst = dst.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
    finally:
        dst.close()
        src.close()
    if not os.path.isfile(dest) or n_src != n_dst:
        raise RuntimeError("backup verification failed (%s vs %s rows): %s" % (n_src, n_dst, dest))
    return dest


def migrate_surfaces(db_path, apply=False, backup_dir=None):
    """Rewrite non-standard surfaces to TARGET_SURFACE.

    Dry run (apply=False): returns the counts, writes nothing.
    Real run: backup_dir is mandatory; the backup is taken and verified
    before the first write. Returns a dict with counts, rewritten rows and
    the backup path. Idempotent: a second run rewrites 0 rows.
    """
    conn = _open_conn(db_path)
    try:
        counts = count_nonstandard(conn)
        result = {"counts": counts, "rewritten": 0, "backup": None}
        if not apply:
            return result
        if not backup_dir:
            raise ValueError("refusing to run: apply requires backup_dir")
        if not counts:
            return result
        result["backup"] = backup_database(db_path, backup_dir)
        marks = ",".join("?" for _ in ALLOWED_SURFACES)
        with conn:
            cur = conn.execute(
                "UPDATE sessions SET surface = ? "
                "WHERE surface IS NULL OR surface NOT IN (%s)" % marks,
                (TARGET_SURFACE,) + tuple(ALLOWED_SURFACES),
            )
        result["rewritten"] = cur.rowcount
        return result
    finally:
        conn.close()


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--db", default=DEFAULT_DB)
    p.add_argument("--apply", action="store_true", help="write changes (default: dry run)")
    p.add_argument("--backup-dir", help="required with --apply")
    args = p.parse_args(argv)

    if not os.path.isfile(args.db):
        print("[FAIL] database not found: %s" % args.db)
        return 2
    try:
        res = migrate_surfaces(args.db, apply=args.apply, backup_dir=args.backup_dir)
    except (ValueError, RuntimeError) as exc:
        print("[FAIL] %s" % exc)
        return 2

    print("%s: %s" % ("APPLY" if args.apply else "DRY RUN", args.db))
    for old, n in res["counts"].items():
        print("  %r -> %r: %d" % (old, TARGET_SURFACE, n))
    print("  total non-standard: %d" % sum(res["counts"].values()))
    if args.apply:
        print("  backup: %s" % res["backup"])
        print("  rewritten: %d" % res["rewritten"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
