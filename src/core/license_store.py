"""
Durable, cross-surface Pro license persistence for LoreConvo.

Storage: ~/.loreconvo/license.json (chmod 600, parent dir chmod 700), with a
~/.loreconvo/license.verified.json grace-period cache refreshed on every
successful write or signature-valid read.

Per SH-13079 (architecture: docs/agent-reports/architecture/proposals/
loreconvo_loredocs_durable_license_persistence_20260713.md, r3 data model):
a `lore_suite` key is written ONLY to the file of the product it was actually
set on; the sibling product resolves suite-wide access via a read-only
cross-file check at resolution time. There is exactly one stored copy of any
given key -- no dual-slot schema, no revoked_before timestamp, nothing to
reconcile.

Windows note: POSIX gets a real fd-based symlink/TOCTOU guard (O_NOFOLLOW +
fstat uid/mode checks), an advisory fcntl lock, and directory/file permission
refusal. Windows gets a best-effort symlink/junction check and an advisory
msvcrt lock but NOT the SID-based ACL verification the architecture proposal
specifies (PART:security) -- that is deferred to a follow-up ticket (filed
alongside this build; see SH-13079 disposition notes). Windows customers are
unaffected functionally: the env var precedence step (unchanged) still works
exactly as before this feature shipped.
"""

import json
import os
import stat
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

try:
    from .license import validate_license_key, LicenseError
except ImportError:  # pragma: no cover -- direct module import (CLI/test contexts)
    from license import validate_license_key, LicenseError  # noqa: F401

_SIBLING = {"loreconvo": "loredocs", "loredocs": "loreconvo"}
_GRACE_PERIOD_SECONDS = 72 * 60 * 60
_LOCK_TIMEOUT_SECONDS = 2.0


def _is_posix() -> bool:
    return sys.platform != "win32"


def _default_dir(product: str) -> Path:
    return Path.home() / f".{product}"


def _primary_path(d: Path) -> Path:
    return d / "license.json"


def _cache_path(d: Path) -> Path:
    return d / "license.verified.json"


def _lock_path(d: Path) -> Path:
    return d / ".license.lock"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _within_grace_period(verified_at: str) -> bool:
    try:
        ts = datetime.fromisoformat(verified_at)
    except (ValueError, TypeError):
        return False
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    age = (datetime.now(timezone.utc) - ts).total_seconds()
    return 0 <= age <= _GRACE_PERIOD_SECONDS


def _dir_is_safe(d: Path) -> bool:
    """POSIX: refuse a group- or world-writable directory. Windows: no-op (True)."""
    if not _is_posix():
        return True
    try:
        st = d.stat()
    except OSError:
        return True  # doesn't exist yet -- caller creates it
    return not (st.st_mode & (stat.S_IWGRP | stat.S_IWOTH))


def _ensure_dir_for_write(d: Path) -> bool:
    """Create the directory (0700) if absent. False if an existing directory
    fails the group/world-writable check."""
    if d.exists():
        return _dir_is_safe(d)
    d.mkdir(parents=True, exist_ok=True)
    if _is_posix():
        os.chmod(d, 0o700)
    return True


def _path_is_symlink(path: Path) -> bool:
    try:
        return path.is_symlink()
    except OSError:
        return False


def _open_readonly_fd(path: Path):
    """Open path refusing symlinks. Returns an fd, or None (never raises)."""
    flags = os.O_RDONLY
    if _is_posix() and hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(str(path), flags)
    except OSError:
        return None

    if _is_posix():
        try:
            st = os.fstat(fd)
        except OSError:
            os.close(fd)
            return None
        if st.st_uid != os.getuid():
            os.close(fd)
            return None
        if st.st_mode & 0o077:
            os.close(fd)
            return None
        if getattr(st, "st_nlink", 1) > 1:
            # Time Machine local snapshots, APFS clones, and ZFS dedup/snapshots can
            # all legitimately produce st_nlink > 1 with no attacker involved -- log,
            # don't refuse (r3 downgrade of the r2 hard-link guard).
            print(
                f"[warn] license_store: {path} has st_nlink={st.st_nlink}; "
                "continuing (expected on Time Machine/APFS-clone/ZFS-dedup filesystems)",
                file=sys.stderr,
            )
    else:
        # Windows best-effort: no O_NOFOLLOW in the stdlib. Check-then-open is racy
        # (see module docstring) but still catches the non-racing common case.
        try:
            if _path_is_symlink(path):
                os.close(fd)
                return None
        except OSError:
            pass

    return fd


