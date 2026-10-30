"""Maintenance command: scan LoreConvo's SQLite store for secret-shaped text
written before write-path redaction (SH-105603) existed, and redact it in
place.

    loreconvo-scan-secrets              # dry-run (default): counts only
    loreconvo-scan-secrets --apply      # redact in place

Scope: sessions.{title,summary,decisions,artifacts,open_questions,
reasoning_notes,previous_summary} and memory_items.{title,body,metadata}.
Uses the same canonical patterns as the write path (scripts/lib/
secret_redaction.py, via the generated product copy) -- one definition of
"secret-shaped", applied going forward by the write path and retroactively
by this command.

--apply takes BEGIN EXCLUSIVE, which in WAL mode blocks other readers too
(unlike BEGIN IMMEDIATE, which only blocks other writers) -- no concurrent
session should observe a half-redacted store [r4/mg-H1]. If the lock can't
be acquired, this fails closed: nonzero exit, no changes [r4/mg-H2]. All
rows are redacted in a single transaction; any row-level error aborts the
whole run with no partial changes [r4/mg-H3]. After COMMIT, PRAGMA
wal_checkpoint(TRUNCATE) folds the WAL back into the main file and VACUUM
reclaims the space freed by shrinking redacted text.

Output is counts only -- rows touched and matches redacted per column --
never the matched text or any field contents [r4/sec-H7, sec-C1].

Finding a secret in the store means it was already exposed (to backups,
other readers, this scan's own process memory) before this command ran.
Redacting the database does not undo that exposure -- rotate every
credential a run reports as redacted.
"""
import argparse
import json
import os
import shutil
import sqlite3
import sys

from .config import Config
from .secret_redaction import redact_secrets, redact_value
from .storage_core import _open_conn

_SESSION_TEXT_COLUMNS = ["title", "summary", "reasoning_notes", "previous_summary"]
_SESSION_LIST_COLUMNS = ["decisions", "artifacts", "open_questions"]
_MEMORY_TEXT_COLUMNS = ["title", "body"]
_MEMORY_DICT_COLUMNS = ["metadata"]


def _redact_text_columns(row, columns):
    """Return ({column: new_value}, match_count) for plain-text columns."""
    updates = {}
    total = 0
    for col in columns:
        value = row[col]
        if not value:
            continue
        new_value, n = redact_secrets(value)
        if n:
            updates[col] = new_value
            total += n
    return updates, total


def _redact_json_list_columns(row, columns):
    """Return ({column: new_json}, match_count) for JSON-list text columns.

    A column whose stored text is not valid JSON is left untouched -- this
    scan redacts secret-shaped text, it does not repair malformed data.
    """
    updates = {}
    total = 0
    for col in columns:
        raw = row[col]
        if not raw:
            continue
        try:
            items = json.loads(raw)
        except (TypeError, ValueError):
            continue
        new_items, n = redact_value(items)
        if n:
            updates[col] = json.dumps(new_items)
            total += n
    return updates, total


def _redact_json_dict_columns(row, columns):
    """Return ({column: new_json}, match_count) for JSON-dict text columns.

    Dict keys are untouched (field names, not values) [r4/dm-H1]."""
    updates = {}
    total = 0
    for col in columns:
        raw = row[col]
        if not raw:
            continue
        try:
            value = json.loads(raw)
        except (TypeError, ValueError):
            continue
        new_value, n = redact_value(value)
        if n:
            updates[col] = json.dumps(new_value)
            total += n
    return updates, total


def _apply_updates(conn, table, row_id, updates):
    set_clause = ", ".join(f"{col} = ?" for col in updates)
    conn.execute(
        f"UPDATE {table} SET {set_clause} WHERE id = ?",
        (*updates.values(), row_id),
    )


