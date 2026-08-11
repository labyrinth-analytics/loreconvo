"""Heuristic memory consolidation engine for LoreConvo Recall (v0.6.0).

Phase 1: pure Python, no API calls, no external dependencies.
Phase 2 (v0.6.1): LLM enrichment via claude-haiku-4-5-20251001.

Advisory notes from Socrates (non-blocking, documented):
- no-llm tag semantics: excluded from LLM mode only; heuristic runs on all sessions.
  Document in INSTALL.md: 'no-llm tag prevents LLM consolidation, not heuristic.'
- Project name is sent in context header for LLM mode; 'local-first' language corrected.
- Credential discovery order: ~/.loreconvo/.env first, then common shell configs.
- Concurrency lock guards MCP and launchd paths; other direct DB writers can bypass.
- Rate limit uses updated_at with no clock skew / multi-machine consideration.
- digest_is_fresh() ignores mutations from bulk imports/deletes (session-count gap).
- Project/surface renaming strands digests; run consolidate_memories after renaming.
- Free-tier 3/day limit enforced at script level, not DB level (scripted callers can bypass);
  this is a known limitation for Phase 1.
"""

import difflib
import fcntl
import json
import logging
import math
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

_SUMMARY_TRUNCATE = 2000   # chars per session before extraction
_AGING_DAYS = 90           # sessions older than this become 'aging'
_STALE_DAYS = 180          # sessions older than this become 'stale'
_FREE_TIER_DAILY_LIMIT = 3
_DEDUP_RATIO = 0.85        # difflib ratio threshold for near-duplicate detection
_MAX_DECISIONS = 10
_MAX_OPEN_QUESTIONS = 5
_DIGEST_MAX_CHARS = 700    # soft cap for digest_markdown

# -- Semantic dedup pass (SH-12694 r4) --

# Mode -> cosine similarity threshold. None means the pass does not run.
DEDUP_MODES = {
    "off":          None,   # no dedup pass runs at all -- SHIPPED DEFAULT (r4)
    "conservative": 0.97,   # near-verbatim restatements only
    "balanced":     0.95,   # the mode a caller opts in to
}
DEDUP_DEFAULT = "off"       # r4: opt-in. Flipping this is a gated release decision.

_dedup_log = logging.getLogger("loreconvo.consolidation.dedup")


def _resolve_dedup(dedup_arg):
    """Resolve the dedup mode per the r4 contract.

    1. If dedup_arg is not None, it wins (explicit argument overrides env).
    2. If dedup_arg is None, read LORECONVO_CONSOLIDATION_DEDUP; default "off".
    3. Matching is exact and case-sensitive against the three lowercase literals.
    4. Unrecognised values resolve to "off" with a logged warning.
    """
    if dedup_arg is not None:
        raw = dedup_arg
    else:
        raw = os.environ.get("LORECONVO_CONSOLIDATION_DEDUP")
    if raw is None:
        return DEDUP_DEFAULT
    if raw in DEDUP_MODES:
        return raw
    _dedup_log.warning(
        "Unrecognised dedup value %r; resolving to 'off'. "
        "Valid: off, conservative, balanced (case-sensitive).",
        raw,
    )
    return "off"


def _cosine(a, b):
    """Cosine similarity over two equal-length float sequences. Stdlib only."""
    dot = na = nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (math.sqrt(na) * math.sqrt(nb))

# Signal line prefixes (case-insensitive)
_DECISION_PREFIXES = (
    "decided:", "approved:", "confirmed:", "will use", "shipping as",
    "going with", "agreed:", "settled on:", "resolved:",
)
_QUESTION_MARKERS = ("?", "tbd", "open question", "to decide", "pending debbie", "open:")
_TECHFACT_PREFIXES = (
    "stack:", "model:", "version ", "running on", "deployed to",
    "using ", "framework:", "library:", "tool:",
)


