"""LoreConvo hook surface derivation (SH-106298).

Extracts surface label (code, cowork, chat) from hook input or environment.
Provides one canonical source for surface derivation across all hook scripts.

Import: from surface_utils import get_surface_from_hook_input
"""

import os
from typing import Dict, Optional


def get_surface_from_hook_input(hook_input: Dict, env_override: Optional[Dict] = None) -> str:
    """
    Derive surface name from hook input or environment variables.
    
    Args:
        hook_input: JSON parsed from stdin containing session info
        env_override: Optional dict for testing environment variables
        
    Returns:
        Normalized surface string ("code", "cowork", or "chat")
        
    Examples:
        >>> get_surface_from_hook_input({"surface": "code"})
        'code'
        >>> get_surface_from_hook_input({})
        'code'
        >>> get_surface_from_hook_input({}, {"CLAUDE_CODE_ENTRYPOINT": "1"})
        'code'
    """
    # Check for explicit surface in hook input (highest priority)
    if 'surface' in hook_input:
        return hook_input['surface']
    
    # Get environment variables (use override for testing)
    env = env_override if env_override is not None else os.environ
    
    # Check for entrypoint environment variables
    if env.get('CLAUDE_CODE_ENTRYPOINT'):
        return 'code'
    elif env.get('CLAUDE_COWORK_ENTRYPOINT'):
        return 'cowork'
    elif env.get('CLAUDE_CHAT_ENTRYPOINT'):
        return 'chat'
    
    # Default for backward compatibility
    return 'code'


def get_surface_name() -> str:
    """
    Get a readable name for the current surface for logging purposes.
    
    Returns:
        String representation of the surface name
    """
    # This would typically be called after get_surface_from_hook_input
    # For now, we just return a generic name since we don't have context here
    return "surface"


if __name__ == "__main__":
    # Test cases
    import doctest
    doctest.testmod()