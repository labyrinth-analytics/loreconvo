"""One-shot migration: rewrite non-standard session surface values to "code".

SH-107094 (decision from SH-106851, option 1). SH-106842 made surface
validation live, so sessions whose surface is not in ALLOWED_SURFACES can no
longer be updated. This rewrites every such value to "code". Values already
valid are never touched. Agent attribution is lossy by design: sessions carry
agent:<name> tags.

Usage (dry run is the default and writes nothing):
    python scripts/migrate_surfaces.py [--db PATH]
    python scripts/migrate_surfaces.py --apply --backup-dir DIR [--db PATH]

The allowed set is imported from server.ALLOWED_SURFACES, never restated.
A real run takes a timestamped backup first and refuses to write if the
backup is missing or does not verify.
"""

import argparse
import os
import sqlite3
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from server import ALLOWED_SURFACES  # noqa: E402

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
    src = sqlite3.connect(db_path)
    dst = sqlite3.connect(dest)
    try:
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
    conn = sqlite3.connect(db_path)
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
