"""Per-project embedding link circuit breaker for LoreConvo.

A per-project dict keyed by project name tracks failure count, open state,
and opened_at timestamp. The circuit half-opens after RESET_SECONDS and allows
one probe attempt. On success the circuit closes; on failure it re-opens.

The dict is unbounded but bounded in practice: one entry per project.
"""

import logging
import os
import time
from typing import Dict, Tuple

_log = logging.getLogger(__name__)

# (failure_count, circuit_open, opened_at)
_embedding_circuits: Dict[str, Tuple[int, bool, float]] = {}

_THRESHOLD = 5
_DEFAULT_RESET_SECONDS = 1800  # 30 minutes


def _reset_seconds() -> int:
    try:
        return int(os.environ.get("LORECONVO_CIRCUIT_RESET_MINUTES", "30")) * 60
    except (ValueError, TypeError):
        return _DEFAULT_RESET_SECONDS


def check_circuit(project: str) -> bool:
    """Return True if embedding linking is allowed for this project."""
    state = _embedding_circuits.get(project, (0, False, 0.0))
    failures, open_, opened_at = state
    if not open_:
        return True
    if time.time() - opened_at >= _reset_seconds():
        _embedding_circuits[project] = (0, False, 0.0)
        _log.info(
            "auto_link embedding circuit half-open for project=%r: "
            "attempting reset after %d min",
            project, _reset_seconds() // 60,
        )
        return True
    return False


def record_success(project: str) -> None:
    """Clear failure state for a project. Also prunes entries older than 2x reset window."""
    _embedding_circuits.pop(project, None)
    _prune_stale()


def record_failure(project: str) -> None:
    """Increment failure count. Open circuit after THRESHOLD consecutive failures."""
    failures, open_, opened_at = _embedding_circuits.get(project, (0, False, 0.0))
    if open_:
        # Already open -- don't re-open, just update count
        _embedding_circuits[project] = (failures + 1, True, opened_at)
        return
    failures += 1
    if failures >= _THRESHOLD:
        _embedding_circuits[project] = (failures, True, time.time())
        _log.warning(
            "auto_link embedding circuit OPEN for project=%r after %d consecutive failures. "
            "Will retry in %d min. Run scripts/repair_lance_index.py to diagnose.",
            project, _THRESHOLD, _reset_seconds() // 60,
        )
    else:
        _embedding_circuits[project] = (failures, False, 0.0)
        _log.error(
            "auto_link embedding failure %d/%d for project=%r",
            failures, _THRESHOLD, project,
        )


def _prune_stale() -> None:
    """Prune circuit entries older than 2x reset window with zero recent failures."""
    cutoff = time.time() - 2 * _reset_seconds()
    stale = [
        k for k, (failures, open_, opened_at) in _embedding_circuits.items()
        if not open_ and opened_at > 0 and opened_at < cutoff
    ]
    for k in stale:
        _embedding_circuits.pop(k, None)
