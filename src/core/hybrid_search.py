"""LanceDB hybrid search for LoreConvo Pro.

Provides LanceIndex: manages sessions.lance/ embedding index alongside sessions.db.
lancedb, fastembed, and pyarrow are BASE dependencies since 2026-07-25 (spec
amendment A1) -- there is no separate Pro install. Their imports stay lazy so a
free-tier user never loads them or downloads the embedding model: the semantic
path is gated on the Pro license in SessionDatabase.search_sessions, not on
whether the packages are present.

ADR: docs/agent-reports/architecture/proposals/lancedb_hybrid_search_evaluation_20260511.md
Stage: 2A (LoreConvo). Stage 2B (LoreDocs) deferred until 2A ships.
"""
import datetime
import json
import logging
import os
import re
import shutil
import tempfile
import threading
import time
from contextlib import nullcontext
from pathlib import Path
from typing import Dict, List, Optional

_UUID_RE = re.compile(
    r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',
    re.IGNORECASE,
)

SEARCH_HALF_LIFE_DAYS = 90     # user-triggered search_sessions default
AUTOLOAD_HALF_LIFE_DAYS = 30   # auto-load hook default

# Batch size for embedding during rebuild. Larger batches amortize the ONNX
# inference overhead. 256 was measured as a good throughput/memory trade-off
# for the BGE-small-en-v1.5 model (384-dim, ~130MB) on M-series Apple Silicon;
# above 512 the memory pressure from the intermediate Arrow array starts to
# outweigh the batching benefit on large stores. This is a tunable, not a
# hard limit -- the ONNX runtime handles any batch size that fits in memory.
REBUILD_BATCH_SIZE = 256

_log = logging.getLogger(__name__)

_INDEX_SOURCE_FIELDS = (
    'id', 'title', 'summary', 'project', 'surface', 'start_date', 'tags',
    'external_tool_session', 'source',
)


def _index_source_snapshot(row):
    """Freeze the authoritative inputs to indexing, before slow embedding."""
    values = []
    for name in _INDEX_SOURCE_FIELDS:
        value = row.get(name)
        if name == 'tags':
            if isinstance(value, str):
                from .database import SessionDatabase
                value = SessionDatabase._parse_json_field(value)
            value = json.dumps(value or [])
        elif name == 'external_tool_session':
            value = bool(value)
        values.append(value)
    return tuple(values)

# SH-104068: one embedding model per process, shared by every caller.
# Building a fresh fastembed/ONNX session per LanceIndex (one per
# SessionDatabase) leaks native memory that the allocator never returns --
# the Python heap stays flat while RSS grows ~70 MB per instance; the test
# suite reached 15-31 GB. The model is stateless for inference, so sharing
# it is safe.
_shared_models: Dict[str, object] = {}
_shared_models_lock = threading.Lock()


def get_shared_embedding_model(name: str = 'BAAI/bge-small-en-v1.5'):
    """Return the process-wide fastembed TextEmbedding for `name`."""
    with _shared_models_lock:
        model = _shared_models.get(name)
        if model is None:
            from fastembed import TextEmbedding  # ONNX runtime, no torch (spec A1)
            _log.info(
                "Loading embedding model %s; the first run downloads it "
                "(~90MB) and may take a minute.", name
            )
            model = TextEmbedding(name)
            _shared_models[name] = model
        return model


def _parse_date(d: Optional[str]) -> datetime.datetime:
    """Parse an ISO 8601 date string to a naive UTC datetime."""
    if not d:
        return datetime.datetime(2000, 1, 1)
    try:
        return datetime.datetime.fromisoformat(d.replace('Z', '+00:00')).replace(tzinfo=None)
    except Exception:
        return datetime.datetime(2000, 1, 1)


def _extract_agent(tags) -> str:
    """Extract the agent:<name> tag value from a tags list or JSON string."""
    if not tags:
        return ''
    if isinstance(tags, str):
        try:
            tags = json.loads(tags)
        except Exception:
            return ''
    for t in tags:
        if isinstance(t, str) and t.startswith('agent:'):
            return t[6:]
    return ''


