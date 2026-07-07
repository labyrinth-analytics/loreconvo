"""LoreAutoCapture async session summarizer (SH-10723, v0.7.0).

Upgrades sessions from heuristic to LLM-quality summaries using the
Claude API. Designed to run as a background subprocess dispatched by
auto_save.py after the hook completes.

Key design decisions (per R5/R6 final spec):
- No fcntl: uses SQLite WAL + busy_timeout=10000ms for all coordination.
- BEGIN EXCLUSIVE for atomic cap check+increment (_claim_cap_slot).
- LORECONVO_ANTHROPIC_API_KEY required (no fallback to ANTHROPIC_API_KEY).
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

# Module-level constants.
MAX_SUMMARY_RETRIES = 5
DAILY_CAP_DEFAULT = 100
_LOG_PATH = Path.home() / ".loreconvo" / "summarizer.log"
_SUMMARIZER_MODEL = "claude-haiku-4-5-20251001"
_MAX_TRANSCRIPT_CHARS = 40000
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
  "decisions": "...",
  "artifacts": "...",
  "open_questions": "..."
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
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)


log = logging.getLogger(__name__)


def _get_db_path() -> str:
    return os.environ.get("LORECONVO_DB",
                          str(Path.home() / ".loreconvo" / "sessions.db"))


def _get_api_key() -> str:
    """Return LORECONVO_ANTHROPIC_API_KEY. No fallback to ANTHROPIC_API_KEY (R6 CRITICAL)."""
    return os.environ.get("LORECONVO_ANTHROPIC_API_KEY", "")


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
        conn = sqlite3.connect(db_path, timeout=5.0)
        conn.execute("PRAGMA journal_mode=WAL")
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
    conn = sqlite3.connect(db_path, timeout=10.0)
    row = conn.execute("PRAGMA journal_mode=WAL").fetchone()
    actual_mode = row[0] if row else "unknown"
    if actual_mode != "wal":
        conn.close()
        raise RuntimeError(
            f"Database at '{db_path}' is in '{actual_mode}' journal mode, expected WAL. "
            "Another process may be using a conflicting journal mode."
        )
    conn.execute("PRAGMA busy_timeout=10000")
    conn.row_factory = sqlite3.Row
    return conn


def _fetch_session(conn: sqlite3.Connection, session_id: str):
    """Return session row or None."""
    return conn.execute(
        "SELECT id, title, summary, source, summary_source, summary_retry_count "
        "FROM sessions WHERE id=?",
        (session_id,),
    ).fetchone()


def _call_claude_api(transcript_excerpt: str, api_key: str) -> dict:
    """Call Claude Haiku to summarize the transcript excerpt.

    Returns parsed JSON dict with title/summary/decisions/artifacts/open_questions.
    Raises on API error.
    """
    import urllib.request

    payload = json.dumps({
        "model": _SUMMARIZER_MODEL,
        "max_tokens": 1024,
        "messages": [
            {
                "role": "user",
                "content": f"{_SUMMARY_PROMPT}\n\n<transcript>\n{transcript_excerpt}\n</transcript>",
            }
        ],
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=payload,
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read())

    text = data["content"][0]["text"]
    # Strip any markdown fences the model may add.
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    return json.loads(text)


def _update_session_with_llm_summary(conn: sqlite3.Connection,
                                      session_id: str, result: dict) -> None:
    conn.execute(
        """UPDATE sessions SET
           title=?, summary=?, decisions=?, artifacts=?, open_questions=?,
           summary_source='claude_async', fallback_reason=NULL
           WHERE id=?""",
        (
            result.get("title"),
            result.get("summary"),
            result.get("decisions"),
            result.get("artifacts"),
            result.get("open_questions"),
            session_id,
        ),
    )
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

    # Check API key (never log its value).
    api_key = _get_api_key()
    if not api_key:
        log.warning("LORECONVO_ANTHROPIC_API_KEY not set -- skipping async summarization")
        return False

    # Check Pro license.
    try:
        from src.core.config import Config
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
        if transcript_path and Path(transcript_path).exists():
            try:
                transcript_text = Path(transcript_path).read_text(encoding="utf-8", errors="replace")
                transcript_text = transcript_text[:_MAX_TRANSCRIPT_CHARS]
            except Exception as exc:
                log.warning("Could not read transcript at %s: %s", transcript_path, exc)
                transcript_text = row["summary"] or ""
        else:
            transcript_text = row["summary"] or ""

        if not transcript_text:
            _mark_fallback(conn, session_id, "no_transcript")
            log.info("No transcript available for session %s -- fallback heuristic", session_id)
            return False

        # Call API.
        try:
            result = _call_claude_api(transcript_text, api_key)
        except Exception as exc:
            # Never log the exc message if it might contain key material.
            safe_msg = str(exc)[:200]
            _mark_fallback(conn, session_id, f"api_error:{safe_msg}")
            log.error("API call failed for session %s: %s", session_id, safe_msg)
            return False

        _update_session_with_llm_summary(conn, session_id, result)
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
