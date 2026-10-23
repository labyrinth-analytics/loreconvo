"""Configurable MCP tool groups for LoreConvo.

Single source of truth for the group -> tool assignment.  Imported by
``server.py`` (startup gating), the Hermes integration (read-side filtering),
and ``scripts/check_tool_group_coverage.py`` (coverage enforcement).

Resolution order (PART:interfaces):
  1. ``LORECONVO_TOOL_GROUPS`` env var (comma-separated) -- wins if set.
  2. ``tool_groups`` key in ``~/.loreconvo/config.json``.
  3. All groups on (upgrade-safe default).

Malformed config fails *closed* to ``core`` + ``ALWAYS_ON`` only (the 7-tool
minimum floor), never to all-on.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

# -- Always-on tools (never removed by group gating) -------------------------

ALWAYS_ON: set[str] = {"get_server_info", "configure_tools"}

# -- Group -> tool assignment ------------------------------------------------

TOOL_GROUPS: dict[str, tuple[str, ...]] = {
    "core": (
        "save_session",
        "search_sessions",
        "get_context_for",
        "get_recent_sessions",
        "get_session",
    ),
    "memory": (
        "consolidate_memories",
        "get_anti_patterns",
        "get_dream_log",
        "get_memory_digest",
        "get_skill_history",
        "pin_session",
        "query_memory_items",
        "save_memory_item",
        "tag_as_anti_pattern",
        "tag_session",
        "transition_memory_item",
        "untag_anti_pattern",
        "update_memory_item",
        "vault_suggest",
        "session_link_doc",
        "get_docs_for_session",
        "set_session_expiry",
        "rebuild_index",
        "rebuild_index_status",
    ),
    "graph": (
        "link_sessions",
        "get_related_sessions",
        "graph_session_map",
    ),
    "agents": (
        "configure_agent_context",
        "inject_agent_context",
    ),
    "admin": (
        "create_project",
        "export_for_anthropic",
        "export_sessions",
        "get_project",
        "get_stats",
        "get_tier",
        "import_sessions",
        "inspect_sessions",
        "list_projects",
        "loreconvo_onboard",
        "vault_set_tier",
    ),
}

# Tools that are conditionally registered (not always present in the live
# FastMCP app).  The coverage checker excludes these from the "must be live"
# side of its set comparison.
CONDITIONAL_TOOLS: set[str] = set()

_ENV_VAR = "LORECONVO_TOOL_GROUPS"


# -- Registry self-consistency (runs at import time) -------------------------


def _validate_registry() -> None:
    """Every name across ALWAYS_ON and all TOOL_GROUPS values is unique."""
    seen: dict[str, str] = {}
    for label, names in {"ALWAYS_ON": tuple(ALWAYS_ON), **TOOL_GROUPS}.items():
        for n in names:
            if n in seen:
                raise ValueError(
                    f"{n} duplicated in {seen[n]!r} and {label!r}"
                )
            seen[n] = label


_validate_registry()


# -- Public API ---------------------------------------------------------------


def all_tool_names() -> set[str]:
    """Return every tool name known to the registry (always-on + grouped)."""
    return set(ALWAYS_ON) | {n for tools in TOOL_GROUPS.values() for n in tools}


def classify_tool(name: str) -> str:
    """Return the owning group name, or the literal ``"ALWAYS_ON"``.

    Raises ``KeyError`` if *name* has no assignment anywhere, or ``ValueError``
    if *name* is assigned more than once (ALWAYS_ON + a group, or two groups) --
    both are registry bugs, not valid inputs.
    """
    in_always_on = name in ALWAYS_ON
    hits = [g for g, tools in TOOL_GROUPS.items() if name in tools]
    if in_always_on and hits:
        raise ValueError(f"{name} is in both ALWAYS_ON and group(s) {hits}")
    if in_always_on:
        return "ALWAYS_ON"
    if len(hits) == 0:
        raise KeyError(f"{name} has no group assignment")
    if len(hits) > 1:
        raise ValueError(f"{name} is assigned to multiple groups: {hits}")
    return hits[0]


def validate_group_names(names: list[str]) -> list[str]:
    """Validate a user-supplied list of group names.

    Returns the validated, deduplicated list.  Raises ``ValueError`` with the
    set of valid names if any entry is not a known group.
    """
    valid = set(TOOL_GROUPS.keys())
    unknown = [n for n in names if n not in valid]
    if unknown:
        raise ValueError(
            f"Unknown group name(s): {unknown}. "
            f"Valid groups: {sorted(valid)}"
        )
    # Deduplicate, preserve order.
    seen: set[str] = set()
    result: list[str] = []
    for n in names:
        if n not in seen:
            seen.add(n)
            result.append(n)
    return result


def resolve_enabled_groups(config_path: Path | None = None) -> set[str]:
    """Resolve which optional groups are enabled (always includes ``core``).

    Resolution order: env var > config.json > all on.  Malformed config or
    unknown group names fail *closed* to ``{"core"}`` only.
    """
    # 1. Env var
    env_val = os.environ.get(_ENV_VAR)
    if env_val is not None:
        names = [g.strip() for g in env_val.split(",") if g.strip()]
        try:
            validated = validate_group_names(names)
        except ValueError:
            return {"core"}
        if not validated:
            return {"core"}
        return set(validated) | {"core"}

    # 2. Config file
    if config_path is not None and config_path.exists():
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
        except Exception:
            return {"core"}
        raw = config.get("tool_groups")
        if "tool_groups" not in config:
            # Absent key = all on (upgrade-safe default).
            return set(TOOL_GROUPS.keys())
        if not isinstance(raw, list):
            return {"core"}
        if len(raw) == 0:
            return {"core"}
        try:
            validated = validate_group_names(raw)
        except ValueError:
            return {"core"}
        return set(validated) | {"core"}

    # 3. All on
    return set(TOOL_GROUPS.keys())