def _should_index(
    title: Optional[str],
    external_tool: bool = False,
    source: Optional[str] = None,
    summary: Optional[str] = None,
) -> bool:
    """Return False for sessions that must be excluded from the Lance index.

    Filters:
    - external_tool_session=True (imported Anthropic sessions, etc.)
    - source in ('periodic', 'file_memory')
    - title starts with '--- name:' (SKILL.md content stored as sessions)
    - summary starts with '--- name:' within first 20 chars (bypass detection)
    - summary is None (missing_summary: must be excluded for consistency with rebuild())
    """
    if external_tool:
        return False
    if source in ('periodic', 'file_memory'):
        return False
    if title and title.startswith('--- name:'):
        return False
    if summary and summary[:20].startswith('--- name:'):
        return False
    if summary is None:
        return False
    return True


def _rrf_merge(vec_results: list, fts_results: list, k: int = 60, limit: int = 10) -> list:
    """Reciprocal Rank Fusion of vector and FTS result lists."""
    scores: dict = {}
    id_to_row: dict = {}
    for rank, r in enumerate(vec_results):
        sid = r.get('session_id', '')
        scores[sid] = scores.get(sid, 0.0) + 1.0 / (k + rank + 1)
        id_to_row[sid] = r
    for rank, r in enumerate(fts_results):
        sid = r.get('session_id', '')
        scores[sid] = scores.get(sid, 0.0) + 1.0 / (k + rank + 1)
        id_to_row[sid] = r
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return [id_to_row[sid] for sid, _ in ranked[:limit]]


def _recency_rerank(results: list, half_life_days: int, limit: int) -> list:
    """Re-score RRF results by exponential recency decay and re-sort."""
    today = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
    scored = []
    for rank, r in enumerate(results):
        date = r.get('session_date')
        if hasattr(date, 'as_py'):
            date = date.as_py()
        if isinstance(date, datetime.datetime):
            days_old = max(0, (today - date.replace(tzinfo=None)).days)
        else:
            days_old = 365
        base_score = 1.0 / (60 + rank + 1)
        decay = 0.5 ** (days_old / half_life_days)
        scored.append((base_score * decay, r))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [r for _, r in scored[:limit]]


def _classify_exclusion(s: dict) -> str:
    """Return the reason a session is excluded from the Lance index.

    Returns the FIRST matching reason found. Callers must verify the
    session IS excluded before calling this function -- an includable
    session returns nothing.
    """
    if not s.get('id'):
        return 'missing_id'
    if not s.get('title'):
        return 'missing_title'
    if s.get('summary') is None:
        return 'missing_summary'
    if bool(s.get('external_tool_session')):
        return 'external_tool_session'
    src = s.get('source')
    if src == 'periodic':
        return 'source_periodic'
    if src == 'file_memory':
        return 'source_file_memory'
    title = s.get('title') or ''
    if title.startswith('--- name:'):
        return 'skill_title'
    summary = s.get('summary') or ''
    if summary[:20].startswith('--- name:'):
        return 'skill_summary'
    return 'unknown'


