"""UTC timestamp generation for session storage (SH-100303 r4)."""
from datetime import datetime, timezone


def utc_now_iso() -> str:
    """Return current UTC time as ISO 8601 string with Z suffix.

    The single source of truth for all session writers (auto_save.py,
    periodic_save.py, pre_compact_save.py).
    """
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
