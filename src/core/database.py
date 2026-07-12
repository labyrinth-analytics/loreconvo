"""SQLite database operations with FTS5 search."""

import calendar
import hashlib
import json
import logging
import os
import re
import socket
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional

from .config import Config
from .hybrid_search import SEARCH_HALF_LIFE_DAYS, AUTOLOAD_HALF_LIFE_DAYS
from .models import (
    PersonaTag, Project, SearchResult, Session, SessionLink, SkillUsage
)

logger = logging.getLogger(__name__)

# DDL constants for keep_forever schema components.
# Used for both creation (slow path) and body validation (fast path).
_CREATE_TRIGGER_SQL = (
    "CREATE TRIGGER prevent_delete_pinned_sessions "
    "BEFORE DELETE ON sessions "
    "WHEN old.keep_forever = 1 "
    "BEGIN "
    "SELECT RAISE(ABORT, "
    "'LORECONVO_PINNED_SESSION: Cannot delete a pinned session. "
    "Unpin with set_keep_forever(id, False) before deleting.'); "
    "END"
)
_CREATE_SESSIONS_PRUNABLE_VIEW_SQL = (
    "CREATE VIEW sessions_prunable AS "
    "SELECT * FROM sessions WHERE keep_forever = 0"
)
_CREATE_SESSIONS_PRUNABLE_DELETE_SQL = (
    "CREATE TRIGGER sessions_prunable_delete "
    "INSTEAD OF DELETE ON sessions_prunable "
    "BEGIN "
    "DELETE FROM sessions WHERE id = OLD.id AND keep_forever = 0; "
    "END"
)


def _create_keep_forever_index(conn: sqlite3.Connection) -> None:
    """Create partial index on keep_forever if SQLite >= 3.9.0, full index otherwise."""
    version = tuple(
        int(x) for x in
        conn.execute("SELECT sqlite_version()").fetchone()[0].split(".")
    )
    if version >= (3, 9, 0):
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_sessions_keep_forever "
            "ON sessions(keep_forever) WHERE keep_forever = 1"
        )
    else:
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_sessions_keep_forever "
            "ON sessions(keep_forever)"
        )


def _pinning_enabled(db) -> bool:
    """Return False if session pinning is disabled via env var or config file.

    Tier 1: LORECONVO_DISABLE_PINNING env var (any non-empty value disables).
    Tier 2: ~/.loreconvo/config.json with {"pinning_enabled": false}.
    """
    if os.environ.get("LORECONVO_DISABLE_PINNING"):
        return False
    config_path = Path(db.config.db_path).parent / "config.json"
    if config_path.exists():
        try:
            import json as _json
            cfg = _json.loads(config_path.read_text(encoding="utf-8"))
            if cfg.get("pinning_enabled") is False:
                return False
        except Exception:
            pass  # malformed config -> pinning remains enabled (safe default)
    return True


def parse_session_id(raw: str) -> tuple:
    """Return (session_id, None) on success or (None, error_dict) on failure.

    Validates UUID format and canonicalizes to lowercase.
    SQL injection is prevented by parameterized queries in all callers.
    """
    import uuid as _uuid
    if not isinstance(raw, str) or not raw.strip():
        return None, {
            "ok": False,
            "code": "invalid_session_id",
            "message": "session_id must be a non-empty string.",
        }
    raw = raw.strip().lower()
    try:
        _uuid.UUID(raw)
    except ValueError:
        return None, {
            "ok": False,
            "code": "invalid_session_id",
            "message": "session_id must be a valid UUID (xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx).",
        }
    return raw, None


def _check_shared_environment_warning() -> None:
    """Warn if running over SSH on a shared account (unsupported trust model)."""
    if os.environ.get("LORECONVO_SKIP_SSH_WARN"):
        return
    ssh_indicators = ("SSH_CLIENT", "SSH_TTY", "SSH_CONNECTION")
    if any(os.environ.get(k) for k in ssh_indicators):
        logger.warning(
            "LoreConvo is running over an SSH connection. If this host has "
            "multiple OS users sharing an account, the trust model (OS user = "
            "sole authorized user) does not hold. Shared-account SSH environments "
            "are not a supported configuration. Set LORECONVO_SKIP_SSH_WARN=1 "
            "to suppress this warning."
        )


def _check_network_filesystem_warning(db_path: str) -> None:
    """Warn if sessions.db appears to be on a network filesystem."""
    if os.environ.get("LORECONVO_SKIP_NETWORK_FS_WARN"):
        return
    path = str(db_path)
    network_prefixes = ("/Volumes/", "/net/", "/mnt/smb", "/mnt/nfs",
                        "/media/nfs", "//")
    if any(path.startswith(p) for p in network_prefixes):
        logger.warning(
            "sessions.db path '%s' appears to be on a network filesystem. "
            "chmod 600 does not prevent access by root-level backup agents "
            "or NFS/SMB servers. Move sessions.db to local storage if this "
            "is a concern. Set LORECONVO_SKIP_NETWORK_FS_WARN=1 to suppress.",
            path
        )


_IMPORT_FIELD_CAPS = {
    "title": 500,
    "summary": 100_000,
    "list_item": 1_000,
}
_MAX_SESSIONS_PER_FILE = 10_000
_MAX_IMPORT_BYTES = 50 * 1024 * 1024  # 50 MB
_INTERNAL_SOURCES = ("file_memory", "periodic")

_TAG_RATE_WINDOW = 60.0   # seconds per rate-limit window
_TAG_RATE_MAX = 20        # max tag_as_anti_pattern calls per window

_STOPWORDS = frozenset({
    "a", "about", "after", "again", "ago", "all", "also", "an", "and",
    "any", "are", "as", "at", "be", "been", "being", "but", "by", "can",
    "could", "did", "do", "does", "done", "down", "during", "each",
    "either", "every", "few", "for", "from", "get", "got", "had", "has",
    "have", "he", "her", "here", "him", "his", "how", "i", "if", "in",
    "into", "is", "it", "its", "just", "like", "may", "me", "more",
    "most", "my", "neither", "new", "no", "nor", "not", "now", "of",
    "off", "on", "once", "only", "or", "other", "our", "out", "over",
    "own", "per", "run", "s", "set", "she", "so", "some", "such", "t",
    "than", "that", "the", "their", "them", "then", "there", "these",
    "they", "this", "those", "through", "to", "too", "under", "up",
    "use", "used", "was", "we", "were", "what", "when", "where", "which",
    "while", "who", "will", "with", "would", "yet", "you", "your",
})


class SessionLimitReachedError(Exception):
    """Raised when the free-tier session limit is reached.

    The BSL 1.1 Additional Use Grant allows personal/non-commercial use
    up to 50 sessions. Exceeding this requires a Pro license.
    """
    pass

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

CREATE TRIGGER IF NOT EXISTS sessions_au AFTER UPDATE ON sessions BEGIN
    UPDATE sessions_fts SET title = new.title, summary = new.summary,
        decisions = new.decisions, tags = new.tags,
        open_questions = new.open_questions,
        reasoning_notes = new.reasoning_notes WHERE rowid = old.rowid;
END;

CREATE TRIGGER IF NOT EXISTS sessions_ad AFTER DELETE ON sessions BEGIN
    DELETE FROM sessions_fts WHERE rowid = old.rowid;
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


