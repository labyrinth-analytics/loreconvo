#!/usr/bin/env python3
"""Backfill cooccurrence terms for sessions missing them.

This script processes all sessions in the SQLite database that lack
cooccurrence rows, re-extracting keywords from summary/decisions/project/tags
and populating the session_cooccurrences table.

Safe to run repeatedly (idempotent): existing cooccurrence rows are not
re-processed, and sessions still without cooccurrence data after processing
are logged for investigation.

Usage:
  python3 scripts/backfill_cooccurrences.py [--store PATH] [--limit N] [--report FILE]

  --store PATH: path to sessions.db (default: ~/.loreconvo/sessions.db)
  --limit N: process max N sessions (default: all)
  --report FILE: write detailed report to FILE (default: backfill_report.json)
"""

import sys
import os
import sqlite3
import json
import argparse
import logging
from datetime import datetime
from pathlib import Path

# Bootstrap: resolve storage_core for non-package callers.
sys.path.insert(0, str(Path(__file__).parent.parent / "hooks" / "scripts"))
from _bootstrap import resolve_session_core, BootstrapError

try:
    _core = resolve_session_core(Path(__file__))
    SessionDatabase = _core.SessionDatabase
    Config = _core.Config
except BootstrapError as exc:
    sys.stderr.write(f"LoreConvo bootstrap error: {exc}\n")
    sys.exit(1)
finally:
    # Remove the temporary hooks/scripts entry after bootstrap
    sys.path.pop(0)

def configure_logging():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    return logging.getLogger(__name__)

def backfill_cooccurrences(store_path, limit=None, report_path=None):
    """Backfill cooccurrences for sessions missing them.
    
    Returns dict with 'processed', 'skipped', 'failed', 'already_indexed' counts.
    """
    logger = logging.getLogger(__name__)
    
    if not os.path.exists(store_path):
        logger.error(f"Database not found: {store_path}")
        sys.exit(1)

    config = Config(db_path=store_path)
    db = SessionDatabase(config=config)
    logger.info(f"Connected to {store_path}")
    
    # Count sessions without cooccurrences
    total_without = db.conn.execute(
        "SELECT COUNT(*) FROM sessions s "
        "WHERE (SELECT COUNT(*) FROM session_cooccurrences sc WHERE sc.session_id = s.id) = 0"
    ).fetchone()[0]
    
    logger.info(f"Found {total_without} sessions without cooccurrences")
    
    # Get sessions to process
    query = """
    SELECT id, summary, decisions, project, tags
    FROM sessions s
    WHERE (SELECT COUNT(*) FROM session_cooccurrences sc WHERE sc.session_id = s.id) = 0
    ORDER BY created_at DESC
    """
    
    if limit:
        query += f" LIMIT {limit}"
    
    rows = db.conn.execute(query).fetchall()
    logger.info(f"Processing {len(rows)} sessions")
    
    stats = {
        'processed': 0,
        'skipped': 0,
        'failed': 0,
        'already_indexed': 0,
    }
    
    failed_sessions = []
    
    for idx, row in enumerate(rows):
        session_id = row[0]
        summary = row[1]
        decisions = row[2]
        project = row[3]
        tags = row[4]
        
        # Skip if it somehow got indexed between our query and now
        check = db.conn.execute(
            "SELECT COUNT(*) FROM session_cooccurrences WHERE session_id = ?",
            (session_id,)
        ).fetchone()[0]
        
        if check > 0:
            stats['already_indexed'] += 1
            if (idx + 1) % 100 == 0:
                logger.info(f"  [{idx + 1}/{len(rows)}] already_indexed={stats['already_indexed']}")
            continue
        
        try:
            db._index_session_cooccurrences(session_id, summary, decisions, project, tags)
            stats['processed'] += 1
            
            if (idx + 1) % 100 == 0:
                logger.info(f"  [{idx + 1}/{len(rows)}] processed={stats['processed']}, failed={stats['failed']}")
        except Exception as e:
            stats['failed'] += 1
            failed_sessions.append({
                'session_id': session_id,
                'error': str(e),
                'type': type(e).__name__,
            })
            logger.warning(f"Failed to index session {session_id}: {type(e).__name__}: {e}")
    
    # Commit all changes
    try:
        db.conn.commit()
        logger.info("All changes committed")
    except Exception as e:
        logger.error(f"Failed to commit: {e}")
        sys.exit(1)
    
    # Write report if requested
    if report_path:
        report = {
            'timestamp': datetime.now().isoformat(),
            'store': store_path,
            'stats': stats,
            'failed_sessions': failed_sessions,
        }
        
        with open(report_path, 'w') as f:
            json.dump(report, f, indent=2)
        logger.info(f"Report written to {report_path}")
    
    logger.info(f"Backfill complete: {stats}")
    return stats

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--store',
        default=os.path.expanduser('~/.loreconvo/sessions.db'),
        help='Path to sessions.db'
    )
    parser.add_argument(
        '--limit',
        type=int,
        default=None,
        help='Max sessions to process'
    )
    parser.add_argument(
        '--report',
        default='backfill_report.json',
        help='Report output file'
    )
    
    args = parser.parse_args()
    configure_logging()
    
    backfill_cooccurrences(args.store, limit=args.limit, report_path=args.report)

if __name__ == "__main__":
    main()
