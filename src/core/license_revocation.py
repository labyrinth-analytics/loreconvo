"""GENERATED from scripts/lib/license_revocation.py -- do not edit.

Regenerate with: .venv/bin/python scripts/generate_license_revocation.py
The products ship standalone to PyPI and cannot import scripts/lib directly,
so this is a byte-identical copy of the canonical module's body
(CLAUDE.md drift rules 1, 3, 4: one human-edited source, products get a
generated copy). --check mode runs in release.sh.
"""

import base64
import hashlib
import json
import logging
import os
import re
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Dedicated revocation public key(s) (base64-encoded raw Ed25519 bytes, 32 each).
# Separate from the license issuance key -- compromise of one does not permit
# abuse of the other. Rotation: ship a release appending the new key, publish
# a list signed by the new key.
_REVOKE_PUBKEYS_B64 = (
    "TPVdyHhQcPDOocgLtaGVNJM8Vk1bT9sRxH4XknuMSNY=",
)

# Maximum seq ahead of the bundled list's seq that a fetched/cached list may have.
MAX_SEQ_AHEAD = 1000

# Input size cap (256 KiB).
_MAX_INPUT_SIZE = 256 * 1024

# Maximum revoked entries per list.
_MAX_ENTRIES = 2000

# Signature domain prefix (defense in depth -- issuance key never signs lists).
_DOMAIN_PREFIX = b"LAB-REVOKE-v1\n"

# Refresh URL (static public file).
_REFRESH_URL = "https://labyrinthanalyticsconsulting.com/revocations.lrl"

# Refresh timeouts.
_REFRESH_CONNECT_TIMEOUT = 3
_REFRESH_TOTAL_TIMEOUT = 5

# Cache refresh interval (24 hours).
_CACHE_REFRESH_INTERVAL = 24 * 60 * 60

# Hex pattern for revoked entries (64 lowercase hex chars = sha256 of sig).
_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")

# Module-level diagnostic: status of the last list operation.
# Values: ok|bad_signature|bad_format|oversize|unsupported_version|absent|bad_seq
LAST_LIST_STATUS = "absent"


# ---------------------------------------------------------------------------
# Exception
# ---------------------------------------------------------------------------

try:
    from .license import LicenseError
except ImportError:
    try:
        from license import LicenseError  # noqa: F401
    except ImportError:
        class LicenseError(Exception):
            """Fallback LicenseError for standalone canonical-source context."""


class LicenseRevoked(LicenseError):
    """Raised when a license key has been revoked.

    Subclasses LicenseError so every existing ``except LicenseError`` block
    degrades to the free tier without code changes.
    """


# ---------------------------------------------------------------------------
# Base64url helpers (same rules as license.py)
# ---------------------------------------------------------------------------

def _b64url_decode(s: str) -> bytes:
    """Decode a base64url string (with or without padding)."""
    s = s + "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s)


# ---------------------------------------------------------------------------
# Public key loading
# ---------------------------------------------------------------------------

