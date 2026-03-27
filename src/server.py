"""Session Bridge MCP Server - FastMCP interface for LLM access."""

import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mcp.server.fastmcp import FastMCP
from core.models import Session
from core.database import SessionDatabase
from core.config import Config

mcp = FastMCP(
    "loreconvo",
    instructions=(
        "LoreConvo provides persistent memory across Claude sessions. "
        "Use save_session to vault decisions and context. "
        "Use search_sessions or get_context_for to recall prior work. "
        "Use get_recent_sessions to see what was done recently. "
        "Use vault_suggest to get proactive recommendations on what to revisit. "
        "Tag sessions with personas for agent-specific memory."
    )
)

db = SessionDatabase(Config())


@mcp.tool()
def save_session(
    title: str,
    surface: str,
    summary: str,
    decisions: list[str] | None = None,
    artifacts: list[str] | None = None,
    open_questions: list[str] | None = None,
    tags: list[str] | None = None,
    skills_used: list[str] | None = None,
    project: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict:
    """Save a session summary to persistent memory.

    Call this at the end of a session or when the user requests /bridge save.
    Captures decisions, artifacts, skills used, and open questions for recall
    in future sessions.

    Args:
        title: Short descriptive title for the session
        surface: Where this session ran - 'cowork', 'code', or 'chat'
        summary: 2-3 paragraph narrative summary of what happened
        decisions: List of key decisions made during the session
        artifacts: List of files created or modified
        open_questions: Unresolved questions to carry forward
        tags: Freeform tags for categorization
        skills_used: Skills that were invoked during this session
        project: Project name if part of a defined project
        start_date: ISO 8601 start time (defaults to now)
        end_date: ISO 8601 end time
    """
    session = Session(
        title=title,
        surface=surface,
        summary=summary,
        decisions=decisions or [],
        artifacts=artifacts or [],
        open_questions=open_questions or [],
        tags=tags or [],
        skills_used=skills_used or [],
        project=project,
    )
    if start_date:
        session.start_date = start_date
    if end_date:
        session.end_date = end_date

    session_id = db.save_session(session)
    return {"session_id": session_id, "status": "saved", "title": title}


@mcp.tool()
def get_recent_sessions(
    limit: int = 10,
    days_back: int = 30,
    project: str | None = None,
    skill: str | None = None,
) -> list[dict]:
    """Get recent session summaries.

    Use to see what work was done recently, optionally filtered by project or skill.

    Args:
        limit: Max sessions to return (default 10)
        days_back: How far back to look (default 30 days)
        project: Filter to sessions in this project
        skill: Filter to sessions that used this skill
    """
    sessions = db.get_recent_sessions(limit, days_back, project, skill)
    return [
        {
            "id": s.id,
            "title": s.title,
            "surface": s.surface,
            "project": s.project,
            "date": s.start_date,
            "summary_preview": s.summary[:200] + "..." if len(s.summary) > 200 else s.summary,
            "decision_count": len(s.decisions),
            "skills": s.skills_used,
        }
        for s in sessions
    ]


@mcp.tool()
def get_session(session_id: str) -> dict:
    """Get full details of a specific session.

    Args:
        session_id: The UUID of the session to retrieve
    """
    session = db.get_session(session_id)
    if not session:
        return {"error": f"Session {session_id} not found"}
    return {
        "id": session.id,
        "title": session.title,
        "surface": session.surface,
        "project": session.project,
        "start_date": session.start_date,
        "end_date": session.end_date,
        "summary": session.summary,
        "decisions": session.decisions,
        "artifacts": session.artifacts,
        "open_questions": session.open_questions,
        "tags": session.tags,
        "skills_used": session.skills_used,
    }


@mcp.tool()
def search_sessions(
    query: str,
    persona: str | None = None,
    tags: list[str] | None = None,
    skills: list[str] | None = None,
    project: str | None = None,
    limit: int = 10,
) -> list[dict]:
    """Search session memory by keyword, with optional filters.

    Use to find sessions where a topic was discussed, a decision was made,
    or a specific skill/project was involved.

    Args:
        query: Search keywords (matched against title, summary, decisions)
        persona: Filter to sessions tagged with this persona (supports prefix matching)
        tags: Filter to sessions with any of these tags
        skills: Filter to sessions that used any of these skills
        project: Filter to sessions in this project
        limit: Max results (default 10)
    """
    results = db.search_sessions(query, persona, tags, skills, project, limit)
    return [
        {
            "id": r.session.id,
            "title": r.session.title,
            "date": r.session.start_date,
            "surface": r.session.surface,
            "project": r.session.project,
            "summary_preview": r.session.summary[:300] + "..." if len(r.session.summary) > 300 else r.session.summary,
            "decisions": r.session.decisions,
            "match_score": r.match_score,
        }
        for r in results
    ]


@mcp.tool()
def get_context_for(topic: str, max_results: int = 5) -> list[dict]:
    """Get relevant session context for a topic.

    Use at the start of a session to load prior decisions and context about a topic.
    Returns the most relevant session excerpts.

    Args:
        topic: The topic to find context for (e.g., 'K-1 parser', 'rental insurance')
        max_results: Max excerpts to return (default 5)
    """
    results = db.get_context_for(topic, max_results)
    return [
        {
            "session_title": r.session.title,
            "date": r.session.start_date,
            "summary": r.session.summary,
            "decisions": r.session.decisions,
            "open_questions": r.session.open_questions,
        }
        for r in results
    ]


@mcp.tool()
def tag_session(
    session_id: str,
    persona_name: str,
    relevance_note: str | None = None,
) -> dict:
    """Tag a session with a persona for filtered recall.

    Supports hierarchical personas (e.g., 'ron-bot:sql' matches 'ron-bot' queries).

    Args:
        session_id: Session to tag
        persona_name: Persona identifier (e.g., 'ron-bot', 'ron-bot:sql', 'tax-prep')
        relevance_note: Optional note about why this session is relevant to the persona
    """
    db.tag_session(session_id, persona_name, relevance_note)
    return {"status": "tagged", "session_id": session_id, "persona": persona_name}


@mcp.tool()
def link_sessions(
    from_id: str,
    to_id: str,
    link_type: str = "continues",
) -> dict:
    """Link two related sessions.

    Args:
        from_id: Source session ID
        to_id: Target session ID
        link_type: Relationship type - 'continues', 'related', or 'supersedes'
    """
    db.link_sessions(from_id, to_id, link_type)
    return {"status": "linked", "from": from_id, "to": to_id, "type": link_type}


@mcp.tool()
def get_project(project_name: str) -> dict:
    """Get project details including recent sessions and skill usage stats.

    Args:
        project_name: The project identifier
    """
    result = db.get_project(project_name)
    if not result:
        return {"error": f"Project '{project_name}' not found"}
    return result


@mcp.tool()
def list_projects() -> list[dict]:
    """List all defined projects with session counts."""
    return db.list_projects()


@mcp.tool()
def create_project(
    name: str,
    description: str = "",
    expected_skills: list[str] | None = None,
    default_persona: str | None = None,
) -> dict:
    """Create or update a project definition.

    Projects group related sessions and can auto-associate based on skill usage.

    Args:
        name: Project identifier (e.g., 'secret-agent-man', 'project-ron')
        description: What this project is about
        expected_skills: Skills typically used in this project's sessions
        default_persona: Auto-tag new sessions with this persona
    """
    db.create_project(name, description, expected_skills, default_persona)
    return {"status": "created", "project": name}


@mcp.tool()
def get_skill_history(
    skill_name: str,
    days_back: int = 90,
) -> list[dict]:
    """Get all sessions that used a specific skill.

    Useful for understanding how often a skill is used and in what contexts.

    Args:
        skill_name: The skill to look up (e.g., 'rental-property-accounting')
        days_back: How far back to search (default 90 days)
    """
    sessions = db.get_skill_history(skill_name, days_back)
    return [
        {
            "id": s.id,
            "title": s.title,
            "date": s.start_date,
            "surface": s.surface,
            "project": s.project,
        }
        for s in sessions
    ]


@mcp.tool()
def vault_suggest(
    project: str | None = None,
    persona: str | None = None,
    days_back: int = 14,
    limit: int = 5,
) -> dict:
    """Get proactive context suggestions based on your session history.

    Analyzes recent sessions and surfaces:
    - Sessions with unresolved open questions that need follow-up
    - Sessions with key decisions worth reviewing before starting new work
    - Skill gaps: skills expected by a project but not used recently

    Use at the start of a session to find the most valuable prior context,
    or when you're unsure what to work on next.

    Args:
        project: Filter suggestions to this project
        persona: Filter to sessions tagged with this persona (prefix matching)
        days_back: How far back to look (default 14 days)
        limit: Max suggestions to return (default 5)
    """
    return db.get_suggestions(project, persona, days_back, limit)


def main():
    """Entry point for uvx / console script execution."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
