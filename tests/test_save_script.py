"""
Tests for scripts/save_to_loreconvo.py -- the fallback session saver.

Validates DB discovery, save, read, and search operations work correctly
against a temp SQLite database.
"""

import json
import os
import sqlite3
import sys
import tempfile
import uuid
from pathlib import Path
from unittest import mock

import pytest

# Import the script module
SCRIPT_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))
import save_to_loreconvo as saver


# -- Fixtures --

@pytest.fixture
def temp_db(tmp_path):
    """Create a temp LoreConvo DB with the sessions table."""
    db_path = tmp_path / "sessions.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE sessions (
            id TEXT PRIMARY KEY,
            title TEXT,
            surface TEXT,
            project TEXT,
            start_date TEXT,
            end_date TEXT,
            summary TEXT,
            decisions TEXT,
            artifacts TEXT,
            open_questions TEXT,
            tags TEXT,
            created_at TEXT
        )
    """)
    conn.commit()
    conn.close()
    return str(db_path)


def _make_args(**kwargs):
    """Build a namespace matching argparse output for save_session."""
    defaults = dict(
        db_path=None,
        title="Test session",
        surface="qa",
        project=None,
        summary="A test summary.",
        decisions=None,
        artifacts=None,
        open_questions=None,
        tags=None,
        start_date=None,
        end_date=None,
        read=False,
        search=None,
        limit=5,
    )
    defaults.update(kwargs)

    class Args:
        pass

    args = Args()
    for k, v in defaults.items():
        setattr(args, k, v)
    return args


# -- Save tests --

class TestSaveSession:

    def test_save_creates_row(self, temp_db):
        args = _make_args(db_path=temp_db, title="QA daily", surface="qa", summary="All green.")
        session_id = saver.save_session(args)

        conn = sqlite3.connect(temp_db)
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
        conn.close()

        assert row is not None
        assert row["title"] == "QA daily"
        assert row["surface"] == "qa"
        assert row["summary"] == "All green."

    def test_save_generates_uuid(self, temp_db):
        args = _make_args(db_path=temp_db)
        session_id = saver.save_session(args)
        # Should be a valid UUID4
        parsed = uuid.UUID(session_id, version=4)
        assert str(parsed) == session_id

    def test_save_json_tags(self, temp_db):
        tags_json = json.dumps(["qa", "agent:meg"])
        args = _make_args(db_path=temp_db, tags=tags_json)
        session_id = saver.save_session(args)

        conn = sqlite3.connect(temp_db)
        row = conn.execute("SELECT tags FROM sessions WHERE id = ?", (session_id,)).fetchone()
        conn.close()

        assert json.loads(row[0]) == ["qa", "agent:meg"]

    def test_save_plain_string_tag(self, temp_db):
        args = _make_args(db_path=temp_db, tags="single-tag")
        session_id = saver.save_session(args)

        conn = sqlite3.connect(temp_db)
        row = conn.execute("SELECT tags FROM sessions WHERE id = ?", (session_id,)).fetchone()
        conn.close()

        assert json.loads(row[0]) == ["single-tag"]

    def test_save_empty_lists_for_none(self, temp_db):
        args = _make_args(db_path=temp_db)
        session_id = saver.save_session(args)

        conn = sqlite3.connect(temp_db)
        row = conn.execute("SELECT decisions, artifacts, open_questions, tags FROM sessions WHERE id = ?", (session_id,)).fetchone()
        conn.close()

        for field in row:
            assert json.loads(field) == []


# -- Read tests --

class TestReadSessions:

    def test_read_returns_sessions(self, temp_db, capsys):
        # Insert a session
        args = _make_args(db_path=temp_db, title="Read test", surface="code", summary="Testing read.")
        saver.save_session(args)

        # Now read
        read_args = _make_args(db_path=temp_db, read=True, limit=5)
        saver.read_sessions(read_args)
        output = capsys.readouterr().out

        assert "Read test" in output
        assert "code" in output

    def test_read_surface_filter(self, temp_db, capsys):
        saver.save_session(_make_args(db_path=temp_db, title="QA session", surface="qa", summary="QA"))
        saver.save_session(_make_args(db_path=temp_db, title="Code session", surface="code", summary="Code"))

        # Clear output from save calls
        capsys.readouterr()

        read_args = _make_args(db_path=temp_db, read=True, surface="qa", limit=5)
        saver.read_sessions(read_args)
        output = capsys.readouterr().out

        assert "QA session" in output
        assert "Code session" not in output

    def test_read_empty_db(self, temp_db, capsys):
        read_args = _make_args(db_path=temp_db, read=True, limit=5)
        saver.read_sessions(read_args)
        output = capsys.readouterr().out

        assert "No sessions found" in output


# -- Search tests --

class TestSearchSessions:

    def test_search_finds_match(self, temp_db, capsys):
        saver.save_session(_make_args(db_path=temp_db, title="Tax prep run", surface="code", summary="Filed taxes."))
        saver.save_session(_make_args(db_path=temp_db, title="QA run", surface="qa", summary="All passing."))

        # Clear output from save calls
        capsys.readouterr()

        search_args = _make_args(db_path=temp_db, search="tax", limit=5)
        saver.search_sessions(search_args)
        output = capsys.readouterr().out

        assert "Tax prep run" in output
        assert "QA run" not in output

    def test_search_no_match(self, temp_db, capsys):
        saver.save_session(_make_args(db_path=temp_db, title="QA run", surface="qa", summary="All passing."))

        # Clear output from save calls
        capsys.readouterr()

        search_args = _make_args(db_path=temp_db, search="nonexistent", limit=5)
        saver.search_sessions(search_args)
        output = capsys.readouterr().out

        assert "No sessions matching" in output


# -- DB discovery tests --

class TestDbDiscovery:

    def test_find_db_returns_none_when_missing(self):
        with mock.patch.object(os.path, "isfile", return_value=False):
            with mock.patch("glob.glob", return_value=[]):
                result = saver._find_loreconvo_db()
                assert result is None

    def test_find_db_returns_home_path(self, tmp_path):
        db_file = tmp_path / "sessions.db"
        db_file.touch()
        with mock.patch.object(os.path, "expanduser", return_value=str(db_file)):
            with mock.patch.object(os.path, "isfile", side_effect=lambda p: p == str(db_file)):
                result = saver._find_loreconvo_db()
                assert result == str(db_file)
