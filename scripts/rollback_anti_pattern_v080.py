"""Rollback script for LoreConvo anti-pattern storage v0.8.0.

Removes the three anti-pattern tables and optionally the PID lockfile.
Usage: python3 rollback_anti_pattern_v080.py path/to/sessions.db

IMPORTANT: Stop the LoreConvo server before running this script.
The script checks for a running server and aborts if one is detected.
"""
import os
import sys
import sqlite3
from pathlib import Path


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 rollback_anti_pattern_v080.py path/to/sessions.db")
        sys.exit(1)

    db_path = sys.argv[1]
    pid_lock = Path.home() / ".loreconvo" / "server.pid"

    # Check for a live server before touching the lockfile
    if pid_lock.exists():
        try:
            existing_pid = int(pid_lock.read_text().strip())
            os.kill(existing_pid, 0)
            print(
                f"ERROR: LoreConvo server (PID {existing_pid}) appears to be running. "
                f"Stop it before rolling back.",
                file=sys.stderr,
            )
            sys.exit(1)
        except (ValueError, OSError):
            pass  # process dead -- safe to proceed

    conn = sqlite3.connect(db_path, isolation_level=None)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")

    conn.execute("BEGIN IMMEDIATE")
    try:
        # Remove r1 artifacts (idempotent -- IF EXISTS guards)
        conn.execute("DROP INDEX IF EXISTS idx_sessions_antipattern_like")
        conn.execute("DROP INDEX IF EXISTS idx_sessions_tags_antipattern")

        # Remove v0.8.0 tables
        conn.execute("DROP TABLE IF EXISTS anti_pattern_sessions")
        conn.execute("DROP TABLE IF EXISTS anti_pattern_audit_log")
        conn.execute("DROP TABLE IF EXISTS anti_pattern_rate_state")

        # Clean log entries -- guard against schema_migration_log not existing
        sml_exists = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migration_log'"
        ).fetchone()
        if sml_exists:
            has_col = any(
                row[1] == 'migration_name'
                for row in conn.execute("PRAGMA table_info(schema_migration_log)")
            )
            if has_col:
                conn.execute(
                    "DELETE FROM schema_migration_log WHERE migration_name LIKE 'anti_pattern%'"
                )

        conn.execute("COMMIT")
        print("Rollback complete.")
    except Exception as exc:
        conn.execute("ROLLBACK")
        print(f"Rollback FAILED: {exc}. Database state unchanged.", file=sys.stderr)
        sys.exit(1)
    finally:
        conn.close()

    # Remove PID lockfile if it exists (server is confirmed dead at this point)
    try:
        pid_lock.unlink()
    except OSError:
        pass


if __name__ == "__main__":
    main()
