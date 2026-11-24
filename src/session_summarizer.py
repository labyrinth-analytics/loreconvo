"""LoreAutoCapture async session summarizer (SH-10723, v0.7.0).

Upgrades sessions from heuristic to LLM-quality summaries using the
Claude API. Designed to run as a background subprocess dispatched by
auto_save.py after the hook completes.

Key design decisions (per R5/R6 final spec):
- No fcntl: uses SQLite WAL + busy_timeout=10000ms for all coordination.
- BEGIN EXCLUSIVE for atomic cap check+increment (_claim_cap_slot).
- The LLM backend comes from core.summarizer_backends (SH-107043): default
  anthropic-haiku reading LORECONVO_ANTHROPIC_API_KEY (no fallback to
  ANTHROPIC_API_KEY); a configured backend reads its own derived key env.
  Invalid backend config fails closed: no request, no retry unit consumed.
- Pro-tier check via Config().is_pro (Ed25519 -- stronger than proposed HMAC).
- session_id validated via stdlib uuid.UUID(val, version=4).
- _verify_db_ownership() UID check (skipped on Windows).
- RotatingFileHandler (10MB, 1 backup) for summarizer.log.
- API key is NEVER logged.
"""

import json
import logging
import logging.handlers
import os
import platform
import sqlite3
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

# Import _open_conn from storage_core. Try relative import first (package
# context), fall back to absolute import (monorepo-root test context).
try:
    from .core.storage_core import _open_conn, redact_parsed_session, redact_text
    from .core.verbatim import open_authorized_transcript
    from .core import summarizer_backends as _backends
except ImportError:
    from core.storage_core import _open_conn, redact_parsed_session, redact_text
    from core.verbatim import open_authorized_transcript
    from core import summarizer_backends as _backends

# Module-level constants.
MAX_SUMMARY_RETRIES = 5
DAILY_CAP_DEFAULT = 100
_LOG_PATH = Path.home() / ".loreconvo" / "summarizer.log"
# Default-backend values, derived from the registry (one derivation per fact).
# Imported by internal_tools/loreconvo-bench and scripts/benchmarks.
_DEFAULT_BACKEND = _backends.BUILTIN_BACKENDS[_backends.DEFAULT_BACKEND_ID]
_SUMMARIZER_MODEL = _DEFAULT_BACKEND.model
_MAX_TRANSCRIPT_CHARS = _DEFAULT_BACKEND.max_input_chars
_SCHEMA_MIGRATION = "v06_v07"
SKIP_SUMMARIZE_SOURCES = frozenset({'claude_api', 'claude_async', 'pre_migration_unknown'})

_SUMMARY_PROMPT = """You are a session memory assistant. Given a Claude Code session transcript, extract:
1. A concise title (max 80 chars)
2. A summary of what was accomplished (3-6 sentences)
3. Key decisions made (bullet list, max 5)
4. Artifacts created or modified (bullet list, file paths when known)
5. Open questions remaining (bullet list, max 3)

Respond in this exact JSON format (no other text):
{
  "title": "...",
  "summary": "...",
  "decisions": ["..."],
  "artifacts": ["..."],
  "open_questions": ["..."]
}"""


def _setup_logging() -> None:
    _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(
        str(_LOG_PATH),
        maxBytes=10 * 1024 * 1024,
        backupCount=1,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    ))
    if os.path.exists(str(_LOG_PATH)):
        os.chmod(str(_LOG_PATH), 0o600)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)


log = logging.getLogger(__name__)


def _get_db_path() -> str:
    return os.environ.get("LORECONVO_DB",
                          str(Path.home() / ".loreconvo" / "sessions.db"))


def _get_api_key() -> str:
    """Return the active backend's key (default: LORECONVO_ANTHROPIC_API_KEY).

    No fallback to ANTHROPIC_API_KEY (R6 CRITICAL); '' when the backend config
    is invalid.
    """
    try:
        from .core.config import get_summarizer_api_key
    except ImportError:
        from core.config import get_summarizer_api_key
    return get_summarizer_api_key()


