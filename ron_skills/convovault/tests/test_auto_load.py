"""Tests for the SessionStart auto-load hook (hooks/scripts/auto_load.py).

Run with:  python -m pytest tests/test_auto_load.py -v
"""

import json
import sys
import os
from datetime import datetime, timedelta
from pathlib import Path

# Allow importing the hook script directly
HOOK_DIR = Path(__file__).parent.parent / "hooks" / "scripts"
sys.path.insert(0, str(HOOK_DIR))

from auto_load import score_session, select_sessions, format_context, MAX_CONTEXT_CHARS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_session(
    title="Test session",
    summary="A test summary.",
    decisions=None,
    artifacts=None,
    open_questions=None,
    days_ago=1,
):
    """Return a session dict like those returned by query_recent_sessions."""
    start_dt = datetime.now() - timedelta(days=days_ago)
    return {
        "id": "test-id",
        "title": title,
        "summary": summary,
        "decisions": json.dumps(decisions or []),
        "artifacts": json.dumps(artifacts or []),
        "open_questions": json.dumps(open_questions or []),
        "tags": "[]",
        "start_date": start_dt.isoformat(),
        "end_date": start_dt.isoformat(),
    }


# ---------------------------------------------------------------------------
# score_session
# ---------------------------------------------------------------------------

class TestScoreSession:
    def _now(self):
        return datetime.now()

    def test_empty_session_gets_penalty(self):
        """Session with no content and no recency should score -2.
        Use days_ago=5 to avoid the 3-day recency bonus."""
        s = make_session(summary="", decisions=[], artifacts=[], open_questions=[], days_ago=5)
        assert score_session(s, self._now()) == -2

    def test_open_questions_adds_three(self):
        """Use days_ago=5 to test open_questions bonus in isolation."""
        s = make_session(open_questions=["What should we do next?"], summary="", days_ago=5)
        score = score_session(s, self._now())
        assert score == 3

    def test_two_decisions_adds_two(self):
        """Use days_ago=5 to test decisions bonus in isolation."""
        s = make_session(decisions=["Use SQLite", "Deploy to Vercel"], summary="", days_ago=5)
        score = score_session(s, self._now())
        # +2 for >= 2 decisions, no recency, no other bonuses
        assert score == 2

    def test_one_decision_adds_one(self):
        """Use days_ago=5 to test single decision in isolation."""
        s = make_session(decisions=["Use SQLite"], summary="", days_ago=5)
        score = score_session(s, self._now())
        assert score == 1

    def test_artifacts_adds_one(self):
        """Use days_ago=5 to test artifacts bonus in isolation."""
        s = make_session(artifacts=["src/server.py"], summary="", days_ago=5)
        score = score_session(s, self._now())
        assert score == 1

    def test_recent_session_gets_recency_bonus(self):
        """Session from 1 hour ago gets +2 recency bonus."""
        s = make_session(summary="Recent work.", days_ago=0)
        # days_ago=0 means start_date is ~now, within 24h threshold
        score = score_session(s, self._now())
        assert score >= 2  # recency bonus alone

    def test_three_day_old_session_gets_plus_one(self):
        s = make_session(summary="Work done 2 days ago.", days_ago=2)
        now = datetime.now()
        score = score_session(s, now)
        # 2-day-old session: within 3 days -> +1
        assert score >= 1

    def test_high_signal_session(self):
        """Session with open questions + decisions + artifacts should score >= 7."""
        s = make_session(
            open_questions=["Should we use Redis?", "What about auth?"],
            decisions=["Deploy on Render", "Use Pydantic v2"],
            artifacts=["src/server.py", "docs/INSTALL.md"],
            days_ago=0,
        )
        score = score_session(s, self._now())
        # +3 open_q, +2 decisions, +1 artifacts, +2 recency = 8
        assert score >= 7

    def test_malformed_json_fields_dont_crash(self):
        s = make_session()
        s["decisions"] = "not-json"
        s["open_questions"] = None
        s["artifacts"] = "{bad}"
        # Should not raise, should return a valid int
        score = score_session(s, self._now())
        assert isinstance(score, int)


