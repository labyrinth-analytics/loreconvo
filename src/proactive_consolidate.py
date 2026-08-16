"""Background runner for proactive session consolidation (SH-12693 r5).

Dispatched by auto_save.py SessionEnd hook when signal/message thresholds are met.
Evaluates gating conditions and performs consolidation if appropriate.

Arguments:
    --signals INT: Number of signals (decisions + open_questions) [1, 10000]
    --messages INT: Number of messages in transcript [1, 100000]
    --project STR: Project identifier
    --surface STR: Surface identifier (code/cowork/chat)

Environment Variables:
    LORECONVO_DB: Path to sessions.db (default: ~/.loreconvo/sessions.db)

Logging:
    RotatingFileHandler to ~/.loreconvo/consolidate.log (10MB, 1 backup)
    Exits 0 always (never fails parent save).
"""

import sys
import os
import argparse
import logging
import logging.handlers
from pathlib import Path

from src.core.storage_core import _open_conn
from src.core.consolidation import check_proactive_consolidation, ProactiveTrigger, HeuristicConsolidator
from src.core.database import Config


_LOG_PATH = Path.home() / ".loreconvo" / "consolidate.log"


def _setup_logging():
    """Setup rotating file logger."""
    _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("loreconvo.consolidation.proactive")
    logger.setLevel(logging.INFO)

    # Avoid duplicate handlers
    if not logger.handlers:
        handler = logging.handlers.RotatingFileHandler(
            str(_LOG_PATH), maxBytes=10*1024*1024, backupCount=1, encoding="utf-8"
        )
        formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger


def _get_db_path():
    """Get database path from environment or default."""
    db_path = os.environ.get("LORECONVO_DB")
    if not db_path:
        db_path = str(Path.home() / ".loreconvo" / "sessions.db")
    return db_path


def _parse_arguments():
    """Parse and validate command-line arguments."""
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--signals", type=int, required=True)
    parser.add_argument("--messages", type=int, required=True)
    parser.add_argument("--project", type=str, required=True)
    parser.add_argument("--surface", type=str, required=True)

    args, _ = parser.parse_known_args()

    # Validate ranges
    if not (1 <= args.signals <= 10000):
        raise ValueError(f"--signals out of range [1, 10000]: {args.signals}")
    if not (1 <= args.messages <= 100000):
        raise ValueError(f"--messages out of range [1, 100000]: {args.messages}")

    return args


def main():
    """Main execution."""
    logger = _setup_logging()

    try:
        args = _parse_arguments()
        db_path = _get_db_path()

        with _open_conn(db_path) as conn:
            # Get pro tier status
            config = Config(conn)
            is_pro = config.is_pro

            # Evaluate gates
            trigger = check_proactive_consolidation(
                project=args.project,
                surface=args.surface,
                source="session",  # SessionEnd hook source is always 'session'
                is_pro=is_pro,
                message_count=args.messages,
                signal_count=args.signals,
                db=conn
            )

            # If gates passed, perform consolidation
            if isinstance(trigger, ProactiveTrigger):
                logger.info(f"Proactive consolidation triggered: {trigger.project}/{trigger.surface} "
                           f"({trigger.signal_count} signals, {trigger.message_count} messages)")

                consolidator = HeuristicConsolidator(conn)
                consolidator.consolidate(
                    mode="heuristic",
                    trigger="proactive_signal_threshold",
                    max_sessions=25,
                    is_pro=is_pro
                )
                logger.info("Proactive consolidation completed")

    except Exception as e:
        logger.exception(f"Proactive consolidation runner error: {e}")

    # Always exit 0 - never fail the parent save operation
    sys.exit(0)


if __name__ == "__main__":
    main()
