"""Tests for NULL-id migration and save_session validation.

Covers the two changes from commit f43e296:
1. _init_schema() now patches NULL id rows with generated UUIDs
2. save_session() raises ValueError if session.id is falsy
"""

import sqlite3
import json
import tempfile
import os
import pytest
import sys

# Add src/ to path so we can import core modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core.config import Config
from core.database import SessionDatabase
from core.models import Session


class TestNullIdMigration:
    """Verify that _init_schema patches rows with NULL id."""

    def setup_method(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.db_path = self.tmp.name

    def teardown_method(self):
        os.unlink(self.db_path)

    def _seed_null_rows(self, count=3):
        """Insert rows with NULL id directly via SQL (bypassing Session dataclass).

        Uses a schema WITHOUT the NOT NULL constraint on id (the old schema)
        so we can seed NULL rows, then let SessionDatabase._init_schema() fix them.
        """
        conn = sqlite3.connect(self.db_path)
        # Use the OLD schema (before the NOT NULL fix) so NULLs can be inserted
        conn.execute(
            """CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                surface TEXT NOT NULL,
                project TEXT,
                start_date TEXT NOT NULL,
                end_date TEXT,
                summary TEXT,
                decisions TEXT,
                artifacts TEXT,
                open_questions TEXT,
                tags TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            )"""
        )
        # Also create the supporting tables so _init_schema() doesn't fail
        conn.execute(
            """CREATE TABLE IF NOT EXISTS session_skills (
                session_id TEXT NOT NULL REFERENCES sessions(id),
                skill_name TEXT NOT NULL,
                skill_source TEXT,
                invocation_count INTEGER DEFAULT 1,
                PRIMARY KEY (session_id, skill_name)
            )"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS projects (
                name TEXT PRIMARY KEY,
                description TEXT,
                expected_skills TEXT,
                default_persona TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            )"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS persona_sessions (
                persona_name TEXT NOT NULL,
                session_id TEXT NOT NULL REFERENCES sessions(id),
                relevance_note TEXT,
                PRIMARY KEY (persona_name, session_id)
            )"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS session_links (
                from_session_id TEXT NOT NULL REFERENCES sessions(id),
                to_session_id TEXT NOT NULL REFERENCES sessions(id),
                link_type TEXT DEFAULT 'continues',
                PRIMARY KEY (from_session_id, to_session_id)
            )"""
        )
        # Create FTS table and triggers to match full schema
        conn.execute(
            """CREATE VIRTUAL TABLE IF NOT EXISTS sessions_fts USING fts5(
                title, summary, decisions, content=sessions, content_rowid=rowid
            )"""
        )
        conn.executescript("""
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
        """)
        for i in range(count):
            conn.execute(
                """INSERT INTO sessions (id, title, surface, start_date, summary,
                   decisions, artifacts, open_questions, tags)
                   VALUES (NULL, ?, 'code', datetime('now'), 'test', '[]', '[]', '[]', '[]')""",
                (f"null-row-{i}",),
            )
        conn.commit()
        # Verify they are NULL
        nulls = conn.execute("SELECT COUNT(*) FROM sessions WHERE id IS NULL").fetchone()[0]
        conn.close()
        assert nulls == count, f"Expected {count} NULL rows, got {nulls}"

    def test_null_rows_get_uuid_on_init(self):
        """Opening the database should patch all NULL-id rows."""
        self._seed_null_rows(3)
        config = Config()
        config.db_path = self.db_path
        db = SessionDatabase(config)
        # After init, no NULL rows should remain
        nulls = db.conn.execute("SELECT COUNT(*) FROM sessions WHERE id IS NULL").fetchone()[0]
        assert nulls == 0
        # All rows should have valid UUIDs
        rows = db.conn.execute("SELECT id FROM sessions").fetchall()
        assert len(rows) == 3
        for row in rows:
            assert row["id"] is not None
            assert len(row["id"]) == 36  # UUID format: 8-4-4-4-12
            assert "-" in row["id"]
        db.close()

    def test_each_null_row_gets_unique_uuid(self):
        """Each NULL row should get a distinct UUID."""
        self._seed_null_rows(5)
        config = Config()
        config.db_path = self.db_path
        db = SessionDatabase(config)
        rows = db.conn.execute("SELECT id FROM sessions").fetchall()
        ids = [row["id"] for row in rows]
        assert len(set(ids)) == 5, "All generated UUIDs should be unique"
        db.close()

    def test_no_null_rows_skips_migration(self):
        """If no NULL rows exist, migration should be a no-op."""
        config = Config()
        config.db_path = self.db_path
        db = SessionDatabase(config)
        # Just verify no error on clean init
        count = db.conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        assert count == 0
        db.close()

    def test_existing_valid_ids_preserved(self):
        """Rows with valid ids should NOT be touched by the migration."""
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            """CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                surface TEXT NOT NULL,
                project TEXT,
                start_date TEXT NOT NULL,
                end_date TEXT,
                summary TEXT,
                decisions TEXT,
                artifacts TEXT,
                open_questions TEXT,
                tags TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            )"""
        )
        conn.execute(
            """INSERT INTO sessions (id, title, surface, start_date, summary,
               decisions, artifacts, open_questions, tags)
               VALUES ('keep-this-id', 'valid row', 'code', datetime('now'), 'test', '[]', '[]', '[]', '[]')"""
        )
        conn.commit()
        conn.close()

        config = Config()
        config.db_path = self.db_path
        db = SessionDatabase(config)
        row = db.conn.execute("SELECT id FROM sessions WHERE title = 'valid row'").fetchone()
        assert row["id"] == "keep-this-id"
        db.close()