def _safe_error_text(exc: Exception) -> str:
    """Fallback-reason text that cannot echo endpoint or provider details.

    Backend errors carry only a class name, a fixed reason and an HTTP status
    (SH-107043); anything else keeps the historical str(exc)[:200].
    """
    if isinstance(exc, (_backends.BackendConfigError, _backends.BackendResponseError,
                        _backends.BackendTransportError)):
        return f"{type(exc).__name__}:{exc}"[:200]
    return str(exc)[:200]


def _get_daily_cap() -> int:
    try:
        return int(os.environ.get("LORECONVO_SUMMARIZER_DAILY_CAP", str(DAILY_CAP_DEFAULT)))
    except (ValueError, TypeError):
        return DAILY_CAP_DEFAULT


def _validate_session_id(val: str) -> str:
    """Validate session_id is a UUID4 string. Raises ValueError if not."""
    parsed = uuid.UUID(val, version=4)
    return str(parsed)


def _db_supports_wal(db_path: str) -> bool:
    """Return True if the DB supports WAL mode (False on NFS/read-only FS)."""
    try:
        conn = _open_conn(db_path, busy_timeout_ms=5000)
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        conn.close()
        return mode == "wal"
    except Exception as exc:
        log.warning("WAL check failed for %s: %s", db_path, exc)
        return False


def _verify_db_ownership(db_path: str) -> None:
    """Raise RuntimeError if sessions.db is owned by a different UID.

    Skipped on Windows (no os.stat().st_uid reliable equivalent).
    """
    if platform.system() == "Windows":
        return
    path = Path(db_path)
    if not path.exists():
        return
    file_uid = path.stat().st_uid
    if file_uid != os.getuid():
        raise RuntimeError(
            f"SECURITY: sessions.db at {db_path} is owned by UID {file_uid}, "
            f"current UID is {os.getuid()}. Refusing to access."
        )


def _check_schema_ready(conn: sqlite3.Connection) -> bool:
    """Return True if v06->v07 migration has been applied."""
    try:
        row = conn.execute(
            "SELECT migration_name FROM schema_migration_log WHERE migration_name=?",
            (_SCHEMA_MIGRATION,),
        ).fetchone()
        return row is not None
    except sqlite3.OperationalError:
        # schema_migration_log table doesn't exist yet -- migration not run.
        return False


def _claim_cap_slot(conn: sqlite3.Connection) -> bool:
    """Atomically check and increment the daily API call counter.

    Uses BEGIN EXCLUSIVE to prevent multi-process race.
    Returns True if a slot was claimed, False if cap exceeded.
    """
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    cap = _get_daily_cap()

    conn.execute("BEGIN EXCLUSIVE")
    try:
        row = conn.execute(
            "SELECT calls_today FROM cap_state WHERE date=?", (today,)
        ).fetchone()
        calls_today = row[0] if row else 0

        if calls_today >= cap:
            conn.execute("ROLLBACK")
            return False

        if row:
            conn.execute(
                "UPDATE cap_state SET calls_today=calls_today+1 WHERE date=?",
                (today,),
            )
        else:
            conn.execute(
                "INSERT INTO cap_state (date, calls_today) VALUES (?, 1)",
                (today,),
            )
        conn.execute("COMMIT")
        return True
    except Exception:
        try:
            conn.execute("ROLLBACK")
        except Exception:
            pass
        raise


def _open_db(db_path: str) -> sqlite3.Connection:
    """Open the database via _open_conn and verify WAL mode."""
    conn = _open_conn(db_path, busy_timeout_ms=10000)
    row = conn.execute("PRAGMA journal_mode").fetchone()
    actual_mode = row[0] if row else "unknown"
    if actual_mode != "wal":
        conn.close()
        raise RuntimeError(
            f"Database at '{db_path}' is in '{actual_mode}' journal mode, expected WAL. "
            "Another process may be using a conflicting journal mode."
        )
    return conn


def _fetch_session(conn: sqlite3.Connection, session_id: str):
    """Return session row or None."""
    return conn.execute(
        "SELECT id, title, summary, source, summary_source, summary_retry_count "
        "FROM sessions WHERE id=?",
        (session_id,),
    ).fetchone()


def _call_claude_api(transcript_excerpt: str, api_key: str) -> dict:
    """DEPRECATED (SH-107043): delegating shim, kept as the historical patch point.

    Resolves the active backend and delegates to summarizer_backends.call,
    so tests and tools that patch this name keep working. New code calls
    summarizer_backends.call directly; removing this shim is a P3 follow-up.
    Returns the parsed JSON dict; raises Backend*Error on failure.
    """
    backend = _backends.get_active_backend()
    return _backends.call(backend, api_key, _SUMMARY_PROMPT, transcript_excerpt)