def _load_revoke_pubkeys():
    """Load the embedded revocation public key(s) for list verification."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    keys = []
    for b64 in _REVOKE_PUBKEYS_B64:
        raw = base64.b64decode(b64)
        keys.append(Ed25519PublicKey.from_public_bytes(raw))
    return keys


# ---------------------------------------------------------------------------
# sig_fingerprint
# ---------------------------------------------------------------------------

def sig_fingerprint(key: str) -> Optional[str]:
    """Compute the revocation identifier for a license key.

    Decodes the key's Ed25519 signature and returns ``sha256(sig_bytes)``
    as a 64-char lowercase hex string. Returns None if the key is malformed
    (the caller -- validate_license_key -- has already validated the key
    before calling check_not_revoked, so None here is a defensive guard).
    """
    if not key or not key.startswith("LAB-"):
        return None
    body = key[4:]
    parts = body.split(".")
    if len(parts) != 2:
        return None
    try:
        sig_bytes = _b64url_decode(parts[1])
    except Exception:
        return None
    return hashlib.sha256(sig_bytes).hexdigest()


# ---------------------------------------------------------------------------
# parse_list
# ---------------------------------------------------------------------------

def parse_list(text: str, bundled_seq: Optional[int] = None) -> Optional[dict]:
    """Verify and parse a signed revocation list.

    Args:
        text: The LRL-... text (one line, may have trailing newline).
        bundled_seq: The seq of the bundled list shipped in the installed
            package. When None (parsing the bundled list itself), only
            ``seq >= 1`` is enforced. When provided, the seq window
            ``[1, bundled_seq + MAX_SEQ_AHEAD]`` is enforced.

    Returns:
        dict with ``v``, ``seq``, ``revoked`` (set of hex strings) on success.
        None on any failure. Sets ``LAST_LIST_STATUS`` to the failure reason.

    Never raises -- all errors are caught and returned as None.
    """
    global LAST_LIST_STATUS

    if not text:
        LAST_LIST_STATUS = "absent"
        return None

    text = text.strip()
    if not text:
        LAST_LIST_STATUS = "absent"
        return None

    # Size cap.
    if len(text) > _MAX_INPUT_SIZE:
        LAST_LIST_STATUS = "oversize"
        return None

    # Must start with LRL- prefix.
    if not text.startswith("LRL-"):
        LAST_LIST_STATUS = "bad_format"
        return None

    body = text[4:]
    parts = body.split(".")
    if len(parts) != 2:
        LAST_LIST_STATUS = "bad_format"
        return None

    encoded_payload, encoded_sig = parts[0], parts[1]

    try:
        payload_bytes = _b64url_decode(encoded_payload)
        sig_bytes = _b64url_decode(encoded_sig)
    except Exception:
        LAST_LIST_STATUS = "bad_format"
        return None

    # Verify signature BEFORE parsing (defense against untrusted input).
    pubkeys = _load_revoke_pubkeys()
    verified = False
    for pk in pubkeys:
        try:
            pk.verify(sig_bytes, _DOMAIN_PREFIX + payload_bytes)
            verified = True
            break
        except Exception:
            continue

    if not verified:
        LAST_LIST_STATUS = "bad_signature"
        return None

    # Parse payload JSON.
    try:
        payload = json.loads(payload_bytes.decode("utf-8"))
    except Exception:
        LAST_LIST_STATUS = "bad_format"
        return None

    if not isinstance(payload, dict):
        LAST_LIST_STATUS = "bad_format"
        return None

    # Version gate.
    v = payload.get("v")
    if v != 1:
        LAST_LIST_STATUS = "unsupported_version"
        return None

    # Seq must be a JSON integer (type(seq) is int -- rejects bool/float/str).
    seq = payload.get("seq")
    if type(seq) is not int:  # noqa: E721 -- explicit type check per proposal
        LAST_LIST_STATUS = "bad_seq"
        return None

    # Seq lower bound.
    if seq < 1:
        LAST_LIST_STATUS = "bad_seq"
        return None

    # Seq upper bound (only for non-bundled lists).
    if bundled_seq is not None:
        if seq > bundled_seq + MAX_SEQ_AHEAD:
            LAST_LIST_STATUS = "bad_seq"
            return None

    # Revoked entries.
    revoked_raw = payload.get("revoked", [])
    if not isinstance(revoked_raw, list):
        LAST_LIST_STATUS = "bad_format"
        return None

    if len(revoked_raw) > _MAX_ENTRIES:
        LAST_LIST_STATUS = "oversize"
        return None

    # Validate entries: must match ^[0-9a-f]{64}$; drop non-conforming;
    # collapse duplicates.
    revoked = set()
    for entry in revoked_raw:
        if isinstance(entry, str) and _HEX64_RE.match(entry):
            revoked.add(entry)

    LAST_LIST_STATUS = "ok"
    return {
        "v": v,
        "seq": seq,
        "revoked": revoked,
    }


# ---------------------------------------------------------------------------
# Bundled list loading
# ---------------------------------------------------------------------------

def _load_bundled_list() -> Optional[dict]:
    """Load and parse the bundled revocations.lrl from the package.

    Uses importlib.resources so it works in wheels, editable installs, and
    zip imports. Returns None if the file is absent or fails to parse.
    """
    global LAST_LIST_STATUS

    try:
        import importlib.resources as ir
        text = ir.files(__package__).joinpath("revocations.lrl").read_text(
            encoding="utf-8"
        )
    except Exception:
        LAST_LIST_STATUS = "absent"
        return None

    # Bundled list: bounded only by seq >= 1.
    return parse_list(text, bundled_seq=None)


def _derive_product() -> str:
    """Derive the product name from __package__."""
    pkg = __package__ or ""
    if "loredocs" in pkg:
        return "loredocs"
    return "loreconvo"


def _cache_path(product: str) -> Path:
    """Return the cache file path for the given product."""
    return Path.home() / f".{product}" / "revocations.lrl"


def _load_cache(product: str, bundled_seq: int) -> Optional[dict]:
    """Load and parse the cache file. Returns None if absent or invalid."""
    path = _cache_path(product)
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return None
    return parse_list(text, bundled_seq=bundled_seq)


def _write_cache(product: str, text: str) -> bool:
    """Write the cache file atomically (temp file + os.replace, chmod 600)."""
    path = _cache_path(product)
    d = path.parent
    try:
        d.mkdir(parents=True, exist_ok=True)
    except OSError:
        return False

    try:
        fd, tmp_name = tempfile.mkstemp(dir=str(d), prefix=".revocations.", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(text)
            if sys.platform != "win32":
                os.chmod(tmp_name, 0o600)
            os.replace(tmp_name, str(path))
        except OSError:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            return False
    except OSError:
        return False
    return True


# ---------------------------------------------------------------------------
# check_not_revoked
# ---------------------------------------------------------------------------

def check_not_revoked(key: str) -> None:
    """Check whether a license key has been revoked.

    Called by validate_license_key() immediately before its success return.
    Raises LicenseRevoked if the key's signature fingerprint appears in the
    highest-seq valid revocation list (bundled or cached). Never raises any
    other exception -- all errors fail open (the key is NOT revoked).

    No network call is made from this function.
    """
    global LAST_LIST_STATUS

    fingerprint = sig_fingerprint(key)
    if fingerprint is None:
        # Malformed key -- validate_license_key would have already rejected it.
        return

    # Load bundled list (the floor).
    bundled = _load_bundled_list()
    if bundled is None:
        # No bundled list -> no anchor -> no cache accepted either.
        LAST_LIST_STATUS = "absent"
        return

    bundled_seq = bundled["seq"]

    # Load cache (if any), bounded by the bundled seq.
    cache = _load_cache(_derive_product(), bundled_seq)

    # Select the highest-seq valid list.
    best = bundled
    if cache is not None and cache["seq"] > bundled["seq"]:
        best = cache

    LAST_LIST_STATUS = "ok"

    if fingerprint in best["revoked"]:
        raise LicenseRevoked(
            "This license key has been revoked. Contact support at "
            "labyrinthanalyticsconsulting.com for a replacement key."
        )


# ---------------------------------------------------------------------------
# refresh_cache_async
# ---------------------------------------------------------------------------

def _no_redirect_handler():
    """Return a urllib handler that refuses redirects."""
    class _NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None
    return _NoRedirect()


def _do_refresh(product: str, bundled_seq: int) -> None:
    """Attempt to download a fresh revocation list and cache it.

    Runs in a daemon thread. Never raises. Only writes a cache entry whose
    seq is greater than the current cache's (compare-before-replace).
    """
    log = logging.getLogger(__name__)

    try:
        # Check current cache seq (if any) to decide whether to write.
        current_cache = _load_cache(product, bundled_seq)
        current_seq = current_cache["seq"] if current_cache else 0

        opener = urllib.request.OpenerDirector()
        opener.add_handler(_no_redirect_handler())

        req = urllib.request.Request(
            _REFRESH_URL,
            headers={
                "User-Agent": "lore-license/1.0",
            },
        )

        deadline = time.monotonic() + _REFRESH_TOTAL_TIMEOUT
        try:
            resp = opener.open(req, timeout=_REFRESH_CONNECT_TIMEOUT)
        except Exception:
            if log:
                log.debug("revocation refresh: connect failed", exc_info=True)
            return

        # Read with total deadline and size cap.
        chunks = []
        total = 0
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                if log:
                    log.debug("revocation refresh: total timeout exceeded")
                return
            try:
                chunk = resp.read(8192)
            except Exception:
                if log:
                    log.debug("revocation refresh: read failed", exc_info=True)
                return
            if not chunk:
                break
            total += len(chunk)
            if total > _MAX_INPUT_SIZE:
                if log:
                    log.debug("revocation refresh: response exceeds size cap")
                return
            chunks.append(chunk)

        text = b"".join(chunks).decode("utf-8", errors="replace")

        # Parse with seq window.
        parsed = parse_list(text, bundled_seq=bundled_seq)
        if parsed is None:
            if log:
                log.debug("revocation refresh: parse failed (status=%s)", LAST_LIST_STATUS)
            return

        # Only write if seq is greater than current cache.
        if parsed["seq"] <= current_seq:
            if log:
                log.debug("revocation refresh: fetched seq %d <= cache seq %d",
                          parsed["seq"], current_seq)
            return

        _write_cache(product, text.strip() + "\n")
        if log:
            log.debug("revocation refresh: cached seq %d", parsed["seq"])

    except Exception:
        if log:
            log.debug("revocation refresh: unexpected error", exc_info=True)


def _cache_needs_refresh(product: str) -> bool:
    """True if the cache is missing, older than 24h, or has a future mtime."""
    path = _cache_path(product)
    try:
        st = path.stat()
    except OSError:
        return True  # missing

    now = time.time()
    mtime = st.st_mtime

    # Future mtime (clock skew / copy) -> refresh.
    if mtime > now:
        return True

    age = now - mtime
    return age >= _CACHE_REFRESH_INTERVAL


def refresh_cache_async(product: str = "") -> None:
    """Start a background refresh of the revocation list cache.

    Called once at MCP server startup and by the ``license status`` command.
    Never blocks and never raises. Refresh is skipped if:
    - LORE_REVOCATION_REFRESH=0 is set
    - The cache is fresh (younger than 24h and not future-dated)

    The refresh makes one unauthenticated GET of a static public file.
    No key, email, purchase_id, or machine identifier is sent.
    """
    if os.environ.get("LORE_REVOCATION_REFRESH", "").strip() == "0":
        return

    prod = product or _derive_product()

    # Load bundled list to get the seq anchor.
    bundled = _load_bundled_list()
    if bundled is None:
        return  # no anchor -> no refresh

    bundled_seq = bundled["seq"]

    if not _cache_needs_refresh(prod):
        return

    t = threading.Thread(
        target=_do_refresh,
        args=(prod, bundled_seq),
        daemon=True,
    )
    t.start()


# ---------------------------------------------------------------------------
# get_revocation_status (for license status command)
# ---------------------------------------------------------------------------

def get_revocation_status() -> dict:
    """Return a dict describing the current revocation list state.

    Used by the ``license status`` command for diagnostics. Never raises.
    """
    bundled = _load_bundled_list()
    if bundled is None:
        return {"seq": None, "status": "none", "entries": 0}

    cache = _load_cache(_derive_product(), bundled["seq"])
    best = bundled
    if cache is not None and cache["seq"] > bundled["seq"]:
        best = cache

    return {
        "seq": best["seq"],
        "status": LAST_LIST_STATUS,
        "entries": len(best["revoked"]),
    }