def _read_json_safe(path: Path) -> Optional[dict]:
    """Read+parse a JSON object file. None on any failure -- never raises."""
    fd = _open_readonly_fd(path)
    if fd is None:
        return None
    try:
        with os.fdopen(fd, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _acquire_lock(f) -> None:
    deadline = time.monotonic() + _LOCK_TIMEOUT_SECONDS
    if _is_posix():
        import fcntl
        while True:
            try:
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return
            except OSError:
                if time.monotonic() >= deadline:
                    print("[warn] license_store: lock timed out, proceeding without lock", file=sys.stderr)
                    return
                time.sleep(0.05)
    else:
        import msvcrt
        while True:
            try:
                msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
                return
            except OSError:
                if time.monotonic() >= deadline:
                    print("[warn] license_store: lock timed out, proceeding without lock", file=sys.stderr)
                    return
                time.sleep(0.05)


def _release_lock(f) -> None:
    try:
        if _is_posix():
            import fcntl
            fcntl.flock(f, fcntl.LOCK_UN)
        else:
            import msvcrt
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
    except OSError:
        pass


def _atomic_write_json(d: Path, path: Path, data: dict) -> bool:
    """Write via tempfile + os.replace. True on success, False on failure (never raises)."""
    if not _ensure_dir_for_write(d):
        return False
    if _path_is_symlink(path):
        return False
    lock_f = None
    try:
        lock_f = open(_lock_path(d), "a+")
        _acquire_lock(lock_f)
        fd, tmp_name = tempfile.mkstemp(dir=str(d), prefix=".license.", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as tf:
                json.dump(data, tf, indent=2)
            if _is_posix():
                os.chmod(tmp_name, 0o600)
            os.replace(tmp_name, str(path))
        except OSError:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            return False
        return True
    except OSError:
        return False
    finally:
        if lock_f is not None:
            _release_lock(lock_f)
            lock_f.close()


def _valid_key_for(product: str, key: Optional[str]) -> Optional[dict]:
    """Return the validated payload for `key`, or None (falsy/unvalidated)."""
    if not key:
        return None
    try:
        return validate_license_key(key)
    except LicenseError:
        return None


def _refresh_cache(d: Path, key: str) -> None:
    _atomic_write_json(d, _cache_path(d), {"key": key, "verified_at": _now_iso()})


def _clear_cache(d: Path) -> None:
    try:
        _cache_path(d).unlink()
    except OSError:
        pass


def is_cleared(product: str, *, own_dir: Optional[Path] = None) -> bool:
    """True if `product`'s own file holds an explicit `license clear` tombstone."""
    d = own_dir or _default_dir(product)
    data = _read_json_safe(_primary_path(d))
    return bool(data and data.get("cleared"))


def read_key(
    product: str,
    *,
    own_dir: Optional[Path] = None,
    sibling_dir: Optional[Path] = None,
) -> Optional[str]:
    """Return a currently-valid LAB- key for `product`: own file, then a
    read-only cross-file check of the sibling's lore_suite-scoped key, then
    the 72h grace-period cache. Every candidate is re-validated via
    validate_license_key() before being returned. Never raises."""
    d = own_dir or _default_dir(product)
    own_data = _read_json_safe(_primary_path(d))
    own_cleared = bool(own_data and own_data.get("cleared"))

    if own_data and not own_cleared:
        candidate = own_data.get("key")
        if _valid_key_for(product, candidate) is not None:
            _refresh_cache(d, candidate)
            return candidate

    sibling = _SIBLING.get(product)
    sd = sibling_dir or (_default_dir(sibling) if sibling else None)
    if sd is not None:
        sib_data = _read_json_safe(_primary_path(sd))
        if sib_data and not sib_data.get("cleared"):
            candidate = sib_data.get("key")
            payload = _valid_key_for(product, candidate)
            if payload is not None and payload.get("product") == "lore_suite":
                return candidate

    if not own_cleared:
        cache = _read_json_safe(_cache_path(d))
        if cache:
            candidate = cache.get("key")
            verified_at = cache.get("verified_at")
            if candidate and verified_at and _within_grace_period(verified_at):
                if _valid_key_for(product, candidate) is not None:
                    return candidate

    return None


def write_key(
    product: str,
    key: str,
    *,
    source: str = "cli",
    own_dir: Optional[Path] = None,
) -> None:
    """Validate `key`, then write it to `product`'s own file only (r3: no
    sibling write, even for a lore_suite-scoped key -- see module docstring).

    source='cli': raise LicenseError with a remediation message on any
    failure (unsafe directory, symlink, or write failure).
    source='env-autopersist': never raise -- log a WARN and return, since a
    failed opportunistic durability write must not be treated as an
    activation failure (Pro access this session already came from the env
    var independent of this write)."""
    d = own_dir or _default_dir(product)
    primary = _primary_path(d)

    payload = _valid_key_for(product, key)
    if payload is None:
        raise LicenseError("Refusing to persist an invalid or unvalidated license key.")

    if d.exists() and not _dir_is_safe(d):
        msg = f"{d} is group- or world-writable; refusing to write license.json there."
        if source == "cli":
            raise LicenseError(msg + " Fix its permissions (chmod 700) and try again.")
        print(f"[warn] license_store: {msg}", file=sys.stderr)
        return

    if _path_is_symlink(primary):
        msg = f"{primary} exists as a symlink; refusing to write through it."
        if source == "cli":
            raise LicenseError(msg)
        print(f"[warn] license_store: {msg}", file=sys.stderr)
        return

    ok = _atomic_write_json(d, primary, {"version": 1, "key": key})
    if not ok:
        msg = f"Could not write {primary}."
        if source == "cli":
            raise LicenseError(
                msg + " Your LORECONVO_PRO/LOREDOCS_PRO environment variable "
                "still works unchanged for this session."
            )
        print(f"[warn] license_store: {msg} (env var Pro still active this session)", file=sys.stderr)
        return

    _refresh_cache(d, key)


def clear_key(
    product: str,
    *,
    suite_too: bool = False,
    own_dir: Optional[Path] = None,
    sibling_dir: Optional[Path] = None,
) -> list:
    """Remove `product`'s own stored key (tombstone, not a delete -- see
    module docstring). `suite_too=True` best-effort clears a lore_suite key
    from the sibling file too (single try, non-fatal).

    Returns a list of warning strings for anything that could NOT be cleared
    (e.g. sibling clear failed) -- empty list means everything requested was
    cleared. Callers (CLI) should surface these, not swallow them, so the
    "no reliable detection" gap flagged in SH-13079 disposition is closed at
    the visibility layer even where the clear itself can't be guaranteed."""
    d = own_dir or _default_dir(product)
    warnings = []

    if not _atomic_write_json(d, _primary_path(d), {"version": 1, "key": None, "cleared": True}):
        warnings.append(f"Could not write tombstone to {_primary_path(d)}.")
    _clear_cache(d)

    if suite_too:
        sibling = _SIBLING.get(product)
        sd = sibling_dir or (_default_dir(sibling) if sibling else None)
        if sd is None:
            return warnings
        try:
            sib_data = _read_json_safe(_primary_path(sd))
            if sib_data and sib_data.get("key"):
                sib_payload = _valid_key_for(product, sib_data.get("key"))
                if sib_payload is not None and sib_payload.get("product") == "lore_suite":
                    if not _atomic_write_json(sd, _primary_path(sd), {"version": 1, "key": None, "cleared": True}):
                        warnings.append(
                            f"Could not clear sibling suite key at {_primary_path(sd)}. "
                            f"Re-run `license clear --suite` from the '{sibling}' product's "
                            "own CLI to finish clearing suite-wide Pro."
                        )
                    else:
                        _clear_cache(sd)
        except OSError as exc:
            warnings.append(
                f"Sibling clear failed ({exc}). Re-run `license clear --suite` from the "
                f"'{sibling}' product's own CLI to finish clearing suite-wide Pro."
            )

    return warnings


def persist_from_env(product: str, key: str, *, own_dir: Optional[Path] = None) -> None:
    """Write-through-on-read durability: called by is_pro_licensed() the
    first time in a process's lifetime that env-var resolution succeeds, if
    the per-product file has no matching, still-valid entry yet. Only ever
    called with an already-validated LAB-... string. Never raises -- a
    failed persist here must not affect the caller's already-successful
    env-var resolution."""
    d = own_dir or _default_dir(product)
    existing = _read_json_safe(_primary_path(d))
    if existing and not existing.get("cleared"):
        candidate = existing.get("key")
        if candidate and _valid_key_for(product, candidate) is not None:
            return  # already durable and valid
    try:
        write_key(product, key, source="env-autopersist", own_dir=d)
    except LicenseError:
        pass  # write_key already logged a WARN for env-autopersist
