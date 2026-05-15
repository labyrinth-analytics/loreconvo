"""LanceDB hybrid search for LoreConvo Pro.

Provides LanceIndex: manages sessions.lance/ embedding index alongside sessions.db.
All lancedb, sentence-transformers, and pyarrow imports are lazy -- free-tier users
who have not installed Pro deps will never trigger them.

ADR: docs/agent-reports/architecture/proposals/lancedb_hybrid_search_evaluation_20260511.md
Stage: 2A (LoreConvo). Stage 2B (LoreDocs) deferred until 2A ships.
"""
import datetime
import json
import logging
import os
import re
from pathlib import Path
from typing import List, Optional

_UUID_RE = re.compile(
    r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',
    re.IGNORECASE,
)

SEARCH_HALF_LIFE_DAYS = 90     # user-triggered search_sessions default
AUTOLOAD_HALF_LIFE_DAYS = 30   # auto-load hook default

_log = logging.getLogger(__name__)


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
) -> bool:
    """Return False for sessions that must be excluded from the Lance index.

    Filters:
    - external_tool_session=True (imported Anthropic sessions, etc.)
    - source in ('periodic', 'file_memory')
    - title starts with '--- name:' (SKILL.md content stored as sessions)
    """
    if external_tool:
        return False
    if source in ('periodic', 'file_memory'):
        return False
    if title and title.startswith('--- name:'):
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
    today = datetime.datetime.utcnow()
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
            from sentence_transformers import SentenceTransformer  # noqa: deferred Pro dep
            self._model = SentenceTransformer('BAAI/bge-small-en-v1.5')
        return self._model

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
        try:
            table = self._open_table()
            return table is not None and table.count_rows() > 0
        except Exception:
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
    ) -> bool:
        """Add or update one session in the Lance index. Returns True on success.

        Sessions excluded by _should_index() are silently skipped (return True).
        Errors are logged but not raised (never block a session save).
        """
        if not _should_index(title, external_tool, source):
            return True

        try:
            embedding = self._get_model().encode(
                f"{title} {summary or ''}"
            ).tolist()

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
            q_vec = self._get_model().encode(query).tolist()

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

    def rebuild(self, sessions: list) -> int:
        """Rebuild the Lance index from a list of session dicts.

        Each dict must have: id, title, summary (nullable), project, surface,
        start_date, tags (JSON string or list), external_tool_session (int), source.

        Drops and recreates the table. Returns count of indexed sessions.
        Raises on fatal errors (caller should handle).
        """
        valid = [
            s for s in sessions
            if s.get('id')
            and s.get('title')
            and _should_index(
                s.get('title'),
                bool(s.get('external_tool_session')),
                s.get('source'),
            )
            and s.get('summary') is not None
        ]

        if not valid:
            return 0

        model = self._get_model()
        texts = [f"{s['title']} {s.get('summary', '')}" for s in valid]
        embeddings = model.encode(texts, show_progress_bar=False, batch_size=64)

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
                'vector': embeddings[i].tolist(),
            })

        db = self._get_db()
        try:
            db.drop_table('sessions')
        except Exception:
            pass
        self._table = None

        schema = self._make_schema()
        self._table = db.create_table('sessions', data, schema=schema)
        self._table.create_fts_index('title', replace=True)
        self._table.create_fts_index('summary', replace=True)
        self._table.create_fts_index('tags', replace=True)
        os.chmod(self._lance_dir, 0o700)
        return len(data)