def _as_list(value) -> list:
    """Normalize a model-returned list field to a list of strings (SH-105355).

    Haiku returns JSON arrays; older prompts asked for bullet strings. Either
    way the sessions columns hold json.dumps(list), like every other writer.
    Each item is capped at 2000 chars (SH-105359 hardening).
    """
    if value is None:
        return []
    if isinstance(value, list):
        items = value
    else:
        items = str(value).splitlines()

    result = []
    for item in items:
        if item is None:
            continue
        if isinstance(item, dict):
            try:
                item_str = json.dumps(item)
            except (TypeError, ValueError):
                continue
        else:
            item_str = str(item)

        item_str = item_str.strip()
        if item_str.startswith(("- ", "* ")):
            item_str = item_str[2:]
        elif item_str.startswith(("-", "*")):
            item_str = item_str[1:]
        item_str = item_str.strip()

        if len(item_str) > 2000:
            item_str = item_str[:2000]

        if item_str:
            result.append(item_str)

    return result


def _update_session_with_llm_summary(conn: sqlite3.Connection,
                                      session_id: str, result: dict) -> None:
    result = redact_parsed_session(result)  # SH-105853: model output too
    existing = conn.execute(
        "SELECT summary, project, surface FROM sessions WHERE id=?",
        (session_id,),
    ).fetchone()
    conn.execute(
        """UPDATE sessions SET
           title=?,
           previous_summary=CASE
               WHEN summary IS NOT ? THEN summary
               ELSE previous_summary
           END,
           summary=?, decisions=?, artifacts=?, open_questions=?,
           summary_source='claude_async', fallback_reason=NULL
           WHERE id=?""",
        (
            result.get("title"),
            result.get("summary"),
            result.get("summary"),
            json.dumps(_as_list(result.get("decisions"))),
            json.dumps(_as_list(result.get("artifacts"))),
            json.dumps(_as_list(result.get("open_questions"))),
            session_id,
        ),
    )
    if existing and existing["summary"] != result.get("summary"):
        try:
            conn.execute(
                "UPDATE memory_digests SET safety_invalidated=1 "
                "WHERE project=? AND (surface IS NULL OR surface IS ?)",
                (existing["project"], existing["surface"]),
            )
        except sqlite3.OperationalError:
            pass
    conn.commit()


def _mark_fallback(conn: sqlite3.Connection, session_id: str,
                   fallback_reason: str, exhausted: bool = False) -> None:
    source = "permanently_heuristic" if exhausted else "heuristic"
    conn.execute(
        """UPDATE sessions SET
           summary_source=?,
           summary_retry_count=summary_retry_count+1,
           fallback_reason=?
           WHERE id=?""",
        (source, fallback_reason, session_id),
    )
    conn.commit()


