"""LoreConvo storage core -- stdlib-only module for database connections.

Imports only stdlib modules so hooks can import it without pulling in
config, hybrid_search, or models. Every database connection path must
go through _open_conn() so WAL, busy_timeout, foreign_keys=ON, and
file permissions stay consistent.

This module is the single source of truth for DDL constants, schema
revision, connection opening, schema initialization, and session
upsert. database.py imports from here and re-exports _open_conn so
no existing caller changes.
"""

import logging
import os
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)

# Schema revision -- increment on any DDL change.
# Used as PRAGMA user_version for cross-environment compatibility gating.
SCHEMA_REVISION = 1

# ---------------------------------------------------------------------------
# DDL constants
# ---------------------------------------------------------------------------

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS sessions (
    id              TEXT PRIMARY KEY NOT NULL,
    title           TEXT NOT NULL,
    surface         TEXT NOT NULL,
    project         TEXT,
    start_date      TEXT NOT NULL,
    end_date        TEXT,
    summary         TEXT,
    decisions       TEXT,
    artifacts       TEXT,
    open_questions  TEXT,
    tags            TEXT,
    created_at      TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    source          TEXT DEFAULT 'session',
    external_tool_session INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS session_skills (
    session_id       TEXT NOT NULL REFERENCES sessions(id),
    skill_name       TEXT NOT NULL,
    skill_source     TEXT,
    invocation_count INTEGER DEFAULT 1,
    PRIMARY KEY (session_id, skill_name)
);

CREATE TABLE IF NOT EXISTS projects (
    name            TEXT PRIMARY KEY,
    description     TEXT,
    expected_skills TEXT,
    default_persona TEXT,
    instructions    TEXT,
    created_at      TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE TABLE IF NOT EXISTS persona_sessions (
    persona_name    TEXT NOT NULL,
    session_id      TEXT NOT NULL REFERENCES sessions(id),
    relevance_note  TEXT,
    PRIMARY KEY (persona_name, session_id)
);

CREATE TABLE IF NOT EXISTS session_links (
    from_session_id TEXT NOT NULL REFERENCES sessions(id),
    to_session_id   TEXT NOT NULL REFERENCES sessions(id),
    link_type       TEXT DEFAULT 'continues',
    PRIMARY KEY (from_session_id, to_session_id)
);

CREATE INDEX IF NOT EXISTS idx_sessions_start_date ON sessions(start_date);
CREATE INDEX IF NOT EXISTS idx_sessions_project ON sessions(project);
CREATE INDEX IF NOT EXISTS idx_persona_sessions_name ON persona_sessions(persona_name);

CREATE TABLE IF NOT EXISTS session_cooccurrences (
    term       TEXT NOT NULL,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    frequency  INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (term, session_id)
);

CREATE INDEX IF NOT EXISTS idx_cooccurrences_session ON session_cooccurrences(session_id);
CREATE INDEX IF NOT EXISTS idx_cooccurrences_term ON session_cooccurrences(term);

CREATE TABLE IF NOT EXISTS project_instruction_audit (
    id              TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    project_name    TEXT NOT NULL REFERENCES projects(name),
    session_id      TEXT,
    changed_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    old_value       TEXT,
    new_value       TEXT
);

CREATE INDEX IF NOT EXISTS idx_project_instruction_audit_project ON project_instruction_audit(project_name);
CREATE INDEX IF NOT EXISTS idx_project_instruction_audit_date ON project_instruction_audit(changed_at);
"""

DREAMING_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS memory_digests (
    id              TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    project         TEXT NOT NULL,
    surface         TEXT,
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    source_count    INTEGER DEFAULT 0,
    oldest_session_date TEXT,
    newest_session_date TEXT,
    decisions       TEXT,
    open_questions  TEXT,
    known_stack     TEXT,
    stale_facts     TEXT,
    digest_markdown TEXT,
    mode            TEXT DEFAULT 'heuristic',
    tier            TEXT DEFAULT 'free',
    disabled        INTEGER DEFAULT 0,
    api_key_found   INTEGER DEFAULT 1,
    UNIQUE(project, surface)
);
"""

FTS_SQL = """
CREATE VIRTUAL TABLE IF NOT EXISTS sessions_fts USING fts5(
    title, summary, decisions, tags, open_questions, reasoning_notes,
    content=sessions, content_rowid=rowid
);
"""

FTS_TRIGGERS = """
CREATE TRIGGER IF NOT EXISTS sessions_ai AFTER INSERT ON sessions BEGIN
    INSERT INTO sessions_fts(rowid, title, summary, decisions, tags, open_questions, reasoning_notes)
    VALUES (new.rowid, new.title, new.summary, new.decisions, new.tags, new.open_questions, new.reasoning_notes);
END;

-- sessions_fts is an EXTERNAL-CONTENT table (content=sessions). Rows must be
-- removed with the special 'delete' command carrying the OLD column values --
-- a plain UPDATE/DELETE corrupts the index (SH-13438). Do not "simplify" these
-- back to ordinary DML.
CREATE TRIGGER IF NOT EXISTS sessions_au AFTER UPDATE ON sessions BEGIN
    INSERT INTO sessions_fts(sessions_fts, rowid, title, summary, decisions,
        tags, open_questions, reasoning_notes)
    VALUES ('delete', old.rowid, old.title, old.summary, old.decisions,
        old.tags, old.open_questions, old.reasoning_notes);
    INSERT INTO sessions_fts(rowid, title, summary, decisions, tags,
        open_questions, reasoning_notes)
    VALUES (new.rowid, new.title, new.summary, new.decisions, new.tags,
        new.open_questions, new.reasoning_notes);
END;

CREATE TRIGGER IF NOT EXISTS sessions_ad AFTER DELETE ON sessions BEGIN
    INSERT INTO sessions_fts(sessions_fts, rowid, title, summary, decisions,
        tags, open_questions, reasoning_notes)
    VALUES ('delete', old.rowid, old.title, old.summary, old.decisions,
        old.tags, old.open_questions, old.reasoning_notes);
END;
"""

ANTI_PATTERN_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS anti_pattern_sessions (
    session_id TEXT NOT NULL,
    tagged_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    source     TEXT NOT NULL DEFAULT 'unknown',
    PRIMARY KEY (session_id),
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_anti_pattern_tagged_at
    ON anti_pattern_sessions (tagged_at DESC);

CREATE TABLE IF NOT EXISTS anti_pattern_audit_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT NOT NULL,
    action      TEXT NOT NULL CHECK(action IN ('tag', 'untag')),
    source      TEXT NOT NULL DEFAULT 'unknown',
    reason      TEXT,
    occurred_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
CREATE INDEX IF NOT EXISTS idx_ap_audit_session
    ON anti_pattern_audit_log (session_id, occurred_at DESC);

CREATE TABLE IF NOT EXISTS anti_pattern_rate_state (
    operation    TEXT NOT NULL PRIMARY KEY,
    window_start TEXT NOT NULL,
    call_count   INTEGER NOT NULL DEFAULT 0
);
"""

# ---------------------------------------------------------------------------
# Connection management
# ---------------------------------------------------------------------------

def _is_in_memory_db(db_path) -> bool:
    """True for in-memory SQLite databases.

    In-memory databases cannot use WAL -- ``PRAGMA journal_mode=WAL`` always
    returns "memory" -- and there is no file for a second client to lock into a
    conflicting mode, so the WAL mixing guard does not apply to them. Used by
    tests (db_path=":memory:") and any in-memory URI form.
    """
    p = str(db_path)
    if p == ":memory:":
        return True
    if p.startswith("file:"):
        return ":memory:" in p or "mode=memory" in p
    return False


def _open_conn(db_path, busy_timeout_ms=10000) -> sqlite3.Connection:
    """Open a SQLite connection with all required pragmas for LoreConvo.

    Sets isolation_level=None (autocommit), row_factory=Row, WAL mode (with
    warning on filesystems that do not support WAL), busy_timeout (default
    10000ms for core, 2000ms for hooks), and foreign_keys=ON. All connection
    open paths must use this helper so FK enforcement is guaranteed on every
    connection.
    """
    conn = sqlite3.connect(str(db_path), isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute(f"PRAGMA busy_timeout={int(busy_timeout_ms)}")
    row = conn.execute("PRAGMA journal_mode=WAL").fetchone()
    actual_mode = row[0] if row else "unknown"
    if actual_mode != "wal" and not _is_in_memory_db(db_path):
        logger.warning(
            "Database at '%s' is in '%s' journal mode; WAL is unavailable "
            "on this filesystem (common with network mounts, FUSE, or "
            "filesystems without POSIX shared-memory). Falling back to "
            "'%s' mode. This process's own connection locking prevents "
            "intra-process conflicts, but if other processes open the "
            "same file with a different journal mode, corruption is "
            "possible.",
            db_path,
            actual_mode,
            actual_mode,
        )
    conn.execute("PRAGMA foreign_keys=ON")
    # sessions.db is created with umask-derived permissions (644 on standard 022
    # systems). Force 600 unconditionally so session data is never world-readable.
    # WAL sidecar files are chmod'd if they already exist; they are created lazily
    # by SQLite on first write and will be corrected on the next open.
    if not _is_in_memory_db(db_path):
        _p = str(db_path)
        if os.path.exists(_p):
            os.chmod(_p, 0o600)
        for _sidecar in (_p + '-shm', _p + '-wal'):
            if os.path.exists(_sidecar):
                os.chmod(_sidecar, 0o600)
    return conn


# ---------------------------------------------------------------------------
# Schema initialization
# ---------------------------------------------------------------------------

def ensure_schema(conn: sqlite3.Connection) -> None:
    """Run CREATE TABLE IF NOT EXISTS and stamp user_version.

    Idempotent -- safe to call on every connection open. Stamps
    PRAGMA user_version = SCHEMA_REVISION when the current value is
    lower (never downgrades).
    """
    conn.executescript(SCHEMA_SQL)
    row = conn.execute("PRAGMA user_version").fetchone()
    current = row[0] if row else 0
    if current < SCHEMA_REVISION:
        conn.execute(f"PRAGMA user_version = {SCHEMA_REVISION}")


# ---------------------------------------------------------------------------
# Session upsert -- single definition for all callers
# ---------------------------------------------------------------------------

def upsert_session(conn: sqlite3.Connection, session_id: str, title: str,
                   surface: str, project: str = None, start_date: str = None,
                   end_date: str = None, summary: str = None,
                   decisions: str = None, artifacts: str = None,
                   open_questions: str = None, tags: str = None,
                   source: str = "session",
                   external_tool_session: int = 0) -> None:
    """Insert or replace a session row.

    Uses INSERT OR REPLACE with the canonical column set. All callers
    (hooks, core, fallback script, summarizer) use this single definition
    so FK cascades, column defaults, and conflict resolution are uniform.
    """
    conn.execute(
        """INSERT OR REPLACE INTO sessions
           (id, title, surface, project, start_date, end_date,
            summary, decisions, artifacts, open_questions, tags,
            source, external_tool_session)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (session_id, title, surface, project, start_date, end_date,
         summary, decisions, artifacts, open_questions, tags,
         source, external_tool_session),
    )


# ---------------------------------------------------------------------------
# Permission remediation (no SQLite connection -- os.stat + os.chmod only)
# ---------------------------------------------------------------------------

def remediate_permissions(data_dir: str) -> None:
    """Fix permissions on the data directory and database files.

    Stats the data directory, sessions.db, and any -wal/-shm sidecars.
    Chmods to 0700 (directory) or 0600 (files) when the current mode is
    wider. Logs once per process which files were corrected.

    Opens no SQLite connection, takes no database lock, and is safe to
    run concurrently with anything including an active writer.
    """
    data_path = Path(data_dir)
    files_to_check = [data_path]
    db_path = data_path / "sessions.db"
    if db_path.exists():
        files_to_check.append(db_path)
        for sidecar in (str(db_path) + '-shm', str(db_path) + '-wal'):
            sp = Path(sidecar)
            if sp.exists():
                files_to_check.append(sp)

    for path in files_to_check:
        try:
            st = path.stat()
            current_mode = st.st_mode & 0o777
            if path.is_dir():
                target_mode = 0o700
            else:
                target_mode = 0o600
            if current_mode != target_mode:
                os.chmod(path, target_mode)
                logger.info(
                    "remediate_permissions: corrected %s from 0%o to 0%o",
                    path, current_mode, target_mode,
                )
        except OSError:
            pass  # best-effort; log at debug if needed
