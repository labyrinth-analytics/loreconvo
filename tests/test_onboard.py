"""Tests for LoreConvo onboarding verification script."""

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest import mock

import pytest

# Add src and scripts to path
LORECONVO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LORECONVO_ROOT / "src"))
sys.path.insert(0, str(LORECONVO_ROOT / "scripts"))

from onboard_verify import (
    CheckResult,
    OnboardReport,
    check_claude_md,
    check_database_access,
    check_hooks,
    check_save_load,
    format_report,
    run_onboard,
)


class TestCheckResult:
    """Tests for CheckResult dataclass."""

    def test_basic_construction(self):
        r = CheckResult(name="Test", step="1", status="PASS", message="OK")
        assert r.name == "Test"
        assert r.step == "1"
        assert r.status == "PASS"
        assert r.message == "OK"
        assert r.detail == ""

    def test_with_detail(self):
        r = CheckResult(name="Test", step="2", status="FAIL", message="Bad", detail="Extra info")
        assert r.detail == "Extra info"


class TestOnboardReport:
    """Tests for OnboardReport dataclass."""

    def test_empty_report(self):
        report = OnboardReport()
        assert report.results == []
        assert report.test_session_id is None
        assert report.all_critical_pass is False

    def test_add_result(self):
        report = OnboardReport()
        report.add(CheckResult(name="Test", step="1", status="PASS", message="OK"))
        assert len(report.results) == 1

    def test_to_dict(self):
        report = OnboardReport()
        report.add(CheckResult(name="Test", step="1", status="PASS", message="OK"))
        report.test_session_id = "abc-123"
        report.all_critical_pass = True
        d = report.to_dict()
        assert d["test_session_id"] == "abc-123"
        assert d["all_critical_pass"] is True
        assert len(d["results"]) == 1
        assert d["results"][0]["name"] == "Test"
        assert d["results"][0]["status"] == "PASS"

    def test_to_dict_serializable(self):
        """Verify to_dict output is JSON-serializable."""
        report = OnboardReport()
        report.add(CheckResult(name="A", step="1", status="PASS", message="OK", detail="d"))
        report.add(CheckResult(name="B", step="2", status="FAIL", message="Bad"))
        output = json.dumps(report.to_dict())
        assert '"PASS"' in output
        assert '"FAIL"' in output


class TestCheckDatabaseAccess:
    """Tests for database access verification."""

    def test_pass_with_temp_db(self):
        """Verify database access passes with a real temp database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            report = OnboardReport()

            with mock.patch.dict(os.environ, {"LORECONVO_DB": db_path}):
                db = check_database_access(report)

            assert db is not None
            # Should have at least 2 results (steps 1 and 2)
            assert len(report.results) >= 2
            assert report.results[0].status == "PASS"
            assert report.results[1].status == "PASS"
            db.close()

    def test_fail_when_src_not_found(self):
        """Verify failure when src directory cannot be located."""
        report = OnboardReport()
        with mock.patch("onboard_verify._find_src_path", return_value=None):
            db = check_database_access(report)
        assert db is None
        assert report.results[0].status == "FAIL"
        assert "Cannot locate" in report.results[0].message


class TestCheckSaveLoad:
    """Tests for save/load/search cycle."""

    def test_skip_when_no_db(self):
        """All sub-steps should SKIP when database is None."""
        report = OnboardReport()
        check_save_load(None, report)
        assert len(report.results) == 3
        assert all(r.status == "SKIP" for r in report.results)

    def test_full_cycle_with_temp_db(self):
        """Test full save/load/search cycle with a real database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")

            from core.config import Config
            from core.database import SessionDatabase

            config = Config()
            config.db_path = db_path
            db = SessionDatabase(config)

            report = OnboardReport()
            check_save_load(db, report)

            # Should have 3 results for steps 3a, 3b, 3c
            assert len(report.results) == 3
            assert report.results[0].step == "3a"
            assert report.results[0].status == "PASS"
            assert report.results[1].step == "3b"
            assert report.results[1].status == "PASS"
            assert report.results[2].step == "3c"
            assert report.results[2].status == "PASS"

            # Test session ID should be set
            assert report.test_session_id is not None

            db.close()


