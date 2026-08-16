"""Session Bridge MCP Server - FastMCP interface for LLM access."""

import concurrent.futures
import json
import signal
import sys
import os
import logging
import importlib.metadata
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logger = logging.getLogger(__name__)

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, ConfigDict, Field
from core.models import Session
from core.database import (
    SessionDatabase, SessionLimitReachedError, _MAX_IMPORT_BYTES,
    _MAX_SESSIONS_PER_FILE, _IMPORT_FIELD_CAPS,
    _pinning_enabled, parse_session_id,
)
from core import graph
from core.loredocs_bridge import (
    CROSS_LINK_EMBEDDING_MODEL,
    LoreDocsAccessError,
    LoreDocsSchemaError,
    discover_loredocs_db,
    get_cross_product_links,
    link_session_to_doc,
)
from core.config import Config, set_tier as _set_tier_config
from core.license import get_license_status, LORECONVO_UPGRADE_URL
from core.onboard_tool import run_onboard as _run_onboard, _config_path as _onboard_config_path
from core.timeutil import parse_iso_utc
from compat_check import check as _compat_check, emit_startup_warnings as _compat_emit


_EGG_INFO_CANDIDATES = (
    Path("src/loreconvo.egg-info"),
    Path("loreconvo.egg-info"),
)


def _check_egg_info_conflict() -> None:
    """Warn if a stale egg-info directory may shadow installed metadata.

    Runs at server startup. Does not raise, since editable dev installs
    legitimately have an egg-info on disk; we only flag version mismatch.
    """
    product = "loreconvo"
    try:
        installed_version = importlib.metadata.version(product)
    except importlib.metadata.PackageNotFoundError:
        logger.debug("loreconvo not installed via pip; skipping egg-info check")
        return

    for egg_info_path in _EGG_INFO_CANDIDATES:
        if not egg_info_path.is_dir():
            continue
        pkg_info = egg_info_path / "PKG-INFO"
        if not pkg_info.is_file():
            logger.warning(
                "stale loreconvo.egg-info detected at %s (missing PKG-INFO). "
                "This may shadow installed metadata. "
                "Consider deleting it or running 'pip install -e .' to update.",
                egg_info_path,
            )
            continue
        egg_version = None
        for line in pkg_info.read_text(encoding="ascii", errors="replace").splitlines():
            if line.startswith("Version:"):
                egg_version = line.split(":", 1)[1].strip()
                break
        if egg_version is None:
            logger.warning(
                "stale loreconvo.egg-info detected at %s (no Version field in PKG-INFO). "
                "This may shadow installed metadata.",
                egg_info_path,
            )
        elif egg_version != installed_version:
            logger.warning(
                "stale loreconvo.egg-info detected at %s. "
                "egg-info version: %s, installed version: %s. "
                "This may shadow installed metadata. "
                "Consider deleting it or running 'pip install -e .' to update.",
                egg_info_path, egg_version, installed_version,
            )
        else:
            logger.debug(
                "egg-info found at %s (version %s) matches installed version",
                egg_info_path, egg_version,
            )


_db = None


def _get_db() -> SessionDatabase:
    """Lazy initialization of the database to defer startup overhead until first tool call."""
    global _db
    if _db is None:
        _db = SessionDatabase(Config())
    return _db


mcp = FastMCP(
    "loreconvo",
    instructions=(
        "LoreConvo provides persistent memory across Claude sessions. "
        "Use save_session to vault decisions and context. "
        "Use search_sessions or get_context_for to recall prior work. "
        "Use get_recent_sessions to see what was done recently. "
        "Use vault_suggest to get proactive recommendations on what to revisit. "
        "Use loreconvo_onboard to set up your workspace on first install. "
        "Fields: surface identifies the platform (code/cowork/chat/codex/custom), "
        "project is a snake_case workspace identifier, "
        "tags use conventions status:*, priority:*, agent:* (see your setup doc), "
        "skills_used lists skill names invoked (not tool names). "
        "Agents tag sessions with agent:<name> -- not the surface field."
    )
)


def _compress_summary(raw_summary: str) -> str:
    """Compress raw_summary via Claude API. Returns raw on any failure (no key, import error, API error)."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return raw_summary
    try:
        import anthropic
    except ImportError:
        return raw_summary
    try:
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            messages=[{
                "role": "user",
                "content": (
                    "Summarize the following session notes concisely. "
                    "Preserve all key decisions, artifacts, and open questions. "
                    "Output only the summary text:\n\n" + raw_summary
                ),
            }],
        )
        return response.content[0].text
    except Exception:
        return raw_summary


def _normalize_tags(tags: list[str] | None) -> list[str]:
    if not tags:
        return []
    result: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        if isinstance(tag, str) and ',' in tag:
            parts = [t.strip() for t in tag.split(',') if t.strip()]
            for part in parts:
                if part not in seen:
                    result.append(part)
                    seen.add(part)
        else:
            tag_str = str(tag).strip() if tag else ''
            if tag_str and tag_str not in seen:
                result.append(tag_str)
                seen.add(tag_str)
    return result


@mcp.tool(title="Save Session")
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
    session_id: str | None = None,
    external_tool_session: bool = False,
    reasoning_notes: str | None = None,
    summarize: bool = False,
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
        session_id: Optional session ID to enable deduplication with the
            auto-save hook. If a session with this ID already exists (e.g.,
            auto-saved at session end), the record is updated with the richer
            manual metadata. Artifacts from the existing record are preserved
            when the caller does not supply artifacts. If omitted, a new UUID
            is generated (existing behavior).
        external_tool_session: Set True when saving a session generated by an
            external tool (e.g., Anthropic Managed Agents). Flagged sessions are
            excluded from auto-load and search by default to prevent context
            contamination. Override exclusion with include_external=True on search,
            or set LORECONVO_EXTERNAL_TOOL_EXCLUSION=0 to disable globally.
        reasoning_notes: Optional free-form text capturing the reasoning chain
            or thought process behind decisions. Stored as-is; blank or None
            leaves the field empty.
        summarize: If True and ANTHROPIC_API_KEY is set, send the summary to
            Claude API (Haiku) for compression before saving. Opt-in only;
            defaults to False. Falls back to the raw summary on any API error
            or if the key is absent. See INSTALL.md Privacy Note.
    """
    summary_source = None
    if summarize:
        compressed = _compress_summary(summary)
        if compressed != summary:
            summary_source = "claude_api"
        summary = compressed

    # Merge artifacts with any existing auto-saved record when session_id is known
    merged_artifacts = artifacts or []
    if session_id is not None and not artifacts:
        existing = _get_db().get_session(session_id)
        if existing and existing.artifacts:
            merged_artifacts = existing.artifacts

    session = Session(
        title=title,
        surface=surface,
        summary=summary,
        decisions=decisions or [],
        artifacts=merged_artifacts,
        open_questions=open_questions or [],
        tags=_normalize_tags(tags),
        skills_used=skills_used or [],
        project=project,
        external_tool_session=external_tool_session,
        reasoning_notes=reasoning_notes if reasoning_notes else None,
    )
    if session_id is not None:
        session.id = session_id
    if start_date:
        session.start_date = start_date
    if end_date:
        session.end_date = end_date

    try:
        saved_id = _get_db().save_session(session)
        # Mark summary_source when LLM compression was applied via MCP save_session.
        if summary_source == "claude_api" and saved_id:
            try:
                _get_db().conn.execute(
                    "UPDATE sessions SET summary_source=? WHERE id=?",
                    (summary_source, saved_id),
                )
                _get_db().conn.commit()
            except Exception:
                pass
    except SessionLimitReachedError as e:
        return {
            "status": "limit_reached",
            "error": str(e),
            "upgrade_url": LORECONVO_UPGRADE_URL,
        }

    # first-use nudge
    config_exists = _onboard_config_path(_get_db()).exists()
    is_first_session = _get_db().session_count() == 1 and not config_exists

    result = {"session_id": saved_id, "status": "saved", "title": title}
    if is_first_session:
        result["setup_tip"] = (
            "First session detected. Run loreconvo_onboard() to set up tag "
            "conventions, project structure, and get a reference doc for your "
            "AI assistant."
        )
    return result


@mcp.tool(title="Get Recent Sessions")
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
    sessions = _get_db().get_recent_sessions(limit, days_back, project, skill)
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


@mcp.tool(title="Get Session")
def get_session(session_id: str) -> dict:
    """Get full details of a specific session.

    Args:
        session_id: The UUID of the session to retrieve
    """
    session = _get_db().get_session(session_id)
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
        "previous_summary": session.previous_summary,
    }


def _validate_date_range(after: str | None, before: str | None) -> str | None:
    """Validate search_sessions() after/before params. Returns an error message, or None if valid.

    Uses parse_iso_utc() rather than datetime.fromisoformat() directly so the
    documented 'Z' suffix format works on Python 3.10 (see core/timeutil.py).
    """
    if after is not None:
        try:
            after_dt = parse_iso_utc(after)
        except ValueError:
            return f"after must be an ISO 8601 UTC instant (e.g. '2026-07-06T00:00:00Z'), got {after!r}"
    else:
        after_dt = None

    if before is not None:
        try:
            before_dt = parse_iso_utc(before)
        except ValueError:
            return f"before must be an ISO 8601 UTC instant (e.g. '2026-07-06T00:00:00Z'), got {before!r}"
    else:
        before_dt = None

    if after_dt is not None and before_dt is not None and after_dt >= before_dt:
        return f"after ({after!r}) must be strictly before before ({before!r})"

    return None


