"""Verbatim conversation capture for LoreConvo (SH-106224).

Stdlib only, and no imports from the loreconvo package: hooks load this
module by file path (hooks/scripts/_bootstrap.py::resolve_verbatim).
Callers pass in the redaction function. The tables are created by
storage_core.ensure_verbatim_schema; there is no DDL in this file.
"""

import json
import os
import re
import stat
from contextlib import ExitStack, contextmanager
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
# User-role records the harness writes on the user's behalf: slash-command
# echoes and their output, shell-mode input/output, background-task
# notifications and persisted tool output. They are tool output, not the
# user's words, and are never stored (SH-106804).
_MACHINE_USER_PREFIXES = (
    "<command-name>", "<command-message>", "<command-args>",
    "<local-command-stdout>", "<local-command-stderr>", "<local-command-caveat>",
    "<bash-input>", "<bash-stdout>", "<bash-stderr>",
    "<task-notification>", "<persisted-output>",
)


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


def read_claude_code_exchanges(transcript_path, extra_roots=()):
    """Return one string per exchange from a Claude Code JSONL transcript.

    An exchange is a user message and the assistant text that follows it.
    Unreadable files and malformed lines yield nothing rather than raising.
    """
    exchanges = []
    try:
        with open_authorized_transcript(transcript_path, extra_roots=extra_roots) as fh:
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
                if (rec.get("isMeta") or rec.get("isSidechain")
                        or rec.get("isCompactSummary")):
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
                if rtype == "user" and text.startswith(_MACHINE_USER_PREFIXES):
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
    limit = SEQ_STRIDE - 1
    if len(pieces) > limit:
        # Keep the seq layout intact, but say what was dropped instead of
        # losing the tail silently (SH-106804).
        kept = pieces[:limit - 1]
        dropped = len(text) - sum(len(p) for p in kept)
        kept.append("[truncated: %d characters not stored]" % dropped)
        return kept
    return pieces


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


def _transcript_target(path, extra_roots=()):
    """Resolve an allowed regular file and remember the authorized identity."""
    if not path:
        raise PermissionError("transcript path is not allowed")
    resolved = Path(path).resolve(strict=True)
    for root in tuple(ALLOWED_TRANSCRIPT_ROOTS) + tuple(extra_roots):
        try:
            root = Path(os.path.expanduser(root)).resolve(strict=True)
            resolved.relative_to(root)
        except (ValueError, OSError, RuntimeError):
            continue
        identity = resolved.stat(follow_symlinks=False)
        if stat.S_ISREG(identity.st_mode):
            return resolved, root, identity
        break
    raise PermissionError("transcript path is not an allowed regular file")


def is_allowed_transcript_path(path, extra_roots=()):
    """True for an existing regular file inside an approved transcript root.

    This predicate is only a dispatch hint. Content readers must use
    open_authorized_transcript to retain the validated identity through open.
    """
    try:
        _transcript_target(path, extra_roots)
        return True
    except (OSError, RuntimeError, ValueError):
        return False


@contextmanager
def open_authorized_transcript(path, extra_roots=(), encoding="utf-8", errors="replace"):
    """Open an authorized regular transcript read-only, without a path reopen.

    Directory descriptors anchor the walk beneath the approved root. No-follow
    opens reject replacement symlinks, and stat/fstat equality rejects replaced
    files before a text stream can read any bytes.
    """
    resolved, root, expected = _transcript_target(path, extra_roots)
    parts = resolved.relative_to(root).parts
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    with ExitStack() as stack:
        root_identity = root.stat(follow_symlinks=False)
        parent_fd = os.open(root, directory_flags)
        stack.callback(os.close, parent_fd)
        opened_root = os.fstat(parent_fd)
        if (opened_root.st_dev, opened_root.st_ino) != (root_identity.st_dev, root_identity.st_ino):
            raise PermissionError("transcript root changed")
        for part in parts[:-1]:
            parent_fd = os.open(part, directory_flags, dir_fd=parent_fd)
            stack.callback(os.close, parent_fd)
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent_fd)
        stack.callback(os.close, fd)
        opened = os.fstat(fd)
        if (not stat.S_ISREG(opened.st_mode)
                or (opened.st_dev, opened.st_ino) != (expected.st_dev, expected.st_ino)
                or Path(path).resolve(strict=True) != resolved):
            raise PermissionError("transcript identity changed")
        current = resolved.stat(follow_symlinks=False)
        if (current.st_dev, current.st_ino) != (opened.st_dev, opened.st_ino):
            raise PermissionError("transcript identity changed")
        stream = stack.enter_context(os.fdopen(
            fd, "r", encoding=encoding, errors=errors, closefd=False))
        yield stream


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
    purged = conn.execute(
        "SELECT purged_through FROM session_text_purges WHERE session_id = ?",
        (session_id,)).fetchone()
    # Exchanges the user deleted are never stored again (SH-106804).
    floor = purged[0] + 1 if purged else 0
    last = len(exchanges) - 1
    start = max(captured, floor, 0)
    if last < 0 or last < captured or last < start:
        return 0
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
    exchanges = reader(transcript_path, extra_roots=extra_roots)
    if not exchanges:
        return {"stored": 0, "reason": "no_text"}
    stored = store_exchanges(conn, session_id, surface, exchanges, redact,
                             source=source)
    return {"stored": stored, "reason": "ok"}