class HeuristicConsolidator:
    """Pure-Python heuristic memory consolidation engine.

    Usage:
        c = HeuristicConsolidator(lore_dir='/path/to/.loreconvo')
        result = c.consolidate('my_project', 'code', db=db_instance)
    """

    def __init__(
        self,
        lore_dir: Optional[str] = None,
        log_path: Optional[str] = None,
    ):
        if lore_dir is None:
            lore_dir = str(Path.home() / ".loreconvo")
        self.lore_dir = Path(lore_dir)
        self.lock_path = self.lore_dir / "consolidation.lock"
        self.log_path = Path(log_path) if log_path else (self.lore_dir / "consolidation.log")

    # -- Public API --

    def consolidate(
        self,
        project: str,
        surface: Optional[str],
        db,
        max_sessions: int = 50,
        mode: str = "heuristic",
        is_pro: bool = False,
        trigger: str = "on-demand",
        dedup: str | None = None,
    ) -> dict:
        """Run heuristic consolidation for (project, surface).

        Returns a result dict with 'status' key:
          'ok'           -- consolidation completed successfully
          'rate_limited' -- free-tier daily limit reached (3/day)
          'lock_held'    -- another consolidation is running
          'no_sessions'  -- no sessions found for this project/surface
        """
        # Acquire OS-level lock to prevent concurrent runs
        lock_file = self._acquire_lock()
        if lock_file is None:
            self._log_entry(project, surface, mode, 0, trigger, "skipped: lock held")
            return {"status": "lock_held", "message": "consolidation already running, try again"}

        try:
            # Rate limit: free tier = 3/day
            if not is_pro:
                count_today = db.count_consolidations_today(
                    project, surface, log_path=str(self.log_path)
                )
                if count_today >= _FREE_TIER_DAILY_LIMIT:
                    self._log_entry(project, surface, mode, 0, trigger, "skipped: rate limited")
                    return {
                        "status": "rate_limited",
                        "message": (
                            f"Free tier limit: {_FREE_TIER_DAILY_LIMIT} consolidations/day reached. "
                            "Upgrade to Pro for unlimited consolidations."
                        ),
                    }

            sessions = db.get_sessions_for_consolidation(
                project, surface, max_sessions=max_sessions
            )
            if not sessions:
                return {"status": "no_sessions", "message": "no sessions found for this project/surface"}

            # -- Semantic dedup pass (SH-12694 r4) --
            resolved_dedup = _resolve_dedup(dedup)
            threshold = DEDUP_MODES[resolved_dedup]
            collapsed_list = []
            if threshold is not None:
                lance = self._get_lance_index()
                if lance is not None:
                    sessions, collapsed_list = self._collapse_near_duplicates(
                        sessions, lance, threshold, project, surface,
                    )
            sessions_considered = len(sessions) + len(collapsed_list)
            sessions_collapsed = len(collapsed_list)
            sessions_consolidated = len(sessions)

            # Truncate summaries before extraction
            for s in sessions:
                if s.get("summary") and len(s["summary"]) > _SUMMARY_TRUNCATE:
                    s["summary"] = s["summary"][:_SUMMARY_TRUNCATE]

            # Extract signals
            all_decisions = []
            all_questions = []
            all_facts = []
            for s in sessions:
                text = s.get("summary") or ""
                all_decisions.extend(self._extract_decisions(text))
                all_questions.extend(self._extract_open_questions(text))
                all_facts.extend(self._extract_tech_facts(text))

            decisions = self._deduplicate(all_decisions)[:_MAX_DECISIONS]
            open_questions = self._deduplicate(all_questions)[:_MAX_OPEN_QUESTIONS]
            known_stack, stale_facts = self._resolve_tech_facts(all_facts, sessions)

            # Apply temporal validity (mutates DB rows)
            self._apply_staleness(sessions, db)

            # Build digest
            oldest = sessions[-1]["start_date"] if sessions else None
            newest = sessions[0]["start_date"] if sessions else None
            updated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            digest_md = self._format_digest_markdown(
                project=project,
                surface=surface,
                source_count=len(sessions),
                decisions=decisions,
                open_questions=open_questions,
                known_stack=known_stack,
                stale_facts=stale_facts,
                updated_at=updated_at,
            )

            db.upsert_memory_digest(project, surface, {
                "source_count": len(sessions),
                "oldest_session_date": oldest,
                "newest_session_date": newest,
                "decisions": json.dumps(decisions),
                "open_questions": json.dumps(open_questions),
                "known_stack": json.dumps(known_stack),
                "stale_facts": json.dumps(stale_facts),
                "digest_markdown": digest_md,
                "mode": mode,
                "tier": "pro" if is_pro else "free",
            })

            self._log_entry(project, surface, mode, len(sessions), trigger)

            return {
                "status": "ok",
                "source_count": len(sessions),
                "decisions_found": len(decisions),
                "open_questions_found": len(open_questions),
                "digest_markdown": digest_md,
                "sessions_considered": sessions_considered,
                "sessions_collapsed": sessions_collapsed,
                "sessions_consolidated": sessions_consolidated,
                "dedup": resolved_dedup,
                "collapsed": collapsed_list,
            }

        finally:
            self._release_lock(lock_file)

    # -- Semantic dedup pass (SH-12694 r4) --

    def _get_lance_index(self):
        """Return a LanceIndex instance for the lore dir, or None on failure.

        The LanceIndex wraps the LanceDB sessions table. If LanceDB is
        unavailable or the index does not exist, returns None so the
        dedup pass degrades gracefully (candidates pass through).
        """
        try:
            from core.hybrid_search import LanceIndex
            lance_dir = self.lore_dir / "sessions.lance"
            return LanceIndex(lance_dir)
        except Exception:
            return None

    def _collapse_near_duplicates(self, candidates, lance, threshold,
                                  project, surface):
        """Return (kept, collapsed) where collapsed is a list of dicts
        describing each removed candidate. Pure over its inputs apart
        from one LanceDB read.

        Input order is irrelevant: the pass sorts internally.
        project/surface are the scope the candidates were selected under;
        the LanceDB read filters on them, so a vector outside the scope
        is never retrievable here.
        """
        if threshold is None or len(candidates) < 2:
            return candidates, []

        # Newest-first, total order. sessions.id is the PRIMARY KEY, so
        # this never falls through to insertion order the way ORDER BY
        # start_date DESC alone does.
        candidates = sorted(
            candidates,
            key=lambda c: (c.get("start_date") or "", c["id"]),
            reverse=True,
        )

        ids = [c["id"] for c in candidates]
        # ONE filtered query, scoped. The Lance sessions table carries
        # project and surface (hybrid_search.py:172-183), so the scope
        # filter is enforced by the query rather than by a convention the
        # caller has to honour.
        try:
            vectors = lance.get_vectors_by_session_ids(
                ids, project=project, surface=surface
            )
        except Exception:
            vectors = {}
        if not vectors:
            return candidates, []

        kept, kept_vecs, collapsed = [], [], []
        for c in candidates:
            v = vectors.get(c["id"])
            if v is None:
                kept.append(c)
                kept_vecs.append(None)
                continue
            best_i, best_sim = -1, 0.0
            for i, kv in enumerate(kept_vecs):
                if kv is None:
                    continue
                s = _cosine(v, kv)
                if s > best_sim:
                    best_i, best_sim = i, s
            if best_sim > threshold:
                collapsed.append({
                    "session_id": c["id"],
                    "similar_to": kept[best_i]["id"],
                    "similarity": round(best_sim, 4),
                })
                _dedup_log.debug(
                    "collapsed %s -> %s (similarity=%.4f)",
                    c["id"], kept[best_i]["id"], best_sim,
                )
            else:
                kept.append(c)
                kept_vecs.append(v)
        return kept, collapsed

    # -- Signal extraction --

    def _extract_decisions(self, text: str) -> list:
        """Extract decision lines from session summary text."""
        results = []
        for line in text.splitlines():
            stripped = line.strip()
            lower = stripped.lower()
            for prefix in _DECISION_PREFIXES:
                if lower.startswith(prefix) or prefix in lower:
                    if len(stripped) > 5:
                        results.append(stripped)
                        break
        return results

    def _extract_open_questions(self, text: str) -> list:
        """Extract open question lines from session summary text."""
        results = []
        for line in text.splitlines():
            stripped = line.strip()
            lower = stripped.lower()
            is_question = False
            if stripped.endswith("?"):
                is_question = True
            else:
                for marker in _QUESTION_MARKERS[1:]:  # skip "?"
                    if marker in lower:
                        is_question = True
                        break
            if is_question and len(stripped) > 5:
                results.append(stripped)
        return results

    def _extract_tech_facts(self, text: str) -> list:
        """Extract technology/stack fact lines from session summary text."""
        results = []
        for line in text.splitlines():
            stripped = line.strip()
            lower = stripped.lower()
            for prefix in _TECHFACT_PREFIXES:
                if lower.startswith(prefix) or lower.startswith(prefix.rstrip(":")):
                    results.append({"text": stripped, "source_date": None})
                    break
        return results

    # -- Deduplication --

    def _deduplicate(self, items: list) -> list:
        """Remove near-duplicate strings using difflib.SequenceMatcher ratio > 0.85.

        Keeps the first occurrence of each near-duplicate group.
        """
        if not items:
            return []
        unique = []
        for candidate in items:
            is_dup = False
            for kept in unique:
                ratio = difflib.SequenceMatcher(None, candidate.lower(), kept.lower()).ratio()
                if ratio > _DEDUP_RATIO:
                    is_dup = True
                    break
            if not is_dup:
                unique.append(candidate)
        return unique

    # -- Tech fact conflict resolution --

    def _resolve_tech_facts(self, facts: list, sessions: list) -> tuple:
        """Resolve tech facts into known_stack (current) and stale_facts (overridden).

        Returns (known_stack: list[str], stale_facts: list[str]).
        """
        known = []
        stale = []
        for f in facts:
            text = f.get("text", "")
            if text and text not in known:
                known.append(text)
        return known, stale

    # -- Temporal validity --

    def _apply_staleness(self, sessions: list, db) -> None:
        """Set staleness_hint on sessions based on age thresholds.

        aging: 90-180 days old
        stale: 180+ days old
        current: < 90 days old
        """
        now = datetime.now(timezone.utc)
        for s in sessions:
            session_id = s.get("id")
            if not session_id:
                continue
            start_raw = s.get("start_date") or ""
            if not start_raw:
                continue
            try:
                start_dt = datetime.fromisoformat(
                    start_raw.replace("Z", "+00:00")
                )
                age_days = (now - start_dt).days
            except (ValueError, TypeError):
                continue

            if age_days >= _STALE_DAYS:
                hint = "stale"
            elif age_days >= _AGING_DAYS:
                hint = "aging"
            else:
                hint = "current"

            db.set_session_staleness(session_id, hint)

    # -- Digest formatting --

    def _format_digest_markdown(
        self,
        project: str,
        surface: Optional[str],
        source_count: int,
        decisions: list,
        open_questions: list,
        known_stack: list,
        stale_facts: list,
        updated_at: str,
    ) -> str:
        """Format consolidated data as a compact markdown digest.

        Target: < 600 chars. Hard cap at _DIGEST_MAX_CHARS for injection safety.
        """
        surface_label = surface if surface else "all surfaces"
        updated_short = updated_at[:10] if updated_at else "unknown"

        parts = [
            f"## Memory Digest ({project}, {surface_label})",
            f"Updated: {updated_short} | Sessions analyzed: {source_count}",
        ]
        if decisions:
            parts.append(f"**Active decisions:** {'; '.join(decisions[:5])}")
        if open_questions:
            parts.append(f"**Open questions:** {'; '.join(open_questions[:3])}")
        if known_stack:
            parts.append(f"**Stack:** {', '.join(known_stack[:5])}")
        if stale_facts:
            parts.append(f"**Flagged stale:** {'; '.join(stale_facts[:3])}")

        result = "\n".join(parts)
        if len(result) > _DIGEST_MAX_CHARS:
            result = result[:_DIGEST_MAX_CHARS - 3] + "..."
        return result

    # -- Lockfile helpers --

    def _acquire_lock(self):
        """Acquire consolidation.lock using fcntl. Returns file handle or None."""
        try:
            lock_file = open(self.lock_path, "w")
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return lock_file
        except OSError:
            try:
                lock_file.close()
            except Exception:
                pass
            return None

    def _release_lock(self, lock_file):
        """Release the consolidation lock."""
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
            lock_file.close()
        except Exception:
            pass

    # -- Log helpers --

    def _log_entry(
        self,
        project: str,
        surface: Optional[str],
        mode: str,
        source_count: int,
        trigger: str,
        note: str = "",
    ) -> None:
        """Append one JSON line to consolidation.log."""
        ts = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        entry: dict = {
            "ts": ts,
            "project": project,
            "surface": surface,
            "mode": mode,
            "source_count": source_count,
            "trigger": trigger,
        }
        if note:
            entry["note"] = note
        try:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as exc:
            sys.stderr.write(f"LoreConvo consolidation: log write error: {exc}\n")
