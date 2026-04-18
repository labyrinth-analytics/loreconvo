"""Tests for LoreConvo FTS v2 migration and query sanitization.

MEG-00063: Covers fresh-install FTS creation, v1-to-v2 migration,
v2 startup idempotency, and _sanitize_fts_query edge cases.
"""

import os
import sqlite3
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from core.config import Config
from core.database import SCHEMA_SQL, SessionDatabase
from core.models import Session


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_cfg(tmp_path):
    """Config pointing at a temp directory, bypassing env-var discovery."""
    cfg = Config.__new__(Config)
    cfg.db_path = os.path.join(str(tmp_path), 'test.db')
    return cfg


FTS_V1_SQL = """
CREATE VIRTUAL TABLE IF NOT EXISTS sessions_fts USING fts5(
    title, summary, decisions,
    content=sessions, content_rowid=rowid
);
"""

FTS_V1_TRIGGERS = """
CREATE TRIGGER IF NOT EXISTS sessions_ai AFTER INSERT ON sessions BEGIN
    INSERT INTO sessions_fts(rowid, title, summary, decisions)
    VALUES (new.rowid, new.title, new.summary, new.decisions);
END;
CREATE TRIGGER IF NOT EXISTS sessions_au AFTER UPDATE ON sessions BEGIN
    UPDATE sessions_fts SET title = new.title, summary = new.summary,
        decisions = new.decisions WHERE rowid = old.rowid;
END;
CREATE TRIGGER IF NOT EXISTS sessions_ad AFTER DELETE ON sessions BEGIN
    DELETE FROM sessions_fts WHERE rowid = old.rowid;
END;
"""


def _make_v1_db(db_path, sessions=None):
    """Create a v1-schema DB (FTS without tags/open_questions) with optional seed data."""
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA_SQL)
    conn.executescript(FTS_V1_SQL)
    conn.executescript(FTS_V1_TRIGGERS)
    if sessions:
        for s in sessions:
            conn.execute(
                """INSERT INTO sessions
                   (id, title, surface, start_date, summary, decisions, tags, open_questions)
                   VALUES (?, ?, 'code', '2026-04-01', ?, ?, ?, ?)""",
                (s['id'], s['title'], s.get('summary', ''), s.get('decisions', ''),
                 s.get('tags', '[]'), s.get('open_questions', '')),
            )
            conn.execute(
                "INSERT INTO sessions_fts(rowid, title, summary, decisions) "
                "SELECT rowid, title, summary, decisions FROM sessions WHERE id = ?",
                (s['id'],),
            )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Fresh-install FTS creation
# ---------------------------------------------------------------------------

class TestFreshInstall:
    def test_fts_table_has_v2_columns(self, tmp_path):
        """A brand-new DB gets an FTS5 table with all v2 columns."""
        db = SessionDatabase(make_cfg(tmp_path))
        cursor = db.conn.execute("SELECT * FROM sessions_fts LIMIT 0")
        col_names = [d[0] for d in cursor.description]
        for col in ('title', 'summary', 'decisions', 'tags', 'open_questions'):
            assert col in col_names, f"Column '{col}' missing from sessions_fts"
        db.close()

    def test_triggers_exist_on_fresh_db(self, tmp_path):
        """INSERT/UPDATE/DELETE triggers are created on a fresh DB."""
        db = SessionDatabase(make_cfg(tmp_path))
        rows = db.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger' AND tbl_name='sessions'"
        ).fetchall()
        trigger_names = {r[0] for r in rows}
        assert 'sessions_ai' in trigger_names
        assert 'sessions_au' in trigger_names
        assert 'sessions_ad' in trigger_names
        db.close()

    def test_insert_trigger_populates_fts(self, tmp_path):
        """A saved session is immediately searchable via FTS."""
        db = SessionDatabase(make_cfg(tmp_path))
        s = Session(title='FTS fresh install test', surface='code',
                    summary='Trigger should sync this', tags=['agent:ron'])
        db.save_session(s)
        results = db.search_sessions('fresh install')
        assert len(results) == 1
        assert results[0].session.title == 'FTS fresh install test'
        db.close()


# ---------------------------------------------------------------------------
# v1-to-v2 migration
# ---------------------------------------------------------------------------