class LanceIndex:
    """Manages the sessions.lance/ LanceDB index for LoreConvo Pro hybrid search.

    Dual-write pattern: SQLite is the system of record; this index is derived.
    If the index is lost or corrupted, call rebuild() to regenerate from SQLite.

    File layout:
        ~/.loreconvo/sessions.db       -- SQLite (always present, all tiers)
        ~/.loreconvo/sessions.lance/   -- LanceDB (Pro only, chmod 700)
    """

    def __init__(self, lance_dir: Path):
        self._lance_dir = lance_dir
        self._model = None
        self._db = None
        self._table = None
        self._write_count = 0

    # ---- lazy accessors ----

    def _get_model(self):
        if self._model is None:
            self._model = get_shared_embedding_model('BAAI/bge-small-en-v1.5')
        return self._model

    def _embed_one(self, text):
        """Embed a single string -> list[float] of dim 384."""
        return next(iter(self._get_model().embed([text]))).tolist()

    def _embed_many(self, texts, batch_size=64):
        """Embed many strings -> list of list[float], one per input, dim 384."""
        return [v.tolist() for v in self._get_model().embed(texts, batch_size=batch_size)]

    def _get_db(self):
        if self._db is None:
            import lancedb  # noqa: deferred Pro dep
            self._lance_dir.mkdir(parents=True, exist_ok=True)
            os.chmod(self._lance_dir, 0o700)
            # timedelta(0): re-check the latest table version on every read, so a
            # long-lived handle (the MCP server) survives another process
            # compacting with cleanup_older_than=0, which deletes the data files
            # an already-open version points at.
            self._db = lancedb.connect(
                str(self._lance_dir), read_consistency_interval=datetime.timedelta(0)
            )
        return self._db

    def _open_table(self):
        """Try to open the sessions table; return None if it does not exist."""
        if self._table is None:
            try:
                self._table = self._get_db().open_table('sessions')
            except Exception:
                self._table = None
        return self._table

    @staticmethod
    def _make_schema():
        import pyarrow as pa  # noqa: deferred Pro dep
        return pa.schema([
            pa.field('session_id', pa.string()),
            pa.field('project', pa.string()),
            pa.field('surface', pa.string()),
            pa.field('session_date', pa.timestamp('us')),
            pa.field('agent', pa.string()),
            pa.field('title', pa.string()),
            pa.field('summary', pa.string()),
            pa.field('tags', pa.string()),
            pa.field('vector', pa.list_(pa.float32(), 384)),
        ])

    # ---- public API ----

    def is_available(self) -> bool:
        """Return True if the index exists and has at least one row."""
        return self.row_count() > 0

    def row_count(self) -> int:
        """Return the number of rows in the Lance index, or 0 if unavailable."""
        try:
            table = self._open_table()
            if table is None:
                return 0
            return table.count_rows()
        except Exception:
            return 0

    def compact_if_needed(self, threshold: int = 100) -> bool:
        """Compact the LanceDB table if write count meets threshold.

        Returns True if compaction ran, False otherwise.
        Never raises; errors are logged but do not block operations.
        """
        if self._write_count < threshold:
            return False

        table = self._open_table()
        if table is None:
            return False

        try:
            # cleanup_older_than=0 prunes superseded fragments/versions immediately
            # instead of the 7-day default. Safe here because this Lance table is
            # a derived index (SQLite is the system of record and can rebuild it),
            # so there is no time-travel/rollback value in keeping old versions --
            # and without this, disk usage grows with write count rather than row
            # count (SH-106101 benchmark: 25974 -> 142618 bytes/session, 1k->15k).
            result = table.optimize(cleanup_older_than=datetime.timedelta(0))

            # Try to extract fragment metrics from result
            old_fragments = None
            new_fragments = None
            if hasattr(result, 'fragments'):
                old_fragments = result.fragments.get('before', None)
                new_fragments = result.fragments.get('after', None)

            # Log results
            if old_fragments is not None and new_fragments is not None:
                _log.info(
                    'Lance table optimized: %d fragments -> %d fragments',
                    old_fragments,
                    new_fragments,
                )
            else:
                _log.info('Lance table optimized')

            self._write_count = 0
            return True
        except Exception as exc:
            _log.warning('Lance compact_if_needed failed: %s', exc)
            return False

    def index_session(
        self,
        session_id: str,
        title: str,
        summary: Optional[str],
        project: Optional[str],
        surface: Optional[str],
        start_date: Optional[str],
        tags,
        external_tool: bool = False,
        source: Optional[str] = None,
        *,
        _publication_context=None,
    ) -> bool:
        """Add or update one session in the Lance index. Returns True on success.

        Sessions excluded by _should_index() are silently skipped (return True).
        Errors are logged but not raised (never block a session save).
        """
        if not _should_index(title, external_tool, source, summary):
            return True

        try:
            tags_str = tags if isinstance(tags, str) else json.dumps(tags or [])
            snapshot = _index_source_snapshot({
                'id': session_id, 'title': title, 'summary': summary,
                'project': project, 'surface': surface, 'start_date': start_date,
                'tags': tags_str, 'external_tool_session': external_tool, 'source': source,
            })
            embedding = self._embed_one(f"{title} {summary or ''}")

            row = {
                'session_id': session_id,
                'project': project or '',
                'surface': surface or '',
                'session_date': _parse_date(start_date),
                'agent': _extract_agent(tags_str),
                'title': title or '',
                'summary': (summary or '')[:2000],
                'tags': tags_str,
                'vector': embedding,
            }

            context = (_publication_context([session_id])
                       if _publication_context else nullcontext(None))
            with context as current:
                if current is not None:
                    if current.get(session_id) != snapshot:
                        return True
                    # Another instance may have replaced the live directory.
                    self._db = None
                    self._table = None
                table = self._open_table()
                if table is None:
                    self._table = self._get_db().create_table(
                        'sessions', [row], schema=self._make_schema()
                    )
                    self._table.create_fts_index('title', replace=True)
                    self._table.create_fts_index('summary', replace=True)
                    self._table.create_fts_index('tags', replace=True)
                else:
                    # Validate UUID format to prevent SQL injection via session_id.
                    # LanceDB 0.34.0 has parameterized filter API via Expr, but UUID
                    # validation provides defense-in-depth. Current approach: constrain
                    # input space to [0-9a-f-] so no SQL metacharacters can reach
                    # the Arrow DataFusion engine. Revisit on every LanceDB upgrade.
                    if not _UUID_RE.match(session_id):
                        _log.warning("index_session: non-UUID session_id rejected: %.64s", session_id)
                        return True
                    self._delete_session_rows(table, [session_id])
                    table.add([row])
                    self._write_count += 1
                    self.compact_if_needed()
            return True
        except Exception as exc:
            _log.error("Lance index_session failed for %s: %s", session_id, exc)
            return False

    def search(
        self,
        query: str,
        project: Optional[str] = None,
        limit: int = 10,
        half_life_days: int = SEARCH_HALF_LIFE_DAYS,
    ) -> List[str]:
        """Hybrid search (vector + BM25 FTS + RRF + recency rerank).

        Returns session_ids in relevance order (best first).
        Returns empty list if index is unavailable or search fails.
        """
        table = self._open_table()
        if table is None:
            return []

        try:
            q_vec = self._embed_one(query)

            where_clause: Optional[str] = None
            if project:
                # LanceDB 0.34.0 has parameterized filter API via Expr, but current
                # approach uses Arrow DataFusion SQL quoting: '' escapes a literal
                # single-quote. Defense-in-depth is adequate; parameterization optional.
                # Revisit on every LanceDB upgrade to check for improvements.
                safe_proj = project.replace("'", "''")
                where_clause = f"project = '{safe_proj}'"

            vec_q = table.search(q_vec, vector_column_name='vector', query_type='vector')
            if where_clause:
                vec_q = vec_q.where(where_clause)
            vec_results = vec_q.limit(20).to_list()

            fts_results: list = []
            try:
                fts_q = table.search(query, query_type='fts')
                if where_clause:
                    fts_q = fts_q.where(where_clause)
                fts_results = fts_q.limit(20).to_list()
            except Exception:
                pass  # FTS index may not exist on very new tables

            merged = _rrf_merge(vec_results, fts_results, k=60, limit=limit * 2)
            reranked = _recency_rerank(merged, half_life_days=half_life_days, limit=limit)
            return [r['session_id'] for r in reranked]
        except Exception as exc:
            _log.error("Lance search failed: %s", exc)
            return []

    def get_vectors_by_session_ids(self, session_ids, project=None,
                                   surface=None):
        """Fetch vectors for a list of session IDs from the Lance index.

        Returns {session_id: vector_list} for sessions that exist and
        match the optional project/surface scope filter. Returns {} if
        the index is unavailable, the table does not exist, or no
        matching rows are found. Never raises.

        The project/surface filter is enforced by the Lance query, so an
        out-of-scope session ID returns no vector -- the caller's
        "no vector, never collapsed" rule makes it unreachable for
        comparison (SH-12694 r3 security binding).
        """
        table = self._open_table()
        if table is None:
            return {}

        try:
            # Build filter clause. session_ids are UUIDs validated at
            # index time, so they are safe for the DataFusion filter.
            # However, we constrain to the UUID regex here as well to
            # guard against any non-UUID input.
            safe_ids = [sid for sid in session_ids if sid and _UUID_RE.match(sid)]
            if not safe_ids:
                return {}

            # Build the WHERE clause: (session_id IN ('a','b',...))
            # AND project = '...' AND surface = '...'
            quoted = ",".join(f"'{sid}'" for sid in safe_ids)
            clauses = [f"session_id IN ({quoted})"]
            if project is not None:
                safe_proj = project.replace("'", "''")
                clauses.append(f"project = '{safe_proj}'")
            if surface is not None:
                safe_surf = surface.replace("'", "''")
                clauses.append(f"surface = '{safe_surf}'")
            where_clause = " AND ".join(clauses)

            results = table.search().where(where_clause).to_list()
            return {
                r["session_id"]: r["vector"]
                for r in results
                if "vector" in r and "session_id" in r
            }
        except Exception as exc:
            _log.error("get_vectors_by_session_ids failed: %s", exc)
            return {}

    @staticmethod
    def _delete_session_rows(table, session_ids):
        """Delete validated UUIDs; the caller owns errors and publication."""
        safe_ids = [sid for sid in session_ids if sid and _UUID_RE.match(sid)]
        if safe_ids:
            quoted = ",".join(f"'{sid}'" for sid in safe_ids)
            table.delete(f"session_id IN ({quoted})")

    def delete_sessions(self, session_ids) -> bool:
        """Delete one or more sessions from the Lance index by session_id.

        Batches all ids into a single Lance delete call. No-op (returns True)
        when the table does not exist or no ids are given. Errors are logged
        but never raised -- callers must not let a Lance failure block or
        roll back the SQLite delete it accompanies.
        """
        if not session_ids:
            return True
        table = self._open_table()
        if table is None:
            return True
        try:
            self._delete_session_rows(table, session_ids)
            return True
        except Exception as exc:
            _log.error("Lance delete_sessions failed for %d id(s): %s", len(session_ids), exc)
            return False

    def rebuild(self, sessions: list, state: Optional[dict] = None, *,
                _publication_context=None) -> dict:
        """Rebuild the Lance index from a list of session dicts.

        Each dict must have: id, title, summary (nullable), project, surface,
        start_date, tags (JSON string or list), external_tool_session (int), source.

        Builds the new index in a temporary directory, then swaps it in
        atomically at the filesystem level.  If the process is killed mid-build
        the previous index stays intact (the temp dir is orphaned, not the live
        dir).

        If *state* is provided it is a mutable dict keyed on 'lock' (optional
        threading.Lock), 'progress' (int), 'total' (int), 'phase' (str),
        'started_at' (float), 'done' (bool), and 'error' (str or None).  The
        caller may read this dict from another thread to observe progress.

        Returns a dict with:
          status: 'ok' | 'error'
          indexed: count of sessions inserted
          total_in_db: total sessions passed in
          exclusions: {reason: count} dict
          elapsed_s: wall-clock seconds
        """
        if state is None:
            state = {}
        lock = state.get('lock')
        state.setdefault('progress', 0)
        state.setdefault('total', len(sessions))
        state.setdefault('phase', 'classifying')
        state.setdefault('started_at', time.time())
        state.setdefault('done', False)
        state.setdefault('error', None)

        # ----- classify every session -----
        exclusions: Dict[str, int] = {}
        valid: list = []
        for s in sessions:
            sid = s.get('id')
            title = s.get('title')
            summary = s.get('summary')
            ext_tool = bool(s.get('external_tool_session'))
            src = s.get('source')

            if not sid or not title or summary is None or not _should_index(title, ext_tool, src, summary):
                reason = _classify_exclusion(s)
                exclusions[reason] = exclusions.get(reason, 0) + 1
            else:
                valid.append(s)

        def _set(k, v):
            state[k] = v
            if k == 'progress' and state.get('total'):
                state['progress_pct'] = int(100 * state['progress'] / state['total'])
            if lock:
                with lock:
                    pass  # memory barrier

        _set('phase', 'embedding')
        _set('exclusions', exclusions)
        _set('valid_count', len(valid))

        snapshots = {s['id']: _index_source_snapshot(s) for s in valid}

        texts = [f"{s['title']} {s.get('summary', '')}" for s in valid]
        _set('total', len(valid))
        _set('progress', 0)

        # Embed in batches, updating progress after each batch
        batch_size = REBUILD_BATCH_SIZE
        all_embeddings = []
        for batch_start in range(0, len(texts), batch_size):
            batch = texts[batch_start:batch_start + batch_size]
            all_embeddings.extend(self._embed_many(batch, batch_size=batch_size))
            _set('progress', min(batch_start + batch_size, len(texts)))

        _set('phase', 'building_table')

        data = []
        for i, s in enumerate(valid):
            tags_raw = s.get('tags') or ''
            data.append({
                'session_id': s['id'],
                'project': s.get('project') or '',
                'surface': s.get('surface') or '',
                'session_date': _parse_date(s.get('start_date')),
                'agent': _extract_agent(tags_raw),
                'title': s['title'],
                'summary': (s.get('summary') or '')[:2000],
                'tags': tags_raw if isinstance(tags_raw, str) else json.dumps(tags_raw),
                'vector': all_embeddings[i],
            })

        # Build in a temp directory, then atomically swap
        self._lance_dir.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        tmp_dir = Path(tempfile.mkdtemp(
            prefix='loreconvo_lance_tmp_', dir=self._lance_dir.parent
        ))
        backup_dir = tmp_dir.with_name(tmp_dir.name + '.old')
        promoted = False
        indexed = len(data)
        try:
            import lancedb as _lancedb
            tmp_db = _lancedb.connect(str(tmp_dir))
            schema = self._make_schema()
            tmp_table = tmp_db.create_table('sessions', data or None, schema=schema)
            tmp_table.create_fts_index('title', replace=True)
            tmp_table.create_fts_index('summary', replace=True)
            tmp_table.create_fts_index('tags', replace=True)
            context = (_publication_context(list(snapshots))
                       if _publication_context else nullcontext(None))
            with context as current:
                if current is not None:
                    rejected = []
                    for sid, captured in snapshots.items():
                        if current.get(sid) != captured:
                            reason = ('deleted_during_rebuild' if sid not in current
                                      else 'changed_during_rebuild')
                            exclusions[reason] = exclusions.get(reason, 0) + 1
                            rejected.append(sid)
                    self._delete_session_rows(tmp_table, rejected)
                    indexed = len(data) - len(rejected)
                if tmp_table.count_rows() != indexed:
                    raise RuntimeError('Rebuild candidate row count mismatch')
                # Release candidate handles before exact same-filesystem renames.
                del tmp_table
                del tmp_db
                _set('phase', 'swapping')
                live_dir = self._lance_dir
                retired = False
                try:
                    if live_dir.exists():
                        os.rename(live_dir, backup_dir)
                        retired = True
                    # Unlike shutil.move, this cannot nest staging inside live.
                    os.replace(tmp_dir, live_dir)
                    promoted = True
                    os.chmod(live_dir, 0o700)
                except Exception:
                    if retired:
                        try:
                            # Replaces only an absent/empty destination; never
                            # removes unexpected nonempty reader-created data.
                            os.replace(backup_dir, live_dir)
                        except OSError:
                            pass
                    raise
                self._db = None
                self._table = None
        finally:
            # Each publication owns its unique staging/retired paths. Recursive
            # cleanup is outside primary writer exclusion.
            for owned in (tmp_dir, backup_dir if promoted else None):
                if owned is not None and owned.exists():
                    try:
                        shutil.rmtree(owned)
                    except OSError:
                        pass

        elapsed = time.time() - state['started_at']
        _set('phase', 'done')
        _set('done', True)
        _set('progress', len(valid))

        return {
            'status': 'ok',
            'indexed': indexed,
            'total_in_db': len(sessions),
            'exclusions': exclusions,
            'elapsed_s': elapsed,
        }
