"""Tests for vault_suggest functionality."""

import json
import sys
import os
import uuid
from datetime import datetime, timedelta

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core.database import SessionDatabase
from core.config import Config
from core.models import Session


def make_db():
    """Create an in-memory database for testing."""
    config = Config()
    config.db_path = ":memory:"
    db = SessionDatabase(config)
    return db


def make_session(
    title="Test session",
    days_ago=1,
    project=None,
    decisions=None,
    open_questions=None,
    skills_used=None,
    tags=None,
):
    """Helper to create a session with sensible defaults."""
    start = (datetime.now() - timedelta(days=days_ago)).isoformat()
    return Session(
        id=str(uuid.uuid4()),
        title=title,
        surface="code",
        project=project,
        start_date=start,
        summary="Summary for: " + title,
        decisions=decisions or [],
        open_questions=open_questions or [],
        tags=tags or [],
        skills_used=skills_used or [],
    )


def test_empty_database():
    """vault_suggest returns empty results on a fresh database."""
    db = make_db()
    result = db.get_suggestions()
    assert result["suggestions"] == [], "Expected no suggestions"
    assert result["skill_gaps"] == [], "Expected no skill gaps"
    assert result["metadata"]["total_sessions_scanned"] == 0
    assert result["metadata"]["suggestions_returned"] == 0
    print("[OK] test_empty_database")


def test_session_with_open_questions():
    """Sessions with open questions are surfaced as suggestions."""
    db = make_db()
    s = make_session(
        title="Auth middleware review",
        days_ago=2,
        open_questions=["Should we use JWT or session tokens?", "What about refresh tokens?"],
    )
    db.save_session(s)

    result = db.get_suggestions()
    assert len(result["suggestions"]) == 1
    suggestion = result["suggestions"][0]
    assert suggestion["type"] == "open_questions"
    assert suggestion["session_id"] == s.id
    assert "2 unresolved" in suggestion["reason"]
    assert len(suggestion["open_questions"]) == 2
    print("[OK] test_session_with_open_questions")


def test_session_with_decisions():
    """Sessions with 2+ decisions are surfaced."""
    db = make_db()
    s = make_session(
        title="Architecture planning",
        days_ago=3,
        decisions=["Use SQLite for storage", "FastMCP for server", "Click for CLI"],
    )
    db.save_session(s)

    result = db.get_suggestions()
    assert len(result["suggestions"]) == 1
    suggestion = result["suggestions"][0]
    assert suggestion["type"] == "decisions"
    assert "3 key decisions" in suggestion["reason"]
    print("[OK] test_session_with_decisions")


def test_single_decision_not_surfaced():
    """Sessions with only 1 decision are NOT surfaced (threshold is 2)."""
    db = make_db()
    s = make_session(
        title="Quick fix",
        days_ago=1,
        decisions=["Fixed the bug"],
    )
    db.save_session(s)

    result = db.get_suggestions()
    assert len(result["suggestions"]) == 0
    print("[OK] test_single_decision_not_surfaced")


def test_open_questions_prioritized_over_decisions():
    """Open questions sessions appear before decision sessions."""
    db = make_db()
    s1 = make_session(
        title="Decisions session",
        days_ago=1,
        decisions=["Decision A", "Decision B", "Decision C"],
    )
    s2 = make_session(
        title="Questions session",
        days_ago=3,
        open_questions=["Unresolved question"],
    )
    db.save_session(s1)
    db.save_session(s2)

    result = db.get_suggestions()
    assert len(result["suggestions"]) == 2
    assert result["suggestions"][0]["type"] == "open_questions"
    assert result["suggestions"][1]["type"] == "decisions"
    print("[OK] test_open_questions_prioritized_over_decisions")


def test_deduplication():
    """A session with both open questions AND decisions only appears once."""
    db = make_db()
    s = make_session(
        title="Big session",
        days_ago=1,
        decisions=["Decision A", "Decision B"],
        open_questions=["Question 1"],
    )
    db.save_session(s)

    result = db.get_suggestions()
    assert len(result["suggestions"]) == 1
    assert result["suggestions"][0]["type"] == "open_questions"
    print("[OK] test_deduplication")


def test_project_filter():
    """Only sessions matching the project filter are returned."""
    db = make_db()
    s1 = make_session(
        title="Project A work",
        days_ago=1,
        project="project-a",
        open_questions=["Q1"],
    )
    s2 = make_session(
        title="Project B work",
        days_ago=1,
        project="project-b",
        open_questions=["Q2"],
    )
    db.save_session(s1)
    db.save_session(s2)

    result = db.get_suggestions(project="project-a")
    assert len(result["suggestions"]) == 1
    assert result["suggestions"][0]["title"] == "Project A work"
    print("[OK] test_project_filter")


def test_persona_filter():
    """Only sessions tagged with the persona are returned."""
    db = make_db()
    s1 = make_session(title="Ron session", days_ago=1, open_questions=["Q1"])
    s2 = make_session(title="Tax session", days_ago=1, open_questions=["Q2"])
    db.save_session(s1)
    db.save_session(s2)
    db.tag_session(s1.id, "ron-bot")
    db.tag_session(s2.id, "tax-prep")

    result = db.get_suggestions(persona="ron-bot")
    assert len(result["suggestions"]) == 1
    assert result["suggestions"][0]["title"] == "Ron session"
    print("[OK] test_persona_filter")


