#!/usr/bin/env python3
"""
Known-item recall probe for semantic vs FTS search.

Selects 10 deterministic probes, runs both FTS and semantic search,
records if target is in top 3. Output: CSV with per-probe results + summary.
"""

import os
import sys
import sqlite3
import csv
import random
from typing import List, Tuple, Optional

# Ensure loreconvo is importable via PYTHONPATH shim or installed
try:
    from loreconvo.core.database import SessionDatabase
except ImportError:
    # Try adding the source path
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    sys.path.insert(0, os.path.join(repo_root, 'src'))
    from core.database import SessionDatabase


STOPWORDS = {
    'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
    'of', 'with', 'by', 'is', 'are', 'was', 'were', 'be', 'been', 'have',
    'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could', 'should',
    'may', 'might', 'must', 'can', 'this', 'that', 'these', 'those', 'i',
    'you', 'he', 'she', 'it', 'we', 'they', 'me', 'him', 'her', 'us', 'them',
    'which', 'what', 'when', 'where', 'why', 'how', 'all', 'each', 'every',
    'both', 'few', 'more', 'most', 'other', 'some', 'such', 'no', 'nor', 'not',
    'only', 'same', 'so', 'than', 'too', 'very', 'just', 'as'
}


def get_probe_sessions(db: SessionDatabase, count: int = 10) -> List[Tuple[str, str]]:
    """
    Select deterministic probe sessions.
    Returns: list of (session_id, title) tuples.
    """
    # Get all non-canary sessions with summary >= 200 chars
    conn = db.conn
    rows = conn.execute(
        "SELECT id, title FROM sessions WHERE length(summary) >= 200 ORDER BY id"
    ).fetchall()

    # Deterministic sample
    rng = random.Random(20261008)
    selected = rng.sample(rows, min(count, len(rows)))
    return [(r[0], r[1]) for r in selected]


def get_doc_frequency(db: SessionDatabase, query: str) -> int:
    """Get document frequency of a query term in FTS5 index."""
    try:
        conn = db.conn
        # For a simple query, count how many FTS5 rows match
        rows = conn.execute(
            "SELECT count(*) FROM sessions_fts WHERE sessions_fts MATCH ?",
            (query,)
        ).fetchone()
        return rows[0] if rows else 0
    except Exception:
        return 9999  # High value so we skip bad queries


def extract_query(db: SessionDatabase, session_id: str) -> Optional[str]:
    """
    Extract 3 consecutive non-stopword tokens (len >= 5) with lowest corpus frequency.
    Returns: the query string, or None if extraction fails.
    """
    try:
        conn = db.conn
        row = conn.execute(
            "SELECT title, summary FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
        if not row:
            return None

        title = row[0] or ""
        summary = row[1] or ""
        text = (title + " " + summary).lower()

        # Tokenize
        words = []
        for word in text.split():
            # Remove punctuation
            word = word.strip('.,!?";:()[]{}')
            if word and len(word) >= 5 and word not in STOPWORDS:
                words.append(word)

        if len(words) < 3:
            return None

        # Generate all 3-word sequences and score by doc frequency
        candidates = []
        for i in range(len(words) - 2):
            trigram = f"{words[i]} {words[i+1]} {words[i+2]}"
            freq = get_doc_frequency(db, trigram)
            candidates.append((trigram, freq))

        # Return the lowest-frequency trigram
        if candidates:
            candidates.sort(key=lambda x: x[1])
            return candidates[0][0]

        return None
    except Exception:
        return None


def main():
    """Main execution."""
    db_path = os.path.expanduser("~/.loreconvo/sessions.db")
    if not os.path.exists(db_path):
        print(f"Error: Database not found at {db_path}", file=sys.stderr)
        return 1

    try:
        db = SessionDatabase(db_path)

        # Get probes
        probes = get_probe_sessions(db)
        if not probes:
            print("Error: No probe sessions found", file=sys.stderr)
            return 1

        # Run probes
        fts_hits = 0
        semantic_hits = 0
        writer = csv.writer(sys.stdout)
        writer.writerow([
            'session_id', 'title', 'query', 'fts_rank', 'semantic_rank', 'fts_hit', 'semantic_hit'
        ])

        for session_id, title in probes:
            query = extract_query(db, session_id)
            if not query:
                continue

            # FTS search
            fts_results = db.search_sessions(query, semantic=False, limit=3)
            fts_hit = any(r.session.id == session_id for r in fts_results)
            fts_rank = None
            if fts_hit:
                for rank, r in enumerate(fts_results, 1):
                    if r.session.id == session_id:
                        fts_rank = rank
                        break

            # Semantic search
            semantic_results = db.search_sessions(query, semantic=True, limit=3)
            semantic_hit = any(r.session.id == session_id for r in semantic_results)
            semantic_rank = None
            if semantic_hit:
                for rank, r in enumerate(semantic_results, 1):
                    if r.session.id == session_id:
                        semantic_rank = rank
                        break

            # Write row
            writer.writerow([
                session_id, title, query,
                fts_rank or '', semantic_rank or '',
                fts_hit, semantic_hit
            ])

            if fts_hit:
                fts_hits += 1
            if semantic_hit:
                semantic_hits += 1

        # Write summary as a separate line
        print(f"\nFTS: {fts_hits}/{len(probes)}, Semantic: {semantic_hits}/{len(probes)}")
        return 0

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
