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
    """
    if external_tool:
        return False
    if source in ('periodic', 'file_memory'):
        return False
    if title and title.startswith('--- name:'):
        return False
    if summary and summary[:20].startswith('--- name:'):
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
            self._db = lancedb.connect(str(self._lance_dir))
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
    ) -> bool:
        """Add or update one session in the Lance index. Returns True on success.

        Sessions excluded by _should_index() are silently skipped (return True).
        Errors are logged but not raised (never block a session save).
        """
        if not _should_index(title, external_tool, source, summary):
            return True

        try:
            embedding = self._embed_one(f"{title} {summary or ''}")

            tags_str = tags if isinstance(tags, str) else json.dumps(tags or [])
            row = {
                'session_id': session_id,
                'project': project or '',
                'surface': surface or '',
                'session_date': _parse_date(start_date),
                'agent': _extract_agent(tags),
                'title': title or '',
                'summary': (summary or '')[:2000],
                'tags': tags_str,
                'vector': embedding,
            }

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
                # LanceDB 0.30.2 has no parameterized filter API; constrain the
                # input space to [0-9a-f-] so no SQL metacharacters can reach
                # the Arrow DataFusion engine. Revisit on every LanceDB upgrade.
                if not _UUID_RE.match(session_id):
                    _log.warning("index_session: non-UUID session_id rejected: %.64s", session_id)
                    return True
                table.delete(f"session_id = '{session_id}'")
                table.add([row])

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
                # LanceDB 0.30.2 has no parameterized filter API. Arrow DataFusion
                # follows standard SQL quoting: '' escapes a literal single-quote.
                # Revisit on every LanceDB upgrade to check for parameterized support.
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

    def rebuild(self, sessions: list, state: Optional[dict] = None) -> dict:
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

        if not valid:
            _set('phase', 'done')
            _set('done', True)
            return {
                'status': 'ok',
                'indexed': 0,
                'total_in_db': len(sessions),
                'exclusions': exclusions,
                'elapsed_s': time.time() - state['started_at'],
            }

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
        tmp_dir = Path(tempfile.mkdtemp(prefix='loreconvo_lance_tmp_'))
        try:
            import lancedb as _lancedb
            tmp_db = _lancedb.connect(str(tmp_dir))
            schema = self._make_schema()
            tmp_table = tmp_db.create_table('sessions', data, schema=schema)
            tmp_table.create_fts_index('title', replace=True)
            tmp_table.create_fts_index('summary', replace=True)
            tmp_table.create_fts_index('tags', replace=True)
            # Close to release file handles before the rename
            del tmp_table
            del tmp_db

            _set('phase', 'swapping')

            # Atomically replace the live directory
            live_dir = self._lance_dir
            if live_dir.exists():
                backup_dir = Path(str(live_dir) + '.old')
                if backup_dir.exists():
                    shutil.rmtree(backup_dir)
                shutil.move(str(live_dir), str(backup_dir))
            shutil.move(str(tmp_dir), str(live_dir))
            os.chmod(live_dir, 0o700)

            # Clean up backup
            backup_dir = Path(str(live_dir) + '.old')
            if backup_dir.exists():
                try:
                    shutil.rmtree(str(backup_dir))
                except Exception:
                    pass

            # Reset cached state so next access reconnects
            self._db = None
            self._table = None
        except Exception:
            # Clean up temp dir on failure
            try:
                if tmp_dir.exists():
                    shutil.rmtree(str(tmp_dir))
            except Exception:
                pass
            raise

        elapsed = time.time() - state['started_at']
        _set('phase', 'done')
        _set('done', True)
        _set('progress', len(valid))

        return {
            'status': 'ok',
            'indexed': len(data),
            'total_in_db': len(sessions),
            'exclusions': exclusions,
            'elapsed_s': elapsed,
        }
