"""MCP SDK version compatibility guard for LoreConvo.

Checks the installed mcp package version at startup against the tested version.
Returns a structured CompatResult; check() never raises.

Dispositions for SH-11533 HIGH findings applied in this implementation:
  HIGH-3: packaging.version.InvalidVersion on installed version -> status=undetermined
  HIGH-4: import packaging.version inside check() try block (not at module level)
  HIGH-6/9: mcp.__version__ fallback when dist metadata absent (PYTHONPATH/marketplace envs)

Accepted (with documentation):
  HIGH-1, HIGH-2: inherent limitation of metadata-based versioning; documented in INSTALL.md
  HIGH-5: cache is intentional; env var changes take effect on restart
  HIGH-7: guard provides detection (get_server_info), not per-request enforcement
  HIGH-8: blocking on undetermined would harm operators where mcp is un-introspectable

Usage:
    python -m loreconvo.compat_check   (primary path)
    loreconvo-compat-check             (console_scripts alias, pip install only)

Exit codes: 0=ok, 1=mismatch, 2=undetermined/internal_error, 3=disabled
"""

import importlib.metadata
import os
import sys
from typing import Dict, List, Optional

_PRODUCT_DIST_NAME = "loreconvo"

# [SH-13566 / SH-13501 follow-up] When bumping this constant for a new mcp release,
# check whether LATEST_PROTOCOL_VERSION is "2026-07-28" or later. If so, re-run the
# SH-13566 spec-change grep (-32002, roots, sampling/create_message, Mcp-Session-Id)
# against the new SDK to verify the stdio-only exemption still holds before assuming
# this product needs no code changes for the new spec.
_MCP_TESTED_VERSION = "1.28.1"

_CACHED_RESULT: Optional[Dict] = None


def _get_installed_mcp_version() -> Optional[str]:
    """Return installed mcp version string, or None if not determinable.

    Tries importlib.metadata first; falls back to mcp.__version__ attribute
    for environments where dist metadata is absent (PYTHONPATH-only installs,
    some marketplace bundles). HIGH-6/HIGH-9 fix.
    """
    try:
        return importlib.metadata.version("mcp")
    except importlib.metadata.PackageNotFoundError:
        pass
    except Exception:
        pass
    try:
        import mcp
        ver = getattr(mcp, "__version__", None)
        if ver:
            return str(ver)
    except Exception:
        pass
    return None


def detect_install_kind() -> str:
    """Return 'wheel' or 'editable' based on install method.

    Checks if installed via `pip install -e` (editable) by looking for
    direct_url.json with "editable": true in the dist-info directory.
    Returns 'wheel' if detection fails or not editable.
    """
    try:
        dist = importlib.metadata.distribution(_PRODUCT_DIST_NAME)
        if hasattr(dist, '_path') and dist._path:
            direct_url_path = dist._path / 'direct_url.json'
            if direct_url_path.exists():
                import json
                try:
                    data = json.loads(direct_url_path.read_text())
                    if data.get('dir_info', {}).get('editable'):
                        return 'editable'
                except Exception:
                    pass
    except Exception:
        pass
    return 'wheel'


def extract_live_version_from_source() -> Optional[str]:
    """Extract version from the live source pyproject.toml when editable.

    For a PEP 660 editable install the dist-info sits in site-packages and
    the real source root is recorded in direct_url.json's 'url' field.
    Falls back to the legacy co-located layout (setup.py develop) before
    giving up. Returns the version string if found and readable, None
    otherwise. Only useful when detect_install_kind() returns 'editable'.
    """
    if detect_install_kind() != 'editable':
        return None

    try:
        from pathlib import Path
        import json
        dist = importlib.metadata.distribution(_PRODUCT_DIST_NAME)

        candidates = []
        if hasattr(dist, '_path') and dist._path:
            # PEP 660 editables: the source root is in direct_url.json.
            direct_url_path = dist._path / 'direct_url.json'
            if direct_url_path.exists():
                try:
                    data = json.loads(direct_url_path.read_text())
                    url = data.get('url', '')
                    if url.startswith('file://'):
                        src_root = Path(url[7:])
                        candidates.append(src_root / 'pyproject.toml')
                except Exception:
                    pass
            # Legacy co-located installs: egg-info/dist-info inside the source tree.
            candidates.append(dist._path.parent / 'pyproject.toml')
            candidates.append(dist._path.parent.parent / 'pyproject.toml')

        for pyproject_path in candidates:
            if not pyproject_path.exists():
                continue
            content = pyproject_path.read_text()
            import re
            match = re.search(r'version\s*=\s*["\']([^"\']+)["\']', content)
            if match:
                return match.group(1)
        return None
    except Exception:
        return None