def _scan(conn, apply: bool) -> dict:
    """Scan sessions + memory_items; redact in place when apply=True.

    Raises on any row-level failure so the caller can roll back the whole
    transaction -- this function never leaves partial changes itself.
    """
    counts = {
        "sessions_scanned": 0, "sessions_redacted": 0,
        "memory_items_scanned": 0, "memory_items_redacted": 0,
        "matches_total": 0,
    }

    session_rows = conn.execute(
        "SELECT id, title, summary, decisions, artifacts, open_questions, "
        "reasoning_notes, previous_summary FROM sessions"
    ).fetchall()
    counts["sessions_scanned"] = len(session_rows)
    for row in session_rows:
        text_updates, text_n = _redact_text_columns(row, _SESSION_TEXT_COLUMNS)
        list_updates, list_n = _redact_json_list_columns(row, _SESSION_LIST_COLUMNS)
        updates = {**text_updates, **list_updates}
        n = text_n + list_n
        if not updates:
            continue
        counts["sessions_redacted"] += 1
        counts["matches_total"] += n
        if apply:
            _apply_updates(conn, "sessions", row["id"], updates)

    item_rows = conn.execute(
        "SELECT id, title, body, metadata FROM memory_items"
    ).fetchall()
    counts["memory_items_scanned"] = len(item_rows)
    for row in item_rows:
        text_updates, text_n = _redact_text_columns(row, _MEMORY_TEXT_COLUMNS)
        dict_updates, dict_n = _redact_json_dict_columns(row, _MEMORY_DICT_COLUMNS)
        updates = {**text_updates, **dict_updates}
        n = text_n + dict_n
        if not updates:
            continue
        counts["memory_items_redacted"] += 1
        counts["matches_total"] += n
        if apply:
            _apply_updates(conn, "memory_items", row["id"], updates)

    return counts


def _check_disk_space(db_path: str):
    """VACUUM rewrites the whole database file; it needs roughly the
    file's current size again in free space on the same filesystem.
    Returns (ok, message)."""
    try:
        db_size = os.path.getsize(db_path)
    except OSError:
        return True, ""
    directory = os.path.dirname(db_path) or "."
    free = shutil.disk_usage(directory).free
    if free < db_size:
        return False, (
            f"insufficient free disk space for VACUUM: {free} bytes free "
            f"on {directory}, database is {db_size} bytes (VACUUM needs "
            "roughly the database's current size again in free space)."
        )
    return True, ""


def _print_counts(counts: dict, applied: bool) -> None:
    verb = "redacted" if applied else "would redact"
    print(f"sessions scanned: {counts['sessions_scanned']}")
    print(f"sessions {verb}: {counts['sessions_redacted']}")
    print(f"memory_items scanned: {counts['memory_items_scanned']}")
    print(f"memory_items {verb}: {counts['memory_items_redacted']}")
    print(f"matches {verb} total: {counts['matches_total']}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="loreconvo-scan-secrets",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=(
            "Scan LoreConvo's SQLite store for secret-shaped text written "
            "before write-path redaction (SH-105603) and redact it in "
            "place. Dry-run by default: reports counts only and changes "
            "nothing. Pass --apply to redact.\n\n"
            "Disk precondition for --apply: VACUUM rewrites the whole "
            "database file, so it needs roughly the file's current size "
            "again in free space on the same filesystem. This command "
            "checks before starting and fails closed (no changes) if "
            "there isn't enough room.\n\n"
            "Rotation guidance: this command removes secret-shaped text "
            "from the store, but it does not undo any exposure that "
            "already happened (backups, prior reads, replication). "
            "Rotate every credential a run reports as redacted."
        ),
    )
    parser.add_argument(
        "--db-path", default=None,
        help="Path to sessions.db (default: discovered the same way the server does)",
    )
    parser.add_argument(
        "--apply", action="store_true",
        help="Redact in place (default: dry-run, counts only, no changes)",
    )
    args = parser.parse_args(argv)

    db_path = args.db_path or Config().db_path
    if not os.path.exists(db_path):
        print(f"[FAIL] no database found at {db_path}")
        return 1

    if args.apply:
        ok, msg = _check_disk_space(db_path)
        if not ok:
            print(f"[FAIL] {msg} No changes made.")
            return 1

    conn = _open_conn(db_path, busy_timeout_ms=10000)
    try:
        if args.apply:
            try:
                conn.execute("BEGIN EXCLUSIVE")
            except sqlite3.OperationalError as exc:
                print(f"[FAIL] could not acquire exclusive lock ({exc}). No changes made.")
                return 1
            try:
                counts = _scan(conn, apply=True)
            except Exception as exc:
                conn.execute("ROLLBACK")
                print(f"[FAIL] redaction aborted ({exc}). No changes made.")
                return 1
            conn.execute("COMMIT")
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            conn.execute("VACUUM")
        else:
            counts = _scan(conn, apply=False)
    finally:
        conn.close()

    _print_counts(counts, applied=args.apply)
    if args.apply and counts["matches_total"]:
        print(
            "\nRotation guidance: the text redacted above was stored "
            "unredacted before this control existed. Redacting the "
            "database does not undo that exposure -- rotate every "
            "credential it matched."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
