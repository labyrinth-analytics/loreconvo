"""Tests for BSL 1.1 free-tier session limit enforcement.

The Additional Use Grant in LICENSE allows personal/non-commercial use
up to 50 sessions (Config.max_free_sessions). Exceeding this raises
SessionLimitReachedError unless LORECONVO_PRO is set.

Added by Ron 2026-03-31 after Debbie confirmed code enforcement required.
"""

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from core.config import Config
from core.database import SessionDatabase, SessionLimitReachedError
from core.models import Session


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def make_db(tmp_path, max_free=50, monkeypatch=None):
    """Create a test database with a configurable session limit."""
    cfg = Config.__new__(Config)
    cfg.db_path = os.path.join(str(tmp_path), 'test.db')
    cfg.db_dir = str(tmp_path)
    cfg.max_free_sessions = max_free
    cfg.default_days_back = 30
    cfg.default_limit = 10
    if monkeypatch:
        monkeypatch.delenv("LORECONVO_PRO", raising=False)
    return SessionDatabase(cfg)


def make_session(n: int) -> Session:
    return Session(
        title=f"Session {n}",
        surface="code",
        summary=f"Summary for session {n}",
    )


# ---------------------------------------------------------------------------
# Config.is_pro
# ---------------------------------------------------------------------------

class TestIsProFlag:
    def test_not_pro_when_env_absent(self, monkeypatch):
        monkeypatch.delenv("LORECONVO_PRO", raising=False)
        cfg = Config.__new__(Config)
        cfg.db_path = ""
        cfg.max_free_sessions = 50
        assert cfg.is_pro is False

    def test_is_pro_when_env_set_to_1(self, monkeypatch):
        monkeypatch.setenv("LORECONVO_PRO", "1")
        cfg = Config.__new__(Config)
        cfg.db_path = ""
        cfg.max_free_sessions = 50
        assert cfg.is_pro is True

    def test_is_pro_when_env_set_to_any_value(self, monkeypatch):
        monkeypatch.setenv("LORECONVO_PRO", "true")
        cfg = Config.__new__(Config)
        cfg.db_path = ""
        cfg.max_free_sessions = 50
        assert cfg.is_pro is True

    def test_not_pro_when_env_empty_string(self, monkeypatch):
        monkeypatch.setenv("LORECONVO_PRO", "")
        cfg = Config.__new__(Config)
        cfg.db_path = ""
        cfg.max_free_sessions = 50
        assert cfg.is_pro is False

    def test_not_pro_when_env_whitespace_only(self, monkeypatch):
        monkeypatch.setenv("LORECONVO_PRO", "   ")
        cfg = Config.__new__(Config)
        cfg.db_path = ""
        cfg.max_free_sessions = 50
        assert cfg.is_pro is False


# ---------------------------------------------------------------------------
# Free-tier enforcement
# ---------------------------------------------------------------------------

class TestFreeTierEnforcement:
    def test_session_count_starts_at_zero(self, tmp_path, monkeypatch):
        db = make_db(tmp_path, max_free=3, monkeypatch=monkeypatch)
        assert db.session_count() == 0
        db.close()

    def test_save_sessions_up_to_limit_succeeds(self, tmp_path, monkeypatch):
        db = make_db(tmp_path, max_free=3, monkeypatch=monkeypatch)
        for i in range(3):
            sid = db.save_session(make_session(i))
            assert sid
        assert db.session_count() == 3
        db.close()

    def test_save_beyond_limit_raises_error(self, tmp_path, monkeypatch):
        db = make_db(tmp_path, max_free=3, monkeypatch=monkeypatch)
        for i in range(3):
            db.save_session(make_session(i))
        with pytest.raises(SessionLimitReachedError) as exc_info:
            db.save_session(make_session(99))
        assert "50" not in str(exc_info.value)  # uses configured limit (3)
        assert "3" in str(exc_info.value)
        assert "LORECONVO_PRO" in str(exc_info.value)
        db.close()

    def test_count_not_incremented_after_limit_error(self, tmp_path, monkeypatch):
        db = make_db(tmp_path, max_free=2, monkeypatch=monkeypatch)
        db.save_session(make_session(0))
        db.save_session(make_session(1))
        with pytest.raises(SessionLimitReachedError):
            db.save_session(make_session(2))
        # Count should still be 2, not 3
        assert db.session_count() == 2
        db.close()

    def test_error_message_contains_upgrade_info(self, tmp_path, monkeypatch):
        db = make_db(tmp_path, max_free=1, monkeypatch=monkeypatch)
        db.save_session(make_session(0))
        with pytest.raises(SessionLimitReachedError) as exc_info:
            db.save_session(make_session(1))
        msg = str(exc_info.value)
        assert "labyrinthanalyticsconsulting.com" in msg
        assert "LORECONVO_PRO" in msg
        db.close()

    def test_at_exactly_limit_raises_error(self, tmp_path, monkeypatch):
        """Boundary: count == max_free_sessions should block the (limit+1)th save."""
        db = make_db(tmp_path, max_free=5, monkeypatch=monkeypatch)
        for i in range(5):
            db.save_session(make_session(i))
        with pytest.raises(SessionLimitReachedError):
            db.save_session(make_session(5))
        db.close()


# ---------------------------------------------------------------------------
# Pro-tier bypass
# ---------------------------------------------------------------------------

class TestProTierBypass:
    def test_pro_mode_allows_saving_beyond_free_limit(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LORECONVO_PRO", "1")
        db = make_db(tmp_path, max_free=2, monkeypatch=None)
        # Save more than the free limit without error
        for i in range(5):
            sid = db.save_session(make_session(i))
            assert sid
        assert db.session_count() == 5
        db.close()

    def test_switching_to_non_pro_enforces_limit(self, tmp_path, monkeypatch):
        """If pro env is unset mid-use, subsequent saves are blocked at limit."""
        monkeypatch.setenv("LORECONVO_PRO", "1")
        db = make_db(tmp_path, max_free=2, monkeypatch=None)
        for i in range(3):
            db.save_session(make_session(i))
        assert db.session_count() == 3

        # Now remove pro flag -- next save should be blocked (count 3 > limit 2)
        monkeypatch.delenv("LORECONVO_PRO")
        with pytest.raises(SessionLimitReachedError):
            db.save_session(make_session(99))
        db.close()
