"""User-facing retrieval health check (SH-106987, proposal SH-106081).

Read-only self-retrieval probe: pick N saved sessions deterministically,
build a 3-term query from each one's own summary, and check whether search
returns that session in the top 3 (known-item recall@3), per arm.

This is NOT an answer-quality or paraphrase-recall measurement, and its
number is not comparable to the published benchmark.

Contract: every section is {"status": ok|unavailable|partial|skipped,
"reason": <fixed code>, ...}. A field is None only with a non-ok status and a
reason. The report holds counts, a seed and hit/miss flags only: no session
text and no session ids.
"""

from __future__ import annotations

import os
import random
import re
import sqlite3
import stat
import threading
import time
from collections import Counter
from typing import Callable, Optional

from .storage_core import normalize_project_name, sanitize_fts_query, session_visibility_clause

# Fixed reason codes (the only values "reason" may take).
REASON_STORE_UNAVAILABLE = "store_unavailable"
REASON_ALREADY_RUNNING = "health check already running"
REASON_NOT_ENOUGH_DATA = "not_enough_data"
REASON_DEADLINE = "deadline_exceeded"
REASON_ARM_ERROR = "arm_error"
REASON_PRO_REQUIRED = "pro_required"
REASON_SEMANTIC_NOT_OPTED_IN = (
    "semantic model not loaded; pass include_semantic=true to load it "
    "(may take a while and use memory)"
)
REASON_SEMANTIC_INDEX_UNAVAILABLE = "semantic_index_unavailable"
REASON_FRAGMENTS_UNAVAILABLE = "lance_fragments_pending_SH-106077"
REASON_PROJECT_NOT_FOUND = "project_not_found"

DEFAULT_SAMPLE = 10
MAX_SAMPLE = 30
MIN_ELIGIBLE = 5
DEADLINE_SECONDS = 60.0
TOP_K = 3
QUERY_TERMS = 3
MIN_TOKENS = 6

# Published LongMemEval recall@5 reference: a static constant, never compared.
PUBLISHED_REFERENCE = {
    "label": "LongMemEval recall@5 (published)",
    "note": "different dataset and task; not comparable to the probe result above",
}

STOPWORDS = frozenset(
    "the and for with that this from have has had will would could should "
    "there their they them then than what when where which while into onto "
    "over under about after before been being were was are not but you your "
    "our out any all can may might must some such only same just also very "
    "more most other each every both few too nor its his her him she".split()
)
_TOKEN_RE = re.compile(r"[A-Za-z0-9_]{4,}")

_RUN_LOCK = threading.Lock()


def recall_at_k(ranked, target, k: int = TOP_K) -> float:
    """1.0 if target is in the first k of ranked else 0.0.

    Same definition as scripts/lib/retrieval_metrics.py (monorepo tooling that
    cannot be imported from the shipped package).
    """
    return 1.0 if target in list(ranked)[:k] else 0.0


def tokens_of(text: str) -> list:
    """Distinct probe tokens of a summary, in first-seen order."""
    seen, out = set(), []
    for tok in _TOKEN_RE.findall(text or ""):
        low = tok.lower()
        if low in STOPWORDS or low in seen:
            continue
        seen.add(low)
        out.append(low)
    return out


def _section(status: str, reason: Optional[str] = None, **fields) -> dict:
    out = {"status": status}
    if reason is not None:
        out["reason"] = reason
    out.update(fields)
    return out


def _unavailable(reason: str, seed, sample) -> dict:
    return {
        "status": "unavailable",
        "reason": reason,
        "seed": seed,
        "sample": sample,
        "index": _section("unavailable", reason),
        "probe": _section("unavailable", reason, arms=None),
        "reference": _section("ok", **PUBLISHED_REFERENCE),
    }