def _open_conn(db_path) -> sqlite3.Connection:
    """Open a SQLite connection with all required pragmas for LoreConvo.

    Sets isolation_level=None (autocommit), row_factory=Row, WAL mode (with
    warning on filesystems that do not support WAL), busy_timeout=10000ms,
    and foreign_keys=ON. All connection open paths must use this helper so FK
    enforcement is guaranteed on every connection.
    """
    conn = sqlite3.connect(str(db_path), isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=10000")
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


def _validate_anti_pattern_schema(conn: sqlite3.Connection) -> None:
    """Validate anti_pattern_sessions schema at startup. Raises RuntimeError on mismatch.

    Checks column presence, PRIMARY KEY structure, FK existence, and FK enforcement.
    Called after CREATE TABLE IF NOT EXISTS so a fresh database always passes.
    """
    EXPECTED_COLS = {"session_id": "TEXT", "tagged_at": "TEXT", "source": "TEXT"}
    cols_info = conn.execute("PRAGMA table_info(anti_pattern_sessions)").fetchall()
    actual_by_name = {row[1]: row for row in cols_info}

    for col in EXPECTED_COLS:
        if col not in actual_by_name:
            row_count = conn.execute(
                "SELECT COUNT(*) FROM anti_pattern_sessions"
            ).fetchone()[0]
            backup_sql = (
                "CREATE TABLE anti_pattern_sessions_bak AS SELECT * FROM anti_pattern_sessions; "
                if row_count > 0 else "(table is empty -- safe to drop without backup)"
            )
            raise RuntimeError(
                f"anti_pattern_sessions schema mismatch: missing column '{col}'. "
                f"Found columns: {list(actual_by_name.keys())}. "
                f"Row count: {row_count}. "
                f"Backup if needed: {backup_sql} "
                f"Then: DROP TABLE anti_pattern_sessions; and restart."
            )

    pk_cols = [row[1] for row in cols_info if row[5] > 0]
    if pk_cols != ['session_id']:
        row_count = conn.execute(
            "SELECT COUNT(*) FROM anti_pattern_sessions"
        ).fetchone()[0]
        if row_count == 0:
            conn.execute("DROP TABLE anti_pattern_sessions")
            conn.executescript("""
                CREATE TABLE anti_pattern_sessions (
                    session_id TEXT NOT NULL,
                    tagged_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
                    source     TEXT NOT NULL DEFAULT 'unknown',
                    PRIMARY KEY (session_id),
                    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_anti_pattern_tagged_at
                    ON anti_pattern_sessions (tagged_at DESC);
            """)
            logger.warning("auto-migrated empty anti_pattern_sessions table to v0.8.0 schema")
            return
        raise RuntimeError(
            f"anti_pattern_sessions PRIMARY KEY mismatch. "
            f"Expected pk=['session_id'], got pk={pk_cols}. "
            f"Row count: {row_count}. "
            "Backup: CREATE TABLE anti_pattern_sessions_bak AS SELECT * FROM anti_pattern_sessions; "
            "DROP TABLE anti_pattern_sessions; then restart to recreate."
        )

    fk_list = conn.execute("PRAGMA foreign_key_list(anti_pattern_sessions)").fetchall()
    fk_cascade = [
        r for r in fk_list
        if r[2] == 'sessions' and r[3] == 'session_id'
        and r[4] == 'id' and r[6] == 'CASCADE'
    ]
    if not fk_cascade:
        row_count = conn.execute(
            "SELECT COUNT(*) FROM anti_pattern_sessions"
        ).fetchone()[0]
        if row_count == 0:
            conn.execute("DROP TABLE anti_pattern_sessions")
            conn.executescript("""
                CREATE TABLE anti_pattern_sessions (
                    session_id TEXT NOT NULL,
                    tagged_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
                    source     TEXT NOT NULL DEFAULT 'unknown',
                    PRIMARY KEY (session_id),
                    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_anti_pattern_tagged_at
                    ON anti_pattern_sessions (tagged_at DESC);
            """)
            logger.warning("auto-migrated empty anti_pattern_sessions table to v0.8.0 schema (FK)")
            return
        recreate_ddl = (
            "CREATE TABLE anti_pattern_sessions ("
            "session_id TEXT NOT NULL, "
            "tagged_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')), "
            "source TEXT NOT NULL DEFAULT 'unknown', "
            "PRIMARY KEY (session_id), "
            "FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE);"
        )
        backup_clause = (
            "Backup: CREATE TABLE anti_pattern_sessions_bak AS SELECT * FROM anti_pattern_sessions; "
            if row_count > 0 else "(table is empty -- safe to drop without backup) "
        )
        raise RuntimeError(
            "anti_pattern_sessions missing FOREIGN KEY to sessions(id) ON DELETE CASCADE. "
            f"Row count: {row_count}. "
            f"{backup_clause}"
            f"DROP TABLE anti_pattern_sessions; {recreate_ddl} then restart."
        )

    fk_status = conn.execute("PRAGMA foreign_keys").fetchone()
    if not fk_status or fk_status[0] != 1:
        raise RuntimeError(
            "PRAGMA foreign_keys = ON failed to take effect after _open_conn(). "
            "Check _open_conn() in database.py -- it must call "
            "conn.execute('PRAGMA foreign_keys = ON') before returning."
        )


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


class SessionDatabase:
    def __init__(self, config: Optional[Config] = None):
        self.config = config or Config()
        self.config.ensure_db_dir()
        # _open_conn() sets isolation_level=None, WAL, busy_timeout=10000,
        # foreign_keys=ON, check_same_thread=False, row_factory=Row.
        self.conn = _open_conn(self.config.db_path)
        # In-process write serialization for multi-statement mutations.
        self._write_lock = threading.Lock()
        self._lance_index = None  # lazy init; LanceIndex instance when Pro
        _check_shared_environment_warning()
        _check_network_filesystem_warning(str(self.config.db_path))
        self._init_schema()

    def _init_schema(self):
        self.conn.executescript(SCHEMA_SQL)
        self._migrate_fts_v2()
        self._migrate_add_source_column()
        self._migrate_add_team_memory_columns()
        self._migrate_add_external_tool_session_column()
        self._migrate_index_existing_cooccurrences()
        self._migrate_add_dreaming_columns()
        self._migrate_add_reasoning_notes_column()
        self._migrate_fts_v3()
        self._migrate_add_project_instructions_column()
        self._migrate_add_previous_summary_column()
        self._migrate_add_summary_source_columns()
        self._migrate_add_cross_product_columns()
        self._migrate_add_cascade_fks()
        self.conn.executescript(ANTI_PATTERN_SCHEMA_SQL)
        _validate_anti_pattern_schema(self.conn)
        self._sweep_anti_pattern_orphans()
        self._ensure_keep_forever_schema()
        # Migration: clean up any rows with NULL id (bug where raw SQL
        # inserts bypassed the Session dataclass UUID generation).
        null_rows = self.conn.execute(
            "SELECT rowid, title FROM sessions WHERE id IS NULL"
        ).fetchall()
        if null_rows:
            import uuid
            for row in null_rows:
                new_id = str(uuid.uuid4())
                self.conn.execute(
                    "UPDATE sessions SET id = ? WHERE rowid = ?",
                    (new_id, row['rowid'])
                )
            self.conn.commit()

    def _migrate_fts_v2(self):
        """Migrate FTS5 index to v2: add tags and open_questions columns.

        The original FTS5 table indexed only (title, summary, decisions).
        v2 adds (tags, open_questions) so searches match tag keywords and
        unresolved questions. This runs on every startup but only rebuilds
        once -- after that the IF NOT EXISTS in FTS_SQL is a no-op.
        """
        needs_rebuild = False
        try:
            cursor = self.conn.execute("SELECT * FROM sessions_fts LIMIT 0")
            col_names = [desc[0] for desc in cursor.description]
            if 'tags' not in col_names:
                needs_rebuild = True
        except sqlite3.OperationalError:
            # FTS table does not exist yet -- fresh install, just create it
            needs_rebuild = False
            self.conn.executescript(FTS_SQL)
            self.conn.executescript(FTS_TRIGGERS)
            return

        if not needs_rebuild:
            # Already on v2 schema -- ensure triggers exist (idempotent)
            self.conn.executescript(FTS_SQL)
            self.conn.executescript(FTS_TRIGGERS)
            return

        # --- Rebuild: drop old FTS table and triggers, recreate with v2 schema ---
        self.conn.executescript("""
            DROP TRIGGER IF EXISTS sessions_ai;
            DROP TRIGGER IF EXISTS sessions_au;
            DROP TRIGGER IF EXISTS sessions_ad;
            DROP TABLE IF EXISTS sessions_fts;
        """)

        # Create the new FTS5 table with expanded columns
        self.conn.executescript(FTS_SQL)

        # Repopulate from existing sessions
        self.conn.execute("""
            INSERT INTO sessions_fts(rowid, title, summary, decisions, tags, open_questions)
            SELECT rowid, title, summary, decisions, tags, open_questions
            FROM sessions
        """)

        # Recreate triggers for the new column set
        self.conn.executescript(FTS_TRIGGERS)

    def _migrate_add_source_column(self):
        """Add 'source' column to sessions table if not already present.

        Backward-compatible: existing rows default to 'session'.
        SQLite raises OperationalError on duplicate column add -- that's the
        signal that migration already ran.
        """
        try:
            self.conn.execute(
                "ALTER TABLE sessions ADD COLUMN source TEXT DEFAULT 'session'"
            )
        except sqlite3.OperationalError:
            pass  # column already exists

    def _migrate_add_team_memory_columns(self):
        """Add shared_by, origin_machine, content_hash columns for v0.4.0 team memory.

        Idempotent: each ALTER TABLE is wrapped in try/except for the duplicate-column
        OperationalError that SQLite raises when the column already exists.
        """
        for col_sql in (
            "ALTER TABLE sessions ADD COLUMN shared_by TEXT",
            "ALTER TABLE sessions ADD COLUMN origin_machine TEXT",
            "ALTER TABLE sessions ADD COLUMN content_hash TEXT",
        ):
            try:
                self.conn.execute(col_sql)
            except sqlite3.OperationalError:
                pass  # column already exists

    def _migrate_add_external_tool_session_column(self):
        """Add external_tool_session column for contamination control (RON-00115).

        Idempotent: wrapped in try/except for duplicate-column OperationalError.
        """
        try:
            self.conn.execute(
                "ALTER TABLE sessions ADD COLUMN external_tool_session INTEGER DEFAULT 0"
            )
        except sqlite3.OperationalError:
            pass  # column already exists

    def _migrate_add_reasoning_notes_column(self):
        """Add reasoning_notes column to sessions table if not already present.

        Idempotent: SQLite raises OperationalError on duplicate column add.
        """
        try:
            self.conn.execute(
                "ALTER TABLE sessions ADD COLUMN reasoning_notes TEXT"
            )
        except sqlite3.OperationalError:
            pass  # column already exists

    def _migrate_fts_v3(self):
        """Migrate FTS5 index to v3: add reasoning_notes column.

        Follows the same rebuild pattern as _migrate_fts_v2.
        Must be called after _migrate_add_reasoning_notes_column so the column exists.
        """
        needs_rebuild = False
        try:
            cursor = self.conn.execute("SELECT * FROM sessions_fts LIMIT 0")
            col_names = [desc[0] for desc in cursor.description]
            if 'reasoning_notes' not in col_names:
                needs_rebuild = True
        except sqlite3.OperationalError:
            needs_rebuild = False
            self.conn.executescript(FTS_SQL)
            self.conn.executescript(FTS_TRIGGERS)
            return

        if not needs_rebuild:
            self.conn.executescript(FTS_SQL)
            self.conn.executescript(FTS_TRIGGERS)
            return

        self.conn.executescript("""
            DROP TRIGGER IF EXISTS sessions_ai;
            DROP TRIGGER IF EXISTS sessions_au;
            DROP TRIGGER IF EXISTS sessions_ad;
            DROP TABLE IF EXISTS sessions_fts;
        """)
        self.conn.executescript(FTS_SQL)
        self.conn.execute("""
            INSERT INTO sessions_fts(rowid, title, summary, decisions, tags, open_questions, reasoning_notes)
            SELECT rowid, title, summary, decisions, tags, open_questions, reasoning_notes
            FROM sessions
        """)
        self.conn.executescript(FTS_TRIGGERS)

    def _migrate_add_dreaming_columns(self):
        """Add dreaming/recall columns and memory_digests table (v0.6.0).

        Idempotent: each ALTER TABLE is wrapped in try/except for the duplicate-column
        OperationalError that SQLite raises when the column already exists.
        """
        self.conn.executescript(DREAMING_SCHEMA_SQL)
        for col_sql in (
            "ALTER TABLE sessions ADD COLUMN expires_at TEXT",
            "ALTER TABLE sessions ADD COLUMN staleness_hint TEXT",
        ):
            try:
                self.conn.execute(col_sql)
            except sqlite3.OperationalError:
                pass  # column already exists

    def _migrate_add_project_instructions_column(self):
        """Add instructions TEXT column to projects table.

        Idempotent: wrapped in try/except for duplicate-column OperationalError.
        """
        try:
            self.conn.execute(
                "ALTER TABLE projects ADD COLUMN instructions TEXT"
            )
        except sqlite3.OperationalError:
            pass  # column already exists

    def _migrate_add_previous_summary_column(self):
        """Add previous_summary column for session version history (SH-10398).

        Idempotent: uses PRAGMA table_info to skip if column already exists.
        Not indexed in FTS5 -- audit field, not search field.
        """
        cols = {row[1] for row in self.conn.execute("PRAGMA table_info(sessions)")}
        if "previous_summary" not in cols:
            self.conn.execute(
                "ALTER TABLE sessions ADD COLUMN previous_summary TEXT"
            )
            self.conn.commit()

    def _migrate_add_summary_source_columns(self):
        """Add async summarization columns and support tables (SH-10723, v0.7.0).

        New sessions columns: summary_source, summary_retry_count, fallback_reason.
        New tables: cap_state (daily API call budget), schema_migration_log.

        summary_source values: heuristic, summary_pending, claude_api,
                               claude_async, permanently_heuristic
        Idempotent: column adds wrapped in try/except; tables use IF NOT EXISTS.
        """
        for col_sql in (
            "ALTER TABLE sessions ADD COLUMN summary_source TEXT DEFAULT 'heuristic'",
            "ALTER TABLE sessions ADD COLUMN summary_retry_count INTEGER DEFAULT 0",
            "ALTER TABLE sessions ADD COLUMN fallback_reason TEXT",
        ):
            try:
                self.conn.execute(col_sql)
            except sqlite3.OperationalError:
                pass  # column already exists

        # Backfill: existing rows with a summary are pre_migration_unknown.
        # Pre-v0.7.0 summaries may be LLM-quality (from v0.5.1 save_session(summarize=True))
        # or heuristic; we cannot distinguish reliably. Use 'pre_migration_unknown'
        # and do not re-summarize unless user explicitly upgrades via save_session(summarize=True).
        self.conn.execute(
            "UPDATE sessions SET summary_source='pre_migration_unknown' "
            "WHERE summary_source IS NULL AND summary IS NOT NULL"
        )

        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS cap_state (
                date            TEXT PRIMARY KEY,
                calls_today     INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS schema_migration_log (
                migration_name  TEXT PRIMARY KEY,
                applied_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
                from_version    TEXT,
                to_version      TEXT
            );
        """)

    def _migrate_add_cross_product_columns(self):
        """Add Phase 2b cross-product linking columns to sessions (SH-10727, v0.7.1).

        cross_link_opt_out: user can prevent this session from appearing in
          cross-product links (soft suppression; links are filtered, not deleted).
        last_cross_linked_at: debounce timestamp; save-triggered linking skips
          sessions cross-linked within the last 10 minutes.
        Both columns are idempotent (try/except on duplicate-column OperationalError).
        """
        for col_sql in (
            "ALTER TABLE sessions ADD COLUMN cross_link_opt_out INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE sessions ADD COLUMN last_cross_linked_at TEXT DEFAULT NULL",
        ):
            try:
                self.conn.execute(col_sql)
            except sqlite3.OperationalError:
                pass  # column already exists

    def _migrate_add_cascade_fks(self):
        """Add ON DELETE CASCADE to session_links, session_skills, persona_sessions (SH-12795).

        Without CASCADE, prune_expired_sessions() fails with FK constraint errors
        when linked/skilled sessions are deleted. This recreates those tables with
        CASCADE directives. Idempotent: checks if migration already applied by
        inspecting the table CREATE DDL for ON DELETE CASCADE.

        If orphaned rows exist (FK references to deleted sessions), they are cleaned
        up before migration to allow the new tables to be created with CASCADE.
        """
        try:
            result = self.conn.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name='session_links'"
            ).fetchone()
            if result and result[0] and 'ON DELETE CASCADE' in result[0]:
                logger.info("Migration already applied: session_links has ON DELETE CASCADE")
                return
        except Exception as e:
            logger.info(f"Error checking session_links migration status: {e}")

        try:
            logger.info("Starting migration to add ON DELETE CASCADE to foreign keys")

            logger.info("Cleaning up stale migration tables if present")
            self.conn.execute("DROP TABLE IF EXISTS session_links_new")
            self.conn.execute("DROP TABLE IF EXISTS session_skills_new")
            self.conn.execute("DROP TABLE IF EXISTS persona_sessions_new")

            logger.info("Cleaning up orphaned rows in session_links")
            self.conn.execute('''\
                DELETE FROM session_links
                WHERE from_session_id NOT IN (SELECT id FROM sessions)
                   OR to_session_id NOT IN (SELECT id FROM sessions)
            ''')

            logger.info("Cleaning up orphaned rows in session_skills")
            self.conn.execute('''\
                DELETE FROM session_skills
                WHERE session_id NOT IN (SELECT id FROM sessions)
            ''')

            logger.info("Cleaning up orphaned rows in persona_sessions")
            self.conn.execute('''\
                DELETE FROM persona_sessions
                WHERE session_id NOT IN (SELECT id FROM sessions)
            ''')

            logger.info("Creating new session_links table with CASCADE")
            self.conn.execute('''\
                CREATE TABLE session_links_new (
                    from_session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                    to_session_id   TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                    link_type       TEXT DEFAULT 'continues',
                    PRIMARY KEY (from_session_id, to_session_id)
                )
            ''')

            logger.info("Creating new session_skills table with CASCADE")
            self.conn.execute('''\
                CREATE TABLE session_skills_new (
                    session_id       TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                    skill_name       TEXT NOT NULL,
                    skill_source     TEXT,
                    invocation_count INTEGER DEFAULT 1,
                    PRIMARY KEY (session_id, skill_name)
                )
            ''')

            logger.info("Creating new persona_sessions table with CASCADE")
            self.conn.execute('''\
                CREATE TABLE persona_sessions_new (
                    persona_name    TEXT NOT NULL,
                    session_id      TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                    relevance_note  TEXT,
                    PRIMARY KEY (persona_name, session_id)
                )
            ''')

            logger.info("Copying data to session_links_new")
            self.conn.execute('''\
                INSERT INTO session_links_new
                SELECT from_session_id, to_session_id, link_type
                FROM session_links
            ''')

            logger.info("Copying data to session_skills_new")
            self.conn.execute('''\
                INSERT INTO session_skills_new
                SELECT session_id, skill_name, skill_source, invocation_count
                FROM session_skills
            ''')

            logger.info("Copying data to persona_sessions_new")
            self.conn.execute('''\
                INSERT INTO persona_sessions_new
                SELECT persona_name, session_id, relevance_note
                FROM persona_sessions
            ''')

            logger.info("Dropping old session_links table")
            self.conn.execute('DROP TABLE session_links')

            logger.info("Dropping old session_skills table")
            self.conn.execute('DROP TABLE session_skills')

            logger.info("Dropping old persona_sessions table")
            self.conn.execute('DROP TABLE persona_sessions')

            logger.info("Renaming session_links_new to session_links")
            self.conn.execute('ALTER TABLE session_links_new RENAME TO session_links')

            logger.info("Renaming session_skills_new to session_skills")
            self.conn.execute('ALTER TABLE session_skills_new RENAME TO session_skills')

            logger.info("Renaming persona_sessions_new to persona_sessions")
            self.conn.execute('ALTER TABLE persona_sessions_new RENAME TO persona_sessions')

            self.conn.commit()
            logger.info("Migration completed successfully: ON DELETE CASCADE applied")

        except Exception as e:
            self.conn.rollback()
            logger.error(f"Migration failed with error: {e}")
            raise

    # -- keep_forever / session pinning (v0.8.1) --

    def _keep_forever_schema_present(self) -> bool:
        """Quick read-only check: True only if all keep_forever schema components
        are present AND their bodies are valid.

        Called before acquiring the EXCLUSIVE lock to avoid blocking short-lived
        CLI invocations on every startup. Returns False on any error or body
        mismatch (triggers slow path).
        """
        try:
            rows = self.conn.execute("PRAGMA table_info(sessions)").fetchall()
            if not any(row[1] == "keep_forever" for row in rows):
                return False
            view_row = self.conn.execute(
                "SELECT sql FROM sqlite_master WHERE type='view' "
                "AND name='sessions_prunable'"
            ).fetchone()
            if not view_row:
                return False
            view_sql = view_row[0] or ""
            if "keep_forever" not in view_sql or "= 0" not in view_sql:
                return False
            bt_row = self.conn.execute(
                "SELECT sql FROM sqlite_master WHERE type='trigger' "
                "AND name='prevent_delete_pinned_sessions'"
            ).fetchone()
            if not bt_row:
                return False
            bt_sql = bt_row[0] or ""
            if "RAISE(ABORT" not in bt_sql or "LORECONVO_PINNED_SESSION" not in bt_sql:
                return False
            iodt_row = self.conn.execute(
                "SELECT sql FROM sqlite_master WHERE type='trigger' "
                "AND name='sessions_prunable_delete'"
            ).fetchone()
            if not iodt_row:
                return False
            iodt_sql = iodt_row[0] or ""
            if "keep_forever = 0" not in iodt_sql:
                return False
            return True
        except Exception:
            return False

    def _ensure_keep_forever_schema(self) -> None:
        """Ensure keep_forever column, view, index, and triggers exist. Idempotent.

        Fast path: if _keep_forever_schema_present() returns True, returns
        immediately without acquiring any lock.

        Slow path: acquires BEGIN EXCLUSIVE for DDL serialization. EXCLUSIVE
        failure raises RuntimeError immediately.
        """
        if self._keep_forever_schema_present():
            return
        saved_isolation = self.conn.isolation_level
        self.conn.isolation_level = None
        try:
            try:
                self.conn.execute("BEGIN EXCLUSIVE")
            except Exception as exc:
                raise RuntimeError(
                    "LoreConvo: keep_forever migration failed to acquire exclusive lock. "
                    "Another process may be holding the DB connection. "
                    "Recovery: ensure no other LoreConvo processes are running, then restart. "
                    "Path: " + str(self.config.db_path)
                ) from exc
            try:
                self._run_keep_forever_migration()
                self.conn.execute("COMMIT")
            except Exception:
                try:
                    self.conn.execute("ROLLBACK")
                except Exception:
                    pass
                raise
        finally:
            self.conn.isolation_level = saved_isolation

    def _run_keep_forever_migration(self) -> None:
        """Execute migration steps inside an already-open EXCLUSIVE transaction."""
        rows = list(self.conn.execute("PRAGMA table_info(sessions)"))
        if not rows:
            raise RuntimeError(
                "LoreConvo: sessions table not found. The database may be corrupted "
                "or not a LoreConvo database. "
                "Recovery: restore sessions.db from your most recent backup. "
                "Path: " + str(self.config.db_path)
            )
        try:
            self.conn.execute("SELECT COUNT(*) FROM sessions LIMIT 1").fetchone()
        except sqlite3.DatabaseError as exc:
            raise RuntimeError(
                "LoreConvo: sessions table is inaccessible despite table_info returning "
                "rows. The database may be partially corrupted. "
                "Recovery: restore sessions.db from your most recent backup. "
                "Path: " + str(self.config.db_path)
            ) from exc

        col_map = {row[1]: row for row in rows}
        if "keep_forever" not in col_map:
            self.conn.execute(
                "ALTER TABLE sessions ADD COLUMN keep_forever INTEGER NOT NULL DEFAULT 0"
            )
        else:
            row = col_map["keep_forever"]
            if row[2].upper() != "INTEGER":
                raise RuntimeError(
                    "LoreConvo: keep_forever column has type {!r} (expected INTEGER). "
                    "Schema modified by incompatible tool. "
                    "Recovery: (1) back up sessions.db, "
                    "(2) ALTER TABLE sessions RENAME COLUMN keep_forever TO keep_forever_old, "
                    "(3) ALTER TABLE sessions ADD COLUMN keep_forever INTEGER NOT NULL DEFAULT 0, "
                    "(4) UPDATE sessions SET keep_forever = "
                    "CASE WHEN typeof(keep_forever_old)='integer' "
                    "AND keep_forever_old IN (0,1) THEN keep_forever_old ELSE 0 END.".format(row[2])
                )
            if row[3] != 1 or str(row[4]).strip("'") != "0":
                logger.warning(
                    "keep_forever column has non-standard nullability=%s or default=%s; "
                    "expected NOT NULL DEFAULT 0. Values coerced to 0/1 by application code.",
                    row[3], row[4]
                )

        existing_indexes = {
            r[0] for r in self.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
            )
        }
        if "idx_sessions_keep_forever" not in existing_indexes:
            _create_keep_forever_index(self.conn)

        trigger_row = self.conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='trigger' "
            "AND name='prevent_delete_pinned_sessions'"
        ).fetchone()
        if trigger_row is None:
            self.conn.execute(_CREATE_TRIGGER_SQL)
        else:
            sql_body = trigger_row[0] or ""
            if "RAISE(ABORT" not in sql_body or "LORECONVO_PINNED_SESSION" not in sql_body:
                logger.warning(
                    "Trigger prevent_delete_pinned_sessions has unexpected body; recreating."
                )
                self.conn.execute("DROP TRIGGER prevent_delete_pinned_sessions")
                self.conn.execute(_CREATE_TRIGGER_SQL)

        view_row = self.conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='view' AND name='sessions_prunable'"
        ).fetchone()
        if view_row is None:
            self.conn.execute(_CREATE_SESSIONS_PRUNABLE_VIEW_SQL)
        else:
            view_sql = view_row[0] or ""
            if "keep_forever" not in view_sql or "= 0" not in view_sql:
                logger.warning(
                    "sessions_prunable view has unexpected body; recreating."
                )
                self.conn.execute("DROP TRIGGER IF EXISTS sessions_prunable_delete")
                self.conn.execute("DROP VIEW sessions_prunable")
                self.conn.execute(_CREATE_SESSIONS_PRUNABLE_VIEW_SQL)

        del_trigger_row = self.conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='trigger' "
            "AND name='sessions_prunable_delete'"
        ).fetchone()
        if del_trigger_row is None:
            self.conn.execute(_CREATE_SESSIONS_PRUNABLE_DELETE_SQL)
        else:
            del_sql = del_trigger_row[0] or ""
            if "keep_forever = 0" not in del_sql:
                logger.warning(
                    "sessions_prunable_delete trigger has unexpected body; recreating."
                )
                self.conn.execute("DROP TRIGGER sessions_prunable_delete")
                self.conn.execute(_CREATE_SESSIONS_PRUNABLE_DELETE_SQL)

        row = self.conn.execute(
            "SELECT COUNT(*) FROM sessions WHERE keep_forever=1"
        ).fetchone()
        pinned_count = row[0] if row else 0
        logger.info("keep_forever schema ready; %d session(s) pinned.", pinned_count)

    def set_keep_forever(self, session_id: str, keep_forever: bool) -> bool:
        """Set or clear keep_forever on a session. Returns False if not found.

        When pinning: clears expires_at atomically in the same UPDATE.
        When unpinning: leaves expires_at unchanged.
        """
        with self.conn:
            if keep_forever:
                cursor = self.conn.execute(
                    "UPDATE sessions SET keep_forever=1, expires_at=NULL WHERE id=?",
                    (session_id,),
                )
            else:
                cursor = self.conn.execute(
                    "UPDATE sessions SET keep_forever=0 WHERE id=?",
                    (session_id,),
                )
        return cursor.rowcount > 0

    def prune_expired_sessions(self, cutoff_ts: str) -> int:
        """Delete sessions with expires_at < cutoff_ts, excluding pinned. Returns count deleted.

        INSTEAD OF triggers on views do not update cursor.rowcount on the originating
        DELETE, so we must count rows before deletion to get the accurate count.
        """
        before = self.conn.execute(
            "SELECT COUNT(*) FROM sessions_prunable WHERE expires_at < ?", (cutoff_ts,)
        ).fetchone()[0]
        with self.conn:
            self.conn.execute(
                "DELETE FROM sessions_prunable WHERE expires_at < ?", (cutoff_ts,)
            )
        if before == 0:
            logger.debug(
                "prune_expired_sessions: 0 rows deleted before %s "
                "(no expired unpinned sessions, or all matching sessions are pinned).",
                cutoff_ts
            )
        return before

    # -- Anti-pattern storage (v0.8.0) --

    @contextmanager
    def _write_context(self):
        """Structural write-lock context manager. ALL mutations MUST use this.

        Acquires self._write_lock and yields self.conn. Does not manage
        transactions -- callers issue BEGIN IMMEDIATE / COMMIT / ROLLBACK
        explicitly (required for cross-process serialization via SQLite WAL).
        Read-only SELECT calls do NOT use this context manager.
        """
        with self._write_lock:
            yield self.conn

    def _sweep_anti_pattern_orphans(self):
        """Startup fallback: remove orphaned anti_pattern_sessions rows.

        Called after _ensure_schema. Safe to run repeatedly; no-op when all
        rows have matching sessions entries. Logs a warning with the count if
        any orphans are removed (indicates prior FK enforcement gap).
        """
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            self.conn.execute("""
                DELETE FROM anti_pattern_sessions
                WHERE session_id NOT IN (SELECT id FROM sessions)
            """)
            orphan_count = self.conn.execute("SELECT changes()").fetchone()[0]
            self.conn.execute("COMMIT")
        except Exception:
            self.conn.execute("ROLLBACK")
            raise

        if orphan_count > 0:
            logger.warning(
                "Startup sweep removed %d orphaned anti_pattern_sessions rows. "
                "PRAGMA foreign_keys may not have been enforced on all prior connections. "
                "Verify _open_conn() is used for every connection in database.py.",
                orphan_count,
            )

    def _check_rate_limit_db(self, conn) -> bool:
        """DB-backed rate limit check. Called inside an open BEGIN IMMEDIATE transaction.

        Returns True if the call is within the rate limit, False if exceeded.
        Caller must already hold _write_lock (via _write_context).
        """
        import time as _time
        now = _time.time()
        now_iso = _time.strftime('%Y-%m-%dT%H:%M:%SZ', _time.gmtime(now))

        row = conn.execute(
            "SELECT window_start, call_count FROM anti_pattern_rate_state WHERE operation = 'tag'"
        ).fetchone()

        if row is None:
            conn.execute(
                "INSERT INTO anti_pattern_rate_state (operation, window_start, call_count) "
                "VALUES ('tag', ?, 1)",
                (now_iso,)
            )
            return True

        try:
            window_start_ts = calendar.timegm(
                _time.strptime(row[0], '%Y-%m-%dT%H:%M:%SZ')
            )
        except ValueError:
            logger.warning(
                "anti_pattern_rate_state: malformed window_start %r, resetting rate window",
                row[0],
            )
            window_start_ts = now - _TAG_RATE_WINDOW - 1

        if now - window_start_ts > _TAG_RATE_WINDOW:
            conn.execute(
                "UPDATE anti_pattern_rate_state SET window_start = ?, call_count = 1 "
                "WHERE operation = 'tag'",
                (now_iso,)
            )
            return True

        if row[1] >= _TAG_RATE_MAX:
            return False

        conn.execute(
            "UPDATE anti_pattern_rate_state SET call_count = call_count + 1 "
            "WHERE operation = 'tag'"
        )
        return True

    def mark_anti_pattern(self, session_id: str,
                           source: str = "unknown",
                           reason: str = "") -> str:
        """Mark a session as an anti-pattern. Idempotent.

        Returns 'added' or 'already_present'. Writes an audit log row on every call.

        Raises:
            ValueError: on invalid session_id format.
            LookupError: if session does not exist.
            RuntimeError: if rate limit exceeded (use str(exc) for the error message).
        """
        if not isinstance(session_id, str) or not session_id.strip() or len(session_id) > 255:
            raise ValueError("Invalid session_id: must be a non-empty string <= 255 chars")

        source = (source or "unknown").strip()[:128]
        reason = (reason or "").strip()[:500]

        with self._write_context() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                if not self._check_rate_limit_db(conn):
                    conn.execute("ROLLBACK")
                    raise RuntimeError("rate_limit_exceeded: tag_as_anti_pattern")

                row = conn.execute(
                    "SELECT id FROM sessions WHERE id = ?", (session_id,)
                ).fetchone()
                if row is None:
                    conn.execute("ROLLBACK")
                    raise LookupError(f"Session not found: {session_id}")

                conn.execute(
                    "INSERT OR IGNORE INTO anti_pattern_sessions (session_id, source) VALUES (?, ?)",
                    (session_id, source)
                )
                # Capture changes() immediately after INSERT OR IGNORE, before audit INSERT
                changes = conn.execute("SELECT changes()").fetchone()[0]

                conn.execute(
                    "INSERT INTO anti_pattern_audit_log (session_id, action, source, reason) "
                    "VALUES (?, 'tag', ?, ?)",
                    (session_id, source, reason or None)
                )
                conn.execute("COMMIT")
            except (LookupError, RuntimeError):
                raise
            except Exception:
                conn.execute("ROLLBACK")
                raise

        return "added" if changes else "already_present"

    def remove_anti_pattern(self, session_id: str,
                             source: str = "unknown",
                             reason: str = "") -> str:
        """Remove an anti-pattern tag from a session. Idempotent.

        Returns 'removed' or 'not_present'. Writes an audit log row only on
        successful removal (no-op path skips audit).

        Raises:
            ValueError: on invalid session_id format.
        """
        if not isinstance(session_id, str) or not session_id.strip() or len(session_id) > 255:
            raise ValueError("Invalid session_id: must be a non-empty string <= 255 chars")

        source = (source or "unknown").strip()[:128]
        reason = (reason or "").strip()[:500]

        with self._write_context() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                conn.execute(
                    "DELETE FROM anti_pattern_sessions WHERE session_id = ?",
                    (session_id,)
                )
                changes = conn.execute("SELECT changes()").fetchone()[0]

                if changes > 0:
                    conn.execute(
                        "INSERT INTO anti_pattern_audit_log (session_id, action, source, reason) "
                        "VALUES (?, 'untag', ?, ?)",
                        (session_id, source, reason or None)
                    )
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise

        return "removed" if changes else "not_present"

    def _migrate_index_existing_cooccurrences(self):
        """Populate session_cooccurrences for existing sessions on first run.

        Idempotent: only runs when the table is empty, indicating first install
        of this schema version. Subsequent startups skip the work.
        Skips rows with NULL id (legacy migration artifact).
        """
        count = self.conn.execute(
            "SELECT COUNT(*) FROM session_cooccurrences"
        ).fetchone()[0]
        if count > 0:
            return  # already indexed

        rows = self.conn.execute(
            "SELECT id, summary, decisions, project, tags FROM sessions WHERE id IS NOT NULL"
        ).fetchall()
        for row in rows:
            self._index_session_cooccurrences(
                row[0], row[1], row[2], row[3], row[4]
            )

    @staticmethod
    def _extract_keywords(text: str, top_n: int = 30) -> List[tuple]:
        """Extract top-N keywords from text using simple term frequency.

        Returns list of (term, frequency) tuples sorted descending by frequency.
        Only includes tokens of 3+ characters not in the stopword list.
        """
        if not text:
            return []
        tokens = re.findall(r'[a-z]{3,}', text.lower())
        counts: dict = {}
        for token in tokens:
            if token not in _STOPWORDS:
                counts[token] = counts.get(token, 0) + 1
        return sorted(counts.items(), key=lambda x: x[1], reverse=True)[:top_n]

    def _index_session_cooccurrences(
        self,
        session_id: str,
        summary: Optional[str],
        decisions_json: Optional[str],
        project: Optional[str],
        tags_json: Optional[str],
    ) -> None:
        """Index keyword co-occurrences for a session.

        Extracts keywords from summary, decisions, project, and tags.
        Stores results in session_cooccurrences, replacing any prior index
        for this session (idempotent for re-saves).
        """
        self.conn.execute(
            "DELETE FROM session_cooccurrences WHERE session_id = ?",
            (session_id,)
        )

        parts: List[str] = []
        if summary:
            parts.append(summary)
        if decisions_json:
            try:
                decisions = json.loads(decisions_json)
                if isinstance(decisions, list):
                    parts.extend(str(d) for d in decisions)
            except (json.JSONDecodeError, TypeError):
                parts.append(str(decisions_json))
        if project:
            parts.append(project)

        text = " ".join(parts)
        keywords = self._extract_keywords(text)
        for term, freq in keywords:
            self.conn.execute(
                "INSERT OR REPLACE INTO session_cooccurrences (term, session_id, frequency) "
                "VALUES (?, ?, ?)",
                (term, session_id, freq)
            )

        # Boost tags as explicit terms (frequency 5 to weight them above noise)
        if tags_json:
            try:
                tags = json.loads(tags_json)
                if isinstance(tags, list):
                    for tag in tags:
                        if isinstance(tag, str):
                            tag_term = re.sub(r'[^a-z]', '', tag.lower())
                            if len(tag_term) >= 3 and tag_term not in _STOPWORDS:
                                self.conn.execute(
                                    "INSERT OR REPLACE INTO session_cooccurrences "
                                    "(term, session_id, frequency) VALUES (?, ?, ?)",
                                    (tag_term, session_id, 5)
                                )
            except (json.JSONDecodeError, TypeError):
                pass

    def _auto_link_cooccurrences(self, session_id: str, min_shared_terms: int = 3) -> None:
        """Create auto-links for sessions sharing >= min_shared_terms terms.

        Links are stored in session_links with link_type='auto:cooccurrence'.
        Uses INSERT OR IGNORE so manual links are never overwritten.
        Caps at 20 new links per session to avoid link explosion.
        """
        candidates = self.conn.execute(
            """SELECT sc2.session_id, COUNT(*) as shared_count
               FROM session_cooccurrences sc1
               JOIN session_cooccurrences sc2 ON sc1.term = sc2.term
               WHERE sc1.session_id = ?
                 AND sc2.session_id != ?
               GROUP BY sc2.session_id
               HAVING COUNT(*) >= ?
               ORDER BY shared_count DESC
               LIMIT 20""",
            (session_id, session_id, min_shared_terms)
        ).fetchall()

        for row in candidates:
            other_id = row[0]
            self.conn.execute(
                "INSERT OR IGNORE INTO session_links "
                "(from_session_id, to_session_id, link_type) VALUES (?, ?, 'auto:cooccurrence')",
                (session_id, other_id)
            )

    # -- Phase 2a: Embedding auto-link (Pro tier) --

    def _auto_link_embeddings(self, session: "Session", cap: int = 10) -> None:
        """Create bidirectional embedding-based links for a just-saved session.

        Same-project scoping enforced. Bidirectional pairs are skipped if EITHER
        direction already has any link type. Circuit breaker suppresses repeated
        Lance failures without failing the save. Pro tier only.
        """
        from . import embedding_circuit as _circ
        if not self.config.is_pro:
            return
        if os.environ.get("LORECONVO_EMBEDDING_LINKS", "1") == "0":
            return
        project = session.project or ""
        if not _circ.check_circuit(project):
            return
        try:
            lance = self._get_lance_index()
            table = lance._open_table()
            query_text = f"{session.title} {session.summary or ''}"
            q_vec = lance._get_model().encode(query_text).tolist()
            raw = table.search(
                q_vec,
                vector_column_name="vector",
                query_type="vector",
            ).limit(25).to_list()

            # Filter: distance <= 0.707 (cosine >= 0.75), same project, not self
            candidates = [
                r["session_id"] for r in raw
                if r.get("_distance", 999) <= 0.707
                and r.get("session_id") != session.id
                and r.get("project") == project
            ]

            inserted = 0
            for other_id in candidates:
                if inserted >= cap:
                    break
                existing = self.conn.execute(
                    "SELECT 1 FROM session_links WHERE "
                    "(from_session_id=? AND to_session_id=?) OR "
                    "(from_session_id=? AND to_session_id=?)",
                    (session.id, other_id, other_id, session.id)
                ).fetchone()
                if existing:
                    continue
                self.conn.execute(
                    "INSERT OR IGNORE INTO session_links "
                    "(from_session_id, to_session_id, link_type) "
                    "VALUES (?, ?, 'auto:embedding')",
                    (session.id, other_id)
                )
                self.conn.execute(
                    "INSERT OR IGNORE INTO session_links "
                    "(from_session_id, to_session_id, link_type) "
                    "VALUES (?, ?, 'auto:embedding')",
                    (other_id, session.id)
                )
                inserted += 1
            self.conn.commit()
            _circ.record_success(project)
        except Exception as exc:
            _circ.record_failure(project)
            import logging as _log
            _log.getLogger(__name__).error(
                "auto_link_embeddings failed for session %s: %s", session.id, exc
            )

    # -- LanceDB hybrid search (Pro tier) --

    def _get_lance_index(self):
        """Return the LanceIndex instance, creating it lazily on first call."""
        if self._lance_index is None:
            from .hybrid_search import LanceIndex
            lance_dir = Path(self.config.db_path).parent / 'sessions.lance'
            self._lance_index = LanceIndex(lance_dir)
        return self._lance_index

    def _lance_write_safe(self, session: Session) -> None:
        """Write session to Lance index if Pro tier. Errors are logged, never raised."""
        if not self.config.is_pro:
            return
        try:
            self._get_lance_index().index_session(
                session_id=session.id,
                title=session.title,
                summary=session.summary,
                project=session.project,
                surface=session.surface,
                start_date=session.start_date,
                tags=session.tags,
                external_tool=session.external_tool_session,
                source=session.source,
            )
        except Exception as exc:
            import logging as _log
            _log.getLogger(__name__).error("Lance write failed for %s: %s", session.id, exc)

    def _fetch_sessions_for_semantic(
        self,
        session_ids: List[str],
        persona: Optional[str],
        tags: Optional[List[str]],
        skills: Optional[List[str]],
        limit: int,
        include_external: bool,
        include_expired: bool = False,
    ) -> List[SearchResult]:
        """Fetch sessions by ID (Lance results) and apply post-filters.

        Preserves the relevance order returned by LanceIndex.search().
        """
        _exclusion_enabled = os.environ.get("LORECONVO_EXTERNAL_TOOL_EXCLUSION", "1") != "0"
        placeholders = ",".join("?" * len(session_ids))
        sql = f"SELECT * FROM sessions WHERE id IN ({placeholders})"
        if _exclusion_enabled and not include_external:
            sql += " AND (external_tool_session IS NULL OR external_tool_session = 0)"
        if not include_expired:
            sql += " AND (expires_at IS NULL OR expires_at > strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))"
        rows = self.conn.execute(sql, session_ids).fetchall()

        # Preserve relevance order from session_ids
        id_to_row = {row['id']: row for row in rows}
        results = []
        for rank, sid in enumerate(session_ids):
            row = id_to_row.get(sid)
            if row is None:
                continue
            session = self._row_to_session(row)
            results.append(SearchResult(session=session, match_score=1.0 / (rank + 1)))

        if persona:
            persona_ids = {r[0] for r in self.conn.execute(
                "SELECT session_id FROM persona_sessions WHERE persona_name LIKE ?",
                (persona + "%",)
            ).fetchall()}
            results = [r for r in results if r.session.id in persona_ids]

        if skills:
            skill_placeholders = ",".join("?" * len(skills))
            skill_ids = {r[0] for r in self.conn.execute(
                f"SELECT session_id FROM session_skills WHERE skill_name IN ({skill_placeholders})",
                skills
            ).fetchall()}
            results = [r for r in results if r.session.id in skill_ids]

        if tags:
            results = [r for r in results if any(t in r.session.tags for t in tags)]

        return results[:limit]

    def rebuild_lance_index(self) -> dict:
        """Rebuild the Lance index from all SQLite sessions. Pro tier only.

        Returns a summary dict with 'indexed' and 'total_in_db' counts.
        Raises on fatal errors.
        """
        if not self.config.is_pro:
            return {"error": "rebuild-index requires LoreConvo Pro"}

        rows = self.conn.execute(
            "SELECT id, title, summary, project, surface, start_date, tags, "
            "external_tool_session, source FROM sessions WHERE id IS NOT NULL AND title IS NOT NULL"
        ).fetchall()
        sessions_list = [dict(r) for r in rows]

        from .hybrid_search import LanceIndex
        lance_dir = Path(self.config.db_path).parent / 'sessions.lance'
        index = LanceIndex(lance_dir)
        count = index.rebuild(sessions_list)

        # Replace cached instance with the freshly built one
        self._lance_index = index
        return {"status": "ok", "indexed": count, "total_in_db": len(sessions_list)}

    def get_related_sessions(
        self,
        session_id: str,
        limit: int = 10,
        min_shared_terms: int = 3,
    ) -> dict:
        """Return sessions related to session_id by co-occurrence and embedding links.

        Returns a version:2 envelope:
            {"version": 2, "sessions": [...]}

        Each session dict includes "link_type": "auto:cooccurrence" or "auto:embedding".
        Co-occurrence entries have shared_term_count >= 1. Embedding entries use
        shared_term_count=0 as a sentinel (semantically related, no term overlap).
        Co-occurrence wins when the same session appears in both result sets.
        Embedding links are excluded for free-tier callers.
        """
        # Co-occurrence results (unchanged from v1)
        cooc_rows = self.conn.execute(
            """SELECT sc2.session_id,
                      COUNT(*) as shared_count,
                      s.title,
                      s.project,
                      s.start_date,
                      s.summary
               FROM session_cooccurrences sc1
               JOIN session_cooccurrences sc2 ON sc1.term = sc2.term
               JOIN sessions s ON sc2.session_id = s.id
               WHERE sc1.session_id = ?
                 AND sc2.session_id != ?
                 AND (s.source IS NULL OR s.source NOT IN ('periodic', 'file_memory'))
               GROUP BY sc2.session_id
               HAVING COUNT(*) >= ?
               ORDER BY shared_count DESC
               LIMIT ?""",
            (session_id, session_id, min_shared_terms, limit)
        ).fetchall()

        seen: dict = {}
        for row in cooc_rows:
            seen[row[0]] = {
                "session_id": row[0],
                "shared_term_count": row[1],
                "link_type": "auto:cooccurrence",
                "title": row[2],
                "project": row[3],
                "start_date": row[4],
                "summary_preview": (row[5] or "")[:200],
            }

        # Embedding results from session_links (Pro only)
        if self.config.is_pro:
            emb_rows = self.conn.execute(
                """SELECT sl.to_session_id, s.title, s.project, s.start_date, s.summary
                   FROM session_links sl
                   JOIN sessions s ON sl.to_session_id = s.id
                   WHERE sl.from_session_id = ?
                     AND sl.link_type = 'auto:embedding'
                     AND (s.source IS NULL OR s.source NOT IN ('periodic', 'file_memory'))
                   LIMIT ?""",
                (session_id, limit)
            ).fetchall()
            for row in emb_rows:
                sid = row[0]
                if sid not in seen:
                    seen[sid] = {
                        "session_id": sid,
                        "shared_term_count": 0,
                        "link_type": "auto:embedding",
                        "title": row[1],
                        "project": row[2],
                        "start_date": row[3],
                        "summary_preview": (row[4] or "")[:200],
                    }

        sessions = sorted(
            seen.values(),
            key=lambda r: r["shared_term_count"],
            reverse=True,
        )
        return {"version": 2, "sessions": sessions}

    def close(self):
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    @staticmethod
    def compute_content_hash(title: str, summary: str, created_at: str) -> str:
        """Compute a stable SHA-256 hash for deduplication on merge."""
        raw = f"{title}|{summary}|{created_at}"
        return "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @staticmethod
    def _get_origin_machine() -> str:
        return os.environ.get("LORECONVO_USER_ID", "") or socket.gethostname()

    # -- Session CRUD --

    def save_session(self, session: Session) -> str:
        if not session.id:
            raise ValueError(
                "Session id must not be None or empty. "
                "Use the Session dataclass (which auto-generates a UUID) "
                "instead of raw SQL inserts."
            )
        # Enforce BSL 1.1 free-tier session limit.
        # Pro mode (valid LORECONVO_PRO license key) bypasses this check.
        if not self.config.is_pro:
            current_count = self.session_count()
            if current_count >= self.config.max_free_sessions:
                raise SessionLimitReachedError(
                    f"Free tier limit reached: {current_count} of "
                    f"{self.config.max_free_sessions} sessions stored. "
                    "Set your LORECONVO_PRO license key to unlock unlimited sessions, "
                    "or contact info@labyrinthanalyticsconsulting.com to upgrade."
                )
        content_hash = (
            session.content_hash
            or self.compute_content_hash(session.title, session.summary, session.created_at)
        )
        origin_machine = session.origin_machine or self._get_origin_machine()
        # Capture prior summary before INSERT OR REPLACE clobbers it (SH-10398).
        prior_summary = None
        existing = self.conn.execute(
            "SELECT summary FROM sessions WHERE id = ?", (session.id,)
        ).fetchone()
        if existing:
            prior_summary = existing[0]
        self.conn.execute(
            """INSERT OR REPLACE INTO sessions
               (id, title, surface, project, start_date, end_date, summary,
                decisions, artifacts, open_questions, tags, created_at, source,
                shared_by, origin_machine, content_hash, external_tool_session,
                reasoning_notes, previous_summary)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                session.id, session.title, session.surface, session.project,
                session.start_date, session.end_date, session.summary,
                json.dumps(session.decisions), json.dumps(session.artifacts),
                json.dumps(session.open_questions), json.dumps(session.tags),
                session.created_at, session.source,
                session.shared_by, origin_machine, content_hash,
                1 if session.external_tool_session else 0,
                session.reasoning_notes if session.reasoning_notes else None,
                prior_summary,
            )
        )
        for skill_name in session.skills_used:
            self.conn.execute(
                """INSERT OR REPLACE INTO session_skills
                   (session_id, skill_name, invocation_count)
                   VALUES (?, ?, 1)""",
                (session.id, skill_name)
            )
        self.conn.commit()

        # Index co-occurrences and auto-link related sessions (additive, non-blocking)
        try:
            self._index_session_cooccurrences(
                session.id,
                session.summary,
                json.dumps(session.decisions),
                session.project,
                json.dumps(session.tags),
            )
            self._auto_link_cooccurrences(session.id)
            self.conn.commit()
        except Exception:
            pass  # co-occurrence index is best-effort; never fail a save

        # Dual-write to Lance index (Pro only, errors never propagate)
        self._lance_write_safe(session)

        # Phase 2a: embedding-based auto-link (Pro only, errors never propagate)
        self._auto_link_embeddings(session)

        # Phase 2b: save-triggered cross-product linking (Pro only, best-effort)
        try:
            self.cross_link_session(session.id, session.summary or "")
        except Exception:
            pass

        return session.id

    def cross_link_session(self, session_id: str, session_text: str) -> int:
        """Trigger save-time cross-product linking for a LoreConvo session.

        Queries the LoreDocs docs.lance index for semantically similar documents,
        writes up to 5 links into LoreDocs cross_product_links. Pro-only.
        Updates sessions.last_cross_linked_at for debounce.

        Returns count of links written (0 if LoreDocs unavailable, not Pro, etc).
        """
        import logging as _logging
        log = _logging.getLogger(__name__)

        if not self.config.is_pro:
            return 0

        # Check debounce
        now_str = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
        row = self.conn.execute(
            "SELECT last_cross_linked_at FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
        if row and row["last_cross_linked_at"]:
            try:
                last = datetime.fromisoformat(row["last_cross_linked_at"].replace("Z", "+00:00"))
                if (datetime.now(timezone.utc) - last).total_seconds() < 600:
                    return 0
            except Exception:
                pass

        # Check session opt-out
        opt_row = self.conn.execute(
            "SELECT cross_link_opt_out FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
        if opt_row and opt_row["cross_link_opt_out"]:
            return 0

        # Discover LoreDocs and its Lance index
        try:
            from loredocs.semantic_search import get_lance_db_path
            from loredocs.storage import (
                VaultStorage, CROSS_LINK_SCHEMA_VERSION,
                REQUIRED_CROSS_LINK_SCHEMA_VERSION,
                _CROSS_LINK_EMBEDDING_MODEL, _CROSS_LINK_EMBEDDING_DIM,
                _CROSS_LINK_CAP, _CROSS_LINK_L2_THRESHOLD,
                discover_product_db, DiscoveryError,
            )
        except ImportError:
            return 0  # LoreDocs not installed

        try:
            ld_db = discover_product_db("loredocs")
        except DiscoveryError:
            return 0
        if ld_db is None:
            return 0

        lance_path = get_lance_db_path()
        if lance_path is None:
            return 0

        query_text = session_text[:2000] if session_text else ""
        if not query_text:
            return 0

        try:
            import lancedb as _lancedb
            from sentence_transformers import SentenceTransformer as _ST

            model = _ST(_CROSS_LINK_EMBEDDING_MODEL)
            q_vec = model.encode(query_text).tolist()

            ld_lance_db = _lancedb.connect(str(lance_path))
            table = ld_lance_db.open_table("docs")
            raw = table.search(
                q_vec, vector_column_name="vector", query_type="vector"
            ).limit(50).to_list()

            # Deduplicate to best distance per doc_id
            best: dict = {}
            for r in raw:
                did = r.get("doc_id")
                dist = r.get("_distance", 999.0)
                if not did:
                    continue
                if dist > _CROSS_LINK_L2_THRESHOLD:
                    continue
                if did not in best or dist < best[did]:
                    best[did] = dist

            # Write cross-product links via LoreDocs storage API
            ld_storage = VaultStorage(ld_db.parent)

            # Verify schema version
            check = ld_storage.get_cross_product_links(
                "loreconvo", session_id, _CROSS_LINK_EMBEDDING_MODEL,
                limit=1, is_pro=True,
            )
            if check.get("schema_version", 0) < REQUIRED_CROSS_LINK_SCHEMA_VERSION:
                log.debug("cross_link_session: LoreDocs schema version too old")
                return 0

            written = 0
            with ld_storage._db() as conn:
                for did, dist in sorted(best.items(), key=lambda x: x[1])[:_CROSS_LINK_CAP]:
                    if written >= _CROSS_LINK_CAP:
                        break
                    # Check vault opt-out
                    vault_row = conn.execute(
                        """SELECT v.cross_link_opt_out FROM documents d
                           JOIN vaults v ON d.vault_id = v.id
                           WHERE d.id = ? AND d.deleted = 0""",
                        (did,)
                    ).fetchone()
                    if not vault_row or vault_row[0]:
                        continue
                    cosine = max(0.0, 1.0 - dist)
                    ld_storage._write_cross_product_link(
                        conn,
                        source_product="loreconvo",
                        source_id=session_id,
                        target_product="loredocs",
                        target_id=did,
                        similarity_score=round(cosine, 4),
                        embedding_model=_CROSS_LINK_EMBEDDING_MODEL,
                        embedding_dim=_CROSS_LINK_EMBEDDING_DIM,
                        link_type="auto",
                        tier_required="pro",
                    )
                    written += 1

            self.conn.execute(
                "UPDATE sessions SET last_cross_linked_at = ? WHERE id = ?",
                (now_str, session_id),
            )
            self.conn.commit()
            log.debug("cross_link_session: wrote %d links for session %s", written, session_id)
            return written
        except Exception as exc:
            log.warning("cross_link_session: unavailable (%s)", type(exc).__name__)
            return 0

    def get_session(self, session_id: str) -> Optional[Session]:
        row = self.conn.execute(
            "SELECT * FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
        if not row:
            return None
        session = self._row_to_session(row)
        skills = self.conn.execute(
            "SELECT skill_name FROM session_skills WHERE session_id = ?",
            (session_id,)
        ).fetchall()
        session.skills_used = [s["skill_name"] for s in skills]
        return session

    def get_recent_sessions(
        self, limit: int = 10, days_back: int = 30,
        project: Optional[str] = None, skill: Optional[str] = None,
        include_external: bool = False,
        include_expired: bool = False,
    ) -> List[Session]:
        _exclusion_enabled = os.environ.get("LORECONVO_EXTERNAL_TOOL_EXCLUSION", "1") != "0"
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days_back)).isoformat().replace('+00:00', 'Z')
        query = "SELECT * FROM sessions WHERE start_date >= ? AND (source IS NULL OR source NOT IN ('periodic', 'file_memory'))"
        if _exclusion_enabled and not include_external:
            query += " AND (external_tool_session IS NULL OR external_tool_session = 0)"
        if not include_expired:
            query += " AND (expires_at IS NULL OR expires_at > strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))"
        params = [cutoff]

        if project:
            query += " AND project = ?"
            params.append(project)

        if skill:
            query += " AND id IN (SELECT session_id FROM session_skills WHERE skill_name = ?)"
            params.append(skill)

        query += " ORDER BY start_date DESC LIMIT ?"
        params.append(limit)

        rows = self.conn.execute(query, params).fetchall()
        return [self._row_to_session(r) for r in rows]

    @staticmethod
    def _expand_compound_token(token: str) -> List[str]:
        """Split a compound token (camelCase, PascalCase, snake_case) into parts.

        Returns the original token plus its constituent parts so FTS5 matches
        both the compound form and individual words.

        Only expands tokens that are purely alphanumeric (plus underscores).
        Tokens with hyphens, colons, or other special chars are left as-is
        since those are not compound identifiers.

        Examples:
            "autoSave"      -> ["autoSave", "auto", "Save"]
            "PreCompact"    -> ["PreCompact", "Pre", "Compact"]
            "snake_case"    -> ["snake_case", "snake", "case"]
            "simple"        -> ["simple"]
            "agent:ron"     -> ["agent:ron"]  (colon = not a compound)
            "K-1"           -> ["K-1"]        (hyphen = not a compound)
        """
        # Only attempt expansion on tokens that look like identifiers
        # (alphanumeric + underscores only)
        if not re.match(r'^[A-Za-z0-9_]+$', token):
            return [token]

        parts = []
        # snake_case / SCREAMING_SNAKE: split on underscores
        if '_' in token:
            parts = [p for p in token.split('_') if p]
        else:
            # camelCase / PascalCase: split on case transitions
            # "autoSave" -> ["auto", "Save"], "HTMLParser" -> ["HTML", "Parser"]
            camel_parts = re.findall(r'[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|[0-9]+', token)
            if len(camel_parts) > 1:
                parts = camel_parts

        if not parts:
            return [token]
        # Return original token first (for exact match), then expanded parts
        return [token] + parts

    @staticmethod
    def _sanitize_fts_query(query: str) -> str:
        """Sanitize and preprocess user input for FTS5 MATCH.

        Processing steps:
        1. Split on whitespace into raw tokens.
        2. Expand compound tokens (camelCase, snake_case) into parts.
        3. Apply prefix matching (trailing *) for short alpha tokens (<=7 chars)
           so partial terms like "precomp" match "PreCompact".
        4. Quote each token to escape FTS5 operators (hyphens, colons).
        5. Implicit AND across all tokens (FTS5 default).

        Examples:
            "stripe billing"     -> '"stripe" "billing"'
            "autoSave"           -> '"autoSave" OR "auto" OR "Save"'
            "snake_case"         -> '"snake_case" OR "snake" OR "case"'
            "precomp"            -> '"precomp"*'
            "fts-migration"      -> '"fts-migration"'
            "agent:ron"          -> '"agent:ron"'
            "K-1 parser waiting" -> '"K-1" "parser" "waiting"'
        """
        safe = query.strip()
        if not safe:
            return '""'

        raw_tokens = safe.split()
        fts_groups = []
        has_or_group = False

        for token in raw_tokens:
            clean = token.replace('"', '')
            if not clean:
                continue

            expanded = SessionDatabase._expand_compound_token(clean)

            if len(expanded) > 1:
                # Compound token: OR the original with its parts
                parts = ['"' + p + '"' for p in expanded]
                fts_groups.append('(' + ' OR '.join(parts) + ')')
                has_or_group = True
            else:
                # Single token: apply prefix matching for short terms
                # Tokens <= 7 chars that are purely alphabetic are likely
                # abbreviations or partial words (e.g., "precomp" -> PreCompact)
                t = expanded[0]
                if len(t) <= 7 and t.isalpha():
                    # Short alphabetic token -- prefix match
                    fts_groups.append('"' + t + '"*')
                else:
                    fts_groups.append('"' + t + '"')

        if not fts_groups:
            return '""'

        # FTS5 requires explicit AND when combining parenthesized OR-groups
        # with other terms. Implicit AND only works between simple tokens.
        joiner = ' AND ' if has_or_group else ' '
        return joiner.join(fts_groups)

    def search_sessions(
        self, query: str, persona: Optional[str] = None,
        tags: Optional[List[str]] = None, skills: Optional[List[str]] = None,
        project: Optional[str] = None, limit: int = 10,
        include_external: bool = False,
        semantic: bool = False,
        include_expired: bool = False,
    ) -> List[SearchResult]:
        # Semantic path: Pro tier + Lance index available
        if semantic and self.config.is_pro:
            lance = self._get_lance_index()
            if lance.is_available():
                session_ids = lance.search(
                    query,
                    project=project,
                    limit=limit * 3,
                    half_life_days=SEARCH_HALF_LIFE_DAYS,
                )
                if session_ids:
                    return self._fetch_sessions_for_semantic(
                        session_ids, persona, tags, skills, limit, include_external,
                        include_expired=include_expired,
                    )
            # Fall through to FTS5 if Lance unavailable or no results

        _exclusion_enabled = os.environ.get("LORECONVO_EXTERNAL_TOOL_EXCLUSION", "1") != "0"
        fts_query = self._sanitize_fts_query(query)
        sql = """
            SELECT s.*, sessions_fts.rank
            FROM sessions s
            JOIN sessions_fts ON s.rowid = sessions_fts.rowid
            WHERE sessions_fts MATCH ?
        """
        if _exclusion_enabled and not include_external:
            sql += " AND (s.external_tool_session IS NULL OR s.external_tool_session = 0)"
        if not include_expired:
            sql += " AND (s.expires_at IS NULL OR s.expires_at > strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))"
        params = [fts_query]

        if persona:
            sql += " AND s.id IN (SELECT session_id FROM persona_sessions WHERE persona_name LIKE ?)"
            params.append(persona + "%")

        if project:
            sql += " AND s.project = ?"
            params.append(project)

        if skills:
            placeholders = ",".join("?" * len(skills))
            sql += f" AND s.id IN (SELECT session_id FROM session_skills WHERE skill_name IN ({placeholders}))"
            params.extend(skills)

        sql += " ORDER BY sessions_fts.rank LIMIT ?"
        params.append(limit)

        rows = self.conn.execute(sql, params).fetchall()
        results = []
        for row in rows:
            session = self._row_to_session(row)
            results.append(SearchResult(
                session=session,
                match_score=abs(row["rank"]) if row["rank"] else 0.0
            ))

        if tags:
            results = [
                r for r in results
                if any(t in r.session.tags for t in tags)
            ]

        return results

    def get_context_for(
        self,
        topic: str,
        max_results: int = 5,
        include_external: bool = False,
        semantic: bool = False,
        half_life_days: int = SEARCH_HALF_LIFE_DAYS,
    ) -> List[SearchResult]:
        if semantic and self.config.is_pro:
            lance = self._get_lance_index()
            if lance.is_available():
                session_ids = lance.search(
                    topic,
                    limit=max_results * 3,
                    half_life_days=half_life_days,
                )
                if session_ids:
                    return self._fetch_sessions_for_semantic(
                        session_ids, None, None, None, max_results, include_external
                    )
        return self.search_sessions(query=topic, limit=max_results, include_external=include_external)

    def list_all_skills(self) -> List[dict]:
        """Return all distinct skill names with session counts, sorted by use count desc."""
        rows = self.conn.execute(
            """SELECT skill_name, COUNT(*) as session_count
               FROM session_skills
               GROUP BY skill_name
               ORDER BY session_count DESC, skill_name ASC"""
        ).fetchall()
        return [{"skill_name": r["skill_name"], "session_count": r["session_count"]} for r in rows]

    def get_skill_history(
        self, skill_name: str, days_back: int = 90
    ) -> List[Session]:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days_back)).isoformat().replace('+00:00', 'Z')
        rows = self.conn.execute(
            """SELECT s.* FROM sessions s
               JOIN session_skills sk ON s.id = sk.session_id
               WHERE sk.skill_name = ? AND s.start_date >= ?
               ORDER BY s.start_date DESC""",
            (skill_name, cutoff)
        ).fetchall()
        return [self._row_to_session(r) for r in rows]

    # -- Persona operations --

    def tag_session(
        self, session_id: str, persona_name: str,
        relevance_note: Optional[str] = None
    ):
        self.conn.execute(
            """INSERT OR REPLACE INTO persona_sessions
               (persona_name, session_id, relevance_note)
               VALUES (?, ?, ?)""",
            (persona_name, session_id, relevance_note)
        )
        self.conn.commit()

    def get_persona_sessions(
        self, persona_name: str, limit: int = 20
    ) -> List[Session]:
        rows = self.conn.execute(
            """SELECT s.* FROM sessions s
               JOIN persona_sessions ps ON s.id = ps.session_id
               WHERE ps.persona_name LIKE ?
               ORDER BY s.start_date DESC LIMIT ?""",
            (persona_name + "%", limit)
        ).fetchall()
        return [self._row_to_session(r) for r in rows]

    # -- Session linking --

    def link_sessions(
        self, from_id: str, to_id: str, link_type: str = "continues"
    ):
        self.conn.execute(
            """INSERT OR REPLACE INTO session_links
               (from_session_id, to_session_id, link_type)
               VALUES (?, ?, ?)""",
            (from_id, to_id, link_type)
        )
        self.conn.commit()

    def get_session_chain(self, session_id: str) -> List[Session]:
        chain_ids = set()
        to_visit = [session_id]
        while to_visit:
            current = to_visit.pop(0)
            if current in chain_ids:
                continue
            chain_ids.add(current)
            links = self.conn.execute(
                """SELECT to_session_id FROM session_links WHERE from_session_id = ?
                   UNION
                   SELECT from_session_id FROM session_links WHERE to_session_id = ?""",
                (current, current)
            ).fetchall()
            for link in links:
                to_visit.append(link[0])

        sessions = []
        for sid in chain_ids:
            s = self.get_session(sid)
            if s:
                sessions.append(s)
        sessions.sort(key=lambda s: s.start_date)
        return sessions

    # -- Project operations --

    def create_project(
        self, name: str, description: str = "",
        expected_skills: Optional[List[str]] = None,
        default_persona: Optional[str] = None,
        instructions: Optional[str] = None
    ):
        self.conn.execute(
            """INSERT OR REPLACE INTO projects
               (name, description, expected_skills, default_persona, instructions)
               VALUES (?, ?, ?, ?, ?)""",
            (name, description, json.dumps(expected_skills or []), default_persona, instructions)
        )
        self.conn.commit()

    def get_project(self, project_name: str) -> Optional[dict]:
        row = self.conn.execute(
            "SELECT * FROM projects WHERE name = ?", (project_name,)
        ).fetchone()
        if not row:
            return None

        sessions = self.get_recent_sessions(
            limit=20, days_back=365, project=project_name
        )

        skill_counts = {}
        for s in sessions:
            skill_rows = self.conn.execute(
                "SELECT skill_name, invocation_count FROM session_skills WHERE session_id = ?",
                (s.id,)
            ).fetchall()
            for sr in skill_rows:
                skill_counts[sr["skill_name"]] = skill_counts.get(sr["skill_name"], 0) + sr["invocation_count"]

        return {
            "name": row["name"],
            "description": row["description"],
            "expected_skills": json.loads(row["expected_skills"] or "[]"),
            "default_persona": row["default_persona"],
            "instructions": row["instructions"],
            "session_count": len(sessions),
            "recent_sessions": [
                {"id": s.id, "title": s.title, "date": s.start_date}
                for s in sessions[:10]
            ],
            "skill_usage": dict(sorted(skill_counts.items(), key=lambda x: -x[1]))
        }

    def list_projects(self) -> List[dict]:
        rows = self.conn.execute("""
            SELECT p.name, p.description,
                   COUNT(s.id) AS session_count
            FROM projects p
            LEFT JOIN sessions s ON s.project = p.name
            GROUP BY p.name, p.description
            ORDER BY p.name
        """).fetchall()
        return [
            {
                "name": row["name"],
                "description": row["description"],
                "session_count": row["session_count"]
            }
            for row in rows
        ]

    # -- Suggestions --

    def get_suggestions(
        self, project: Optional[str] = None,
        persona: Optional[str] = None,
        days_back: int = 14, limit: int = 5
    ) -> dict:
        """Generate proactive context suggestions.

        Finds sessions worth revisiting based on:
        - Unresolved open questions
        - Recent decisions that may need follow-up
        - Skill gaps (expected by project but not used recently)
        """
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days_back)).isoformat().replace('+00:00', 'Z')
        suggestions = []

        # 1. Sessions with open questions (highest priority)
        oq_sql = """
            SELECT * FROM sessions
            WHERE start_date >= ?
              AND open_questions IS NOT NULL
              AND open_questions != '[]'
        """
        oq_params: list = [cutoff]
        if project:
            oq_sql += " AND project = ?"
            oq_params.append(project)
        if persona:
            oq_sql += " AND id IN (SELECT session_id FROM persona_sessions WHERE persona_name LIKE ?)"
            oq_params.append(persona + "%")
        oq_sql += " ORDER BY start_date DESC"

        rows = self.conn.execute(oq_sql, oq_params).fetchall()
        for row in rows:
            session = self._row_to_session(row)
            if session.open_questions:
                suggestions.append({
                    "session_id": session.id,
                    "title": session.title,
                    "date": session.start_date,
                    "reason": "Has %d unresolved open question(s)" % len(session.open_questions),
                    "type": "open_questions",
                    "priority": 1,
                    "open_questions": session.open_questions,
                    "summary_preview": session.summary[:300] + "..." if len(session.summary) > 300 else session.summary,
                })

        # 2. Sessions with decisions worth reviewing
        dec_sql = """
            SELECT * FROM sessions
            WHERE start_date >= ?
              AND decisions IS NOT NULL
              AND decisions != '[]'
        """
        dec_params: list = [cutoff]
        if project:
            dec_sql += " AND project = ?"
            dec_params.append(project)
        if persona:
            dec_sql += " AND id IN (SELECT session_id FROM persona_sessions WHERE persona_name LIKE ?)"
            dec_params.append(persona + "%")
        dec_sql += " ORDER BY start_date DESC"

        seen_ids = {s["session_id"] for s in suggestions}
        rows = self.conn.execute(dec_sql, dec_params).fetchall()
        for row in rows:
            session = self._row_to_session(row)
            if session.id not in seen_ids and len(session.decisions) >= 2:
                suggestions.append({
                    "session_id": session.id,
                    "title": session.title,
                    "date": session.start_date,
                    "reason": "Contains %d key decisions worth reviewing" % len(session.decisions),
                    "type": "decisions",
                    "priority": 2,
                    "decisions": session.decisions,
                    "summary_preview": session.summary[:300] + "..." if len(session.summary) > 300 else session.summary,
                })
                seen_ids.add(session.id)

        # 3. Skill gaps (project expected_skills not used recently)
        skill_gaps = []
        if project:
            proj_row = self.conn.execute(
                "SELECT expected_skills FROM projects WHERE name = ?",
                (project,)
            ).fetchone()
            if proj_row:
                expected = json.loads(proj_row["expected_skills"] or "[]")
                if expected:
                    recent_skills = self.conn.execute(
                        """SELECT DISTINCT sk.skill_name
                           FROM session_skills sk
                           JOIN sessions s ON sk.session_id = s.id
                           WHERE s.start_date >= ? AND s.project = ?""",
                        (cutoff, project)
                    ).fetchall()
                    used = {r["skill_name"] for r in recent_skills}
                    for skill in expected:
                        if skill not in used:
                            # Find last time this skill was used
                            last = self.conn.execute(
                                """SELECT s.start_date FROM sessions s
                                   JOIN session_skills sk ON s.id = sk.session_id
                                   WHERE sk.skill_name = ?
                                   ORDER BY s.start_date DESC LIMIT 1""",
                                (skill,)
                            ).fetchone()
                            skill_gaps.append({
                                "skill": skill,
                                "last_used": last["start_date"] if last else None,
                                "reason": "Expected in project '%s' but not used in last %d days" % (project, days_back),
                            })

        # Sort by priority, then recency
        suggestions.sort(key=lambda s: (s["priority"], s["date"]))
        # Remove priority field from output, take top N
        for s in suggestions:
            del s["priority"]
        suggestions = suggestions[:limit]

        total_scanned = self.conn.execute(
            "SELECT COUNT(*) as c FROM sessions WHERE start_date >= ?",
            (cutoff,)
        ).fetchone()["c"]

        return {
            "suggestions": suggestions,
            "skill_gaps": skill_gaps,
            "metadata": {
                "total_sessions_scanned": total_scanned,
                "days_back": days_back,
                "suggestions_returned": len(suggestions),
                "project_filter": project,
                "persona_filter": persona,
            }
        }

    # -- Helpers --

    @staticmethod
    def _parse_json_field(value, default="[]"):
        """Parse a JSON field that may contain a raw string instead of a JSON array.

        Handles three storage formats found in the database:
        1. JSON array (current format):  '["tag1", "tag2"]'
        2. Comma-separated string (legacy tags): 'tag1,tag2,tag3'
        3. Plain text blob (Gina architecture proposals in decisions field)

        Always returns a list so callers never need to handle multiple types.
        """
        raw = value or default
        try:
            result = json.loads(raw)
            if not isinstance(result, list):
                return [str(result)]
            return result
        except (json.JSONDecodeError, ValueError):
            if not raw or raw == default:
                return []
            # Legacy comma-separated tags (e.g. 'security,supply-chain,audit')
            # Detect by checking whether the string looks like a CSV tag list:
            # short tokens, no spaces, commas present.
            stripped = raw.strip().rstrip(',')
            tokens = [t.strip() for t in stripped.split(',') if t.strip()]
            all_short = all(len(t) <= 60 and ' ' not in t for t in tokens)
            if len(tokens) > 1 and all_short:
                return tokens
            # Plain text blob (architecture proposals, free-form text) -- keep as one item
            return [raw]

    def _row_to_session(self, row) -> Session:
        row_keys = row.keys()
        return Session(
            id=row["id"],
            title=row["title"],
            surface=row["surface"],
            project=row["project"],
            start_date=row["start_date"],
            end_date=row["end_date"],
            summary=row["summary"] or "",
            decisions=self._parse_json_field(row["decisions"]),
            artifacts=self._parse_json_field(row["artifacts"]),
            open_questions=self._parse_json_field(row["open_questions"]),
            tags=self._parse_json_field(row["tags"]),
            created_at=row["created_at"] or "",
            source=row["source"] if "source" in row_keys else "session",
            shared_by=row["shared_by"] if "shared_by" in row_keys else None,
            origin_machine=row["origin_machine"] if "origin_machine" in row_keys else None,
            content_hash=row["content_hash"] if "content_hash" in row_keys else None,
            external_tool_session=bool(row["external_tool_session"]) if "external_tool_session" in row_keys else False,
            reasoning_notes=row["reasoning_notes"] if "reasoning_notes" in row_keys else None,
            previous_summary=row["previous_summary"] if "previous_summary" in row_keys else None,
            keep_forever=bool(row["keep_forever"]) if "keep_forever" in row_keys else False,
        )

    def get_sessions_for_shared_export(
        self,
        project: Optional[str] = None,
        session_id_filter: Optional[List[str]] = None,
        export_all: bool = False,
    ) -> List[Session]:
        """Return sessions formatted for team-memory shared export.

        SEC-00071: source='periodic' sessions are excluded.
        SH-10121: external_tool_session sessions excluded -- re-exporting imported
        sessions creates circular contamination once Phase 3 import lands.
        """
        _exclusion_enabled = os.environ.get("LORECONVO_EXTERNAL_TOOL_EXCLUSION", "1") != "0"
        query = "SELECT * FROM sessions WHERE (source IS NULL OR source NOT IN ('periodic', 'file_memory'))"
        if _exclusion_enabled:
            query += " AND (external_tool_session IS NULL OR external_tool_session = 0)"
        params: list = []

        if not export_all:
            if session_id_filter:
                placeholders = ",".join("?" * len(session_id_filter))
                query += f" AND id IN ({placeholders})"
                params.extend(session_id_filter)
            elif project:
                query += " AND project = ?"
                params.append(project)

        query += " ORDER BY start_date DESC LIMIT 1000"
        rows = self.conn.execute(query, params).fetchall()
        return [self._row_to_session(r) for r in rows]

    def merge_session(self, session_dict: dict, shared_by: str) -> str:
        """Import one session from a shared export dict. Returns 'imported' or 'skipped'.

        SEC-00067: skip-on-exist only, no replace option.
        SEC-00068: field length caps applied before any DB insert.
        SEC-00069: content_hash always recomputed locally; imported value is ignored.
        """
        session_id = str(session_dict.get("id", "")).strip()
        if not session_id:
            return "skipped"

        # UUID-exists check (exact duplicate)
        if self.conn.execute(
            "SELECT id FROM sessions WHERE id = ?", (session_id,)
        ).fetchone():
            return "skipped"

        # Apply field caps (SEC-00068)
        title = str(session_dict.get("title", "") or "")[:_IMPORT_FIELD_CAPS["title"]]
        summary = str(session_dict.get("summary", "") or "")[:_IMPORT_FIELD_CAPS["summary"]]
        created_at = str(session_dict.get("created_at", "") or "")

        # Recompute content_hash locally; never trust the imported value (SEC-00069)
        local_hash = self.compute_content_hash(title, summary, created_at)

        # Content-hash dedup (same content, different UUID path)
        if self.conn.execute(
            "SELECT id FROM sessions WHERE content_hash = ?", (local_hash,)
        ).fetchone():
            return "skipped"

        tags = [str(t)[:_IMPORT_FIELD_CAPS["list_item"]]
                for t in (session_dict.get("tags") or [])]
        decisions = [str(d)[:_IMPORT_FIELD_CAPS["list_item"]]
                     for d in (session_dict.get("decisions") or [])]
        open_questions = [str(q)[:_IMPORT_FIELD_CAPS["list_item"]]
                          for q in (session_dict.get("open_questions") or [])]
        # SEC-00070: strip artifacts to basename only
        import os as _os
        artifacts = [_os.path.basename(str(a)) for a in (session_dict.get("artifacts") or [])]

        surface = str(session_dict.get("surface", "") or "")
        project = session_dict.get("project") or None
        origin_machine = str(session_dict.get("origin_machine", "") or "")

        self.conn.execute(
            """INSERT OR IGNORE INTO sessions
               (id, title, surface, project, start_date, end_date, summary,
                decisions, artifacts, open_questions, tags, created_at, source,
                shared_by, origin_machine, content_hash)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                session_id, title, surface, project,
                created_at, None, summary,
                json.dumps(decisions), json.dumps(artifacts),
                json.dumps(open_questions), json.dumps(tags),
                created_at, "imported",
                shared_by, origin_machine, local_hash,
            )
        )
        self.conn.commit()
        return "imported"

    def session_exists(self, session_id: str) -> bool:
        row = self.conn.execute(
            "SELECT id FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
        return row is not None

    def session_count(self) -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) as c FROM sessions WHERE source IS NULL OR source != 'file_memory'"
        ).fetchone()
        return row["c"]

    def inspect_sessions(
        self,
        search: Optional[str] = None,
        tag: Optional[str] = None,
        surface: Optional[str] = None,
        since: Optional[str] = None,
        limit: int = 20,
    ) -> List[Session]:
        """Return sessions matching inspect filters."""
        if search:
            results = self.search_sessions(search, limit=limit)
            sessions = [r.session for r in results]
            sessions = [s for s in sessions if s.source not in ('periodic', 'file_memory')]
            if surface:
                sessions = [s for s in sessions if s.surface == surface]
            if tag:
                sessions = [s for s in sessions if any(tag in t for t in s.tags)]
            if since:
                sessions = [s for s in sessions if s.start_date >= since]
            return sessions[:limit]

        query = "SELECT * FROM sessions WHERE (source IS NULL OR source NOT IN ('periodic', 'file_memory'))"
        params: list = []

        if since:
            query += " AND start_date >= ?"
            params.append(since)
        if surface:
            query += " AND surface = ?"
            params.append(surface)
        if tag:
            query += " AND tags LIKE ?"
            params.append(f'%{tag}%')

        query += " ORDER BY start_date DESC LIMIT ?"
        params.append(limit)

        rows = self.conn.execute(query, params).fetchall()
        return [self._row_to_session(r) for r in rows]

    def get_inspect_stats(self) -> dict:
        """Return aggregate stats for inspect --show-stats."""
        _src_filter = "(source IS NULL OR source NOT IN ('periodic', 'file_memory'))"
        total = self.conn.execute(
            f"SELECT COUNT(*) as c FROM sessions WHERE {_src_filter}"
        ).fetchone()["c"]
        by_surface = self.conn.execute(
            f"SELECT surface, COUNT(*) as c FROM sessions WHERE {_src_filter} "
            "GROUP BY surface ORDER BY c DESC"
        ).fetchall()
        by_project = self.conn.execute(
            f"SELECT project, COUNT(*) as c FROM sessions WHERE {_src_filter} "
            "AND project IS NOT NULL GROUP BY project ORDER BY c DESC LIMIT 10"
        ).fetchall()
        with_oq = self.conn.execute(
            f"SELECT COUNT(*) as c FROM sessions WHERE {_src_filter} "
            "AND open_questions IS NOT NULL AND open_questions != '[]'"
        ).fetchone()["c"]
        return {
            "total": total,
            "by_surface": {r["surface"]: r["c"] for r in by_surface},
            "by_project": {r["project"]: r["c"] for r in by_project},
            "with_open_questions": with_oq,
        }

    def delete_session(self, session_id: str) -> bool:
        """Delete a session by ID. Returns True if deleted, False if not found or pinned.

        Pinned sessions (keep_forever=1) cannot be deleted; unpin first.
        All deletes are routed through sessions_prunable to honour the
        keep_forever enforcement layer.
        """
        row = self.conn.execute(
            "SELECT keep_forever FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
        if not row:
            return False
        if row["keep_forever"]:
            return False  # caller should surface "unpin first" guidance
        self.conn.execute("DELETE FROM session_skills WHERE session_id = ?", (session_id,))
        self.conn.execute("DELETE FROM persona_sessions WHERE session_id = ?", (session_id,))
        self.conn.execute(
            "DELETE FROM session_links WHERE from_session_id = ? OR to_session_id = ?",
            (session_id, session_id)
        )
        self.conn.execute("DELETE FROM sessions_prunable WHERE id = ?", (session_id,))
        self.conn.commit()
        return True

    def get_usage_stats(self) -> dict:
        """Return aggregate usage statistics for the get_stats MCP tool.

        Excludes periodic snapshots and file_memory entries (internal sources).
        """
        _s = _INTERNAL_SOURCES

        total = self.conn.execute(
            "SELECT COUNT(*) as c FROM sessions "
            "WHERE (source IS NULL OR source NOT IN (?, ?))",
            _s,
        ).fetchone()["c"]

        by_surface = self.conn.execute(
            "SELECT surface, COUNT(*) as c FROM sessions "
            "WHERE (source IS NULL OR source NOT IN (?, ?)) "
            "GROUP BY surface ORDER BY c DESC",
            _s,
        ).fetchall()

        by_project = self.conn.execute(
            "SELECT COALESCE(project, '(none)') as project, COUNT(*) as c "
            "FROM sessions WHERE (source IS NULL OR source NOT IN (?, ?)) "
            "GROUP BY project ORDER BY c DESC LIMIT 10",
            _s,
        ).fetchall()

        recent_5 = self.conn.execute(
            "SELECT title, start_date, surface, project FROM sessions "
            "WHERE (source IS NULL OR source NOT IN (?, ?)) "
            "ORDER BY start_date DESC LIMIT 5",
            _s,
        ).fetchall()

        # Tag breakdown: parse JSON tags column in Python
        tag_rows = self.conn.execute(
            "SELECT tags FROM sessions "
            "WHERE tags IS NOT NULL AND tags != '[]' "
            "AND (source IS NULL OR source NOT IN (?, ?))",
            _s,
        ).fetchall()
        tag_counts: dict = {}
        for row in tag_rows:
            for tag in self._parse_json_field(row["tags"]):
                tag_counts[tag] = tag_counts.get(tag, 0) + 1
        top_tags = dict(sorted(tag_counts.items(), key=lambda x: -x[1])[:10])

        # Storage metrics
        db_size_bytes = 0
        if os.path.exists(self.config.db_path):
            db_size_bytes = os.path.getsize(self.config.db_path)

        char_count_row = self.conn.execute(
            "SELECT SUM(LENGTH(COALESCE(title,'')) + LENGTH(COALESCE(summary,'')) + "
            "LENGTH(COALESCE(decisions,'')) + LENGTH(COALESCE(open_questions,''))) as total_chars "
            "FROM sessions WHERE (source IS NULL OR source NOT IN (?, ?))",
            _s,
        ).fetchone()
        total_chars = char_count_row["total_chars"] or 0

        return {
            "total_sessions": total,
            "by_surface": {r["surface"]: r["c"] for r in by_surface},
            "by_project": {r["project"]: r["c"] for r in by_project},
            "top_tags": top_tags,
            "recent_sessions": [
                {
                    "title": r["title"],
                    "date": r["start_date"][:10] if r["start_date"] else "",
                    "surface": r["surface"],
                    "project": r["project"],
                }
                for r in recent_5
            ],
            "storage": {
                "db_size_bytes": db_size_bytes,
                "db_size_mb": round(db_size_bytes / (1024 * 1024), 2),
                "estimated_tokens": total_chars // 4,
            },
        }

    # -- Dreaming / Recall operations (v0.6.0) --

    def upsert_memory_digest(self, project: str, surface: Optional[str], data: dict) -> None:
        """Insert or update a memory digest keyed by (project, surface)."""
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        existing = self.conn.execute(
            "SELECT id FROM memory_digests WHERE project=? AND surface IS ?",
            (project, surface)
        ).fetchone()
        if existing:
            self.conn.execute(
                """UPDATE memory_digests SET
                   updated_at=?,
                   source_count=COALESCE(?,source_count),
                   oldest_session_date=COALESCE(?,oldest_session_date),
                   newest_session_date=COALESCE(?,newest_session_date),
                   decisions=COALESCE(?,decisions),
                   open_questions=COALESCE(?,open_questions),
                   known_stack=COALESCE(?,known_stack),
                   stale_facts=COALESCE(?,stale_facts),
                   digest_markdown=COALESCE(?,digest_markdown),
                   mode=COALESCE(?,mode),
                   tier=COALESCE(?,tier),
                   api_key_found=COALESCE(?,api_key_found)
                   WHERE project=? AND surface IS ?""",
                (
                    now,
                    data.get("source_count"),
                    data.get("oldest_session_date"),
                    data.get("newest_session_date"),
                    data.get("decisions"),
                    data.get("open_questions"),
                    data.get("known_stack"),
                    data.get("stale_facts"),
                    data.get("digest_markdown"),
                    data.get("mode"),
                    data.get("tier"),
                    data.get("api_key_found"),
                    project, surface,
                )
            )
        else:
            digest_id = __import__("uuid").uuid4().hex
            self.conn.execute(
                """INSERT INTO memory_digests
                   (id, project, surface, created_at, updated_at,
                    source_count, oldest_session_date, newest_session_date,
                    decisions, open_questions, known_stack, stale_facts,
                    digest_markdown, mode, tier, api_key_found)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    digest_id, project, surface, now, now,
                    data.get("source_count", 0),
                    data.get("oldest_session_date"),
                    data.get("newest_session_date"),
                    data.get("decisions"),
                    data.get("open_questions"),
                    data.get("known_stack"),
                    data.get("stale_facts"),
                    data.get("digest_markdown"),
                    data.get("mode", "heuristic"),
                    data.get("tier", "free"),
                    data.get("api_key_found", 1),
                )
            )
        self.conn.commit()

    def get_memory_digest(self, project: str, surface: Optional[str]) -> Optional[dict]:
        """Return the current digest for (project, surface) as a dict, or None."""
        row = self.conn.execute(
            "SELECT * FROM memory_digests WHERE project=? AND surface IS ?",
            (project, surface)
        ).fetchone()
        if not row:
            return None
        return dict(row)

    def update_digest_disabled(self, project: str, surface: Optional[str], disabled: bool) -> None:
        """Set the disabled flag on a digest to suppress auto-load injection."""
        self.conn.execute(
            "UPDATE memory_digests SET disabled=? WHERE project=? AND surface IS ?",
            (1 if disabled else 0, project, surface)
        )
        self.conn.commit()

    def set_session_expiry(self, session_id: str, expires_at: Optional[str]) -> dict:
        """Set or clear the expires_at field on a session.

        Returns dict with 'ok', 'code', and optionally 'message'.
        Refuses to set expiry on a pinned (keep_forever=1) session.
        """
        row = self.conn.execute(
            "SELECT keep_forever FROM sessions WHERE id=?", (session_id,)
        ).fetchone()
        if not row:
            return {"ok": False, "code": "session_not_found", "message": "Session not found."}
        if row["keep_forever"]:
            return {"ok": False, "code": "session_pinned",
                    "message": "Session is pinned. Unpin before setting expiry."}
        self.conn.execute(
            "UPDATE sessions SET expires_at=? WHERE id=?",
            (expires_at, session_id)
        )
        self.conn.commit()
        return {"ok": True}

    def set_session_staleness(self, session_id: str, hint: Optional[str]) -> None:
        """Set or clear the staleness_hint field on a session."""
        self.conn.execute(
            "UPDATE sessions SET staleness_hint=? WHERE id=?",
            (hint, session_id)
        )
        self.conn.commit()

    def get_sessions_for_consolidation(
        self,
        project: str,
        surface: Optional[str],
        max_sessions: int = 50,
        exclude_no_llm: bool = False,
    ) -> List[dict]:
        """Return up to max_sessions recent sessions for a (project, surface) pair.

        Excludes periodic/file_memory sources. When exclude_no_llm=True, also
        excludes sessions tagged 'no-llm'.
        """
        params: list = [project]
        sql = (
            "SELECT id, title, summary, decisions, open_questions, tags, "
            "start_date, created_at, staleness_hint, expires_at, source "
            "FROM sessions "
            "WHERE project=? "
            "AND (source IS NULL OR source NOT IN ('periodic', 'file_memory'))"
        )
        if surface is not None:
            sql += " AND surface=?"
            params.append(surface)
        sql += " ORDER BY start_date DESC LIMIT ?"
        params.append(max_sessions)

        rows = self.conn.execute(sql, params).fetchall()
        results = [dict(r) for r in rows]

        if exclude_no_llm:
            filtered = []
            for r in results:
                tags = self._parse_json_field(r.get("tags"))
                if "no-llm" not in tags:
                    filtered.append(r)
            results = filtered

        return results

    def count_consolidations_today(
        self,
        project: str,
        surface: Optional[str],
        log_path: Optional[str] = None,
    ) -> int:
        """Count how many consolidation runs occurred today for this (project, surface).

        Reads from consolidation.log (JSON-lines format). Returns 0 if log missing.
        """
        if log_path is None:
            lore_dir = Path(self.config.db_path).parent
            log_path = str(lore_dir / "consolidation.log")

        if not Path(log_path).is_file():
            return 0

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        count = 0
        try:
            for line in Path(log_path).read_text().splitlines():
                line = line.strip()
                if not line:
                    continue
                entry = json.loads(line)
                ts = entry.get("ts", "")
                if (
                    entry.get("project") == project
                    and entry.get("surface") == surface
                    and ts.startswith(today)
                ):
                    count += 1
        except Exception:
            pass
        return count

    def get_consolidation_log_entries(
        self,
        project: Optional[str] = None,
        surface: Optional[str] = None,
        limit: int = 10,
        log_path: Optional[str] = None,
    ) -> List[dict]:
        """Return recent consolidation log entries, newest first.

        Filters by project/surface when provided. Reads from consolidation.log.
        """
        if log_path is None:
            lore_dir = Path(self.config.db_path).parent
            log_path = str(lore_dir / "consolidation.log")

        entries = []
        if not Path(log_path).is_file():
            return entries

        try:
            for line in Path(log_path).read_text().splitlines():
                line = line.strip()
                if not line:
                    continue
                entry = json.loads(line)
                if project and entry.get("project") != project:
                    continue
                if surface and entry.get("surface") != surface:
                    continue
                entries.append(entry)
        except Exception:
            pass

        entries.reverse()
        return entries[:limit]

    def get_sessions_for_export(
        self,
        project: Optional[str] = None,
        tags: Optional[List[str]] = None,
        days_back: Optional[int] = None,
        limit: int = 1000,
    ) -> List[Session]:
        """Return sessions with full detail (including skills) for export."""
        query = "SELECT * FROM sessions WHERE 1=1"
        params: list = []

        if days_back is not None:
            cutoff = (datetime.now(timezone.utc) - timedelta(days=days_back)).isoformat().replace('+00:00', 'Z')
            query += " AND start_date >= ?"
            params.append(cutoff)

        if project:
            query += " AND project = ?"
            params.append(project)

        query += " ORDER BY start_date DESC LIMIT ?"
        params.append(limit)

        rows = self.conn.execute(query, params).fetchall()
        sessions = [self._row_to_session(r) for r in rows]

        if tags:
            sessions = [s for s in sessions if any(t in s.tags for t in tags)]

        for session in sessions:
            skill_rows = self.conn.execute(
                "SELECT skill_name FROM session_skills WHERE session_id = ?",
                (session.id,)
            ).fetchall()
            session.skills_used = [r["skill_name"] for r in skill_rows]

        return sessions

    def import_session(self, session: Session, replace: bool = False) -> str:
        """Import one session. Returns 'imported', 'replaced', or 'skipped'."""
        existing = self.conn.execute(
            "SELECT id FROM sessions WHERE id = ?", (session.id,)
        ).fetchone()

        if existing and not replace:
            return "skipped"

        if not existing:
            if not self.config.is_pro:
                current_count = self.session_count()
                if current_count >= self.config.max_free_sessions:
                    raise SessionLimitReachedError(
                        f"Free tier limit reached: {current_count} of "
                        f"{self.config.max_free_sessions} sessions stored. "
                        "Set your LORECONVO_PRO license key to unlock unlimited sessions."
                    )

        content_hash = (
            session.content_hash
            or self.compute_content_hash(session.title, session.summary, session.created_at)
        )
        origin_machine = session.origin_machine or self._get_origin_machine()
        self.conn.execute(
            """INSERT OR REPLACE INTO sessions
               (id, title, surface, project, start_date, end_date, summary,
                decisions, artifacts, open_questions, tags, created_at, source,
                shared_by, origin_machine, content_hash, external_tool_session)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                session.id, session.title, session.surface, session.project,
                session.start_date, session.end_date, session.summary,
                json.dumps(session.decisions), json.dumps(session.artifacts),
                json.dumps(session.open_questions), json.dumps(session.tags),
                session.created_at, session.source,
                session.shared_by, origin_machine, content_hash,
                1 if session.external_tool_session else 0,
            )
        )
        if existing:
            self.conn.execute(
                "DELETE FROM session_skills WHERE session_id = ?", (session.id,)
            )
        if session.skills_used:
            for skill_name in session.skills_used:
                self.conn.execute(
                    """INSERT OR REPLACE INTO session_skills
                       (session_id, skill_name, invocation_count)
                       VALUES (?, ?, 1)""",
                    (session.id, skill_name)
                )
        self.conn.commit()
        return "replaced" if existing else "imported"
