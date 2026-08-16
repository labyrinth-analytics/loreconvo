"""UTC timestamp generation and parsing for session storage (SH-100303 r4)."""
from datetime import datetime, timezone


def utc_now_iso() -> str:
    """Return current UTC time as ISO 8601 string with Z suffix.

    The single source of truth for all session writers (auto_save.py,
    periodic_save.py, pre_compact_save.py).
    """
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def parse_iso_utc(value: str) -> datetime:
    """Parse an ISO 8601 UTC instant, including the documented 'Z' suffix.

    datetime.fromisoformat() only accepts a trailing 'Z' from Python 3.11
    onward; this package's requires-python floor is 3.10 (pyproject.toml),
    where a raw 'Z' raises ValueError. Normalizing 'Z' -> '+00:00' before
    parsing sidesteps the version difference entirely rather than depending
    on it, so this is correct on 3.10 through the current interpreter alike.
    """
    return datetime.fromisoformat(value.replace('Z', '+00:00'))
