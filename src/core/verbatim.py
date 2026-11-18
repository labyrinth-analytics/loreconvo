"""Verbatim conversation capture for LoreConvo (SH-106224).

Stdlib only, and no imports from the loreconvo package: hooks load this
module by file path (hooks/scripts/_bootstrap.py::resolve_verbatim).
Callers pass in the redaction function. The tables are created by
storage_core.ensure_verbatim_schema; there is no DDL in this file.
"""

import json
import os
import re
from pathlib import Path

CONFIG_KEY = "verbatim_capture"
ENV_VAR = "LORECONVO_VERBATIM_CAPTURE"
_ENV_TRUE = {"1", "true", "on", "yes"}


def verbatim_capture_enabled(db_dir, environ=None):
    """Return True when verbatim text may be stored.

    Order: the environment variable wins when set to a non-empty value
    (only 1/true/on/yes mean on; anything else is off). Otherwise the
    `verbatim_capture` key in config.json next to the database. Default on.
    A config file that cannot be read as a JSON object, or a key that is not
    a JSON boolean, resolves to off, so a broken file never stores more than
    the user chose.
    """
    env = os.environ if environ is None else environ
    raw = env.get(ENV_VAR)
    if raw is not None and raw.strip() != "":
        return raw.strip().lower() in _ENV_TRUE
    path = Path(db_dir) / "config.json"
    if not path.exists():
        return True
    try:
        cfg = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    if not isinstance(cfg, dict):
        return False
    if CONFIG_KEY not in cfg:
        return True
    return cfg[CONFIG_KEY] is True


MAX_CHUNK_CHARS = 2000
# seq = exchange * SEQ_STRIDE + piece, so one exchange holds at most
# SEQ_STRIDE - 1 pieces.
SEQ_STRIDE = 1000
_REMINDER_RE = re.compile(r"<system-reminder>.*?</system-reminder>", re.DOTALL)


