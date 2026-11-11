def resolve_session_id(session_id: str | None, lore_session_id: str | None, required: bool) -> str | None:
    """Resolve session_id alias for remote-devices bridge compatibility.

    The remote-devices bridge (used by Claude Cowork) strips arguments named
    'session_id' in transit. This helper accepts both 'session_id' (primary)
    and 'lore_session_id' (alias) to work around that limitation.

    Args:
        session_id: Primary session_id parameter
        lore_session_id: Alias for session_id (for remote-devices bridge)
        required: Whether a session_id is required

    Returns:
        Resolved session_id value, or None if optional and not provided

    Raises:
        ValueError: If both differ or none provided when required
    """
    if session_id is not None and lore_session_id is not None:
        if session_id != lore_session_id:
            raise ValueError("both session_id and lore_session_id provided with different values")
        return session_id

    if session_id is not None:
        return session_id
    if lore_session_id is not None:
        return lore_session_id

    if required:
        raise ValueError("session_id is required")
    return None