class TestCheckHooks:
    """Tests for hooks configuration verification."""

    def test_pass_when_hooks_exist(self):
        """Should PASS when both hook files exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            hooks_dir = Path(tmpdir) / "hooks" / "scripts"
            hooks_dir.mkdir(parents=True)
            (hooks_dir / "on_session_start.sh").write_text("#!/bin/bash\n")
            (hooks_dir / "on_session_end.sh").write_text("#!/bin/bash\n")

            report = OnboardReport()
            # Patch to find hooks in our temp dir
            with mock.patch("onboard_verify.Path") as mock_path:
                # Make the script_dir.parent / "hooks" / "scripts" resolve to our temp
                mock_resolve = mock.MagicMock()
                mock_resolve.parent = Path(tmpdir)
                mock_path.return_value.resolve.return_value = mock_resolve

                # Simpler: just patch os.environ to set CLAUDE_PLUGIN_ROOT
                with mock.patch.dict(os.environ, {"CLAUDE_PLUGIN_ROOT": tmpdir}):
                    report = OnboardReport()
                    check_hooks(report)

            assert len(report.results) == 1
            assert report.results[0].status == "PASS"

    def test_fail_when_hooks_missing(self):
        """Should FAIL when hook files are missing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            hooks_dir = Path(tmpdir) / "hooks" / "scripts"
            hooks_dir.mkdir(parents=True)
            # Only create start hook, not end
            (hooks_dir / "on_session_start.sh").write_text("#!/bin/bash\n")

            with mock.patch.dict(os.environ, {"CLAUDE_PLUGIN_ROOT": tmpdir}):
                report = OnboardReport()
                check_hooks(report)

            assert report.results[0].status == "FAIL"
            assert "on_session_end.sh" in report.results[0].message

    def test_fail_when_dir_missing(self):
        """Should FAIL when hooks directory does not exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            fake_root = os.path.join(tmpdir, "nonexistent")
            with mock.patch.dict(os.environ, {"CLAUDE_PLUGIN_ROOT": fake_root}):
                report = OnboardReport()
                check_hooks(report)

            assert report.results[0].status == "FAIL"
            assert "not found" in report.results[0].message


class TestCheckClaudeMd:
    """Tests for CLAUDE.md integration check."""

    def test_skip_when_no_claude_md(self):
        """Should SKIP when CLAUDE.md does not exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            report = OnboardReport()
            check_claude_md(report, project_dir=tmpdir)
            assert report.results[0].status == "SKIP"

    def test_pass_when_loreconvo_mentioned(self):
        """Should PASS when CLAUDE.md mentions LoreConvo."""
        with tempfile.TemporaryDirectory() as tmpdir:
            claude_md = Path(tmpdir) / "CLAUDE.md"
            claude_md.write_text("# My Project\n\nUse LoreConvo for session memory.\n")
            report = OnboardReport()
            check_claude_md(report, project_dir=tmpdir)
            assert report.results[0].status == "PASS"

    def test_pass_when_save_session_mentioned(self):
        """Should PASS when CLAUDE.md mentions save_session."""
        with tempfile.TemporaryDirectory() as tmpdir:
            claude_md = Path(tmpdir) / "CLAUDE.md"
            claude_md.write_text("# My Project\n\nCall save_session at end.\n")
            report = OnboardReport()
            check_claude_md(report, project_dir=tmpdir)
            assert report.results[0].status == "PASS"

    def test_suggest_when_no_mention(self):
        """Should SUGGEST when CLAUDE.md exists but no LoreConvo mention."""
        with tempfile.TemporaryDirectory() as tmpdir:
            claude_md = Path(tmpdir) / "CLAUDE.md"
            claude_md.write_text("# My Project\n\nSome other content.\n")
            report = OnboardReport()
            check_claude_md(report, project_dir=tmpdir)
            assert report.results[0].status == "SUGGEST"


class TestFormatReport:
    """Tests for report formatting."""

    def test_pass_report_contains_ok(self):
        report = OnboardReport()
        report.add(CheckResult(name="Test", step="1", status="PASS", message="Good"))
        report.all_critical_pass = True
        output = format_report(report)
        assert "[OK]" in output
        assert "fully operational" in output

    def test_fail_report_contains_fail(self):
        report = OnboardReport()
        report.add(CheckResult(name="Test", step="1", status="FAIL", message="Bad thing"))
        report.all_critical_pass = False
        output = format_report(report)
        assert "[FAIL]" in output
        assert "need attention" in output

    def test_report_ascii_only(self):
        """Verify report output uses only ASCII characters."""
        report = OnboardReport()
        report.add(CheckResult(name="Test", step="1", status="PASS", message="OK"))
        report.add(CheckResult(name="Test2", step="2", status="FAIL", message="Bad", detail="Info"))
        report.all_critical_pass = False
        report.test_session_id = "abc-123"
        output = format_report(report)
        assert all(ord(c) < 128 for c in output), "Report contains non-ASCII characters"

    def test_report_includes_session_id(self):
        report = OnboardReport()
        report.test_session_id = "test-uuid-123"
        report.all_critical_pass = True
        output = format_report(report)
        assert "test-uuid-123" in output


class TestRunOnboard:
    """Integration tests for the full onboarding flow."""

    def test_full_run_with_temp_db(self):
        """Run full onboarding against a temporary database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")

            # Create CLAUDE.md with LoreConvo mention
            claude_md = Path(tmpdir) / "CLAUDE.md"
            claude_md.write_text("# Test\nUse LoreConvo.\n")

            # Create hooks
            hooks_dir = Path(tmpdir) / "hooks" / "scripts"
            hooks_dir.mkdir(parents=True)
            (hooks_dir / "on_session_start.sh").write_text("#!/bin/bash\n")
            (hooks_dir / "on_session_end.sh").write_text("#!/bin/bash\n")

            with mock.patch.dict(os.environ, {
                "LORECONVO_DB": db_path,
                "CLAUDE_PLUGIN_ROOT": tmpdir,
            }):
                report = run_onboard(project_dir=tmpdir, cleanup=False)

            assert report.all_critical_pass is True
            assert report.test_session_id is not None
            # Should have results for all 5 steps (7 sub-checks)
            assert len(report.results) >= 6

    def test_cleanup_deletes_test_session(self):
        """Verify cleanup=True removes the test session."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")

            hooks_dir = Path(tmpdir) / "hooks" / "scripts"
            hooks_dir.mkdir(parents=True)
            (hooks_dir / "on_session_start.sh").write_text("#!/bin/bash\n")
            (hooks_dir / "on_session_end.sh").write_text("#!/bin/bash\n")

            with mock.patch.dict(os.environ, {
                "LORECONVO_DB": db_path,
                "CLAUDE_PLUGIN_ROOT": tmpdir,
            }):
                report = run_onboard(project_dir=tmpdir, cleanup=True)

            assert report.test_session_id is not None
            # Verify session was deleted
            import sqlite3
            conn = sqlite3.connect(db_path)
            row = conn.execute(
                "SELECT id FROM sessions WHERE id = ?",
                (report.test_session_id,)
            ).fetchone()
            conn.close()
            assert row is None, "Test session should have been deleted"