def test_persona_prefix_matching():
    """Persona filter matches prefixes (e.g., 'ron' matches 'ron-bot:sql')."""
    db = make_db()
    s = make_session(title="SQL work", days_ago=1, open_questions=["Q1"])
    db.save_session(s)
    db.tag_session(s.id, "ron-bot:sql")

    result = db.get_suggestions(persona="ron-bot")
    assert len(result["suggestions"]) == 1
    print("[OK] test_persona_prefix_matching")


def test_days_back_filter():
    """Sessions older than days_back are excluded."""
    db = make_db()
    s_recent = make_session(title="Recent", days_ago=2, open_questions=["Q1"])
    s_old = make_session(title="Old", days_ago=20, open_questions=["Q2"])
    db.save_session(s_recent)
    db.save_session(s_old)

    result = db.get_suggestions(days_back=7)
    assert len(result["suggestions"]) == 1
    assert result["suggestions"][0]["title"] == "Recent"
    print("[OK] test_days_back_filter")


def test_limit():
    """Only limit number of suggestions are returned."""
    db = make_db()
    for i in range(10):
        s = make_session(
            title="Session %d" % i,
            days_ago=i + 1,
            open_questions=["Q%d" % i],
        )
        db.save_session(s)

    result = db.get_suggestions(limit=3)
    assert len(result["suggestions"]) == 3
    print("[OK] test_limit")


def test_skill_gaps():
    """Detects skills expected by project but not used recently."""
    db = make_db()
    db.create_project(
        "project-ron",
        description="Ron's products",
        expected_skills=["loreconvo", "sql-optimizer", "loredocs"],
    )
    # Only use loreconvo in recent sessions
    s = make_session(
        title="LoreConvo work",
        days_ago=2,
        project="project-ron",
        skills_used=["loreconvo"],
    )
    db.save_session(s)

    result = db.get_suggestions(project="project-ron")
    gap_skills = {g["skill"] for g in result["skill_gaps"]}
    assert "sql-optimizer" in gap_skills
    assert "loredocs" in gap_skills
    assert "loreconvo" not in gap_skills
    assert len(result["skill_gaps"]) == 2
    # Check reason text
    for gap in result["skill_gaps"]:
        assert "project-ron" in gap["reason"]
    print("[OK] test_skill_gaps")


def test_skill_gaps_with_last_used():
    """Skill gap includes last_used date when skill was used before the window."""
    db = make_db()
    db.create_project("myproject", expected_skills=["rare-skill"])
    # Old session used the skill
    s_old = make_session(
        title="Old skill use",
        days_ago=60,
        project="myproject",
        skills_used=["rare-skill"],
    )
    db.save_session(s_old)

    result = db.get_suggestions(project="myproject", days_back=14)
    assert len(result["skill_gaps"]) == 1
    assert result["skill_gaps"][0]["skill"] == "rare-skill"
    assert result["skill_gaps"][0]["last_used"] is not None
    print("[OK] test_skill_gaps_with_last_used")


def test_skill_gaps_never_used():
    """Skill gap shows last_used=None when skill was never used."""
    db = make_db()
    db.create_project("myproject", expected_skills=["brand-new-skill"])

    result = db.get_suggestions(project="myproject")
    assert len(result["skill_gaps"]) == 1
    assert result["skill_gaps"][0]["last_used"] is None
    print("[OK] test_skill_gaps_never_used")


def test_no_skill_gaps_without_project():
    """Skill gaps are not checked when no project filter is given."""
    db = make_db()
    db.create_project("myproject", expected_skills=["some-skill"])

    result = db.get_suggestions()
    assert result["skill_gaps"] == []
    print("[OK] test_no_skill_gaps_without_project")


def test_metadata():
    """Metadata reflects actual scan parameters and results."""
    db = make_db()
    for i in range(5):
        s = make_session(title="Session %d" % i, days_ago=i + 1)
        db.save_session(s)

    result = db.get_suggestions(project="test", days_back=7, limit=3)
    meta = result["metadata"]
    assert meta["days_back"] == 7
    assert meta["project_filter"] == "test"
    assert meta["persona_filter"] is None
    assert meta["total_sessions_scanned"] >= 0
    print("[OK] test_metadata")


def test_summary_preview_truncation():
    """Long summaries are truncated in the preview."""
    db = make_db()
    long_summary = "A" * 500
    s = make_session(title="Verbose", days_ago=1, open_questions=["Q1"])
    s.summary = long_summary
    db.save_session(s)

    result = db.get_suggestions()
    preview = result["suggestions"][0]["summary_preview"]
    assert preview.endswith("...")
    assert len(preview) == 303  # 300 chars + "..."
    print("[OK] test_summary_preview_truncation")


def test_priority_field_not_in_output():
    """The internal priority field is removed from final output."""
    db = make_db()
    s = make_session(title="Test", days_ago=1, open_questions=["Q1"])
    db.save_session(s)

    result = db.get_suggestions()
    for suggestion in result["suggestions"]:
        assert "priority" not in suggestion
    print("[OK] test_priority_field_not_in_output")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print("[FAIL] %s: %s" % (test.__name__, e))
            failed += 1
    print("\n%d passed, %d failed, %d total" % (passed, failed, passed + failed))
    if failed:
        sys.exit(1)
