"""Tests for LoreConvo CLI (src/cli.py).

Covers the Click CLI commands: save, list, search, export, skill-history,
skills list, and stats. Uses Click's CliRunner for isolated invocation.
"""

import json
import os
import sys
import tempfile
import unittest

# Ensure src/ is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from click.testing import CliRunner

from core.config import Config
from core.database import SessionDatabase
from core.models import Session


def _make_db():
    """Create a temp DB and return (db, db_path)."""
    tmp = tempfile.mkdtemp()
    db_path = os.path.join(tmp, "test_cli.db")
    cfg = Config.__new__(Config)
    cfg.db_path = db_path
    db = SessionDatabase(cfg)
    return db, db_path


def _seed_session(db, title="Test Session", project="side_hustle", surface="code"):
    """Insert a session and return its id."""
    s = Session(
        title=title,
        surface=surface,
        summary="A test summary for CLI testing.",
        project=project,
        decisions=["Decided to use SQLite"],
        skills_used=["sql-optimizer"],
        tags=["test"],
    )
    return db.save_session(s)


class TestCliSave(unittest.TestCase):
    """Test the 'save' command."""

    def setUp(self):
        self.db, self.db_path = _make_db()
        self.runner = CliRunner()

    def test_save_creates_session(self):
        # Monkey-patch the module-level db object
        import cli as cli_mod
        original_db = cli_mod.db
        cli_mod.db = self.db
        try:
            result = self.runner.invoke(cli_mod.cli, [
                "save", "-t", "My Title", "-s", "code", "-m", "My summary",
                "-p", "testproj",
            ])
            self.assertEqual(result.exit_code, 0, result.output)
            self.assertIn("Saved session", result.output)
            self.assertIn("My Title", result.output)
        finally:
            cli_mod.db = original_db

    def test_save_requires_title(self):
        import cli as cli_mod
        result = self.runner.invoke(cli_mod.cli, [
            "save", "-s", "code", "-m", "No title given",
        ])
        self.assertNotEqual(result.exit_code, 0)


class TestCliList(unittest.TestCase):
    """Test the 'list' command."""

    def setUp(self):
        self.db, self.db_path = _make_db()
        self.runner = CliRunner()

    def test_list_empty(self):
        import cli as cli_mod
        original_db = cli_mod.db
        cli_mod.db = self.db
        try:
            result = self.runner.invoke(cli_mod.cli, ["list"])
            self.assertEqual(result.exit_code, 0)
            self.assertIn("No sessions found", result.output)
        finally:
            cli_mod.db = original_db

    def test_list_shows_sessions(self):
        _seed_session(self.db, title="Alpha Session")
        import cli as cli_mod
        original_db = cli_mod.db
        cli_mod.db = self.db
        try:
            result = self.runner.invoke(cli_mod.cli, ["list"])
            self.assertEqual(result.exit_code, 0)
            self.assertIn("Alpha Session", result.output)
            self.assertIn("1 session(s)", result.output)
        finally:
            cli_mod.db = original_db


class TestCliSearch(unittest.TestCase):
    """Test the 'search' command."""

    def setUp(self):
        self.db, self.db_path = _make_db()
        self.runner = CliRunner()

    def test_search_no_results(self):
        import cli as cli_mod
        original_db = cli_mod.db
        cli_mod.db = self.db
        try:
            result = self.runner.invoke(cli_mod.cli, ["search", "nonexistent"])
            self.assertEqual(result.exit_code, 0)
            self.assertIn("No sessions found", result.output)
        finally:
            cli_mod.db = original_db

    def test_search_finds_session(self):
        _seed_session(self.db, title="SQLite optimization session")
        import cli as cli_mod
        original_db = cli_mod.db
        cli_mod.db = self.db
        try:
            result = self.runner.invoke(cli_mod.cli, ["search", "SQLite"])
            self.assertEqual(result.exit_code, 0)
            self.assertIn("SQLite optimization session", result.output)
        finally:
            cli_mod.db = original_db