@mcp.tool(title="Search Sessions")
def search_sessions(
    query: str,
    persona: str | None = None,
    tags: list[str] | None = None,
    skills: list[str] | None = None,
    project: str | None = None,
    limit: int = 10,
    include_external: bool = False,
    semantic: bool = False,
    include_expired: bool = False,
    after: str | None = None,
    before: str | None = None,
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
        include_external: If True, include sessions flagged as external_tool_session.
            Default False. Can also be enabled globally via LORECONVO_EXTERNAL_TOOL_EXCLUSION=0.
        semantic: If True, use LanceDB hybrid (vector + BM25) search instead of FTS5.
            Pro tier only. Falls back to FTS5 if index not built yet; run
            rebuild_index to build it after first Pro activation.
        include_expired: If True, include sessions whose expires_at is in the past.
            Default False (expired sessions are hidden from search).
        after: Optional ISO 8601 UTC instant (e.g. "2026-07-06T00:00:00Z"). Only
            sessions started at or after this instant are returned.
        before: Optional ISO 8601 UTC instant. Only sessions started strictly
            before this instant are returned.

            To answer a question like "what did I work on last week", resolve
            the range yourself -- you know the user's local date, the server
            does not -- and pass the two instants. Do not put date words in
            `query`; they are matched as literal keywords, not parsed.
    """
    error = _validate_date_range(after, before)
    if error:
        return {"error": error}

    results = _get_db().search_sessions(query, persona, tags, skills, project, limit, include_external=include_external, semantic=semantic, include_expired=include_expired, after=after, before=before)
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


@mcp.tool(title="Get Context for Topic")
def get_context_for(
    topic: str,
    max_results: int = 5,
    include_external: bool = False,
    semantic: bool = False,
) -> list[dict]:
    """Get relevant session context for a topic.

    Use at the start of a session to load prior decisions and context about a topic.
    Returns the most relevant session excerpts.

    Args:
        topic: The topic to find context for (e.g., 'K-1 parser', 'rental insurance')
        max_results: Max excerpts to return (default 5)
        include_external: If True, include sessions flagged as external_tool_session.
            Default False.
        semantic: If True, use LanceDB hybrid search (Pro only). Falls back to FTS5
            if index not yet built.
    """
    results = _get_db().get_context_for(topic, max_results, include_external=include_external, semantic=semantic)
    return [
        {
            "session_title": r.session.title,
            "date": r.session.start_date,
            "summary": r.session.summary,
            "decisions": r.session.decisions,
            "open_questions": r.session.open_questions,
            "match_score": r.match_score,
        }
        for r in results
    ]


# -- Agent context injection (SH-12766) --

_INJECT_DEFAULT_TIMEOUT = 5.0
_INJECT_MIN_TIMEOUT = 0.5
_INJECT_MAX_TIMEOUT = 60.0
_INJECT_CONTEXT_CHAR_CAP = 4000

# Static, non-sensitive error messages (PART:interfaces: never leak schema
# names, SQLite error text, or file paths in the message field).
_AGENT_CONTEXT_ERROR_MESSAGES = {
    "invalid_agent_name": "agent_name must match ^[a-z][a-z0-9-]{1,63}$.",
    "invalid_project": "project must match ^[a-z_][a-z0-9_]{0,63}$.",
    "invalid_topics": "Each topic must be a non-empty string of at most 200 characters.",
    "too_many_topics": "At most 10 topics are allowed per config.",
    "duplicate_topics": "Topics must be unique after normalization (strip/lowercase).",
    "invalid_max_results": "max_results_per_topic must be an integer between 1 and 10.",
}


def _get_inject_timeout() -> float:
    """Read and validate LORECONVO_AGENT_CONTEXT_TIMEOUT. Clamped to [0.5, 60.0]s.

    Invalid (non-numeric, zero, negative) values fall back to the default.
    """
    raw = os.environ.get("LORECONVO_AGENT_CONTEXT_TIMEOUT", str(_INJECT_DEFAULT_TIMEOUT))
    try:
        value = float(raw)
        if value <= 0:
            logger.warning(
                "LORECONVO_AGENT_CONTEXT_TIMEOUT=%r is non-positive; using default %.1fs.",
                raw, _INJECT_DEFAULT_TIMEOUT,
            )
            return _INJECT_DEFAULT_TIMEOUT
    except (ValueError, TypeError):
        logger.warning(
            "LORECONVO_AGENT_CONTEXT_TIMEOUT=%r is not a valid number; using default %.1fs.",
            raw, _INJECT_DEFAULT_TIMEOUT,
        )
        return _INJECT_DEFAULT_TIMEOUT
    clamped = max(_INJECT_MIN_TIMEOUT, min(value, _INJECT_MAX_TIMEOUT))
    if clamped != value:
        logger.warning(
            "LORECONVO_AGENT_CONTEXT_TIMEOUT=%.1f clamped to [%.1f, %.1f]; using %.1fs.",
            value, _INJECT_MIN_TIMEOUT, _INJECT_MAX_TIMEOUT, clamped,
        )
    return clamped


def _fan_out_topics_fts5(topics, max_results, global_timeout_s):
    """Sequential per-topic search for FTS5 (free tier, P95 < 100ms/topic).

    Deadline is checked both before AND after each topic query (H-O3) so a
    slow first topic cannot let the loop continue past the deadline. A
    per-topic elapsed-time warning replaces the disposition's dead
    `remaining` variable, giving operators visibility into pathological
    slow queries (H-O4/H-O5).

    Returns (results, timed_out, topics_completed).
    """
    results = []
    timed_out = False
    completed = 0
    deadline = time.monotonic() + global_timeout_s
    for topic in topics:
        if time.monotonic() >= deadline:
            timed_out = True
            break
        topic_started = time.monotonic()
        try:
            results.extend(
                _get_db().get_context_for(topic, max_results, include_external=False, semantic=False)
            )
        except Exception as exc:
            logger.warning(
                "inject_agent_context: FTS5 query for topic %r failed: %s", topic, exc
            )
        elapsed = time.monotonic() - topic_started
        if elapsed > global_timeout_s * 0.5:
            logger.warning(
                "inject_agent_context: topic %r took %.2fs, over half the %.1fs "
                "global timeout (pathological query).", topic, elapsed, global_timeout_s,
            )
        completed += 1
        if time.monotonic() >= deadline:
            timed_out = True
            break
    return results, timed_out, completed


def _fan_out_topics_semantic(topics, max_results, global_timeout_s):
    """Concurrent per-topic search for semantic mode (Pro, P95 < 700ms/topic).

    ThreadPoolExecutor capped at 4 workers. Residual bound: running threads
    cannot be preempted (max 4 x P95 700ms = 2.8s), documented in the
    architecture proposal PART:ops-cost.

    Returns (results, timed_out, topics_completed).
    """
    results = []
    timed_out = False
    completed = 0
    deadline = time.monotonic() + global_timeout_s
    per_topic_s = max(1.0, global_timeout_s / max(len(topics), 1))

    with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(topics), 4)) as ex:
        futures = {
            ex.submit(_get_db().get_context_for, t, max_results, False, True): t
            for t in topics
        }
        try:
            for fut in concurrent.futures.as_completed(futures, timeout=global_timeout_s):
                if time.monotonic() >= deadline:
                    timed_out = True
                    break
                try:
                    results.extend(fut.result(timeout=per_topic_s))
                    completed += 1
                except concurrent.futures.TimeoutError:
                    timed_out = True
                    logger.warning(
                        "inject_agent_context: per-topic semantic timeout "
                        "(%.1fs) for topic %r", per_topic_s, futures[fut],
                    )
                    break
                except Exception as exc:
                    logger.warning(
                        "inject_agent_context: semantic query failed for topic %r: %s",
                        futures[fut], exc,
                    )
                    completed += 1
        except TimeoutError:
            timed_out = True
            logger.warning(
                "inject_agent_context: global timeout (%.1fs) reached "
                "before all semantic topics completed.", global_timeout_s,
            )
    return results, timed_out, completed


def _format_agent_context_markdown(results, char_cap=_INJECT_CONTEXT_CHAR_CAP):
    """Dedupe SearchResults by session id, format as markdown, cap at char_cap chars.

    session_count reflects sessions INCLUDED after the cap (PART:interfaces),
    not the total deduped count. Mirrors the [TRUNCATED] pattern in
    get_memory_digest.

    Returns (markdown, session_count, truncated).
    """
    seen = set()
    deduped = []
    for r in results:
        sid = r.session.id
        if sid in seen:
            continue
        seen.add(sid)
        deduped.append(r)
    deduped.sort(key=lambda r: r.match_score, reverse=True)

    parts = []
    included = 0
    truncated = False
    running_len = 0
    for r in deduped:
        s = r.session
        lines = [f"### {s.title} ({s.start_date})"]
        if s.summary:
            lines.append(s.summary)
        if s.decisions:
            lines.append("Decisions: " + "; ".join(s.decisions))
        if s.open_questions:
            lines.append("Open questions: " + "; ".join(s.open_questions))
        block = "\n".join(lines)
        added_len = len(block) + (2 if parts else 0)  # "\n\n" separator
        if running_len + added_len > char_cap:
            truncated = True
            break
        parts.append(block)
        running_len += added_len
        included += 1

    markdown = "\n\n".join(parts)
    if truncated:
        markdown += "\n\n[TRUNCATED -- context exceeded 4000 chars]"

    return markdown, included, truncated


@mcp.tool(title="Configure Agent Context Topics")
def configure_agent_context(
    agent_name: str,
    project: str,
    topics: list,
    max_results_per_topic: int = 3,
    enabled: bool = True,
    retire: bool = False,
) -> dict:
    """Store or update a named topic configuration for an agent.

    Args:
        agent_name: Canonical agent name (^[a-z][a-z0-9-]{1,63}$).
        project: Project name matching sessions.project (^[a-z_][a-z0-9_]{0,63}$).
        topics: Non-empty list of topic strings; max 10; each max 200 chars.
            Replaces all existing topics for this (agent_name, project) pair.
        max_results_per_topic: Sessions returned per topic search. 1-10.
        enabled: Set False to disable injection without deleting the config.
        retire: Set True to soft-retire this config (status='retired').
            inject_agent_context treats a retired config like enabled=0.
            Any write with retire=False reactivates a previously retired
            config (reflected in the response's reactivated_retired_config).
    """
    if os.environ.get("LORECONVO_DISABLE_CONTEXT_WRITE"):
        return {
            "status": "error", "code": "feature_disabled",
            "message": "Context configuration is disabled by LORECONVO_DISABLE_CONTEXT_WRITE.",
        }
    try:
        result = _get_db().configure_agent_context(
            agent_name=agent_name, project=project, topics=topics,
            max_results_per_topic=max_results_per_topic, enabled=enabled, retire=retire,
        )
    except ValueError as exc:
        code = str(exc)
        return {
            "status": "error", "code": code,
            "message": _AGENT_CONTEXT_ERROR_MESSAGES.get(code, "Invalid input."),
        }
    except Exception:
        logger.warning("configure_agent_context: DB error", exc_info=True)
        return {"status": "error", "code": "db_error", "message": "Database error occurred."}

    return {
        "status": "ok",
        "agent_name": agent_name,
        "project": project,
        "topic_count": result["topic_count"],
        "reactivated_retired_config": result["reactivated_retired_config"],
    }


@mcp.tool(title="Inject Agent Context")
def inject_agent_context(
    agent_name: str,
    project: str,
    topics: list | None = None,
    max_results_per_topic: int = 3,
    semantic: bool = False,
) -> dict:
    """Return targeted session context for an agent at session start.

    If topics is provided (non-empty, len<=10), it overrides stored config.
    If topics is None, stored config is used.
    If topics=[], has_config reflects stored state; no injection runs.

    Returns status in {"ok", "partial", "warning", "error"}.
    Branch on status first; treat "warning" as skipped (not success), not
    as a synonym for "ok" -- a caller that only checks `status != "error"`
    will silently treat skipped or empty injection as success.
    """
    try:
        SessionDatabase._validate_agent_context_agent_name(agent_name)
        SessionDatabase._validate_agent_context_project(project)
    except ValueError as exc:
        code = str(exc)
        return {
            "status": "error", "code": code,
            "message": _AGENT_CONTEXT_ERROR_MESSAGES.get(code, "Invalid input."),
        }

    if not isinstance(max_results_per_topic, int) or isinstance(max_results_per_topic, bool) \
            or not (1 <= max_results_per_topic <= 10):
        return {
            "status": "error", "code": "invalid_max_results",
            "message": _AGENT_CONTEXT_ERROR_MESSAGES["invalid_max_results"],
        }

    try:
        config = _get_db().get_agent_context_config(agent_name, project)
    except Exception:
        logger.warning("inject_agent_context: DB error reading config", exc_info=True)
        return {"status": "error", "code": "db_error", "message": "Database error occurred."}

    has_config = config is not None

    # H-I2: topics=[] is an explicit override to "search nothing" -- report
    # has_config from the stored state, but never run injection.
    if topics == []:
        if has_config and config["enabled"] and config["status"] == "active":
            warning = "topics=[] overrides stored config"
        elif has_config:
            warning = "topics=[] provided; stored config is disabled"
        else:
            warning = "No topics to search and no stored config found"
        return {
            "status": "warning", "context": "", "session_count": 0, "topics_searched": 0,
            "source": "call_time_topics", "has_config": has_config,
            "timed_out": False, "warning": warning,
        }

    if topics:
        try:
            resolved_topics = SessionDatabase._normalize_agent_context_topics(topics)
        except ValueError as exc:
            code = str(exc)
            return {
                "status": "error", "code": code,
                "message": _AGENT_CONTEXT_ERROR_MESSAGES.get(code, "Invalid input."),
            }
        resolved_max_results = max_results_per_topic
        source = "call_time_topics"
    else:
        # topics is None -- fall back to stored config.
        if not has_config:
            return {
                "status": "warning", "context": "", "session_count": 0, "topics_searched": 0,
                "source": "agent_not_found", "has_config": False,
                "timed_out": False,
                "warning": "No stored config found for this agent/project.",
            }
        if not config["enabled"] or config["status"] != "active":
            source = "config_retired" if config["status"] == "retired" else "config_disabled"
            return {
                "status": "warning", "context": "", "session_count": 0, "topics_searched": 0,
                "source": source, "has_config": True,
                "timed_out": False,
                "warning": f"Stored config exists but is {source[len('config_'):]}.",
            }
        if not config["topics"]:
            return {
                "status": "warning", "context": "", "session_count": 0, "topics_searched": 0,
                "source": "empty_topics", "has_config": True,
                "timed_out": False, "warning": "Stored config has no topics configured.",
            }
        resolved_topics = config["topics"]
        resolved_max_results = config["max_results_per_topic"]
        source = "stored_config"

    global_timeout_s = _get_inject_timeout()
    try:
        if semantic:
            raw_results, timed_out, searched = _fan_out_topics_semantic(
                resolved_topics, resolved_max_results, global_timeout_s
            )
        else:
            raw_results, timed_out, searched = _fan_out_topics_fts5(
                resolved_topics, resolved_max_results, global_timeout_s
            )
    except Exception:
        logger.warning("inject_agent_context: fan-out failed", exc_info=True)
        return {"status": "error", "code": "db_error", "message": "Database error occurred."}

    markdown, session_count, capped = _format_agent_context_markdown(raw_results)
    warning = None
    if capped:
        warning = "Context truncated at 4000 chars."
    if timed_out:
        warning = (warning + " " if warning else "") + "Injection timed out; partial results used."

    if source == "stored_config":
        try:
            _get_db().touch_agent_context_last_used(agent_name, project)
        except Exception:
            logger.warning(
                "inject_agent_context: failed to update last_used_at", exc_info=True
            )

    return {
        "status": "partial" if timed_out else "ok",
        "context": markdown,
        "session_count": session_count,
        "topics_searched": searched,
        "source": source,
        "timed_out": timed_out,
        "warning": warning,
    }


@mcp.tool(title="Tag Session")
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
    _get_db().tag_session(session_id, persona_name, relevance_note)
    return {"status": "tagged", "session_id": session_id, "persona": persona_name}


@mcp.tool(title="Link Sessions")
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
    _get_db().link_sessions(from_id, to_id, link_type)
    return {"status": "linked", "from": from_id, "to": to_id, "type": link_type}


@mcp.tool(title="Get Related Sessions")
def get_related_sessions(
    session_id: str,
    limit: int = 10,
    min_shared_terms: int = 3,
) -> dict:
    """Find sessions related to a given session by co-occurrence and embedding. Pro only.

    Returns co-occurrence links (shared_term_count >= 1) and embedding-based
    semantic links (shared_term_count=0 sentinel). Co-occurrence results rank
    above embedding results when sorting by shared_term_count DESC.
    Response version=2 signals the new format with link_type field.

    Args:
        session_id: UUID of the session to find related sessions for
        limit: Max results to return (default 10, max 50)
        min_shared_terms: Minimum shared keywords required (default 3)
    """
    status = get_license_status()
    if not status["is_pro"]:
        return {
            "error": (
                "get_related_sessions requires LoreConvo Pro. "
                f"Upgrade at {LORECONVO_UPGRADE_URL}, then set your "
                "LORECONVO_PRO license key."
            )
        }
    limit = max(1, min(limit, 50))
    result = _get_db().get_related_sessions(session_id, limit, min_shared_terms)
    # v2 envelope: result is {"version": 2, "sessions": [...]}
    sessions = result.get("sessions", [])
    return {
        "version": result.get("version", 2),
        "session_id": session_id,
        "related_count": len(sessions),
        "related": sessions,
    }


@mcp.tool(title="Graph Session Map")
def graph_session_map(
    session_id: str | None = None,
    project: str | None = None,
    depth: int = 1,
    max_nodes: int = 60,
) -> dict:
    """Render a Mermaid knowledge-graph neighborhood around a session or project.

    Exactly one of session_id/project selects the seed. Traversal is a
    bounded, read-only BFS over session_links (undirected) plus each
    admitted session's attribute leaves (project/skill/persona/tag). Pro
    tier adds derived (co-occurrence/embedding) and doc (LoreDocs
    cross-link) edges, seed-only. Every emitted label is restricted to a
    fixed character allowlist so no title/tag/skill text can alter the
    diagram's structure.

    Args:
        session_id: UUID of the seed session. Exactly one of session_id/project required.
        project: name of the seed project. Exactly one of session_id/project required.
        depth: number of BFS expansion hops over link edges, clamped [0, 3]
        max_nodes: node budget (sessions + attribute leaves), clamped [1, 200]

    Returns a dict with version, seed, seed_found, mermaid, nodes, edges,
    truncated, nodes_emitted, nodes_available, edges_emitted,
    nodes_dropped_by_kind, edges_dropped_by_kind, frontier_session_ids,
    edge_kinds_included, edge_kinds_omitted -- or {"error": {...}} on a
    validation failure or an unavailable database.
    """
    if bool(session_id) == bool(project):
        return {"error": {
            "code": "SEED_XOR", "field": None,
            "message": "Exactly one of session_id or project is required.",
        }}
    try:
        depth = int(depth)
    except (TypeError, ValueError):
        return {"error": {
            "code": "INVALID_PARAM", "field": "depth",
            "message": "depth must be an integer.",
        }}
    try:
        max_nodes = int(max_nodes)
    except (TypeError, ValueError):
        return {"error": {
            "code": "INVALID_PARAM", "field": "max_nodes",
            "message": "max_nodes must be an integer.",
        }}

    neighborhood = _get_db().get_graph_neighborhood(
        seed_session_id=session_id, seed_project=project, depth=depth, max_nodes=max_nodes,
    )
    if "error" in neighborhood:
        return {"error": {
            "code": "GRAPH_DB_UNAVAILABLE", "field": None,
            "message": neighborhood["message"],
        }}

    for node in neighborhood["nodes"]:
        node["label"] = graph.sanitize_label(node.pop("raw_label"))
    mermaid = graph.build_mermaid(neighborhood)

    nodes_dropped_by_kind = neighborhood["nodes_dropped_by_kind"]
    edges_dropped_by_kind = neighborhood["edges_dropped_by_kind"]
    nodes_available = len(neighborhood["nodes"]) + sum(nodes_dropped_by_kind.values())

    return {
        "version": 1,
        "seed": {
            "kind": "session" if session_id else "project",
            "value": session_id or project,
        },
        "seed_found": neighborhood["seed_found"],
        "mermaid": mermaid,
        "nodes": neighborhood["nodes"],
        "edges": neighborhood["edges"],
        "truncated": bool(nodes_dropped_by_kind) or bool(edges_dropped_by_kind),
        "nodes_emitted": len(neighborhood["nodes"]),
        "nodes_available": nodes_available,
        "edges_emitted": len(neighborhood["edges"]),
        "nodes_dropped_by_kind": nodes_dropped_by_kind,
        "edges_dropped_by_kind": edges_dropped_by_kind,
        "frontier_session_ids": neighborhood["frontier_session_ids"],
        "edge_kinds_included": neighborhood["edge_kinds_included"],
        "edge_kinds_omitted": neighborhood["edge_kinds_omitted"],
    }


@mcp.tool(title="Rebuild Semantic Index")
def rebuild_index() -> dict:
    """Rebuild the LanceDB semantic search index from all stored sessions. Pro only.

    Run after first Pro activation, or to recover from a corrupted index.
    Downloads BAAI/bge-small-en-v1.5 (~130MB) once on first run; subsequent
    runs use the cached model. May take 1-2 minutes for large session stores.

    Returns a dict with 'indexed' (sessions added to index) and 'total_in_db'
    (total sessions in SQLite, including those excluded from indexing).
    """
    status = get_license_status()
    if not status["is_pro"]:
        return {
            "error": (
                "rebuild_index requires LoreConvo Pro. "
                f"Get a license by upgrading at {LORECONVO_UPGRADE_URL}."
            )
        }
    return _get_db().rebuild_lance_index()


@mcp.tool(title="Get Project")
def get_project(project_name: str) -> dict:
    """Get project details including recent sessions and skill usage stats.

    Args:
        project_name: The project identifier
    """
    result = _get_db().get_project(project_name)
    if not result:
        return {"error": f"Project '{project_name}' not found"}
    return result


@mcp.tool(title="List Projects")
def list_projects() -> list[dict]:
    """List all defined projects with session counts."""
    return _get_db().list_projects()


@mcp.tool(title="Create Project")
def create_project(
    name: str,
    description: str = "",
    expected_skills: list[str] | None = None,
    default_persona: str | None = None,
    instructions: str | None = None,
    session_id: str | None = None,
) -> dict:
    """Create or update a project definition.

    Projects group related sessions and can auto-associate based on skill usage.
    All changes to project instructions are logged for audit purposes.

    Args:
        name: Project identifier (e.g., 'secret-agent-man', 'project-ron')
        description: What this project is about
        expected_skills: Skills typically used in this project's sessions
        default_persona: Auto-tag new sessions with this persona
        instructions: Optional project-wide instructions or constraints
        session_id: Optional session ID for audit trail (typically provided by MCP context)
    """
    _get_db().create_project(name, description, expected_skills, default_persona, instructions, session_id=session_id)
    return {"status": "created", "project": name}


@mcp.tool(title="Onboard LoreConvo")
def loreconvo_onboard(
    name: str | None = None,
    projects: list[str] | None = None,
    agents: list[str] | None = None,
    tag_style: str = "simple",
) -> dict:
    """Set up or update your LoreConvo workspace configuration.

    Call this once after installing LoreConvo to get a recommended setup.
    Call again any time to add projects or agents, or to regenerate your
    reference doc.

    Creates:
    - Project registrations for each project listed
    - A config file at ~/.loreconvo/onboard_config.json
    - A reference doc (markdown) in the response -- paste it into your
      CLAUDE.md or a LoreDocs vault so your AI assistant can apply your
      conventions consistently

    Args:
        name: Your workspace or team name (e.g. 'Labyrinth Analytics')
        projects: Snake_case project identifiers (e.g. ['side_hustle', 'finance'])
        agents: Agent names that will tag sessions (e.g. ['ron', 'meg'])
        tag_style: 'simple' (status + priority) or 'detailed' (adds effort,
                   scout-run markers, date tag guidance)

    Surfaces: code (Claude Code), cowork (Claude.ai Projects), chat (Claude.ai
    chat), codex (Codex CLI). Custom values are allowed for other tools.
    Agent identity: use tags=['agent:name'] -- not the surface field.
    """
    if tag_style not in ("simple", "detailed"):
        return {"error": "tag_style must be 'simple' or 'detailed'"}
    return _run_onboard(_get_db(), name=name, projects=projects, agents=agents, tag_style=tag_style)


@mcp.tool(title="Get Skill History")
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
    sessions = _get_db().get_skill_history(skill_name, days_back)
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


@mcp.tool(title="Get Context Suggestions")
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
    return _get_db().get_suggestions(project, persona, days_back, limit)


@mcp.tool(title="Get License Tier")
def get_tier() -> dict:
    """Return the current LoreConvo license tier and status.

    Use this to confirm whether the Pro license key is loaded and valid.

    Returns a dict with keys:
        is_pro      -- bool, True if Pro tier is active
        mode        -- "licensed" | "dev_bypass" | "free" | "invalid_key"
        product     -- product name from the license payload (if licensed)
        exp         -- expiry date or "never" (if licensed)
        email       -- customer email (if licensed and present)
        error       -- error message (if mode is "invalid_key")
        upgrade_url -- Stripe checkout link (present when not already Pro)
    """
    status = get_license_status()
    if not status.get("is_pro"):
        status["upgrade_url"] = LORECONVO_UPGRADE_URL
    return status


class VaultSetTierInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    tier: str = Field(
        ...,
        description="Tier to activate: 'free' or 'pro'",
        pattern="^(free|pro)$"
    )


@mcp.tool(
    title="Set License Tier",
    name="vault_set_tier",
    annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}
)
def vault_set_tier(params: VaultSetTierInput) -> str:
    """Activate a tier (free or pro) for LoreConvo.

    Pro tier removes the free-tier session limit (default: 50 sessions).
    After purchasing a Pro license, set LORECONVO_PRO=<your-license-key> in
    your environment and restart the server, then call this tool with tier='pro'
    to confirm Pro is active. Reverting to tier='free' re-enables limits (existing
    sessions are preserved -- only new saves are blocked once the limit is hit).
    """
    if params.tier == "pro":
        status = get_license_status()
        if not status["is_pro"]:
            if status.get("mode") == "invalid_key":
                return (
                    "Error: Invalid or expired license key in LORECONVO_PRO. "
                    + status.get("error", "")
                    + f" Get a new key by upgrading at {LORECONVO_UPGRADE_URL}."
                )
            return (
                "Error: No Pro license key found. "
                "Set LORECONVO_PRO=<your-license-key> in your environment and "
                "restart the server, then call vault_set_tier again. "
                f"Get a license key by upgrading at {LORECONVO_UPGRADE_URL}."
            )

    db_dir = Path(_get_db().config.db_path).parent
    try:
        _set_tier_config(db_dir, params.tier)
    except ValueError as exc:
        return f"Error: {exc}"

    if params.tier == "pro":
        return "[OK] Tier set to 'pro'. All limits removed. Enjoy unlimited sessions."
    return (
        f"[OK] Tier set to 'free'. Free tier active. "
        f"Limit: {_get_db().config.max_free_sessions} sessions."
    )


def _validate_export_path(output_path: str) -> tuple[Path, str | None]:
	"""Validate output_path against the configured export root.
	Returns (resolved_path, None) on success, (None, error_msg) on failure."""
	export_root = Path(
		os.environ.get('LORECONVO_EXPORT_DIR', Path.home() / 'loreconvo-exports')
	).expanduser().resolve()

	resolved = Path(output_path).expanduser().resolve()

	# Path must be within the export root
	try:
		resolved.relative_to(export_root)
	except ValueError:
		return None, (
			f"output_path must be within the export directory ({export_root}). "
			f"Set LORECONVO_EXPORT_DIR to change the export root."
		)

	# Extension check
	if resolved.suffix.lower() not in ('.json', '.jsonl'):
		return None, "output_path must end with .json or .jsonl"

	# Create export root if it does not exist (chmod 700)
	if not export_root.exists():
		export_root.mkdir(parents=True, mode=0o700, exist_ok=True)

	return resolved, None


@mcp.tool(title="Export Sessions")
def export_sessions(
    output_path: str | None = None,
    project: str | None = None,
    tags: list[str] | None = None,
    days_back: int | None = None,
    limit: int = 1000,
    format: str = "json",
) -> dict:
    """Export sessions to JSON or JSONL for backup or migration.

    Exports all matching sessions with full detail (including skills, tags,
    artifacts). Use output_path to write to a file; omit it to receive the
    data inline. Use import_sessions to load the exported file.

    Args:
        output_path: File path to write export (e.g. '/tmp/loreconvo_export.json').
                     If omitted, data is returned inline.
        project: Export only sessions from this project.
        tags: Export only sessions that have any of these tags.
        days_back: Limit to sessions from the last N days. Omit for all time.
        limit: Max sessions to export (default 1000).
        format: 'json' (array wrapped in metadata) or 'jsonl' (one session per line).
    """
    sessions = _get_db().get_sessions_for_export(
        project=project, tags=tags, days_back=days_back, limit=limit
    )

    def _session_to_dict(s) -> dict:
        return {
            "id": s.id,
            "title": s.title,
            "surface": s.surface,
            "project": s.project,
            "start_date": s.start_date,
            "end_date": s.end_date,
            "summary": s.summary,
            "decisions": s.decisions,
            "artifacts": s.artifacts,
            "open_questions": s.open_questions,
            "tags": s.tags,
            "skills_used": s.skills_used,
            "created_at": s.created_at,
        }

    session_dicts = [_session_to_dict(s) for s in sessions]

    if format == "jsonl":
        data_str = "\n".join(json.dumps(d) for d in session_dicts)
    else:
        export_obj = {
            "loreconvo_export": {
                "version": "1.0",
                "session_count": len(session_dicts),
                "filters": {
                    "project": project,
                    "tags": tags,
                    "days_back": days_back,
                },
                "sessions": session_dicts,
            }
        }
        data_str = json.dumps(export_obj, indent=2)

    if output_path:
        resolved, err = _validate_export_path(output_path)
        if err:
            return {"error": err}
        resolved.write_text(data_str, encoding="utf-8")
        return {
            "status": "exported",
            "path": str(resolved),
            "session_count": len(sessions),
            "format": format,
        }

    return {
        "status": "exported",
        "session_count": len(sessions),
        "format": format,
        "data": data_str,
    }


@mcp.tool(title="Export Sessions for Anthropic")
def export_for_anthropic(
    output_path: str | None = None,
    project: str | None = None,
    session_ids: list[str] | None = None,
    days_back: int | None = None,
) -> dict:
    """Export LoreConvo sessions to Anthropic managed-agents memory format. Pro only.

    Produces a JSON file in 'anthropic-memory-v1' format, suitable for import into
    Anthropic managed-agents memory stores. Only non-periodic, non-file-memory sessions
    are exported (contamination control).

    NOTE: Field mapping is preliminary pending Anthropic beta API schema stabilization.
    Cassandra will signal when the schema is stable. Save the output and validate
    against Anthropic docs before submitting to a managed-agents memory store.

    Args:
        output_path: File path to write the export. If omitted, data is returned inline.
        project: Export only sessions from this project.
        session_ids: List of specific session UUIDs to export. Overrides project filter.
        days_back: Limit to sessions from the last N days.
    """
    from datetime import datetime, timedelta, timezone as _tz

    status = get_license_status()
    if not status["is_pro"]:
        return {
            "error": (
                "Export to Anthropic format requires LoreConvo Pro. "
                f"Get a license by upgrading at {LORECONVO_UPGRADE_URL}."
            )
        }

    sessions = _get_db().get_sessions_for_shared_export(
        project=project,
        session_id_filter=session_ids,
        export_all=(session_ids is None and project is None),
    )

    if days_back is not None:
        cutoff = (datetime.now(_tz.utc) - timedelta(days=days_back)).isoformat().replace('+00:00', 'Z')
        sessions = [s for s in sessions if s.start_date >= cutoff]

    entries = []
    for s in sessions:
        entries.append({
            "id": s.id,
            "content": s.summary or "",
            "created_at": s.created_at,
            "tags": s.tags or [],
            "metadata": {
                "title": s.title,
                "surface": s.surface,
                "project": s.project,
            },
        })

    export_obj = {
        "format": "anthropic-memory-v1",
        "source": "loreconvo",
        "exported_at": datetime.now(_tz.utc).isoformat().replace("+00:00", "Z"),
        "schema_note": (
            "Preliminary field mapping -- validate against Anthropic beta API "
            "docs before submitting to Anthropic memory stores."
        ),
        "entry_count": len(entries),
        "entries": entries,
    }

    data_str = json.dumps(export_obj, indent=2)

    if output_path:
        resolved, err = _validate_export_path(output_path)
        if err:
            return {"error": err}
        resolved.write_text(data_str, encoding="utf-8")
        return {
            "status": "exported",
            "format": "anthropic-memory-v1",
            "path": str(resolved),
            "entry_count": len(entries),
        }

    return {
        "status": "exported",
        "format": "anthropic-memory-v1",
        "entry_count": len(entries),
        "data": data_str,
    }


@mcp.tool(title="Import Sessions")
def import_sessions(
    file_path: str,
    on_conflict: str = "skip",
    dry_run: bool = False,
) -> dict:
    """Import sessions from a LoreConvo export file (JSON or JSONL).

    Reads an export created by export_sessions and saves sessions into the
    local database. Session UUIDs are preserved so re-importing is safe.

    Args:
        file_path: Path to the export file (JSON or JSONL format).
        on_conflict: What to do if a session ID already exists.
                     'skip' (default) -- leave the existing session unchanged.
                     'replace' -- overwrite with the imported version.
        dry_run: If True, parse and validate the file but make no DB changes.
    """
    if on_conflict not in ("skip", "replace"):
        return {"error": "on_conflict must be 'skip' or 'replace'"}

    path = Path(file_path)
    if not path.exists():
        return {"error": f"File not found: {file_path}"}

    if path.stat().st_size > _MAX_IMPORT_BYTES:
        return {"error": "Import file too large. Max: 50 MB."}

    raw = path.read_text(encoding="utf-8").strip()

    raw_sessions: list[dict] = []
    # Try JSON format with wrapper first
    try:
        wrapper = json.loads(raw)
        if "loreconvo_export" in wrapper:
            raw_sessions = wrapper["loreconvo_export"]["sessions"]
        elif isinstance(wrapper, dict) and ("id" in wrapper or "title" in wrapper):
            # Single-session JSONL: one JSON object that is valid JSON on its own
            raw_sessions = [wrapper]
        else:
            return {"error": "Invalid export file: missing 'loreconvo_export' key"}
    except json.JSONDecodeError:
        # Fall back to JSONL -- one session per line
        for line_num, line in enumerate(raw.splitlines(), 1):
            line = line.strip()
            if not line:
                continue
            try:
                raw_sessions.append(json.loads(line))
            except json.JSONDecodeError as exc:
                return {"error": f"Invalid JSON on line {line_num}: {exc}"}

    if len(raw_sessions) > _MAX_SESSIONS_PER_FILE:
        return {"error": "Import file contains too many sessions. Max: 10,000."}

    imported = 0
    replaced = 0
    skipped = 0
    limit_hit = False

    for raw_s in raw_sessions:
        title = str(raw_s.get("title", "") or "")[:_IMPORT_FIELD_CAPS["title"]]
        summary = str(raw_s.get("summary", "") or "")[:_IMPORT_FIELD_CAPS["summary"]]
        decisions = [str(d)[:_IMPORT_FIELD_CAPS["list_item"]] for d in (raw_s.get("decisions") or [])]
        open_questions = [str(q)[:_IMPORT_FIELD_CAPS["list_item"]] for q in (raw_s.get("open_questions") or [])]
        tags = [str(t)[:_IMPORT_FIELD_CAPS["list_item"]] for t in (raw_s.get("tags") or [])]
        artifacts = [Path(str(a)).name for a in (raw_s.get("artifacts") or [])]
        skills_used = [str(s)[:_IMPORT_FIELD_CAPS["list_item"]] for s in (raw_s.get("skills_used") or [])]
        session = Session(
            id=raw_s.get("id", ""),
            title=title,
            surface=raw_s.get("surface", ""),
            project=raw_s.get("project"),
            start_date=raw_s.get("start_date", ""),
            end_date=raw_s.get("end_date"),
            summary=summary,
            decisions=decisions,
            artifacts=artifacts,
            open_questions=open_questions,
            tags=tags,
            skills_used=skills_used,
            created_at=raw_s.get("created_at", ""),
        )
        if not session.id:
            skipped += 1
            continue

        if dry_run:
            if _get_db().session_exists(session.id):
                if on_conflict == "replace":
                    replaced += 1
                else:
                    skipped += 1
            else:
                imported += 1
            continue

        try:
            result = _get_db().import_session(session, replace=(on_conflict == "replace"))
        except SessionLimitReachedError:
            limit_hit = True
            break

        if result == "imported":
            imported += 1
        elif result == "replaced":
            replaced += 1
        else:
            skipped += 1

    summary = {
        "status": "dry_run" if dry_run else "done",
        "total_in_file": len(raw_sessions),
        "imported": imported,
        "replaced": replaced,
        "skipped": skipped,
    }
    if dry_run:
        summary["note"] = (
            f"Dry run preview: {imported} would-import, {replaced} would-replace, "
            f"{skipped} would-skip. No changes made."
        )
    if limit_hit:
        summary["warning"] = (
            "Free tier limit reached. Some sessions were not imported. "
            "Upgrade to Pro for unlimited sessions."
        )
        summary["upgrade_url"] = LORECONVO_UPGRADE_URL
    return summary


@mcp.tool(title="Inspect Sessions")
def inspect_sessions(
    session_id: str | None = None,
    search: str | None = None,
    tag: str | None = None,
    surface: str | None = None,
    since: str | None = None,
    limit: int = 20,
    show_stats: bool = False,
) -> dict:
    """Inspect stored sessions: list, filter, or get full detail for one session.

    Answers 'what do you know about me?' and helps users find, browse, and
    understand their stored session memory.

    Args:
        session_id: If provided, return full detail for this specific session.
        search: Full-text search query across title, summary, decisions, tags.
        tag: Filter by tag substring (e.g. 'agent:ron', 'side_hustle').
        surface: Filter by surface ('code', 'cowork', 'chat').
        since: Return sessions on or after this date (YYYY-MM-DD).
        limit: Max sessions to return (default 20).
        show_stats: If True, include aggregate counts (total, by_surface, by_project).
    """
    if session_id:
        session = _get_db().get_session(session_id)
        if not session:
            return {"error": f"Session {session_id} not found"}
        return {
            "id": session.id,
            "title": session.title,
            "date": session.start_date[:16] if session.start_date else "",
            "surface": session.surface,
            "project": session.project,
            "tags": session.tags,
            "summary": session.summary,
            "decisions": session.decisions,
            "artifacts": session.artifacts,
            "open_questions": session.open_questions,
            "skills_used": session.skills_used,
            "keep_forever": 1 if session.keep_forever else 0,
        }

    sessions = _get_db().inspect_sessions(
        search=search, tag=tag, surface=surface, since=since, limit=limit
    )

    result: dict = {
        "sessions": [
            {
                "id": s.id[:8] if s.id else "",
                "full_id": s.id,
                "date": s.start_date[:10] if s.start_date else "",
                "surface": s.surface,
                "tags": s.tags,
                "title": s.title,
            }
            for s in sessions
        ],
        "count": len(sessions),
    }

    if show_stats:
        result["stats"] = _get_db().get_inspect_stats()

    return result


@mcp.tool(title="Get Usage Stats")
def get_stats() -> dict:
    """Return a usage dashboard: session counts by surface, project, and tag;
    storage metrics (DB size, estimated tokens stored); and the 5 most recent sessions.

    Provides visibility into your memory usage -- who saved what, how much is stored,
    and what's been captured most recently. Includes hook_saves_failing status.
    """
    result = _get_db().get_usage_stats()
    data_dir = Path(_get_db().config.db_path).parent
    breadcrumb_path = data_dir / "hook_failure.json"
    result["hook_saves_failing"] = breadcrumb_path.exists()
    return result


@mcp.tool(title="Consolidate Memories")
def consolidate_memories(
    project: str,
    surface: str | None = None,
    max_sessions: int = 50,
    mode: str = "heuristic",
    dedup: str | None = None,
) -> dict:
    """Run memory consolidation for a project to build a structured digest.

    Analyzes recent sessions and extracts decisions, open questions, and tech
    stack facts. Free tier: up to 3 consolidations per day. Pro: unlimited.

    Returns a digest dict with status, decisions found, open questions, and
    the formatted digest_markdown for reference.

    Acquires an exclusive lock; returns status='lock_held' if another
    consolidation is already running.

    Args:
        project: Project name (matches the --project tag used when saving sessions)
        surface: Surface to consolidate ('code', 'cowork', 'chat', etc.) or None for all
        max_sessions: Maximum number of recent sessions to analyze (default 50)
        mode: 'heuristic' (free, default). 'llm' requires Pro (v0.6.1).
        dedup: Semantic dedup pass mode: 'off' (default), 'conservative', or
            'balanced'. When 'off' (or unset, or unrecognised), the pass does
            not run and consolidation behaves exactly as before. 'conservative'
            collapses near-verbatim restatements (cosine > 0.97); 'balanced'
            collapses paraphrases (cosine > 0.95). Can also be set via the
            LORECONVO_CONSOLIDATION_DEDUP environment variable; an explicit
            argument always overrides the env var.
    """
    from core.consolidation import HeuristicConsolidator
    import pathlib
    lore_dir = str(pathlib.Path(_get_db().config.db_path).parent)
    consolidator = HeuristicConsolidator(lore_dir=lore_dir)
    result = consolidator.consolidate(
        project=project,
        surface=surface,
        db=_get_db(),
        max_sessions=max_sessions,
        mode="heuristic",  # LLM mode deferred to v0.6.1
        is_pro=_get_db().config.is_pro,
        trigger="on-demand",
        dedup=dedup,
    )
    return result


@mcp.tool(title="Get Memory Digest")
def get_memory_digest(
    project: str,
    surface: str | None = None,
    disable: bool | None = None,
    max_tokens: int = 2000,
) -> dict:
    """Retrieve the current memory digest for a project without re-running consolidation.

    Returns None if no digest exists. Use consolidate_memories first to generate one.

    Optionally set disable=True to suppress auto-load injection for this digest,
    or disable=False to re-enable injection. Omit disable to just read the current state.

    Args:
        project: Project name
        surface: Surface filter (or None for all)
        disable: If provided, update the disabled flag on the digest
        max_tokens: Truncate digest_markdown to this estimated token limit (len // 4).
                    Default 2000. If truncated, appends [TRUNCATED] marker.
    """
    if disable is not None:
        _get_db().update_digest_disabled(project, surface, disabled=disable)
    digest = _get_db().get_memory_digest(project, surface)
    if digest is None:
        return {
            "status": "no_digest",
            "message": "No memory digest found. Run consolidate_memories to generate one.",
            "project": project,
            "surface": surface,
        }
    digest_md = digest.get("digest_markdown", "")
    if digest_md and max_tokens > 0:
        estimated_tokens = len(digest_md) // 4
        if estimated_tokens > max_tokens:
            # Truncate at estimated token boundary (max_tokens * 4 chars)
            truncate_at = max_tokens * 4
            digest_md = digest_md[:truncate_at] + (
                "\n\n[TRUNCATED -- request smaller max_tokens or "
                "run consolidation with fewer sources]"
            )
    return {
        "status": "ok",
        "project": digest["project"],
        "surface": digest["surface"],
        "mode": digest.get("mode", "heuristic"),
        "source_count": digest.get("source_count", 0),
        "updated_at": digest.get("updated_at", ""),
        "disabled": bool(digest.get("disabled", 0)),
        "digest_markdown": digest_md,
        "decisions": digest.get("decisions"),
        "open_questions": digest.get("open_questions"),
        "known_stack": digest.get("known_stack"),
    }


@mcp.tool(title="Set Session Expiry")
def set_session_expiry(
    session_id: str,
    expires_at: str | None,
) -> dict:
    """Set or clear an expiry date on a session.

    After expires_at passes, the session is excluded from search_sessions,
    get_recent_sessions, and the auto-load hook. The session is NOT deleted --
    recover it with search_sessions(include_expired=True).
    Pass expires_at=None to clear a previously set expiry.

    Args:
        session_id: ID of the session to update
        expires_at: ISO 8601 date string (e.g. '2027-01-01T00:00:00Z'), or None to clear
    """
    result = _get_db().set_session_expiry(session_id, expires_at)
    if not result.get("ok"):
        return {
            "status": result.get("code", "error"),
            "session_id": session_id,
            "message": result.get("message"),
        }
    return {
        "status": "ok",
        "session_id": session_id,
        "expires_at": expires_at,
    }


@mcp.tool(title="Get Dream Log")
def get_dream_log(
    project: str | None = None,
    surface: str | None = None,
    limit: int = 10,
) -> dict:
    """Return recent consolidation log entries for transparency and diagnostics.

    Each entry shows: timestamp, project, surface, mode, source_count, trigger.
    Use this to confirm consolidation ran, check rate limit status, and diagnose
    fallbacks (e.g. api_key_found=false for LLM-mode fallback).

    Args:
        project: Filter by project (or None for all projects)
        surface: Filter by surface (or None for all)
        limit: Maximum number of entries to return (default 10, newest first)
    """
    import pathlib
    lore_dir = pathlib.Path(_get_db().config.db_path).parent
    log_path = str(lore_dir / "consolidation.log")
    entries = _get_db().get_consolidation_log_entries(
        project=project,
        surface=surface,
        limit=limit,
        log_path=log_path,
    )
    digest = None
    if project:
        raw = _get_db().get_memory_digest(project, surface)
        if raw:
            inject_env = os.environ.get("LORECONVO_DREAM_INJECT", "true").lower()
            inject_active = inject_env != "false" and not bool(raw.get("disabled", 0))
            digest = {
                "updated_at": raw.get("updated_at", ""),
                "mode": raw.get("mode", "heuristic"),
                "source_count": raw.get("source_count", 0),
                "disabled": bool(raw.get("disabled", 0)),
                "api_key_found": bool(raw.get("api_key_found", 1)),
                "injection_active": inject_active,
                "injection_reason": (
                    "active" if inject_active
                    else ("LORECONVO_DREAM_INJECT=false" if inject_env == "false"
                          else "digest.disabled=1 -- manually suppressed")
                ),
            }
    return {
        "status": "ok",
        "project": project,
        "surface": surface,
        "entries": entries,
        "digest_status": digest,
    }


@mcp.tool(title="Get Docs for Session")
def get_docs_for_session(session_id: str, limit: int = 5) -> dict:
    """Return LoreDocs documents cross-linked to a LoreConvo session. Pro tier only.

    Queries the LoreDocs cross_product_links table. Both LoreConvo and LoreDocs
    must be installed. Returns an empty list for free-tier callers (not an error).

    Manual links (link_type='manual') are always sorted first. Auto-links created
    with a stale embedding model are marked with is_stale=True and include an
    upgrade_message.

    Args:
        session_id  -- LoreConvo session UUID
        limit       -- max results (default 5)

    Returns dict with:
        schema_version          -- int, for version negotiation by callers
        cross_product_available -- bool
        tier_gate               -- "satisfied" | "pro_required"
        links                   -- list of link dicts
        reason                  -- set when cross_product_available is False
    """
    try:
        ld_db = discover_loredocs_db()
    except LoreDocsAccessError as exc:
        return {
            "schema_version": 0,
            "cross_product_available": False,
            "reason": f"LoreDocs installed but unreachable: {exc}",
            "links": [],
        }
    if ld_db is None:
        return {
            "schema_version": 0,
            "cross_product_available": False,
            "reason": "LoreDocs not installed",
            "links": [],
        }

    try:
        return get_cross_product_links(
            ld_db,
            source_product="loreconvo",
            source_id=session_id,
            current_embedding_model=CROSS_LINK_EMBEDDING_MODEL,
            limit=limit,
            is_pro=_get_db().config.is_pro,
        )
    except LoreDocsSchemaError as exc:
        return {
            "schema_version": 0,
            "cross_product_available": False,
            "reason": f"LoreDocs schema too old: {exc}",
            "links": [],
        }


@mcp.tool(title="Link Session to Doc")
def session_link_doc(session_id: str, doc_id: str, vault_id: str) -> dict:
    """Create a manual cross-product link from a LoreConvo session to a LoreDocs doc.

    Manual links are accessible on all tiers. The target doc must not be in a
    vault with cross_link_opt_out enabled. Both products must be installed.

    Args:
        session_id  -- LoreConvo session UUID
        doc_id      -- LoreDocs document ID
        vault_id    -- LoreDocs vault containing the document

    Returns dict with:
        ok      -- bool
        reason  -- failure description on error. Specific since SH-100670:
                   "LoreDocs not installed" | "LoreDocs installed but
                   unreachable: <detail>" | "LoreDocs schema too old: <detail>"
                   | "vault not found" | "vault has cross-linking disabled"
                   | "document not found"
    """
    try:
        ld_db = discover_loredocs_db()
    except LoreDocsAccessError as exc:
        return {"ok": False, "reason": f"LoreDocs installed but unreachable: {exc}"}
    if ld_db is None:
        return {"ok": False, "reason": "LoreDocs not installed"}

    try:
        return link_session_to_doc(
            ld_db,
            session_id=session_id,
            doc_id=doc_id,
            vault_id=vault_id,
            link_type="manual",
            is_pro=_get_db().config.is_pro,
        )
    except LoreDocsSchemaError as exc:
        return {"ok": False, "reason": f"LoreDocs schema too old: {exc}"}


@mcp.tool(title="Get Server Info")
def get_server_info() -> dict:
    """Return MCP compatibility status for this LoreConvo server.

    Returns product version, installed mcp SDK version, tested version, and
    compatibility status. Useful for diagnosing version mismatches on running
    servers without requiring a restart.

    Returns dict with: product_name, product_version, install_kind (wheel|editable),
    version_from_source (if editable), mcp_installed, mcp_tested, mcp_accepted,
    status (ok|mismatch|undetermined|disabled|internal_error), note,
    error_detail (set only on internal_error), hook_saves_failing.
    """
    from compat_check import detect_install_kind, extract_live_version_from_source

    result = _compat_check()
    result_copy = dict(result)

    install_kind = detect_install_kind()
    result_copy["install_kind"] = install_kind

    if install_kind == "editable":
        live_version = extract_live_version_from_source()
        if live_version:
            result_copy["version_from_source"] = live_version
        existing_note = result_copy.get("note", "")
        editable_note = "Product version from install-time metadata (frozen at pip install -e); may lag actual source"
        if existing_note:
            result_copy["note"] = existing_note + "; " + editable_note
        else:
            result_copy["note"] = editable_note

    data_dir = Path(_get_db().config.db_path).parent
    breadcrumb_path = data_dir / "hook_failure.json"
    result_copy["hook_saves_failing"] = breadcrumb_path.exists()
    return result_copy


# -- Anti-pattern storage tools (v0.8.0) --

@mcp.tool(title="Get Anti-Patterns")
def get_anti_patterns(
    topic: str | None = None,
    limit: int = 10,
    project: str | None = None,
) -> list[dict]:
    """Retrieve sessions marked as anti-patterns.

    Returns a list of dicts with a 'truncated' boolean. Use at session start
    or before attempting a known-tricky approach to surface past failures.

    Args:
        topic: Optional keyword to filter within anti-patterns. Omit for all
               anti-patterns ordered by recency. When provided, uses FTS5 with
               a fan-out heuristic; result may be truncated if anti-patterns are
               sparse in the corpus.
        limit: Max results to return (1-100). Defaults to 10.
        project: Restrict to a specific project slug. Case-sensitive.
    """
    if not isinstance(limit, int) or limit < 1 or limit > 100:
        return [{"error": "limit must be an integer 1-100", "status": "error"}]

    topic_clean = (topic or "").strip()[:500]
    project_clean = (project or "").strip() or None
    truncated = False

    if not topic_clean:
        params: list = []
        sql = """
            SELECT s.*
            FROM sessions s
            JOIN anti_pattern_sessions ap ON ap.session_id = s.id
        """
        if project_clean:
            sql += " WHERE s.project = ?"
            params.append(project_clean)
        sql += " ORDER BY s.start_date DESC LIMIT ?"
        params.append(limit)
        rows = _get_db().conn.execute(sql, params).fetchall()
        sessions_list = [_get_db()._row_to_session(r) for r in rows]
    else:
        fetch_limit = min(limit * 4, 400)
        fts_results = _get_db().search_sessions(
            query=topic_clean,
            project=project_clean,
            limit=fetch_limit,
        )
        if not fts_results:
            sessions_list = []
        else:
            candidate_ids = [r.session.id for r in fts_results]
            placeholders = ",".join("?" * len(candidate_ids))
            anti_ids = set(
                row[0] for row in _get_db().conn.execute(
                    f"SELECT session_id FROM anti_pattern_sessions "
                    f"WHERE session_id IN ({placeholders})",
                    candidate_ids
                ).fetchall()
            )
            sessions_list = [
                r.session for r in fts_results if r.session.id in anti_ids
            ][:limit]
        # FTS path can under-return when anti-patterns are sparse in corpus.
        truncated = len(sessions_list) < limit

    return [
        {
            "session_id": s.id or "",
            "session_title": s.title or "",
            "date": s.start_date or "",
            "project": s.project or "",
            "summary": (s.summary or "")[:2000],
            "decisions": list(s.decisions) if isinstance(s.decisions, list) else [],
            "open_questions": list(s.open_questions) if isinstance(s.open_questions, list) else [],
            "truncated": truncated,
        }
        for s in sessions_list
    ]


@mcp.tool(title="Tag Session as Anti-Pattern")
def tag_as_anti_pattern(session_id: str,
                         source: str = "unknown",
                         reason: str = "") -> dict:
    """Mark an existing session as an anti-pattern. Idempotent.

    Args:
        session_id: The sessions.id value to mark (TEXT <= 255 chars).
        source: Attribution for this tag (e.g., 'claude-code', 'agent:gina').
        reason: Human-readable reason for the tag. Stored in audit log.
    """
    try:
        result = _get_db().mark_anti_pattern(session_id, source=source, reason=reason)
        return {"status": result, "session_id": session_id}
    except (ValueError, LookupError) as exc:
        return {"status": "error", "error": str(exc)}
    except RuntimeError as exc:
        return {"status": "error", "error": str(exc), "error_code": "rate_limit_exceeded"}


@mcp.tool(title="Untag Anti-Pattern")
def untag_anti_pattern(session_id: str,
                        source: str = "unknown",
                        reason: str = "") -> dict:
    """Remove an anti-pattern tag from a session. Idempotent.

    The audit log row is written on successful removal; not written if the
    session was not tagged (idempotent no-op case).

    Args:
        session_id: The sessions.id value to untag (TEXT <= 255 chars).
        source: Attribution for this untag (e.g., 'claude-code', 'admin').
        reason: Human-readable reason for the removal. Stored in audit log.
    """
    try:
        result = _get_db().remove_anti_pattern(session_id, source=source, reason=reason)
        return {"status": result, "session_id": session_id}
    except ValueError as exc:
        return {"status": "error", "error": str(exc)}


@mcp.tool(title="Pin Session")
def pin_session(session_id: str, keep_forever: object = True) -> dict:
    """Pin or unpin a session to exclude it from automated cleanup.

    keep_forever=True (default): session excluded from future cleanup;
      any existing expires_at is cleared atomically.
    keep_forever=False: pin removed; session can receive expiry again.

    Returns:
        {"ok": True, "session_id": "...", "keep_forever": bool}
        {"ok": False, "code": "invalid_session_id", "message": "..."}
        {"ok": False, "code": "invalid_param", "message": "..."}
        {"ok": False, "code": "session_not_found", "message": "..."}
        {"ok": False, "code": "db_error", "message": "..."}
        {"ok": False, "code": "feature_disabled", "message": "..."}
    """
    import logging
    # Explicit bool coercion: accept True/False/1/0/"true"/"false"/"1"/"0"
    if isinstance(keep_forever, str):
        kf_lower = keep_forever.lower()
        if kf_lower in ("true", "1"):
            keep_forever = True
        elif kf_lower in ("false", "0"):
            keep_forever = False
        else:
            return {"ok": False, "code": "invalid_param",
                    "message": "keep_forever must be true or false; got an unrecognized string."}
    elif isinstance(keep_forever, int) and not isinstance(keep_forever, bool):
        # Reject non-0/1 integers [r6 HIGH #6]
        if keep_forever not in (0, 1):
            return {"ok": False, "code": "invalid_param",
                    "message": "keep_forever as an integer must be 0 or 1."}
        keep_forever = bool(keep_forever)
    elif not isinstance(keep_forever, bool):
        return {"ok": False, "code": "invalid_param",
                "message": "keep_forever must be a boolean."}

    if not _pinning_enabled(_get_db()):
        return {"ok": False, "code": "feature_disabled",
                "message": "Session pinning is disabled by configuration."}

    sid, err = parse_session_id(session_id)
    if err:
        return err
    try:
        found = _get_db().set_keep_forever(sid, keep_forever)
    except Exception as exc:
        logging.getLogger("loreconvo").error(
            "pin_session DB error for session %s: %s", sid, exc, exc_info=True
        )
        return {"ok": False, "code": "db_error",
                "message": "Database error occurred. Check logs for details."}
    if not found:
        return {"ok": False, "code": "session_not_found",
                "message": "No session found with the given id."}
    logging.getLogger("loreconvo").info(
        "pin_session: %s set to keep_forever=%s", sid, keep_forever
    )
    return {"ok": True, "session_id": sid, "keep_forever": keep_forever}


# -- Structured memory items: decisions/questions/artifacts (SH-12768) --

@mcp.tool(title="Save Memory Item")
def save_memory_item(
    item_type: str,
    title: str,
    body: str | None = None,
    session_id: str | None = None,
    project: str = "unspecified",
    tags: list[str] | None = None,
    metadata: dict | None = None,
    external_id: str | None = None,
    artifact_type: str | None = None,
) -> dict:
    """Save a structured memory item: a decision, open question, or artifact.

    Replaces the old free-text decisions/open_questions/artifacts lists on
    sessions with queryable, lifecycle-tracked rows. Idempotent when
    external_id is given: a second save with the same (project, external_id)
    returns the existing item (created=False) instead of creating a duplicate.

    Args:
        item_type: One of 'decision', 'open_question', 'artifact'.
        title: The decision text, the question text, or the artifact identifier.
        body: Free-text detail/rationale for decision/open_question. Ignored
            for artifacts -- use artifact_type instead. Capped at 4096 chars.
        session_id: Originating session, if any. Must reference an existing session.
        project: Project namespace (default 'unspecified').
        tags: Freeform tag list.
        metadata: Freeform key-value metadata (mainly for artifacts).
        external_id: Caller-supplied dedup key, unique per (project, external_id).
        artifact_type: For item_type='artifact', the artifact's type (e.g. 'file', 'url').
    """
    return _get_db().save_memory_item(
        item_type=item_type, title=title, body=body, session_id=session_id,
        project=project, tags=tags, metadata=metadata, external_id=external_id,
        artifact_type=artifact_type,
    )


@mcp.tool(title="Query Memory Items")
def query_memory_items(
    item_type: str | None = None,
    project: str | None = None,
    status: str | None = None,
    artifact_type: str | None = None,
    days: int | None = None,
    limit: int = 50,
) -> dict:
    """Query structured memory items by type, project, status, and recency.

    Args:
        item_type: Filter to 'decision', 'open_question', or 'artifact'.
        project: Filter to a project namespace.
        status: Filter to a lifecycle status (e.g. 'active', 'open', 'retired').
        artifact_type: Filter artifacts by their artifact_type. Only applies
            with item_type='artifact'.
        days: Only items created in the last N days.
        limit: Max rows to return (default 50, max 200).
    """
    return _get_db().query_memory_items(
        item_type=item_type, project=project, status=status,
        artifact_type=artifact_type, days=days, limit=limit,
    )


@mcp.tool(title="Transition Memory Item")
def transition_memory_item(
    item_id: str,
    transition: str,
    reason: str | None = None,
    closing_session_id: str | None = None,
) -> dict:
    """Move a memory item through its lifecycle.

    Valid transitions: 'retire' (decision -> retired); 'answer' and
    'wont-answer' (open_question -> answered / wont-answer). Already-closed
    items return code='already_closed' so callers can retry idempotently.

    Args:
        item_id: The memory item's id.
        transition: 'retire', 'answer', or 'wont-answer'.
        reason: Optional free-text reason recorded on close.
        closing_session_id: Session performing the transition, if any. Must
            reference an existing session.
    """
    return _get_db().transition_memory_item(
        item_id=item_id, transition=transition, reason=reason,
        closing_session_id=closing_session_id,
    )


@mcp.tool(title="Update Memory Item")
def update_memory_item(
    item_id: str,
    title: str | None = None,
    body: str | None = None,
    tags: list[str] | None = None,
    metadata: dict | None = None,
    new_project: str | None = None,
    allow_project_change: bool = False,
) -> dict:
    """Correct a memory item's title, body, tags, or metadata, or move it between projects.

    Moving projects requires allow_project_change=True as an explicit guard
    against accidental cross-project moves. If the item has an external_id,
    the move is rejected with code='external_id_conflict' when the
    destination project already has an item with that external_id.

    Args:
        item_id: The memory item's id.
        title: New title, if changing.
        body: New body, if changing. Capped at 4096 chars.
        tags: New tag list, if changing (replaces, not merges).
        metadata: New metadata dict, if changing (replaces, not merges).
        new_project: Destination project, if moving.
        allow_project_change: Must be True to actually move projects.
    """
    return _get_db().update_memory_item(
        item_id=item_id, title=title, body=body, tags=tags, metadata=metadata,
        new_project=new_project, allow_project_change=allow_project_change,
    )


def main():
    """Entry point for uvx / console script execution."""
    import argparse
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--dry-run-validate", action="store_true",
                        help="Validate schema and exit (exit 1 on failure, exit 0 on success).")
    args, _ = parser.parse_known_args()

    if args.dry_run_validate:
        from core.database import _validate_anti_pattern_schema
        try:
            _validate_anti_pattern_schema(_get_db().conn)
            print("Schema validation: OK", file=sys.stderr)
            sys.exit(0)
        except RuntimeError as exc:
            print(f"Schema validation FAILED: {exc}", file=sys.stderr)
            sys.exit(1)

    _compat_emit(_compat_check())
    _check_egg_info_conflict()
    from core import idle_watchdog
    # Release the DB connection (and its write lock) when the client parks
    # this process idle -- stays alive so Claude Code/Desktop (which do not
    # re-spawn a stdio server that exits) keep a working connection (SH-13610).
    idle_watchdog.install(
        mcp, env_var="LORECONVO_IDLE_TIMEOUT",
        release_func=_get_db().release_idle_connection,
        backstop_env_var="LORECONVO_IDLE_BACKSTOP_TIMEOUT",
    )
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