class TestSaveSessionValidation:
    """Verify save_session rejects sessions without ids."""

    def setup_method(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        config = Config()
        config.db_path = self.tmp.name
        self.db = SessionDatabase(config)

    def teardown_method(self):
        self.db.close()
        os.unlink(self.tmp.name)

    def test_normal_session_saves(self):
        """A Session created via the dataclass (auto-generated UUID) should save fine."""
        s = Session(title="test", surface="code", summary="ok")
        sid = self.db.save_session(s)
        assert sid is not None
        assert len(sid) == 36

    def test_none_id_raises_value_error(self):
        """A Session with id=None should raise ValueError."""
        s = Session(title="bad", surface="code", summary="nope")
        s.id = None
        with pytest.raises(ValueError, match="Session id must not be None"):
            self.db.save_session(s)

    def test_empty_string_id_raises_value_error(self):
        """A Session with id='' should raise ValueError."""
        s = Session(title="bad", surface="code", summary="nope")
        s.id = ""
        with pytest.raises(ValueError, match="Session id must not be None"):
            self.db.save_session(s)

    def test_error_message_mentions_dataclass(self):
        """The error message should guide the user to use Session dataclass."""
        s = Session(title="bad", surface="code")
        s.id = None
        with pytest.raises(ValueError, match="Session dataclass"):
            self.db.save_session(s)


class TestAutoSaveInputGuard:
    """Test the auto_save.py input_val guard for non-dict input blocks."""

    def test_input_as_string_does_not_crash(self):
        """When block['input'] is a string instead of dict, skill extraction should handle it."""
        # Simulate a tool_use block where input is a string (malformed)
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "hooks", "scripts"))
        from auto_save import parse_transcript

        # Create a temp transcript with a string input value
        import tempfile
        content = json.dumps({
            "type": "assistant",
            "message": {
                "role": "assistant",
                "content": [
                    {"type": "tool_use", "name": "Skill", "input": "just-a-string"}
                ]
            }
        }) + "\n" + json.dumps({
            "type": "user",
            "message": {"role": "user", "content": "hello"}
        }) + "\n"

        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False)
        tmp.write(content)
        tmp.close()

        try:
            result = parse_transcript(tmp.name)
            # Should not crash; the tool_use should fall back to "Skill"
            if result:
                assert "Skill" in result.get("tools_used", [])
        finally:
            os.unlink(tmp.name)

    def test_input_as_none_does_not_crash(self):
        """When block['input'] is None, skill extraction should handle it."""
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "hooks", "scripts"))
        from auto_save import parse_transcript

        content = json.dumps({
            "type": "assistant",
            "message": {
                "role": "assistant",
                "content": [
                    {"type": "tool_use", "name": "Skill", "input": None}
                ]
            }
        }) + "\n" + json.dumps({
            "type": "user",
            "message": {"role": "user", "content": "hello"}
        }) + "\n"

        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False)
        tmp.write(content)
        tmp.close()

        try:
            result = parse_transcript(tmp.name)
            if result:
                assert "Skill" in result.get("tools_used", [])
        finally:
            os.unlink(tmp.name)