# ---------------------------------------------------------------------------
# select_sessions
# ---------------------------------------------------------------------------

class TestSelectSessions:
    def test_empty_input_returns_empty(self):
        assert select_sessions([]) == []

    def test_returns_at_most_max_count(self):
        sessions = [make_session(title=f"s{i}", decisions=["d1", "d2"]) for i in range(10)]
        result = select_sessions(sessions, max_count=3)
        assert len(result) <= 3

    def test_noise_sessions_filtered_when_good_ones_exist(self):
        """Empty noise sessions should not appear when good sessions are available."""
        noise = make_session(title="Noise", summary="", decisions=[], artifacts=[], open_questions=[])
        good = make_session(
            title="Real work",
            decisions=["Decision A", "Decision B"],
            open_questions=["Follow-up?"],
        )
        result = select_sessions([noise, good], max_count=5)
        titles = [s["title"] for s in result]
        assert "Real work" in titles
        assert "Noise" not in titles

    def test_all_noise_falls_back_to_returning_sessions(self):
        """If everything scores <= 0, we still return something (top by score)."""
        sessions = [make_session(title=f"n{i}", summary="", decisions=[], artifacts=[], open_questions=[]) for i in range(3)]
        result = select_sessions(sessions, max_count=5)
        # Should return the sessions rather than empty list
        assert len(result) >= 1

    def test_higher_scored_sessions_come_first(self):
        low = make_session(title="Low", decisions=["one decision"])
        high = make_session(
            title="High",
            decisions=["d1", "d2"],
            open_questions=["open q"],
            artifacts=["file.py"],
        )
        result = select_sessions([low, high], max_count=5)
        assert result[0]["title"] == "High"


# ---------------------------------------------------------------------------
# format_context
# ---------------------------------------------------------------------------

class TestFormatContext:
    def test_empty_sessions_returns_empty_string(self):
        assert format_context([], "/some/cwd") == ""

    def test_includes_project_name_when_cwd_provided(self):
        s = make_session(title="My session", summary="Some work.")
        output = format_context([s], "/Users/debbie/projects/side_hustle")
        assert "side_hustle" in output

    def test_includes_open_questions_section(self):
        s = make_session(open_questions=["Should we use Redis?", "What about auth?"])
        output = format_context([s], "/cwd")
        assert "Open questions:" in output
        assert "Should we use Redis?" in output

    def test_includes_decisions_section(self):
        s = make_session(decisions=["Use SQLite", "Deploy on Render"])
        output = format_context([s], "/cwd")
        assert "Key decisions:" in output
        assert "Use SQLite" in output

    def test_includes_artifacts_section(self):
        s = make_session(artifacts=["src/server.py", "docs/INSTALL.md"])
        output = format_context([s], "/cwd")
        assert "Artifacts:" in output
        assert "src/server.py" in output

    def test_respects_max_context_chars_soft_cap(self):
        """Output should not greatly exceed MAX_CONTEXT_CHARS."""
        # Create many large sessions
        sessions = [
            make_session(
                title=f"Session {i}",
                summary="x" * 500,
                decisions=[f"Decision {j}" for j in range(5)],
                open_questions=[f"Question {j}" for j in range(4)],
                artifacts=[f"file_{j}.py" for j in range(5)],
            )
            for i in range(10)
        ]
        output = format_context(sessions, "/cwd")
        # Allow a reasonable margin (footer lines, etc.) above the cap
        assert len(output) < MAX_CONTEXT_CHARS + 500

    def test_no_cwd_shows_fallback_label(self):
        s = make_session()
        output = format_context([s], "")
        assert "no project filter" in output

    def test_summary_is_truncated_at_400_chars(self):
        long_summary = "A" * 600
        s = make_session(summary=long_summary)
        output = format_context([s], "/cwd")
        assert "AAAA" in output
        # Truncation marker
        assert "..." in output
        # The raw 600-char string should not appear verbatim
        assert long_summary not in output

    def test_footer_included(self):
        s = make_session()
        output = format_context([s], "/cwd")
        assert "avoid re-asking questions" in output
