"""LoreConvo hook bootstrap -- resolve storage_core for non-package callers.

Hooks run standalone under Claude Code's hook runner and cannot assume
the loreconvo package is importable. This module provides a single
resolve_storage_core() helper that every non-package caller uses.

Resolution algorithm:
  Path 1 -- installed package (preferred).  If loreconvo.core is
    importable, import storage_core from it.
  Path 2 -- bounded upward search from the calling file.  Looks for
    src/core/storage_core.py or core/storage_core.py within
    _MAX_UPWARD_LEVELS directories above the origin.  No sys.path
    mutation -- loads by explicit file location via
    importlib.util.spec_from_file_location.

If path 1 fails with a broken package (import error), the exception is
remembered and path 2 is attempted.  If path 2 succeeds, a once-per-process
degraded-mode warning is emitted.  If both paths fail, BootstrapError is
raised naming every probed path and the broken-package exception when there
was one.

On BootstrapError, a breadcrumb is written to <data_dir>/hook_failure.json
so the MCP server can surface the failure via get_server_info/get_stats
even if the hook runner discarded stderr.  The breadcrumb is deleted on
the next successful bootstrap.
"""

import importlib.util
import json
import os
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

_MAX_UPWARD_LEVELS = 4
_REL_CANDIDATES = (
    Path("src") / "core" / "storage_core.py",
    Path("core") / "storage_core.py",
)

_DEGRADED_WARNED = False
_BREADCRUMB_DELETED_THIS_PROCESS = False


class BootstrapError(ImportError):
    """Raised when storage_core cannot be resolved.

    Never falls back to hook-local SQL -- that code is deleted.
    """


def _get_data_dir():
    """Return the LoreConvo data directory path."""
    return os.environ.get(
        "LORECONVO_DATA_DIR",
        os.path.expanduser("~/.loreconvo"),
    )


def _write_breadcrumb(hook_name, error_msg, probed):
    """Write a failure breadcrumb so the MCP server can surface it.

    Best-effort -- a failure to write the breadcrumb is warned to stderr
    but never masks the original BootstrapError.
    """
    data_dir = _get_data_dir()
    breadcrumb_path = os.path.join(data_dir, "hook_failure.json")
    try:
        os.makedirs(data_dir, exist_ok=True)
        payload = {
            "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "hook": hook_name,
            "error": error_msg,
            "probed": probed,
        }
        with open(breadcrumb_path, "w") as f:
            json.dump(payload, f)
        try:
            os.chmod(breadcrumb_path, 0o600)
        except OSError:
            pass
    except OSError as exc:
        print(
            f"WARNING: Cannot write hook failure breadcrumb to "
            f"{breadcrumb_path}: {exc}",
            file=sys.stderr,
        )


def _clear_breadcrumb():
    """Delete the failure breadcrumb on successful bootstrap.

    Called once per process -- the first successful bootstrap clears
    any stale breadcrumb from a previous failure.
    """
    global _BREADCRUMB_DELETED_THIS_PROCESS
    if _BREADCRUMB_DELETED_THIS_PROCESS:
        return
    _BREADCRUMB_DELETED_THIS_PROCESS = True
    breadcrumb_path = os.path.join(_get_data_dir(), "hook_failure.json")
    try:
        os.unlink(breadcrumb_path)
    except FileNotFoundError:
        pass
    except OSError:
        pass


def _warn_once_degraded(local_path, broken_pkg_exc):
    """Emit a once-per-process degraded-mode warning."""
    global _DEGRADED_WARNED
    if _DEGRADED_WARNED:
        return
    _DEGRADED_WARNED = True
    print(
        f"WARNING: loreconvo package is installed but broken "
        f"({broken_pkg_exc}). Falling back to local module at "
        f"{local_path}. The install is degraded; reinstall "
        f"loreconvo to restore the normal path.",
        file=sys.stderr,
    )


def _load_by_path(path):
    """Load a Python module by explicit file location.

    No sys.path mutation -- uses spec_from_file_location under a
    private module name so a stale copy on sys.path cannot shadow it.
    """
    spec = importlib.util.spec_from_file_location(
        "_loreconvo_storage_core", str(path)
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("_loreconvo_storage_core", mod)
    spec.loader.exec_module(mod)
    return mod


def _unsupported_layout_message(probed, broken_pkg):
    """Build a human-readable error for unsupported layouts."""
    parts = ["Cannot resolve loreconvo storage_core."]
    parts.append(f"Probed paths ({len(probed)}):")
    for p in probed:
        parts.append(f"  {p}")
    if broken_pkg is not None:
        parts.append(
            f"loreconvo package was found but is broken: {broken_pkg}"
        )
    parts.append(
        "Remedy: pip install loreconvo, or run hooks from the "
        "distributed bundle where hooks/ and src/ are siblings."
    )
    return "\n".join(parts)


def resolve_storage_core(origin):
    """Resolve the storage_core module for a non-package caller.

    Args:
        origin: Path(__file__) of the calling script.

    Returns:
        The storage_core module object.

    Raises:
        BootstrapError: if storage_core cannot be resolved.
    """
    # Path 1 -- installed package, preferred.
    broken_pkg = None
    try:
        if importlib.util.find_spec("loreconvo.core") is not None:
            try:
                from loreconvo.core import storage_core
                _clear_breadcrumb()
                return storage_core
            except Exception as exc:
                broken_pkg = exc  # remembered, NOT fatal -- see path 2
    except Exception as exc:
        # find_spec itself can raise on broken namespace packages
        broken_pkg = exc

    # Path 2 -- bounded upward search from this file, no sys.path mutation.
    probed = []
    base = origin.resolve().parent
    for level in range(_MAX_UPWARD_LEVELS + 1):
        root = base.parents[level - 1] if level else base
        for rel in _REL_CANDIDATES:
            cand = root / rel
            probed.append(str(cand))
            if cand.is_file():
                if broken_pkg is not None:
                    _warn_once_degraded(cand, broken_pkg)
                _clear_breadcrumb()
                return _load_by_path(cand)

    # Both paths failed -- raise with full diagnostics.
    msg = _unsupported_layout_message(probed, broken_pkg)
    raise BootstrapError(msg)
