from typing import Literal, overload


@overload
def resolve_session_id(session_id: str | None, lore_session_id: str | None, required: Literal[True]) -> str: ...
@overload
def resolve_session_id(session_id: str | None, lore_session_id: str | None, required: Literal[False]) -> str | None: ...
@overload
def resolve_session_id(session_id: str | None, lore_session_id: str | None, required: bool) -> str | None: ...
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


def resolve_session_ids(
    session_ids: list[str] | None,
    lore_session_ids: list[str] | None,
) -> list[str] | None:
    """Resolve session_ids (plural) alias for remote-devices bridge compatibility.

    Same logic as resolve_session_id but for list-typed parameters (e.g.,
    export_for_anthropic's session_ids). Neither value is required; returns
    None when the caller supplies neither.

    Args:
        session_ids: Primary session_ids parameter
        lore_session_ids: Alias for session_ids (for remote-devices bridge)

    Returns:
        Resolved session_ids list, or None if not provided

    Raises:
        ValueError: If both differ
    """
    if session_ids is not None and lore_session_ids is not None:
        if session_ids != lore_session_ids:
            raise ValueError("both session_ids and lore_session_ids provided with different values")
        return session_ids
    if session_ids is not None:
        return session_ids
    if lore_session_ids is not None:
        return lore_session_ids
    return None
