"""Session Bridge configuration."""

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path


_VALID_TIERS = {"free", "pro"}

# The Anthropic key LoreConvo owns. Never fall back to ANTHROPIC_API_KEY: the
# README promises that leaving this unset keeps all data local (SH-105079).
# It is the key env of the built-in `anthropic-haiku` summarizer backend and
# the ONLY key the Anthropic-SDK paths (capture_worker, save_session
# summarize=True) may use (SH-107043).
SUMMARIZER_API_KEY_ENV = "LORECONVO_ANTHROPIC_API_KEY"


def get_summarizer_api_key() -> str:
    """Return the ACTIVE summarizer backend's API key, or '' when it is unset
    or the backend configuration is invalid (SH-107043).

    With nothing configured the active backend is `anthropic-haiku`, so this
    reads LORECONVO_ANTHROPIC_API_KEY exactly as before. A configured
    OpenAI-compatible backend reads its own derived LORECONVO_<ID>_API_KEY.
    Callers that post to Anthropic's SDK must NOT use this accessor -- see
    get_anthropic_capture_key().
    """
    from .summarizer_backends import BackendConfigError, get_active_backend
    try:
        backend = get_active_backend()
    except BackendConfigError:
        return ""
    return os.environ.get(backend.key_env, "")


def get_anthropic_capture_key() -> str:
    """Return LORECONVO_ANTHROPIC_API_KEY only, or '' when unset.

    For code that calls api.anthropic.com directly (the post-turn capture
    worker and save_session(summarize=True)). It never returns another
    backend's key, so a non-Anthropic summarizer key can never be sent to
    Anthropic (SH-107043 wire-boundary invariant).
    """
    return os.environ.get(SUMMARIZER_API_KEY_ENV, "")


def _locked_config_update(
    config_path: Path,
    update_fn,
    timeout: float = 2.0,
) -> None:
    """Read-modify-write ``config.json`` under an advisory lock with atomic
    replace.

    Acquires an exclusive ``fcntl.flock`` on a sibling ``config.json.lock``
    file (bounded retry, never blocks), reads the existing config, applies
    *update_fn* (which mutates the dict in place), then writes to a temp file
    and ``os.replace``s it atomically.  This prevents lost updates between
    concurrent writers (e.g. ``set_tier`` and ``configure_tools``) and ensures
    a crash mid-write never leaves a truncated file.
    """
    try:
        import fcntl
    except ImportError:  # Windows -- no fcntl; atomic replace still safe
        fcntl = None  # type: ignore

    lock_path = str(config_path) + ".lock"
    deadline = time.monotonic() + timeout

    lock_fd: int | None = None
    while True:
        lock_fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        if fcntl is None:
            break  # no locking on Windows -- proceed with atomic replace only
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            break
        except (BlockingIOError, OSError):
            os.close(lock_fd)
            lock_fd = None
            if time.monotonic() > deadline:
                raise TimeoutError(
                    "config.json is locked by another writer; try again."
                )
            time.sleep(0.05)

    try:
        config: dict = {}
        if config_path.exists():
            try:
                config = json.loads(
                    config_path.read_text(encoding="utf-8")
                )
            except Exception:
                pass
        update_fn(config)
        tmp_path = str(config_path) + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)
        os.chmod(tmp_path, 0o600)
        os.replace(tmp_path, str(config_path))
    finally:
        if lock_fd is not None:
            if fcntl is not None:
                try:
                    fcntl.flock(lock_fd, fcntl.LOCK_UN)
                except Exception:
                    pass
            os.close(lock_fd)


def set_tier(db_dir: Path, tier: str) -> None:
    """Persist a tier change to config.json in the database directory.

    Called by the vault_set_tier MCP tool after license validation.
    """
    if tier not in _VALID_TIERS:
        raise ValueError(
            f"Invalid tier '{tier}'. Valid: {sorted(_VALID_TIERS)}"
        )
    config_path = db_dir / "config.json"

    def _apply(cfg: dict) -> None:
        cfg["tier"] = tier

    _locked_config_update(config_path, _apply)


def save_tool_groups(db_dir: Path, groups: list[str]) -> None:
    """Persist the enabled tool-group selection to config.json.

    Called by the ``configure_tools`` MCP tool.  Validates group names before
    writing.
    """
    from .tool_groups import validate_group_names

    validated = validate_group_names(groups)
    config_path = db_dir / "config.json"

    def _apply(cfg: dict) -> None:
        cfg["tool_groups"] = validated

    _locked_config_update(config_path, _apply)


def save_verbatim_capture(db_dir: Path, enabled: bool) -> None:
    """Persist the verbatim capture switch to config.json (SH-106224)."""
    if not isinstance(enabled, bool):
        raise ValueError("enabled must be True or False")
    config_path = Path(db_dir) / "config.json"

    def _apply(cfg: dict) -> None:
        cfg["verbatim_capture"] = enabled

    _locked_config_update(config_path, _apply)


@dataclass
class Config:
    db_path: str = ""
    max_free_sessions: int = 50
    default_days_back: int = 30
    default_limit: int = 10

    def __post_init__(self):
        if not self.db_path:
            from .storage_core import discover_loreconvo_db
            self.db_path = str(discover_loreconvo_db())

    def ensure_db_dir(self):
        db_dir = Path(self.db_path).parent
        db_dir.mkdir(parents=True, mode=0o700, exist_ok=True)

    @property
    def config_path(self) -> Path:
        """Path to config.json in the database directory."""
        return Path(self.db_path).parent / "config.json"

    @property
    def is_pro(self) -> bool:
        """Return True if the user has a valid Pro license.

        Pro mode is enabled by setting the LORECONVO_PRO environment variable
        to a valid Labyrinth Analytics license key (LAB-...).

        For internal agents: set both LORECONVO_PRO=1 and LAB_DEV_MODE=1 in
        the internal .mcp.json to bypass key validation.  The public plugin
        .mcp.json files must NOT include LAB_DEV_MODE.
        """
        from .license import is_pro_licensed
        return is_pro_licensed()