def _open_ro_conn(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=10000")
    return conn


def _index_section(db_path: str) -> dict:
    """Index health from short read-only queries."""
    try:
        conn = _open_ro_conn(db_path)
    except sqlite3.Error:
        return _section("unavailable", REASON_STORE_UNAVAILABLE)
    try:
        sessions = conn.execute("SELECT count(*) FROM sessions").fetchone()[0]
        fts_rows = conn.execute("SELECT count(*) FROM sessions_fts_docsize").fetchone()[0]
        return _section(
            "ok",
            session_count=sessions,
            fts_row_count=fts_rows,
            fts_in_sync=(sessions == fts_rows),
            lance_fragments=None,
            lance_fragments_status=_section("unavailable", REASON_FRAGMENTS_UNAVAILABLE),
        )
    except sqlite3.Error:
        return _section("unavailable", REASON_STORE_UNAVAILABLE)
    finally:
        conn.close()


def _select_probes(db_path: str, project: Optional[str], seed: int, sample: int):
    """One short read transaction, closed before any probe runs.

    Returns (probes, eligible_count, excluded_count) where probes is a list of
    (session_id, [3 query tokens]). Session ids never leave this module.
    """
    conn = _open_ro_conn(db_path)
    try:
        sql = "SELECT id, summary FROM sessions WHERE 1=1" + session_visibility_clause("")
        params: list = []
        if project:
            sql += " AND project = ?"
            params.append(project)
        sql += " ORDER BY id"
        rows = conn.execute(sql, params).fetchall()
    finally:
        conn.close()

    dupes = Counter((r["summary"] or "").strip().lower() for r in rows)
    eligible, excluded = [], 0
    for r in rows:
        toks = tokens_of(r["summary"])
        if len(toks) < MIN_TOKENS or dupes[(r["summary"] or "").strip().lower()] > 1:
            excluded += 1
            continue
        eligible.append((r["id"], toks))
    rng = random.Random(seed)
    chosen = rng.sample(eligible, min(sample, len(eligible))) if eligible else []
    probes = [(sid, rng.sample(toks, QUERY_TERMS)) for sid, toks in chosen]
    return probes, len(eligible), excluded


def run_retrieval_health(
    config,
    project: Optional[str] = None,
    sample: int = DEFAULT_SAMPLE,
    seed: Optional[int] = None,
    include_semantic: bool = False,
    deadline_seconds: float = DEADLINE_SECONDS,
    clock: Callable[[], float] = time.monotonic,
) -> dict:
    """Run the health check. Never raises for store/arm problems; never writes."""
    from .database import SessionDatabase  # local: avoid import cycle at package load

    sample = max(1, min(int(sample), MAX_SAMPLE))
    if seed is None:
        seed = random.SystemRandom().randrange(1, 2**31)
    if not _RUN_LOCK.acquire(blocking=False):
        return _unavailable(REASON_ALREADY_RUNNING, seed, sample)
    try:
        start = clock()
        db_path = str(config.db_path)
        if not os.path.exists(db_path):
            return _unavailable(REASON_STORE_UNAVAILABLE, seed, sample)
        norm_project = normalize_project_name(project) if project else None
        index = _index_section(db_path)
        if index["status"] != "ok":
            return _unavailable(REASON_STORE_UNAVAILABLE, seed, sample)
        if norm_project:
            conn = _open_ro_conn(db_path)
            try:
                known = conn.execute(
                    "SELECT 1 FROM sessions WHERE project = ? LIMIT 1", (norm_project,)
                ).fetchone()
            except sqlite3.Error:
                known = None
            finally:
                conn.close()
            if not known:
                return _unavailable(REASON_PROJECT_NOT_FOUND, seed, sample)
        try:
            probes, eligible, excluded = _select_probes(db_path, norm_project, seed, sample)
        except sqlite3.Error:
            return _unavailable(REASON_STORE_UNAVAILABLE, seed, sample)

        base = {
            "status": "ok",
            "seed": seed,
            "sample": sample,
            "project": norm_project,
            "index": index,
            "reference": _section("ok", **PUBLISHED_REFERENCE),
            "scope_note": (
                "Known-item self-retrieval on your own saved text; it does not "
                "measure answer quality or paraphrase recall. Point-in-time, best "
                "effort; comparable across runs only when the eligible count is "
                "unchanged."
            ),
        }
        if eligible < MIN_ELIGIBLE:
            base["probe"] = _section(
                "unavailable", REASON_NOT_ENOUGH_DATA, eligible=eligible,
                not_probeable=excluded, arms=None)
            return base

        arms = {"fts": False}
        arm_status = {"fts": _section("ok")}
        if include_semantic and config.is_pro:
            arms["semantic"] = True
            arm_status["semantic"] = _section("ok")
        elif not config.is_pro:
            arm_status["semantic"] = _section("skipped", REASON_PRO_REQUIRED)
        else:
            arm_status["semantic"] = _section("skipped", REASON_SEMANTIC_NOT_OPTED_IN)

        results = {name: {"completed": 0, "attempted": 0, "hits": 0, "unverifiable": 0,
                          "per_probe": []} for name in arms}
        timed_out = False
        sem_off_reason = None
        for ordinal, (sid, terms) in enumerate(probes, start=1):
            query = " ".join(terms)
            for name, semantic in arms.items():
                if sem_off_reason and name == "semantic":
                    continue
                if clock() - start > deadline_seconds:
                    timed_out = True
                    break
                res = results[name]
                res["attempted"] += 1
                try:
                    db = SessionDatabase.open_readonly(config)
                except sqlite3.Error:
                    return _unavailable(REASON_STORE_UNAVAILABLE, seed, sample)
                try:
                    if semantic and not db._get_lance_index().is_available():
                        sem_off_reason = REASON_SEMANTIC_INDEX_UNAVAILABLE
                        res["attempted"] -= 1
                        continue
                    present = db._conn.execute(
                        "SELECT count(*) FROM sessions_fts WHERE sessions_fts MATCH ?",
                        (sanitize_fts_query(query),),
                    ).fetchone()[0]
                    if present == 0:
                        res["unverifiable"] += 1
                        res["per_probe"].append({"ordinal": ordinal, "outcome": "unverifiable"})
                        continue
                    found = db.search_sessions(
                        query, semantic=semantic, limit=TOP_K, include_passages=False)
                    hit = recall_at_k([r.session.id for r in found], sid)
                    res["completed"] += 1
                    res["hits"] += int(hit)
                    res["per_probe"].append(
                        {"ordinal": ordinal, "outcome": "hit" if hit else "miss"})
                except Exception:  # an arm failing must not take down the report
                    arm_status[name] = _section("unavailable", REASON_ARM_ERROR)
                    res["attempted"] -= 1
                    arms = {k: v for k, v in arms.items() if k != name}
                    break
                finally:
                    db.release_readonly()
            if timed_out:
                break

        if sem_off_reason and "semantic" in results:
            arm_status["semantic"] = _section("unavailable", sem_off_reason)
        out_arms = {}
        for name, status in arm_status.items():
            res = results.get(name)
            if res is None or status["status"] != "ok":
                out_arms[name] = dict(status, recall_at_3=None, completed=None, attempted=None)
                continue
            denom = res["completed"]
            arm_state = "ok"
            reason = None
            if timed_out:
                arm_state, reason = "partial", REASON_DEADLINE
            out_arms[name] = _section(
                arm_state, reason,
                recall_at_3=(res["hits"] / denom) if denom else None,
                completed=denom,
                attempted=res["attempted"],
                unverifiable=res["unverifiable"],
                per_probe=res["per_probe"],
            )
            if denom == 0 and arm_state == "ok":
                out_arms[name]["status"] = "unavailable"
                out_arms[name]["reason"] = REASON_NOT_ENOUGH_DATA
        probe_state, probe_reason = ("partial", REASON_DEADLINE) if timed_out else ("ok", None)
        base["probe"] = _section(
            probe_state, probe_reason, eligible=eligible, not_probeable=excluded, arms=out_arms)
        if timed_out:
            base["status"] = "partial"
            base["reason"] = REASON_DEADLINE
        return base
    finally:
        _RUN_LOCK.release()


def append_history(path: str, report: dict, version: str) -> None:
    """Append one JSON line to a user-chosen local file (script-only, off by default).

    Refuses symlinks (the path itself or any existing parent component) and
    creates the file 0600. Raises ValueError on a refused path.
    """
    import json

    abspath = os.path.abspath(path)
    probe = abspath
    while True:
        if os.path.islink(probe):
            raise ValueError(f"refusing symlinked history path: {probe}")
        parent = os.path.dirname(probe)
        if parent == probe:
            break
        probe = parent
    flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(abspath, flags, 0o600)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise ValueError("history path is not a regular file")
        os.fchmod(fd, 0o600)
        arms = (report.get("probe") or {}).get("arms") or {}
        line = {
            "date": time.strftime("%Y-%m-%d"),
            "version": version,
            "seed": report.get("seed"),
            "n": report.get("sample"),
            "eligible": (report.get("probe") or {}).get("eligible"),
            "recall_at_3": {k: v.get("recall_at_3") for k, v in arms.items()},
        }
        os.write(fd, (json.dumps(line, sort_keys=True) + "\n").encode("ascii"))
    finally:
        os.close(fd)
