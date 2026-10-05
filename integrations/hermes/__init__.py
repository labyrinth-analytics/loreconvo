"""
LoreConvo memory provider for Hermes Agent.

Wraps LoreConvo's SessionDatabase directly — no MCP, no stdio.
Same ~/.loreconvo/sessions.db, same schema, same data.

Activate with: hermes memory setup  (select "loreconvo")
Or:             memory.provider: loreconvo  in config.yaml
"""

from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# -- LoreConvo imports (pip-installed package or source-tree fallback) --------

def _import_loreconvo(module: str):
    """Import a loreconvo core submodule from the installed package."""
    import importlib
    return importlib.import_module(f"loreconvo.core.{module}")

# -- Hermes imports (only available inside Hermes runtime) -------------------
try:
    from agent.memory_provider import MemoryProvider, RecallStatus
    _HERMES_AVAILABLE = True
except ImportError:
    MemoryProvider = object  # type: ignore
    RecallStatus = None  # type: ignore
    _HERMES_AVAILABLE = False


# -- Provider -----------------------------------------------------------------

class LoreConvoMemoryProvider(MemoryProvider):  # type: ignore
    """Hermes memory provider backed by LoreConvo's SQLite session store."""

    name = "loreconvo"

    def __init__(self) -> None:
        self._session_id: str = ""
        self._project: str = ""
        self._db: Any = None
        self._last_prefetch_count: int = 0
        self._initialized: bool = False
        self._is_primary: bool = True

    # -- Core lifecycle -------------------------------------------------------

    def is_available(self) -> bool:
        """True if the loreconvo package is installed and the DB directory is writable."""
        if not _HERMES_AVAILABLE:
            return False
        try:
            import loreconvo  # noqa: F401
        except ImportError:
            logger.warning("is_available: loreconvo import failed")
            return False
        try:
            db_dir = Path.home() / ".loreconvo"
            if db_dir.exists():
                return os.access(db_dir, os.W_OK)
            return os.access(db_dir.parent, os.W_OK)
        except Exception:
            logger.warning("is_available: path check failed", exc_info=True)
            return False

    def unavailable_reason(self) -> str:
        if not _HERMES_AVAILABLE:
            return "Not running inside Hermes Agent"
        try:
            import loreconvo  # noqa: F401
        except ImportError:
            return "loreconvo package not installed (pip install loreconvo)"
        return ""

    def initialize(self, session_id: str, **kwargs: Any) -> None:
        """Open the LoreConvo database and set up session tracking."""
        SessionDatabase = _import_loreconvo("database").SessionDatabase

        self._session_id = session_id
        self._project = os.environ.get("LORECONVO_HERMES_PROJECT", "hermes")
        agent_context = kwargs.get("agent_context", "primary")
        self._is_primary = agent_context not in ("cron", "flush", "subagent")
        try:
            self._db = SessionDatabase()
            self._initialized = True
            logger.info(
                "LoreConvo memory provider initialized (session=%s, project=%s, primary=%s)",
                session_id[:8] if session_id else "?", self._project, self._is_primary,
            )
        except Exception as exc:
            logger.warning("LoreConvo DB open failed: %s — provider will be inert", exc)
            self._initialized = False

    def shutdown(self) -> None:
        """Close the database connection."""
        if self._db is not None:
            try:
                self._db.close()
            except Exception:
                pass
            self._db = None
        self._initialized = False

    # -- System prompt --------------------------------------------------------

    def system_prompt_block(self) -> str:
        return (
            "LoreConvo session memory is active. Past sessions across Claude surfaces "
            "(Code, Cowork, Chat) are searchable. Use loreconvo_search_sessions to find "
            "prior work, loreconvo_get_context to recall project context, and "
            "loreconvo_save_memory to persist decisions, questions, or artifacts."
        )

    # -- Recall / prefetch ----------------------------------------------------

    def prefetch(self, query: str, *, session_id: str = "") -> str:
        """Return formatted context from past LoreConvo sessions relevant to the query."""
        if not self._initialized or not self._db:
            return ""
        if not query.strip():
            return ""

        try:
            results = self._db.get_context_for(
                topic=query,
                max_results=3,
            )
            # get_context_for returns List[SearchResult]
            if not results:
                self._last_prefetch_count = 0
                return ""

            # Build a compact recall block from SearchResult objects
            lines: List[str] = ["[LoreConvo recall]"]
            session_count = 0
            decisions_seen: set = set()

            for sr in results:
                session = sr.session
                session_count += 1
                title = getattr(session, "title", "")
                summary = (getattr(session, "summary", "") or "")[:300]
                decisions = getattr(session, "decisions", []) or []
                questions = getattr(session, "open_questions", []) or []

                if summary:
                    lines.append(f"- {title}: {summary}")

                for d in decisions:
                    if d not in decisions_seen and len(decisions_seen) < 8:
                        decisions_seen.add(d)
                        lines.append(f"  [decision] {d}")

                for q in questions[:3]:
                    lines.append(f"  [open question] {q}")

            self._last_prefetch_count = session_count
            return "\n".join(lines[:20])  # Cap at 20 lines
        except Exception as exc:
            logger.debug("LoreConvo prefetch failed: %s", exc)
            self._last_prefetch_count = 0
            return ""

    def recall_status(self) -> Optional[RecallStatus]:
        if not RecallStatus:
            return None
        if self._last_prefetch_count > 0:
            return RecallStatus(
                provider_label="loreconvo",
                count=self._last_prefetch_count,
                glyph="\U0001f4be",
            )
        return None

    # -- Turn persistence -----------------------------------------------------

    def sync_turn(
        self,
        user_content: str,
        assistant_content: str,
        *,
        session_id: str = "",
        messages: Optional[List[Dict[str, Any]]] = None,
        turn_author: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Per-turn sync disabled — LoreConvo saves once at session end to avoid noise.
        Override to re-enable incremental saves."""
        pass

    def on_session_end(self, messages: List[Dict[str, Any]]) -> None:
        """End-of-session save: persist the full conversation (primary sessions only)."""
        if not self._initialized or not self._db or not self._is_primary:
            return

        def _save() -> None:
            try:
                Session = _import_loreconvo("models").Session

                now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

                lines: List[str] = []
                for m in messages[:200]:  # Cap message count
                    role = m.get("role", "?")
                    content = m.get("content", "") or ""
                    if isinstance(content, list):
                        text_parts = [
                            p.get("text", "")
                            for p in content
                            if isinstance(p, dict) and p.get("type") == "text"
                        ]
                        content = " ".join(text_parts)
                    content = str(content)[:500]
                    lines.append(f"[{role}] {content}")

                transcript = "\n".join(lines)
                title = f"Hermes session {self._session_id[:8]}"

                session = Session(
                    title=title,
                    surface="code",
                    project=self._project,
                    start_date=now,
                    end_date=now,
                    summary=f"Hermes agent session.\n\n{transcript[:3000]}",
                    tags=["hermes", "session-end"],
                    source="hermes",
                    external_tool_session=False,
                )
                self._db.save_session(session)
                logger.info(
                    "LoreConvo on_session_end saved: %s (%d messages)",
                    title, len(messages),
                )
            except Exception as exc:
                logger.debug("LoreConvo on_session_end failed: %s", exc)

        t = threading.Thread(target=_save, daemon=True)
        t.start()

    def on_memory_write(
        self,
        action: str,
        target: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Mirror built-in memory writes to LoreConvo (primary sessions only)."""
        if not self._initialized or not self._db or not self._is_primary:
            return

        def _save() -> None:
            try:
                item_type = "decision" if target == "memory" else "open_question"
                title = f"[hermes] memory {action}: {content[:80]}"

                self._db.save_memory_item(
                    item_type=item_type,
                    title=title,
                    body=content,
                    project=self._project,
                    tags=["hermes", f"action:{action}", f"target:{target}"],
                )
            except Exception as exc:
                logger.debug("LoreConvo on_memory_write failed: %s", exc)

        t = threading.Thread(target=_save, daemon=True)
        t.start()

    # -- Tools ----------------------------------------------------------------

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "loreconvo_search_sessions",
                "description": (
                    "Search past LoreConvo sessions by keyword. "
                    "Returns matching sessions with titles, dates, and summaries."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query — keywords to find in session titles and summaries",
                        },
                        "project": {
                            "type": "string",
                            "description": f"Filter by project (default: {self._project})",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum results (default: 10, max: 25)",
                            "default": 10,
                            "minimum": 1,
                            "maximum": 25,
                        },
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "loreconvo_get_context",
                "description": (
                    "Get relevant past sessions for a topic. "
                    "Returns matching sessions with summaries and decisions."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "topic": {
                            "type": "string",
                            "description": "The topic or question to find context for",
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "Maximum results (default: 5, max: 15)",
                            "default": 5,
                            "minimum": 1,
                            "maximum": 15,
                        },
                    },
                    "required": ["topic"],
                },
            },
            {
                "name": "loreconvo_save_memory",
                "description": (
                    "Save a structured memory item — a decision, question, artifact, or note — "
                    "to LoreConvo for future recall."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "title": {
                            "type": "string",
                            "description": "Short title for this memory item",
                        },
                        "content": {
                            "type": "string",
                            "description": "Full content of the memory item",
                        },
                        "item_type": {
                            "type": "string",
                            "enum": ["decision", "open_question", "artifact"],
                            "description": "Type of memory item",
                        },
                        "tags": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Tags for categorization (e.g. [\"architecture\", \"p0\"])",
                        },
                    },
                    "required": ["title", "content"],
                },
            },
        ]

    def handle_tool_call(self, tool_name: str, args: Dict[str, Any], **kwargs: Any) -> str:
        if not self._initialized or not self._db:
            return json.dumps({"error": "LoreConvo is not available"})

        handlers = {
            "loreconvo_search_sessions": self._handle_search,
            "loreconvo_get_context": self._handle_context,
            "loreconvo_save_memory": self._handle_save_memory,
        }
        handler = handlers.get(tool_name)
        if handler is None:
            return json.dumps({"error": f"Unknown tool: {tool_name}"})

        try:
            return handler(args)
        except Exception as exc:
            logger.debug("LoreConvo tool %s failed: %s", tool_name, exc)
            return json.dumps({"error": str(exc)})

    def _handle_search(self, args: Dict[str, Any]) -> str:
        query = args.get("query", "")
        project = args.get("project") or self._project
        limit = min(int(args.get("limit", 10)), 25)

        # search_sessions returns List[SearchResult]
        results = self._db.search_sessions(
            query=query,
            project=project,
            limit=limit,
            include_external=False,
        )

        sessions = []
        for sr in results:
            s = sr.session
            sessions.append({
                "id": getattr(s, "id", ""),
                "title": getattr(s, "title", ""),
                "date": getattr(s, "start_date", ""),
                "surface": getattr(s, "surface", ""),
                "summary": (getattr(s, "summary", "") or "")[:300],
                "decisions": getattr(s, "decisions", []),
                "tags": getattr(s, "tags", []),
                "match_score": getattr(sr, "match_score", 0.0),
            })

        return json.dumps({
            "query": query,
            "project": project,
            "count": len(sessions),
            "sessions": sessions,
        })

    def _handle_context(self, args: Dict[str, Any]) -> str:
        topic = args.get("topic", "")
        max_results = min(int(args.get("max_results", 5)), 15)

        # get_context_for returns List[SearchResult]
        results = self._db.get_context_for(
            topic=topic,
            max_results=max_results,
        )

        if not results:
            return json.dumps({
                "topic": topic,
                "found": False,
                "message": "No relevant sessions found.",
            })

        sessions = []
        decisions: List[str] = []
        questions: List[str] = []

        for sr in results:
            s = sr.session
            sessions.append({
                "id": getattr(s, "id", ""),
                "title": getattr(s, "title", ""),
                "date": getattr(s, "start_date", ""),
                "summary": (getattr(s, "summary", "") or "")[:200],
                "match_score": getattr(sr, "match_score", 0.0),
            })
            for d in (getattr(s, "decisions", []) or [])[:3]:
                if d not in decisions:
                    decisions.append(d)
            for q in (getattr(s, "open_questions", []) or [])[:3]:
                if q not in questions:
                    questions.append(q)

        return json.dumps({
            "topic": topic,
            "found": True,
            "session_count": len(sessions),
            "sessions": sessions,
            "decisions": decisions[:10],
            "open_questions": questions[:5],
        })

    def _handle_save_memory(self, args: Dict[str, Any]) -> str:
        title = args.get("title", "")
        content = args.get("content", "")
        item_type = args.get("item_type", "open_question")
        tags = args.get("tags", [])

        _VALID_TYPES = {"decision", "open_question", "artifact"}
        if item_type not in _VALID_TYPES:
            item_type = "open_question"

        result = self._db.save_memory_item(
            item_type=item_type,
            title=title,
            body=content,
            project=self._project,
            tags=["hermes"] + tags,
        )

        return json.dumps({
            "saved": result.get("ok", False),
            "id": result.get("id", ""),
            "title": title,
            "item_type": item_type,
        })

    # -- Helpers --------------------------------------------------------------

    @staticmethod
    def _make_title(user_message: str) -> str:
        """Derive a short session title from the user's message."""
        cleaned = user_message.strip().replace("\n", " ")
        if len(cleaned) <= 80:
            return cleaned
        return cleaned[:77] + "..."


# -- Plugin registration ------------------------------------------------------

def register(ctx: Any) -> None:
    """Register this memory provider with the Hermes plugin system."""
    provider = LoreConvoMemoryProvider()
    ctx.register_memory_provider(provider)
    logger.info("LoreConvo memory provider registered")