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
import types
from datetime import datetime, timezone
from pathlib import Path

_MAX_UPWARD_LEVELS = 4
_SRC_REL = Path("src")
_REL_CANDIDATES = (
    Path("src") / "core" / "storage_core.py",
    Path("core") / "storage_core.py",
)
_TIMEUTIL_REL_CANDIDATES = (
    Path("src") / "core" / "timeutil.py",
    Path("core") / "timeutil.py",
)
_SESSION_CORE_CLOSURE = (
    "core/models.py",
    "core/config.py",
    "core/storage_core.py",
    "core/trust_framing.py",
    "core/hybrid_search.py",
    "core/license_store.py",
    "core/license.py",
    "core/loredocs_bridge.py",
    "core/database.py",
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


def _load_by_path(path, mod_name="_loreconvo_storage_core"):
    """Load a Python module by explicit file location.

    No sys.path mutation -- uses spec_from_file_location under a
    private module name so a stale copy on sys.path cannot shadow it.
    """
    spec = importlib.util.spec_from_file_location(mod_name, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules.setdefault(mod_name, mod)
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
                # Validate that the module has the attributes callers need.
                # A stale/incomplete install may import successfully but be
                # missing functions added in recent versions (e.g.,
                # discover_loreconvo_db). Treat as broken and fall back to
                # source if validation fails.
                _required_attrs = ("discover_loreconvo_db", "ensure_schema",
                                   "sanitize_fts_query", "_open_conn")
                missing = [attr for attr in _required_attrs
                           if not hasattr(storage_core, attr)]
                if missing:
                    broken_pkg = AttributeError(
                        f"storage_core missing attributes: {missing}")
                else:
                    _clear_breadcrumb()
                    return storage_core
            except Exception as exc:
                broken_pkg = exc  # remembered, NOT fatal -- see path 2
    except ModuleNotFoundError as exc:
        # find_spec("loreconvo.core") imports the parent package first and
        # raises if it is absent -- it does not return None. A missing
        # 'loreconvo' therefore means "not installed", which is the normal
        # source-checkout layout, NOT a broken install. Only a missing
        # submodule (parent present, core absent) is genuinely broken.
        if exc.name != "loreconvo":
            broken_pkg = exc
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


def resolve_timeutil(origin):
    """Resolve the timeutil module for a non-package caller.

    Same two-path algorithm as resolve_storage_core(). Hooks cannot
    import loreconvo.core.timeutil directly: under the source-checkout
    layout the package is not installed at all, and a module-level
    package import would also run BEFORE the storage_core bootstrap,
    killing the process before it can write a failure breadcrumb.

    Args:
        origin: Path(__file__) of the calling script.

    Returns:
        The timeutil module object.

    Raises:
        BootstrapError: if timeutil cannot be resolved.
    """
    # Path 1 -- installed package, preferred.
    broken_pkg = None
    try:
        if importlib.util.find_spec("loreconvo.core") is not None:
            try:
                from loreconvo.core import timeutil
                return timeutil
            except Exception as exc:
                broken_pkg = exc  # remembered, NOT fatal -- see path 2
    except ModuleNotFoundError as exc:
        # See resolve_storage_core: a missing 'loreconvo' is the normal
        # source-checkout layout, not a broken install.
        if exc.name != "loreconvo":
            broken_pkg = exc
    except Exception as exc:
        broken_pkg = exc

    # Path 2 -- bounded upward search from this file, no sys.path mutation.
    probed = []
    base = origin.resolve().parent
    for level in range(_MAX_UPWARD_LEVELS + 1):
        root = base.parents[level - 1] if level else base
        for rel in _TIMEUTIL_REL_CANDIDATES:
            cand = root / rel
            probed.append(str(cand))
            if cand.is_file():
                if broken_pkg is not None:
                    _warn_once_degraded(cand, broken_pkg)
                return _load_by_path(cand, "_loreconvo_timeutil")

    # Both paths failed -- raise with full diagnostics.
    parts = ["Cannot resolve loreconvo timeutil."]
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
    raise BootstrapError("\n".join(parts))


# ---------------------------------------------------------------------------
# Session-core resolution (SH-101932 Phase B)
# ---------------------------------------------------------------------------
#
# The fallback saver (scripts/save_to_loreconvo.py) is a second caller of
# SessionDatabase.save_session -- the same internal API the MCP server uses,
# never a second implementation. The MCP server is always launched from an
# environment where `loreconvo` is importable (uvx/editable install). The
# fallback is not: the Hermes session-end ceremony invokes it via
# sys.executable, which in some fleet contexts is a bare system Python with
# no loreconvo distribution installed. A package-level `import loreconvo`
# in the fallback therefore fails on exactly the production path it exists
# to serve. resolve_session_core() below gives the fallback the package in
# BOTH worlds:
#
#   Path 1 -- installed package (preferred). When loreconvo.core is
#     importable, its modules are returned directly.
#   Path 2 -- bounded upward search for a sibling src/ checkout, then
#     package synthesis: real package objects ('loreconvo', 'loreconvo.core')
#     whose __path__ points at src/ are registered in sys.modules BEFORE any
#     submodule is loaded, so the relative imports inside core/database.py
#     (`.config`, `.hybrid_search`, ...) resolve naturally against the
#     synthesized package. Only the session-core closure is loaded --
#     server.py (FastMCP), anthropic_bridge.py (anthropic), and
#     idle_watchdog.py (mcp.types) stay OUT, so synthesis works on a
#     stdlib-only interpreter. The closure is stdlib-only at module scope
#     by design: cryptography/lancedb/mcp imports are lazy inside the
#     modules (checked 2026-09-27). src/__init__.py is NOT executed: it
#     only carries version plumbing and re-exports the closure caller
#     never needs.
#
# Force-registration (plain assignment, not setdefault) is deliberate:
# path 1 has definitively failed by the time synthesis runs, so any
# 'loreconvo' entry left in sys.modules by the failed attempt must be
# replaced, not kept.


def _synthesize_session_core(src_root, broken_pkg):
    """Synthesize the loreconvo package and load the session-core closure.

    Registers 'loreconvo' and 'loreconvo.core' as package objects whose
    __path__ points at the checkout src/, then loads each closure module
    under its canonical name. Modules already in sys.modules (loaded by an
    earlier relative import) are skipped, never re-executed.

    Raises BootstrapError on any missing file or load failure.
    """
    probed = [str(src_root / rel) for rel in _SESSION_CORE_CLOSURE]
    missing = [p for p in probed if not Path(p).is_file()]
    if missing:
        parts = ["Cannot resolve loreconvo session core."]
        parts.append(f"Missing closure files ({len(missing)}):")
        for p in missing:
            parts.append(f"  {p}")
        if broken_pkg is not None:
            parts.append(
                f"loreconvo package was found but is broken: {broken_pkg}"
            )
        parts.append(
            "Remedy: pip install loreconvo, or run the fallback from a "
            "checkout where hooks/ and src/ are siblings."
        )
        raise BootstrapError("\n".join(parts))

    pkg = types.ModuleType("loreconvo")
    pkg.__path__ = [str(src_root)]
    pkg.__package__ = "loreconvo"
    pkg.__file__ = str(src_root / "__init__.py")
    pkg.__spec__ = None
    sys.modules["loreconvo"] = pkg

    core_pkg = types.ModuleType("loreconvo.core")
    core_pkg.__path__ = [str(src_root / "core")]
    core_pkg.__package__ = "loreconvo.core"
    core_pkg.__file__ = str(src_root / "core" / "__init__.py")
    core_pkg.__spec__ = None
    sys.modules["loreconvo.core"] = core_pkg

    for rel in _SESSION_CORE_CLOSURE:
        name = "loreconvo." + rel[:-3].replace("/", ".")
        # Pop unconditionally: a failed path-1 import may have left a
        # partial module under this name (editable installs register the
        # module BEFORE its body finishes executing). Re-executing the
        # closure under the synthesized package guarantees a consistent
        # module graph; module-scope code here is idempotent.
        sys.modules.pop(name, None)
        try:
            _load_by_path(src_root / rel, name)
        except Exception as exc:
            raise _raise_synth_failed(src_root, broken_pkg, exc) from exc

    if broken_pkg is not None:
        _warn_once_degraded(str(src_root), broken_pkg)
    _clear_breadcrumb()


def _raise_synth_failed(src_root, broken_pkg, exc):
    parts = ["Cannot synthesize loreconvo session core."]
    parts.append(f"src root probed: {src_root}")
    parts.append(f"Failure: {exc!r}")
    if broken_pkg is not None:
        parts.append(
            f"loreconvo package was found but is broken: {broken_pkg}"
        )
    parts.append(
        "Remedy: pip install loreconvo, or run the fallback from a "
        "checkout where hooks/ and src/ are siblings."
    )
    return BootstrapError("\n".join(parts))


def resolve_session_core(origin):
    """Resolve the SessionDatabase/Config/Session triad for non-package callers.

    Args:
        origin: Path(__file__) of the calling script.

    Returns:
        A SimpleNamespace with attributes SessionDatabase,
        SessionLimitReachedError, Config, and Session.

    Raises:
        BootstrapError: if neither the installed package nor a sibling
            src/ checkout can provide the session core.
    """
    # Path 1 -- installed package, preferred.
    broken_pkg = None
    try:
        if importlib.util.find_spec("loreconvo.core") is not None:
            try:
                from loreconvo.core.database import (
                    SessionDatabase,
                    SessionLimitReachedError,
                )
                from loreconvo.core.config import Config
                from loreconvo.core.models import Session
                _clear_breadcrumb()
                return types.SimpleNamespace(
                    SessionDatabase=SessionDatabase,
                    SessionLimitReachedError=SessionLimitReachedError,
                    Config=Config,
                    Session=Session,
                )
            except Exception as exc:
                broken_pkg = exc  # remembered, NOT fatal -- see path 2
    except ModuleNotFoundError as exc:
        # See resolve_storage_core: a missing 'loreconvo' is the normal
        # source-checkout layout, not a broken install.
        if exc.name != "loreconvo":
            broken_pkg = exc
    except Exception as exc:
        broken_pkg = exc

    # Path 2 -- bounded upward search for a sibling src/ checkout.
    base = origin.resolve().parent
    for level in range(_MAX_UPWARD_LEVELS + 1):
        root = base.parents[level - 1] if level else base
        src_root = root / _SRC_REL
        if src_root.is_dir():
            _synthesize_session_core(src_root, broken_pkg)
            from loreconvo.core.database import (
                SessionDatabase,
                SessionLimitReachedError,
            )
            from loreconvo.core.config import Config
            from loreconvo.core.models import Session
            return types.SimpleNamespace(
                SessionDatabase=SessionDatabase,
                SessionLimitReachedError=SessionLimitReachedError,
                Config=Config,
                Session=Session,
            )

    # Both paths failed -- raise with full diagnostics.
    parts = ["Cannot resolve loreconvo session core."]
    parts.append(
        "No installed package and no sibling src/ checkout within "
        f"{_MAX_UPWARD_LEVELS} levels above {origin.resolve().parent}."
    )
    if broken_pkg is not None:
        parts.append(
            f"loreconvo package was found but is broken: {broken_pkg}"
        )
    parts.append(
        "Remedy: pip install loreconvo, or run the fallback from a "
        "checkout where hooks/ and src/ are siblings."
    )
    raise BootstrapError("\n".join(parts))