class TestV1ToV2Migration:
    def test_migration_adds_missing_columns(self, tmp_path):
        """Opening a v1 DB adds tags and open_questions to sessions_fts."""
        db_path = os.path.join(str(tmp_path), 'test.db')
        _make_v1_db(db_path)
        db = SessionDatabase(make_cfg(tmp_path))
        cursor = db.conn.execute("SELECT * FROM sessions_fts LIMIT 0")
        col_names = [d[0] for d in cursor.description]
        assert 'tags' in col_names
        assert 'open_questions' in col_names
        db.close()

    def test_migration_preserves_existing_sessions(self, tmp_path):
        """Sessions present before migration remain searchable afterward."""
        db_path = os.path.join(str(tmp_path), 'test.db')
        _make_v1_db(db_path, sessions=[
            {'id': 'abc-1', 'title': 'Pre-migration session', 'summary': 'Old data kept'},
            {'id': 'abc-2', 'title': 'Another old session', 'summary': 'Still here'},
        ])
        db = SessionDatabase(make_cfg(tmp_path))
        results = db.search_sessions('Pre-migration')
        assert len(results) == 1
        assert results[0].session.title == 'Pre-migration session'
        db.close()

    def test_migration_repopulates_fts_from_sessions(self, tmp_path):
        """After v1->v2 migration, session data is searchable (not just title)."""
        db_path = os.path.join(str(tmp_path), 'test.db')
        _make_v1_db(db_path, sessions=[
            {'id': 'xyz-1', 'title': 'Agent work log', 'summary': 'zephyr keyword in summary'},
        ])
        db = SessionDatabase(make_cfg(tmp_path))
        results = db.search_sessions('zephyr')
        assert len(results) == 1
        db.close()

    def test_migration_rebuilds_triggers(self, tmp_path):
        """After v1->v2 migration, new sessions are still synced to FTS."""
        db_path = os.path.join(str(tmp_path), 'test.db')
        _make_v1_db(db_path)
        db = SessionDatabase(make_cfg(tmp_path))
        s = Session(title='Post-migration session', surface='code',
                    summary='Added after upgrade')
        db.save_session(s)
        results = db.search_sessions('Post-migration')
        assert len(results) == 1
        db.close()


# ---------------------------------------------------------------------------
# v2 startup idempotency
# ---------------------------------------------------------------------------

class TestV2Idempotency:
    def test_reopening_v2_db_does_not_corrupt_data(self, tmp_path):
        """Re-opening a v2 DB (simulating restart) leaves search results intact."""
        cfg = make_cfg(tmp_path)
        db = SessionDatabase(cfg)
        s = Session(title='Idempotency check', surface='code',
                    summary='Should survive restart')
        db.save_session(s)
        db.close()

        db2 = SessionDatabase(cfg)
        results = db2.search_sessions('Idempotency')
        assert len(results) == 1
        assert results[0].session.title == 'Idempotency check'
        db2.close()

    def test_reopening_does_not_duplicate_fts_rows(self, tmp_path):
        """Re-opening a v2 DB does not create duplicate FTS entries."""
        cfg = make_cfg(tmp_path)
        db = SessionDatabase(cfg)
        s = Session(title='Dedup check', surface='code', summary='Only one copy')
        db.save_session(s)
        db.close()

        db2 = SessionDatabase(cfg)
        results = db2.search_sessions('Dedup check')
        assert len(results) == 1
        db2.close()

    def test_reopening_preserves_trigger_names(self, tmp_path):
        """After a v2 restart the trigger names are still correct."""
        cfg = make_cfg(tmp_path)
        db = SessionDatabase(cfg)
        db.close()

        db2 = SessionDatabase(cfg)
        rows = db2.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger' AND tbl_name='sessions'"
        ).fetchall()
        trigger_names = {r[0] for r in rows}
        assert 'sessions_ai' in trigger_names
        assert 'sessions_au' in trigger_names
        assert 'sessions_ad' in trigger_names
        db2.close()


# ---------------------------------------------------------------------------
# _sanitize_fts_query edge cases
# ---------------------------------------------------------------------------

class TestSanitizeFtsQuery:
    def test_single_word(self):
        assert SessionDatabase._sanitize_fts_query("stripe") == '"stripe"'

    def test_two_words_implicit_and(self):
        assert SessionDatabase._sanitize_fts_query("stripe billing") == '"stripe" "billing"'

    def test_three_words(self):
        assert SessionDatabase._sanitize_fts_query("stripe billing integration") == \
            '"stripe" "billing" "integration"'

    def test_hyphen_treated_as_literal(self):
        assert SessionDatabase._sanitize_fts_query("fts-migration") == '"fts-migration"'

    def test_colon_treated_as_literal(self):
        assert SessionDatabase._sanitize_fts_query("agent:ron") == '"agent:ron"'

    def test_mixed_hyphen_and_spaces(self):
        assert SessionDatabase._sanitize_fts_query("K-1 parser waiting") == \
            '"K-1" "parser" "waiting"'

    def test_empty_string(self):
        assert SessionDatabase._sanitize_fts_query("") == '""'

    def test_whitespace_only(self):
        assert SessionDatabase._sanitize_fts_query("   ") == '""'

    def test_embedded_double_quotes_stripped(self):
        # Quotes inside a token are stripped to prevent FTS5 parse errors
        result = SessionDatabase._sanitize_fts_query('has"quote')
        assert result == '"hasquote"'

    def test_leading_trailing_whitespace_ignored(self):
        assert SessionDatabase._sanitize_fts_query("  stripe  ") == '"stripe"'

    def test_multiple_spaces_between_words(self):
        result = SessionDatabase._sanitize_fts_query("a  b")
        assert '"a"' in result
        assert '"b"' in result

    def test_result_is_fts5_executable(self, tmp_path):
        """Sanitized queries must not raise OperationalError when used in MATCH."""
        db = SessionDatabase(make_cfg(tmp_path))
        for raw in ("agent:ron", "fts-migration", "K-1 parser", "", "multi word query"):
            sanitized = SessionDatabase._sanitize_fts_query(raw)
            # Should not raise
            db.conn.execute(
                "SELECT rowid FROM sessions_fts WHERE sessions_fts MATCH ?", (sanitized,)
            ).fetchall()
        db.close()
