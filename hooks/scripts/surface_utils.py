"""LoreConvo hook surface derivation (SH-106298).

Extracts surface label (code, cowork, chat) from hook input or environment.
Provides one canonical source for surface derivation across all hook scripts.

Import: from surface_utils import get_surface_from_hook_input
"""

import functools
import os
import sys
from pathlib import Path
from typing import Dict, Optional

sys.path.insert(0, str(Path(__file__).parent))
from _bootstrap import resolve_storage_core  # noqa: E402


@functools.lru_cache(maxsize=1)
def _allowed_surfaces() -> frozenset:
    """Accepted explicit surface values.

    One derivation (SH-107166): storage_core.ALLOWED_SURFACES, the same set
    the MCP server validates against and migrate_surfaces enforces. Resolved
    lazily; clear_breadcrumb=False so this lookup never erases hook-failure
    evidence.
    """
    storage = resolve_storage_core(Path(__file__), clear_breadcrumb=False)
    return frozenset(storage.ALLOWED_SURFACES)


def get_surface_from_hook_input(hook_input: Dict, env_override: Optional[Dict] = None) -> str:
    """
    Derive surface name from hook input or environment variables.

    Args:
        hook_input: JSON parsed from stdin containing session info
        env_override: Optional dict for testing environment variables

    Returns:
        Normalized surface string ("code", "cowork", or "chat")

    Design assumption: Exactly one CLAUDE_*_ENTRYPOINT environment variable
    is set per surface execution context. In Claude Code, only
    CLAUDE_CODE_ENTRYPOINT is set; in Cowork, only CLAUDE_COWORK_ENTRYPOINT;
    in Chat, only CLAUDE_CHAT_ENTRYPOINT. The truthiness check works because
    only one env var will be set at a time.

    Examples:
        >>> get_surface_from_hook_input({"surface": "code"})
        'code'
        >>> get_surface_from_hook_input({})
        'code'
        >>> get_surface_from_hook_input({}, {"CLAUDE_CODE_ENTRYPOINT": "sdk-cli"})
        'code'
    """
    # Check for explicit surface in hook input (highest priority)
    # Only accept it when it is a known surface string; anything else falls
    # through to environment detection.
    surface = hook_input.get('surface')
    if isinstance(surface, str) and surface in _allowed_surfaces():
        return surface

    # Get environment variables (use override for testing)
    env = env_override if env_override is not None else os.environ

    # Check for entrypoint environment variables. The design assumes only one
    # CLAUDE_*_ENTRYPOINT is set per surface context, so order doesn't matter.
    if env.get('CLAUDE_CODE_ENTRYPOINT'):
        return 'code'
    elif env.get('CLAUDE_COWORK_ENTRYPOINT'):
        return 'cowork'
    elif env.get('CLAUDE_CHAT_ENTRYPOINT'):
        return 'chat'

    # Default for backward compatibility
    return 'code'


if __name__ == "__main__":
    # Test cases
    import doctest
    doctest.testmod()