def summarize_session(session_id: str, transcript_path: str = None) -> bool:
    """Attempt to upgrade a single session to LLM-quality summary.

    Returns True if LLM summary written, False if skipped or fallback.
    """
    _setup_logging()

    # Validate session_id.
    try:
        session_id = _validate_session_id(session_id)
    except (ValueError, AttributeError) as exc:
        log.error("Invalid session_id %r: %s", session_id, exc)
        return False

    # Resolve the configured backend (SH-107043). Invalid or unknown config
    # fails closed: nothing is sent anywhere and no retry unit is consumed.
    try:
        backend = _backends.get_active_backend()
    except _backends.BackendConfigError as exc:
        log.warning("backend config invalid: %s -- skipping async summarization", exc)
        return False

    # Check API key (never log its value).
    api_key = _get_api_key()
    if not api_key and not backend.key_optional:
        log.warning("%s not set -- skipping async summarization", backend.key_env)
        return False

    # Check Pro license.
    try:
        try:
            from loreconvo.core.config import Config
        except ImportError:
            from core.config import Config
        if not Config().is_pro:
            log.info("Non-Pro tier -- skipping async summarization")
            return False
    except Exception as exc:
        log.warning("Could not check Pro status: %s -- skipping", exc)
        return False

    db_path = _get_db_path()

    # Verify DB ownership (shared-machine protection).
    try:
        _verify_db_ownership(db_path)
    except RuntimeError as exc:
        log.error("%s", exc)
        return False

    # Check WAL support.
    if not _db_supports_wal(db_path):
        log.warning("WAL mode unavailable for %s (NFS?) -- skipping async summarization", db_path)
        return False

    conn = _open_db(db_path)
    try:
        # Check migration is applied before touching new columns.
        if not _check_schema_ready(conn):
            log.info("Schema migration %s not yet applied -- skipping", _SCHEMA_MIGRATION)
            return False

        row = _fetch_session(conn, session_id)
        if row is None:
            log.warning("Session %s not found in DB", session_id)
            return False

        current_source = row["summary_source"] or "heuristic"
        retry_count = row["summary_retry_count"] or 0

        # Skip if already LLM-summarized, pre-migration (unknown quality), or permanently failed.
        if current_source in SKIP_SUMMARIZE_SOURCES:
            log.info("Session %s already has sufficient summary quality (%s) -- skipping", session_id, current_source)
            return True
        if current_source == "permanently_heuristic":
            log.info("Session %s permanently heuristic (exhausted retries) -- skipping", session_id)
            return False

        # Check retry budget.
        if retry_count >= MAX_SUMMARY_RETRIES:
            _mark_fallback(conn, session_id, "max_retries_exceeded", exhausted=True)
            log.warning("Session %s exhausted retry budget -- marked permanently_heuristic", session_id)
            return False

        # Claim daily cap slot.
        if not _claim_cap_slot(conn):
            _mark_fallback(conn, session_id, "daily_cap_exceeded")
            log.info("Daily API cap reached -- session %s fallback heuristic", session_id)
            return False

        # Mark as pending before calling API.
        conn.execute(
            "UPDATE sessions SET summary_source='summary_pending' WHERE id=?",
            (session_id,),
        )
        conn.commit()

        # Build transcript excerpt.
        transcript_text = ""
        if transcript_path:
            try:
                with open_authorized_transcript(transcript_path) as transcript:
                    transcript_text = transcript.read()
                # SH-105853: redact before the cut (a key straddling it would
                # otherwise survive as an unmatchable prefix).
                transcript_text = redact_text(transcript_text)[:backend.max_input_chars]
            except Exception as exc:
                log.warning("Could not read authorized transcript: %s", type(exc).__name__)
                transcript_text = row["summary"] or ""
        else:
            transcript_text = row["summary"] or ""

        if not transcript_text:
            _mark_fallback(conn, session_id, "no_transcript")
            log.info("No transcript available for session %s -- fallback heuristic", session_id)
            return False

        # SH-105853: never send a raw secret to the API.
        transcript_text = redact_text(transcript_text)

        # Call the configured backend. Log only the validated id/model and the
        # error class + status -- never the URL, key, or provider error text.
        log.info("Calling backend=%s model=%s for session %s",
                 backend.id, backend.model, session_id)
        try:
            result = _call_claude_api(transcript_text, api_key)
        except Exception as exc:
            safe_msg = _safe_error_text(exc)
            _mark_fallback(conn, session_id, f"api_error:{safe_msg}")
            log.error("API call failed for session %s backend=%s: %s",
                      session_id, backend.id, safe_msg)
            return False

        try:
            _update_session_with_llm_summary(conn, session_id, result)
        except Exception as exc:
            # SH-105355: a result we cannot apply must not leave the session
            # stuck at summary_pending or crash the dispatched process.
            safe_msg = str(exc)[:200]
            _mark_fallback(conn, session_id, f"apply_error:{safe_msg}")
            log.error("Could not apply summary for session %s: %s", session_id, safe_msg)
            return False
        log.info("SUMMARY_COMPLETE session_id=%s source=claude_async", session_id)
        return True

    finally:
        conn.close()


def main() -> int:
    """Entry point for subprocess dispatch from auto_save.py."""
    _setup_logging()

    if len(sys.argv) < 2:
        log.error("Usage: session_summarizer.py <session_id> [transcript_path]")
        return 1

    session_id = sys.argv[1]
    transcript_path = sys.argv[2] if len(sys.argv) > 2 else None

    success = summarize_session(session_id, transcript_path)
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