def _text_of(content):
    """Text blocks only. Tool calls, tool results and thinking are dropped."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n\n".join(
            block["text"] for block in content
            if isinstance(block, dict) and block.get("type") == "text"
            and isinstance(block.get("text"), str) and block["text"])
    return ""


def read_claude_code_exchanges(transcript_path):
    """Return one string per exchange from a Claude Code JSONL transcript.

    An exchange is a user message and the assistant text that follows it.
    Unreadable files and malformed lines yield nothing rather than raising.
    """
    exchanges = []
    try:
        with open(transcript_path, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(rec, dict):
                    continue
                if rec.get("isMeta") or rec.get("isSidechain"):
                    continue
                rtype = rec.get("type")
                if rtype not in ("user", "assistant"):
                    continue
                msg = rec.get("message")
                if not isinstance(msg, dict):
                    continue
                text = _REMINDER_RE.sub("", _text_of(msg.get("content"))).strip()
                if not text:
                    continue
                if rtype == "user":
                    exchanges.append([text, []])
                elif exchanges:
                    exchanges[-1][1].append(text)
                else:
                    exchanges.append(["", [text]])
    except OSError:
        return []
    out = []
    for user_text, replies in exchanges:
        parts = []
        if user_text:
            parts.append("User: " + user_text)
        if replies:
            parts.append("Assistant: " + "\n\n".join(replies))
        out.append("\n\n".join(parts))
    return out


def chunk_exchange(text, max_chars=MAX_CHUNK_CHARS):
    """Split one exchange into pieces of at most max_chars, on paragraphs."""
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]
    pieces = []
    current = ""
    for para in text.split("\n\n"):
        while len(para) > max_chars:
            if current:
                pieces.append(current)
                current = ""
            pieces.append(para[:max_chars])
            para = para[max_chars:]
        candidate = para if not current else current + "\n\n" + para
        if len(candidate) <= max_chars:
            current = candidate
        else:
            pieces.append(current)
            current = para
    if current:
        pieces.append(current)
    return pieces[:SEQ_STRIDE - 1]


# surface -> reader. Cowork sessions keep a Claude Code format transcript
# on the host (spec Appendix A), so they share the reader.
READERS = {
    "claude_code": read_claude_code_exchanges,
    "cowork": read_claude_code_exchanges,
}


# Directories a transcript may be read from. Keep in step with the roots
# auto_save._is_valid_transcript_path accepted before SH-106224; the Cowork
# root is the one addition (spec Appendix A).
ALLOWED_TRANSCRIPT_ROOTS = (
    "~/.claude",
    "~/Library/Application Support/Claude/local-agent-mode-sessions",
)


def is_allowed_transcript_path(path, extra_roots=()):
    """True when path resolves inside an allowed transcript directory."""
    if not path:
        return False
    try:
        resolved = Path(path).resolve()
    except (OSError, RuntimeError, ValueError):
        return False
    for root in tuple(ALLOWED_TRANSCRIPT_ROOTS) + tuple(extra_roots):
        try:
            resolved.relative_to(Path(os.path.expanduser(root)).resolve())
            return True
        except (ValueError, OSError, RuntimeError):
            continue
    return False


def record_source(conn, session_id, surface, external_session_id=None,
                  id_source=None, transcript_path=None):
    """Create or update the link between a session and its origin.

    A value already recorded is kept when the new call passes None.
    """
    conn.execute(
        """INSERT INTO session_sources
               (session_id, surface, external_session_id, id_source,
                transcript_path, updated_at)
           VALUES (?, ?, ?, ?, ?, strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
           ON CONFLICT(session_id, surface) DO UPDATE SET
               external_session_id = COALESCE(excluded.external_session_id,
                                              session_sources.external_session_id),
               id_source = COALESCE(excluded.id_source, session_sources.id_source),
               transcript_path = COALESCE(excluded.transcript_path,
                                          session_sources.transcript_path),
               updated_at = excluded.updated_at""",
        (session_id, surface, external_session_id, id_source, transcript_path))


def store_exchanges(conn, session_id, surface, exchanges, redact, source="hook"):
    """Store exchanges as chunks. Safe to call repeatedly for one session.

    The last exchange captured earlier is replaced, because a hook can fire
    while the assistant is still replying; newer exchanges are appended. A
    transcript shorter than what is stored changes nothing. Returns the
    number of chunks written. The source record must already exist.
    """
    row = conn.execute(
        "SELECT captured_exchange FROM session_sources "
        "WHERE session_id = ? AND surface = ?", (session_id, surface)).fetchone()
    captured = row[0] if row else -1
    last = len(exchanges) - 1
    if last < 0 or last < captured:
        return 0
    start = max(captured, 0)
    rows = []
    for idx in range(start, len(exchanges)):
        # Redact the WHOLE exchange before chunking, so a secret that spans a
        # chunk boundary is still one string when the patterns run (SH-106224-F30).
        # Fail closed: an exception or non-string return propagates before the
        # write transaction opens, so nothing is stored and captured_exchange
        # does not advance.
        clean_exchange = redact(exchanges[idx])
        if not isinstance(clean_exchange, str):
            raise TypeError("redaction returned a non-string")
        for piece_no, piece in enumerate(chunk_exchange(clean_exchange)):
            rows.append((session_id, idx * SEQ_STRIDE + piece_no, idx,
                         piece, len(piece), source))
    conn.execute("SAVEPOINT verbatim_store")
    try:
        conn.execute(
            "DELETE FROM session_chunks WHERE session_id = ? AND exchange >= ?",
            (session_id, start))
        conn.executemany(
            "INSERT INTO session_chunks "
            "(session_id, seq, exchange, text, char_count, source) "
            "VALUES (?, ?, ?, ?, ?, ?)", rows)
        conn.execute(
            "UPDATE session_sources SET captured_exchange = ?, "
            "updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') "
            "WHERE session_id = ? AND surface = ?", (last, session_id, surface))
        conn.execute("RELEASE verbatim_store")
    except Exception:
        conn.execute("ROLLBACK TO verbatim_store")
        conn.execute("RELEASE verbatim_store")
        raise
    return len(rows)


def capture_transcript(conn, session_id, transcript_path, redact, db_dir,
                       surface="claude_code", external_session_id=None,
                       id_source=None, source="hook", environ=None,
                       extra_roots=()):
    """Record a session's source and, when allowed, store its text.

    The source record is written even when capture is off: it holds no
    conversation text and is what makes a later backfill possible.
    """
    record_source(conn, session_id, surface,
                  external_session_id=external_session_id,
                  id_source=id_source, transcript_path=transcript_path)
    if not verbatim_capture_enabled(db_dir, environ=environ):
        return {"stored": 0, "reason": "disabled"}
    reader = READERS.get(surface)
    if reader is None:
        return {"stored": 0, "reason": "no_reader"}
    if not is_allowed_transcript_path(transcript_path, extra_roots=extra_roots):
        return {"stored": 0, "reason": "path_not_allowed"}
    exchanges = reader(transcript_path)
    if not exchanges:
        return {"stored": 0, "reason": "no_text"}
    stored = store_exchanges(conn, session_id, surface, exchanges, redact,
                             source=source)
    return {"stored": stored, "reason": "ok"}


def search_chunks(conn, fts_query, limit, passages_per_session=3):
    """Keyword search over stored text, grouped by session, best first.

    fts_query is an already-sanitized FTS5 MATCH expression. Each result is
    {"session_id", "rank", "passages"}; rank is the session's best BM25
    score (more negative is better) and passages are snippets around the
    match, at most passages_per_session each. Passages are trimmed to 300
    characters around the match, identical adjacent passages are
    de-duplicated, and rows are ordered by FTS rank with seq as the
    tie-break (SH-106569).
    """
    rows = conn.execute(
        """SELECT c.session_id AS session_id,
                  bm25(session_chunks_fts) AS rank,
                  c.seq AS seq,
                  snippet(session_chunks_fts, 0, '', '', ' ... ', 48) AS passage
           FROM session_chunks_fts
           JOIN session_chunks c ON c.id = session_chunks_fts.rowid
           WHERE session_chunks_fts MATCH ?
           ORDER BY rank, c.seq
           LIMIT ?""", (fts_query, max(int(limit), 1) * 10)).fetchall()
    grouped = {}
    order = []
    for row in rows:
        sid = row["session_id"]
        if sid not in grouped:
            grouped[sid] = {"session_id": sid, "rank": row["rank"], "passages": []}
            order.append(sid)
        if len(grouped[sid]["passages"]) < passages_per_session:
            passage = _trim_passage(row["passage"], 300)
            # De-duplicate adjacent identical passages (SH-106569).
            existing = grouped[sid]["passages"]
            if not existing or existing[-1] != passage:
                existing.append(passage)
    return [grouped[sid] for sid in order[:limit]]


def _trim_passage(passage, max_chars=300):
    """Trim a passage to at most max_chars, keeping the match-centered text."""
    if len(passage) <= max_chars:
        return passage
    return passage[:max_chars]


# Environment variables through which a harness exposes its own session id
# to commands the agent runs (tested 2026-11-14, spec Appendix A). First
# match wins. Codex also sets CODEX_SESSION_ID, the root conversation; the
# thread id is recorded because it names the transcript of whoever saved.
_EXTERNAL_ID_VARS = (
    ("codex", "CODEX_THREAD_ID"),
    ("cursor", "CURSOR_CONVERSATION_ID"),
    ("hermes", "HERMES_SESSION_ID"),
)


def detect_external_session(environ=None):
    """Return (surface, external_session_id, id_source) or None."""
    env = os.environ if environ is None else environ
    for surface, name in _EXTERNAL_ID_VARS:
        value = (env.get(name) or "").strip()
        if value:
            return surface, value, "env:" + name
    return None


def format_status(status):
    return [
        "Verbatim capture: %s" % ("on" if status["enabled"] else "off"),
        "Sessions with stored text: %d" % status["sessions_with_text"],
        "Chunks: %d (%d characters)" % (status["chunks"], status["chars"]),
    ]


def format_backfill(report):
    lines = [
        "Sessions: %d" % report["sessions_total"],
        "  already have text: %d" % report["already_filled"],
        "  can be filled: %d (about %d KB of text)"
        % (report["fillable"], report["estimated_chars"] // 1024),
        "  no transcript known: %d" % report["no_source"],
        "  transcript no longer on disk: %d" % report["no_transcript"],
        "  from a tool with no reader yet: %d" % report["no_reader"],
    ]
    if report["applied"]:
        lines.append("[OK] Filled %d session(s), %d chunk(s)."
                     % (report["filled"], report["chunks_written"]))
    else:
        lines.append("Dry run. Nothing was written. Re-run with --apply to store the text.")
    return lines


def delete_chunks(conn, session_id=None, project=None):
    """Delete verbatim chunks from the database via forensic purge.

    Implements SH-106224-F09 purge semantics: for every scope (session, project,
    all), deletes chunks + source rows in one BEGIN IMMEDIATE transaction, then
    FTS5 rebuild, wal_checkpoint(TRUNCATE), VACUUM, and final wal_checkpoint.

    Args:
        conn: writable database connection
        session_id: optional session ID to delete chunks for (scope='session')
        project: optional project name to delete chunks for (scope='project')

    If neither session_id nor project is provided, all chunks are deleted
    (scope='all').

    Returns:
        Number of chunks deleted
    """
    from . import storage_core

    if session_id is not None:
        return storage_core.purge_verbatim(conn, 'session', session_id)
    elif project is not None:
        return storage_core.purge_verbatim(conn, 'project', project)
    else:
        return storage_core.purge_verbatim(conn, 'all', None)