def check() -> Dict:
    """Return MCP compatibility status. Never raises.

    Result is cached on first call (except for internal_error). To re-evaluate
    after env var changes, restart the server -- cached state reflects startup
    configuration.

    Returns a dict with keys:
        product_name     -- "loreconvo"
        product_version  -- installed loreconvo version or None
        mcp_installed    -- installed mcp version or None
        mcp_tested       -- _MCP_TESTED_VERSION constant
        mcp_accepted     -- effective accepted version list (tested + operator overrides)
        status           -- ok | mismatch | undetermined | disabled | internal_error
        note             -- human-readable summary (no raw exception text)
        error_detail     -- set only on internal_error; None otherwise
    """
    global _CACHED_RESULT
    if _CACHED_RESULT is not None:
        return _CACHED_RESULT

    product_version: Optional[str] = None
    try:
        # Get product version (best-effort; failure is non-fatal)
        try:
            product_version = importlib.metadata.version(_PRODUCT_DIST_NAME)
        except Exception:
            product_version = None

        # Check disable flag first
        if os.environ.get("LORECONVO_MCP_COMPAT_DISABLE"):
            result: Dict = {
                "product_name": _PRODUCT_DIST_NAME,
                "product_version": product_version,
                "mcp_installed": None,
                "mcp_tested": _MCP_TESTED_VERSION,
                "mcp_accepted": [_MCP_TESTED_VERSION],
                "status": "disabled",
                "note": "MCP compatibility guard disabled via LORECONVO_MCP_COMPAT_DISABLE env var",
                "error_detail": None,
            }
            _CACHED_RESULT = result
            return result

        # Get installed mcp version
        mcp_installed = _get_installed_mcp_version()

        if mcp_installed is None:
            result = {
                "product_name": _PRODUCT_DIST_NAME,
                "product_version": product_version,
                "mcp_installed": None,
                "mcp_tested": _MCP_TESTED_VERSION,
                "mcp_accepted": [_MCP_TESTED_VERSION],
                "status": "undetermined",
                "note": (
                    "Cannot determine installed mcp version; compatibility unverified. "
                    "Set LORECONVO_MCP_ACCEPTED_VERSIONS=<version> if running a known version, "
                    "or reinstall mcp (pip install mcp) to restore dist metadata."
                ),
                "error_detail": None,
            }
            _CACHED_RESULT = result
            return result

        # HIGH-4 fix: import packaging inside try block so missing package -> internal_error
        import packaging.version

        # Build effective accepted set (tested version + operator overrides)
        accepted_set = {_MCP_TESTED_VERSION}
        accepted_extra: List[str] = []
        accepted_raw = os.environ.get("LORECONVO_MCP_ACCEPTED_VERSIONS", "").strip()
        if accepted_raw:
            for token in accepted_raw.split(","):
                token = token.strip()
                if not token:
                    continue
                try:
                    packaging.version.Version(token)
                    accepted_set.add(token)
                    accepted_extra.append(token)
                except packaging.version.InvalidVersion:
                    sys.stderr.write(
                        "WARNING [mcp-compat]: skipping invalid version in "
                        "LORECONVO_MCP_ACCEPTED_VERSIONS: " + repr(token) + "\n"
                    )
                    sys.stderr.flush()

        if accepted_extra:
            sys.stderr.write(
                "INFO [mcp-compat]: accepted operator overrides: "
                + ", ".join(accepted_extra) + "\n"
            )
            sys.stderr.flush()

        effective_accepted = sorted(accepted_set)

        # HIGH-3 fix: non-PEP-440 installed version -> undetermined (not mismatch or exception)
        try:
            installed_ver = packaging.version.Version(mcp_installed)
        except packaging.version.InvalidVersion:
            result = {
                "product_name": _PRODUCT_DIST_NAME,
                "product_version": product_version,
                "mcp_installed": mcp_installed,
                "mcp_tested": _MCP_TESTED_VERSION,
                "mcp_accepted": effective_accepted,
                "status": "undetermined",
                "note": (
                    "Installed mcp version " + repr(mcp_installed) + " is not a valid "
                    "PEP 440 version string; compatibility unverified."
                ),
                "error_detail": None,
            }
            _CACHED_RESULT = result
            return result

        # Compare installed version against effective accepted set
        is_ok = any(
            installed_ver == packaging.version.Version(v) for v in accepted_set
        )

        if is_ok:
            status = "ok"
            note = "mcp " + mcp_installed + " matches tested/accepted version"
        else:
            status = "mismatch"
            note = (
                "mcp " + mcp_installed + " does not match tested version "
                + _MCP_TESTED_VERSION + ". Set "
                "LORECONVO_MCP_ACCEPTED_VERSIONS=" + mcp_installed
                + " to acknowledge, or pin mcp==" + _MCP_TESTED_VERSION + "."
            )

        result = {
            "product_name": _PRODUCT_DIST_NAME,
            "product_version": product_version,
            "mcp_installed": mcp_installed,
            "mcp_tested": _MCP_TESTED_VERSION,
            "mcp_accepted": effective_accepted,
            "status": status,
            "note": note,
            "error_detail": None,
        }
        _CACHED_RESULT = result
        return result

    except Exception as exc:
        result = {
            "product_name": _PRODUCT_DIST_NAME,
            "product_version": product_version,
            "mcp_installed": None,
            "mcp_tested": _MCP_TESTED_VERSION,
            "mcp_accepted": [],
            "status": "internal_error",
            "note": "Unexpected error in MCP compatibility check; guard inactive",
            "error_detail": str(exc),
        }
        return result


def emit_startup_warnings(result: Dict) -> None:
    """Emit startup warnings to stderr. Raise RuntimeError on mismatch+strict."""
    status = result["status"]
    if status == "disabled":
        sys.stderr.write(
            "WARNING [mcp-compat]: compatibility guard DISABLED via "
            "LORECONVO_MCP_COMPAT_DISABLE env var\n"
        )
        sys.stderr.flush()
    elif status in ("mismatch", "undetermined", "internal_error"):
        sys.stderr.write("WARNING [mcp-compat]: " + result["note"] + "\n")
        sys.stderr.flush()

    # Strict mode raises ONLY on confirmed mismatch, never on infrastructure failures
    if status == "mismatch" and os.environ.get("LORECONVO_MCP_STRICT") == "1":
        raise RuntimeError("MCP version mismatch (strict mode): " + result["note"])


def main() -> None:
    """CLI entry point. Prints CompatResult JSON and exits with a status code."""
    import json
    result = check()
    print(json.dumps(result, indent=2))
    status = result["status"]
    if status == "ok":
        sys.exit(0)
    elif status == "mismatch":
        sys.exit(1)
    elif status in ("undetermined", "internal_error"):
        sys.exit(2)
    else:
        sys.exit(3)


if __name__ == "__main__":
    main()
