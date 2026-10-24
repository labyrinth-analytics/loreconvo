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

# Tool names where the generic DB-dispatch fallback would miss because the
# Hermes tool name differs from the SessionDatabase method name. Each target
# method is a pure pass-through used by the matching MCP tool in server.py
# (SH-104903/SH-104905).
TOOL_NAME_ALIASES: Dict[str, str] = {
    "consolidate_memories": "consolidate_memories_payload",
    "graph_session_map": "build_graph_map_payload",
    "vault_suggest": "get_suggestions",
    "import_sessions": "import_export_file",
    "rebuild_index": "rebuild_lance_index",
}

# Tools with no Hermes-native dispatch path. Disclosed, not silent: the
# business logic lives only in server.py (async config writes, multi-branch
# fan-out search with trust-framing) and duplicating it here would be a
# single-source-of-truth violation. Available via MCP/CLI. (SH-104903)
MCP_ONLY_TOOLS = {"inject_agent_context", "configure_tools"}

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
        if not self._is_primary:
            return ""
        return (
            "LoreConvo session memory is active. Past sessions across Claude surfaces "
            "(Code, Cowork, Chat) are searchable. Use loreconvo_search_sessions to find "
            "prior work, loreconvo_get_context to recall project context, and "
            "loreconvo_save_memory to persist decisions, questions, or artifacts."
        )

    # -- Recall / prefetch ----------------------------------------------------

    def prefetch(self, query: str, *, session_id: str = "") -> str:
        """Return formatted context from past LoreConvo sessions relevant to the query."""
        if not self._initialized or not self._db or not self._is_primary:
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

    # -- License ---------------------------------------------------------------

    def _resolve_license(self) -> bool:
        """Return True if a valid Pro license is present.

        Checks LORECONVO_PRO env var (set in plugin.yaml requires_env or by the
        user), then the durable license store on disk.  Cached once per process.
        """
        if hasattr(self, "_cached_is_pro"):
            return self._cached_is_pro

        is_pro = False
        try:
            key = os.environ.get("LORECONVO_PRO")
            if not key:
                try:
                    license_store = _import_loreconvo("license_store")
                    key = license_store.read_key("loreconvo")
                except Exception:
                    pass
            if key:
                license_mod = _import_loreconvo("license")
                try:
                    license_mod.validate_license_key(key)
                    is_pro = True
                except Exception:
                    pass
        except Exception:
            pass

        self._cached_is_pro = is_pro
        return is_pro

    # -- Tools ----------------------------------------------------------------

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        """Return Hermes-format tool schemas derived from the MCP server registry.

        Loads from the build-time-generated hermes_tool_schemas.json, filtered
        by the shared tool-group config.  Schemas are derived, not hand-written.
        """
        enabled_groups = self._resolve_enabled_groups()

        try:
            from loreconvo.core.hermes_tool_loader import load_schemas_for_groups
            return load_schemas_for_groups(enabled_groups)
        except ImportError:
            logger.warning("hermes_tool_loader not available -- falling back to empty schema list")
            return []

    def _resolve_enabled_groups(self) -> set:
        """Resolve enabled tool groups the same way the MCP server does.

        Cached once at first call (matching the existing pattern where
        Hermes holds a long-lived SessionDatabase handle).
        """
        if hasattr(self, "_cached_enabled_groups"):
            return self._cached_enabled_groups

        try:
            tool_groups_mod = _import_loreconvo("tool_groups")
            config_dir = Path.home() / ".loreconvo"
            config_path = config_dir / "config.json"
            groups = tool_groups_mod.resolve_enabled_groups(config_path)
        except Exception:
            groups = {"core", "memory", "graph", "agents", "admin"}

        self._cached_enabled_groups = groups
        return groups

    def handle_tool_call(self, tool_name: str, args: Dict[str, Any], **kwargs: Any) -> str:
        if not self._initialized or not self._db:
            return json.dumps({"error": "LoreConvo is not available"})

        # Pro gating (matches MCP server behavior).
        try:
            from loreconvo.core.hermes_tool_loader import is_pro_tool, upgrade_message
        except ImportError:
            is_pro_tool = lambda n: False  # type: ignore
            upgrade_message = lambda: json.dumps({"error": "Pro check unavailable"})  # type: ignore

        if is_pro_tool(tool_name) and not self._resolve_license():
            return upgrade_message()

        if tool_name in MCP_ONLY_TOOLS:
            return json.dumps({
                "error": f"Tool '{tool_name}' is not implemented in Hermes-native dispatch.",
                "note": "Available via the LoreConvo MCP server or CLI. Scope documented in SH-104903/SH-104905.",
            })

        # Build dispatch table from both hand-coded handlers and generic DB dispatchers.
        handlers: Dict[str, Any] = {
            "search_sessions": self._handle_search,
            "get_context_for": self._handle_context,
            "save_memory_item": self._handle_save_memory,
            "save_session": self._handle_save_session,
            "get_recent_sessions": self._handle_recent_sessions,
            "get_session": self._handle_get_session,
            "get_project": self._handle_get_project,
            "list_projects": self._handle_list_projects,
            "get_stats": self._handle_stats,
            "get_tier": self._handle_tier,
            "get_server_info": self._handle_server_info,
            "get_memory_digest": self._handle_memory_digest,
            "pin_session": self._handle_pin_session,
            "set_session_expiry": self._handle_set_expiry,
            "tag_session": self._handle_tag_session,
            "inspect_sessions": self._handle_inspect_sessions,
            "get_dream_log": self._handle_dream_log,
            "loreconvo_onboard": self._handle_onboard,
            "vault_set_tier": self._handle_set_tier,
            "export_sessions": self._handle_export_sessions,
            "export_for_anthropic": self._handle_export_for_anthropic,
            "get_docs_for_session": self._handle_get_docs_for_session,
            "session_link_doc": self._handle_session_link_doc,
            "tag_as_anti_pattern": self._handle_tag_anti_pattern,
            "untag_anti_pattern": self._handle_untag_anti_pattern,
        }

        handler = handlers.get(tool_name)
        if handler is not None:
            try:
                return handler(args)
            except Exception as exc:
                logger.debug("LoreConvo tool %s failed: %s", tool_name, exc)
                return json.dumps({"error": str(exc)})

        # Generic DB-dispatch fallback: tool name matches a SessionDatabase
        # method, resolving through TOOL_NAME_ALIASES when the Hermes tool
        # name differs from the method name.
        db_method_name = TOOL_NAME_ALIASES.get(tool_name, tool_name)
        try:
            db_method = getattr(self._db, db_method_name, None)
            if callable(db_method):
                result = db_method(**args)
                return json.dumps(result, default=str)
        except Exception as exc:
            logger.debug("LoreConvo tool %s dispatch failed: %s", tool_name, exc)
            return json.dumps({"error": str(exc)})

        return json.dumps({
            "error": f"Hermes-native handler not yet implemented for {tool_name}.",
            "note": "This tool is available via MCP. Hermes parity build is in progress (SH-103849).",
        })

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

    # -- Additional Hermes tool handlers ---------------------------------------

    def _handle_save_session(self, args: Dict[str, Any]) -> str:
        """Handle save_session tool call."""
        title = args.get("title", "")
        summary = args.get("summary", "")
        project = args.get("project") or self._project
        surface = args.get("surface", "code")
        tags = args.get("tags", [])
        try:
            Session = _import_loreconvo("models").Session
            now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            session = Session(
                title=title, surface=surface, project=project,
                start_date=now, end_date=now, summary=summary,
                tags=tags + ["hermes"], source="hermes",
            )
            self._db.save_session(session)
            return json.dumps({"saved": True, "title": title})
        except Exception as exc:
            return json.dumps({"error": str(exc)})

    def _handle_recent_sessions(self, args: Dict[str, Any]) -> str:
        project = args.get("project") or self._project
        limit = min(int(args.get("limit", 10)), 25)
        surface = args.get("surface")
        results = self._db.get_recent_sessions(project=project, limit=limit, surface=surface)
        sessions = []
        for s in results:
            sessions.append({
                "id": getattr(s, "id", ""),
                "title": getattr(s, "title", ""),
                "date": getattr(s, "start_date", ""),
                "surface": getattr(s, "surface", ""),
                "summary": (getattr(s, "summary", "") or "")[:300],
                "tags": getattr(s, "tags", []),
            })
        return json.dumps({"project": project, "count": len(sessions), "sessions": sessions})

    def _handle_get_session(self, args: Dict[str, Any]) -> str:
        session_id = args.get("session_id", "")
        if not session_id:
            return json.dumps({"error": "session_id is required"})
        s = self._db.get_session(session_id)
        if s is None:
            return json.dumps({"found": False, "session_id": session_id})
        return json.dumps({
            "found": True,
            "id": getattr(s, "id", ""),
            "title": getattr(s, "title", ""),
            "date": getattr(s, "start_date", ""),
            "surface": getattr(s, "surface", ""),
            "summary": (getattr(s, "summary", "") or "")[:500],
            "decisions": getattr(s, "decisions", []),
            "tags": getattr(s, "tags", []),
            "project": getattr(s, "project", ""),
        })

    def _handle_get_project(self, args: Dict[str, Any]) -> str:
        project = args.get("project") or self._project
        result = self._db.get_project(project)
        return json.dumps(result, default=str)

    def _handle_list_projects(self, args: Dict[str, Any]) -> str:
        result = self._db.list_projects()
        return json.dumps(result, default=str)

    def _handle_stats(self, args: Dict[str, Any]) -> str:
        try:
            status = self._db.get_stats()
            return json.dumps(status, default=str)
        except Exception as exc:
            return json.dumps({"error": str(exc)})

    def _handle_tier(self, args: Dict[str, Any]) -> str:
        is_pro = self._resolve_license()
        return json.dumps({
            "product": "loreconvo",
            "tier": "pro" if is_pro else "free",
            "is_pro": is_pro,
        })

    def _handle_server_info(self, args: Dict[str, Any]) -> str:
        import importlib.metadata
        try:
            version = importlib.metadata.version("loreconvo")
        except Exception:
            version = "unknown"
        return json.dumps({
            "product": "loreconvo",
            "version": version,
            "protocol": "mcp",
            "hermes_mode": True,
        })

    def _handle_memory_digest(self, args: Dict[str, Any]) -> str:
        project = args.get("project") or self._project
        try:
            digest = self._db.get_memory_digest(project=project)
            return json.dumps(digest, default=str)
        except Exception as exc:
            return json.dumps({"error": str(exc)})

    def _handle_pin_session(self, args: Dict[str, Any]) -> str:
        session_id = args.get("session_id", "")
        keep_forever = bool(args.get("keep_forever", True))
        if not session_id:
            return json.dumps({"error": "session_id is required"})
        try:
            self._db.set_session_pin(session_id, keep_forever=keep_forever)
            return json.dumps({"pinned": keep_forever, "session_id": session_id})
        except Exception as exc:
            return json.dumps({"error": str(exc)})

    def _handle_set_expiry(self, args: Dict[str, Any]) -> str:
        session_id = args.get("session_id", "")
        expires_at = args.get("expires_at")
        if not session_id:
            return json.dumps({"error": "session_id is required"})
        try:
            self._db.set_session_expiry(session_id, expires_at)
            return json.dumps({"ok": True, "session_id": session_id, "expires_at": expires_at})
        except Exception as exc:
            return json.dumps({"error": str(exc)})

    def _handle_tag_session(self, args: Dict[str, Any]) -> str:
        session_id = args.get("session_id", "")
        tag = args.get("tag", "")
        if not session_id or not tag:
            return json.dumps({"error": "session_id and tag are required"})
        try:
            self._db.tag_session(session_id, tag)
            return json.dumps({"ok": True, "session_id": session_id, "tag": tag})
        except Exception as exc:
            return json.dumps({"error": str(exc)})

    def _handle_inspect_sessions(self, args: Dict[str, Any]) -> str:
        try:
            result = self._db.inspect_sessions(**args)
            return json.dumps(result, default=str)
        except Exception as exc:
            return json.dumps({"error": str(exc)})

    def _handle_dream_log(self, args: Dict[str, Any]) -> str:
        project = args.get("project")
        surface = args.get("surface")
        limit = int(args.get("limit", 10))
        entries, digest = self._db.get_dream_log_entries(
            project=project, surface=surface, limit=limit
        )
        return json.dumps({
            "status": "ok", "project": project, "surface": surface,
            "entries": entries, "digest_status": digest,
        }, default=str)

    def _handle_onboard(self, args: Dict[str, Any]) -> str:
        tag_style = args.get("tag_style", "simple")
        if tag_style not in ("simple", "detailed"):
            return json.dumps({"error": "tag_style must be 'simple' or 'detailed'"})
        run_onboard = _import_loreconvo("onboard_tool").run_onboard
        result = run_onboard(
            self._db, name=args.get("name"), projects=args.get("projects"),
            agents=args.get("agents"), tag_style=tag_style,
        )
        return json.dumps(result, default=str)

    def _handle_set_tier(self, args: Dict[str, Any]) -> str:
        params = args.get("params") or {}
        tier = params.get("tier", "")
        if tier not in ("free", "pro"):
            return json.dumps({"error": "tier must be 'free' or 'pro'"})
        if tier == "pro" and not self._resolve_license():
            return json.dumps({
                "error": "No valid Pro license key found. Set LORECONVO_PRO=<key> and restart.",
            })
        set_tier = _import_loreconvo("config").set_tier
        db_dir = Path(self._db.config.db_path).parent
        try:
            set_tier(db_dir, tier)
        except ValueError as exc:
            return json.dumps({"error": str(exc)})
        return json.dumps({"status": "ok", "tier": tier})

    def _handle_export_sessions(self, args: Dict[str, Any]) -> str:
        if args.get("output_path"):
            return json.dumps({
                "error": "output_path file-write is not supported via Hermes dispatch.",
                "note": "Omit output_path for inline data, or use the MCP server/CLI for file export.",
                "status": "unsupported_in_hermes",
            })
        payload = self._db.export_payload(
            project=args.get("project"), tags=args.get("tags"),
            days_back=args.get("days_back"), limit=int(args.get("limit", 1000)),
            fmt=args.get("format", "json"),
        )
        return json.dumps({
            "status": "exported", "session_count": payload["session_count"],
            "format": args.get("format", "json"), "data": payload["data"],
        })

    def _handle_export_for_anthropic(self, args: Dict[str, Any]) -> str:
        if args.get("output_path"):
            return json.dumps({
                "error": "output_path file-write is not supported via Hermes dispatch.",
                "note": "Omit output_path for inline data, or use the MCP server/CLI for file export.",
                "status": "unsupported_in_hermes",
            })
        payload = self._db.anthropic_export_payload(
            project=args.get("project"), session_ids=args.get("session_ids"),
            days_back=args.get("days_back"),
        )
        if "error" in payload:
            return json.dumps({"error": payload["error"]})
        return json.dumps({
            "status": "exported", "format": "anthropic-memory-v1",
            "entry_count": payload["entry_count"], "data": payload["data"],
        })

    def _handle_get_docs_for_session(self, args: Dict[str, Any]) -> str:
        bridge = _import_loreconvo("loredocs_bridge")
        try:
            ld_db = bridge.discover_loredocs_db()
        except bridge.LoreDocsAccessError as exc:
            return json.dumps({
                "schema_version": 0, "cross_product_available": False,
                "reason": f"LoreDocs installed but unreachable: {exc}", "links": [],
            })
        if ld_db is None:
            return json.dumps({
                "schema_version": 0, "cross_product_available": False,
                "reason": "LoreDocs not installed", "links": [],
            })
        try:
            result = bridge.get_cross_product_links(
                ld_db, source_product="loreconvo", source_id=args.get("session_id", ""),
                current_embedding_model=bridge.CROSS_LINK_EMBEDDING_MODEL,
                limit=int(args.get("limit", 5)), is_pro=self._resolve_license(),
            )
            return json.dumps(result, default=str)
        except bridge.LoreDocsSchemaError as exc:
            return json.dumps({
                "schema_version": 0, "cross_product_available": False,
                "reason": f"LoreDocs schema too old: {exc}", "links": [],
            })

    def _handle_session_link_doc(self, args: Dict[str, Any]) -> str:
        bridge = _import_loreconvo("loredocs_bridge")
        try:
            ld_db = bridge.discover_loredocs_db()
        except bridge.LoreDocsAccessError as exc:
            return json.dumps({"ok": False, "reason": f"LoreDocs installed but unreachable: {exc}"})
        if ld_db is None:
            return json.dumps({"ok": False, "reason": "LoreDocs not installed"})
        try:
            result = bridge.link_session_to_doc(
                ld_db, session_id=args.get("session_id", ""), doc_id=args.get("doc_id", ""),
                vault_id=args.get("vault_id", ""), link_type="manual", is_pro=self._resolve_license(),
            )
            return json.dumps(result, default=str)
        except bridge.LoreDocsSchemaError as exc:
            return json.dumps({"ok": False, "reason": f"LoreDocs schema too old: {exc}"})

    def _handle_tag_anti_pattern(self, args: Dict[str, Any]) -> str:
        session_id = args.get("session_id", "")
        try:
            result = self._db.mark_anti_pattern(
                session_id, source=args.get("source", "unknown"), reason=args.get("reason", "")
            )
            return json.dumps({"status": result, "session_id": session_id})
        except (ValueError, LookupError) as exc:
            return json.dumps({"status": "error", "error": str(exc)})
        except RuntimeError as exc:
            return json.dumps({"status": "error", "error": str(exc), "error_code": "rate_limit_exceeded"})

    def _handle_untag_anti_pattern(self, args: Dict[str, Any]) -> str:
        session_id = args.get("session_id", "")
        try:
            result = self._db.remove_anti_pattern(
                session_id, source=args.get("source", "unknown"), reason=args.get("reason", "")
            )
            return json.dumps({"status": result, "session_id": session_id})
        except ValueError as exc:
            return json.dumps({"status": "error", "error": str(exc)})

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
