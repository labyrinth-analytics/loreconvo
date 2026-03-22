#!/bin/bash
# Run Ron - autonomous AI agent for side_hustle products
# Usage:
#   ./run_ron.sh                    # Default: 25 turns, pick highest TODO
#   ./run_ron.sh 10                 # Short session: 10 turns
#   ./run_ron.sh 15 "Build vault_suggest tool"  # Specific task, 15 turns

MAX_TURNS=${1:-25}
TASK=${2:-"Work on your highest priority TODO from CLAUDE.md. Commit when done."}

cd ~/projects/side_hustle || exit 1

echo "[$(date)] Ron session starting: max_turns=$MAX_TURNS task='$TASK'" >> ~/.convovault/ron.log

claude -p "$TASK" --max-turns "$MAX_TURNS"

echo "[$(date)] Ron session finished" >> ~/.convovault/ron.log