class TestCliExport(unittest.TestCase):
    """Test the 'export' command."""

    def setUp(self):
        self.db, self.db_path = _make_db()
        self.runner = CliRunner()

    def test_export_no_args_shows_help(self):
        import cli as cli_mod
        original_db = cli_mod.db
        cli_mod.db = self.db
        try:
            result = self.runner.invoke(cli_mod.cli, ["export"])
            self.assertEqual(result.exit_code, 0)
            self.assertIn("Provide a session_id or use --last", result.output)
        finally:
            cli_mod.db = original_db

    def test_export_last_markdown(self):
        _seed_session(self.db, title="Export Test Session")
        import cli as cli_mod
        original_db = cli_mod.db
        cli_mod.db = self.db
        try:
            result = self.runner.invoke(cli_mod.cli, ["export", "--last"])
            self.assertEqual(result.exit_code, 0)
            self.assertIn("# Context from Previous Session", result.output)
            self.assertIn("Export Test Session", result.output)
            self.assertIn("## Summary", result.output)
        finally:
            cli_mod.db = original_db

    def test_export_last_json(self):
        _seed_session(self.db, title="JSON Export Test")
        import cli as cli_mod
        original_db = cli_mod.db
        cli_mod.db = self.db
        try:
            result = self.runner.invoke(cli_mod.cli, ["export", "--last", "--format", "json"])
            self.assertEqual(result.exit_code, 0)
            data = json.loads(result.output)
            self.assertEqual(data["title"], "JSON Export Test")
            self.assertIn("decisions", data)
            self.assertIn("artifacts", data)
        finally:
            cli_mod.db = original_db

    def test_export_nonexistent_id(self):
        import cli as cli_mod
        original_db = cli_mod.db
        cli_mod.db = self.db
        try:
            result = self.runner.invoke(cli_mod.cli, ["export", "fake-id-12345"])
            self.assertEqual(result.exit_code, 0)
            self.assertIn("not found", result.output)
        finally:
            cli_mod.db = original_db


class TestCliSkills(unittest.TestCase):
    """Test the 'skills list' command."""

    def setUp(self):
        self.db, self.db_path = _make_db()
        self.runner = CliRunner()

    def test_skills_list_empty(self):
        import cli as cli_mod
        original_db = cli_mod.db
        cli_mod.db = self.db
        try:
            result = self.runner.invoke(cli_mod.cli, ["skills", "list"])
            self.assertEqual(result.exit_code, 0)
            self.assertIn("No skills recorded", result.output)
        finally:
            cli_mod.db = original_db

    def test_skills_list_shows_skills(self):
        _seed_session(self.db, title="Skill test session")
        import cli as cli_mod
        original_db = cli_mod.db
        cli_mod.db = self.db
        try:
            result = self.runner.invoke(cli_mod.cli, ["skills", "list"])
            self.assertEqual(result.exit_code, 0)
            self.assertIn("sql-optimizer", result.output)
            self.assertIn("1 distinct skill(s)", result.output)
        finally:
            cli_mod.db = original_db


class TestCliStats(unittest.TestCase):
    """Test the 'stats' command."""

    def setUp(self):
        self.db, self.db_path = _make_db()
        self.runner = CliRunner()

    def test_stats_empty_db(self):
        import cli as cli_mod
        original_db = cli_mod.db
        cli_mod.db = self.db
        try:
            result = self.runner.invoke(cli_mod.cli, ["stats"])
            self.assertEqual(result.exit_code, 0)
            self.assertIn("Total sessions: 0", result.output)
        finally:
            cli_mod.db = original_db

    def test_stats_with_sessions(self):
        _seed_session(self.db, title="Stats test", project="myproject")
        import cli as cli_mod
        original_db = cli_mod.db
        cli_mod.db = self.db
        try:
            result = self.runner.invoke(cli_mod.cli, ["stats"])
            self.assertEqual(result.exit_code, 0)
            self.assertIn("Total sessions: 1", result.output)
            # Projects count comes from the projects table (explicit registration),
            # not from distinct project values in sessions. So 0 is expected here.
            self.assertIn("Most recent: Stats test", result.output)
        finally:
            cli_mod.db = original_db


if __name__ == "__main__":
    unittest.main()