_SNIPPET_MATCH_START = "\x01"
_SNIPPET_MATCH_END = "\x02"


def search_chunks(conn, fts_query, limit, passages_per_session=3,
                  session_filter_sql="", session_filter_params=()):
    """Keyword search over stored text, grouped by session, best first.

    fts_query is an already-sanitized FTS5 MATCH expression. Each result is
    {"session_id", "rank", "passages"}; rank is the session's best BM25
    score (more negative is better) and passages are snippets around the
    match, at most passages_per_session each. Passages are trimmed to 300
    characters around the match, identical adjacent passages are
    de-duplicated, and rows are ordered by FTS rank with seq as the
    tie-break (SH-106569).

    session_filter_sql is an optional ' AND ...' fragment over the sessions
    table aliased s. It is applied inside the query, before the row limit,
    so filtered-out sessions cannot crowd out matching ones (SH-106804).
    """
    filter_clause = ""
    if session_filter_sql:
        filter_clause = (" AND c.session_id IN (SELECT s.id FROM sessions s "
                         "WHERE 1=1" + session_filter_sql + ")")
    rows = conn.execute(
        """SELECT c.session_id AS session_id,
                  bm25(session_chunks_fts) AS rank,
                  c.seq AS seq,
                  snippet(session_chunks_fts, 0, ?, ?, ' ... ', 48) AS passage
           FROM session_chunks_fts
           JOIN session_chunks c ON c.id = session_chunks_fts.rowid
           WHERE session_chunks_fts MATCH ?""" + filter_clause + """
           ORDER BY rank, c.seq
           LIMIT ?""", (_SNIPPET_MATCH_START, _SNIPPET_MATCH_END, fts_query,
                        *session_filter_params,
                        max(int(limit), 1) * 10)).fetchall()
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
    """Trim around the first FTS-owned match and remove its internal markers."""
    match_start = passage.find(_SNIPPET_MATCH_START)
    marker_length = len(_SNIPPET_MATCH_START)
    match_end = passage.find(_SNIPPET_MATCH_END, match_start + marker_length)
    clean = passage.replace(_SNIPPET_MATCH_START, "").replace(_SNIPPET_MATCH_END, "")
    if len(clean) <= max_chars:
        return clean
    start = 0
    if match_start >= 0 and match_end > match_start:
        # The start marker is not part of the visible matched span.
        center = (match_start + match_end - marker_length) // 2
        start = max(0, min(center - max_chars // 2, len(clean) - max_chars))
    return clean[start:start + max_chars]


# Environment variables through which a harness exposes its own session id
# to commands the agent runs (tested 2026-11-14, spec Appendix A). First
# match wins. Codex also sets CODEX_SESSION_ID, the root conversation; the
# thread id is recorded because it names the transcript of whoever saved.
_EXTERNAL_ID_VARS = (
    ("codex", "CODEX_THREAD_ID"),
    ("cursor", "CURSOR_CONVERSATION_ID"),
    ("hermes", "HERMES_SESSION_ID"),
)


# Surfaces an external session id may belong to: the ones with a transcript
# reader plus the ones whose id is read from the environment (SH-106804).
EXTERNAL_SURFACES = tuple(sorted(set(READERS) | {s for s, _ in _EXTERNAL_ID_VARS}))
MAX_EXTERNAL_ID_CHARS = 256


def detect_external_session(environ=None):
    """Return (surface, external_session_id, id_source) or None."""
    env = os.environ if environ is None else environ
    for surface, name in _EXTERNAL_ID_VARS:
        value = (env.get(name) or "").strip()
        if value:
            return surface, value, "env:" + name
    return None


# Printed after every delete, on every surface (SH-106804).
DELETE_NOTE = ("Deleted text is not stored again by later captures. "
               "Run 'verbatim backfill --apply' to restore it from a "
               "surviving transcript.")


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
