#!/bin/bash
# LoreConvo Stop hook auto-capture.
# Saves session state when the user halts execution mid-session.
# Provides feature parity with claude-mem auto-capture.

LOG="$HOME/.loreconvo/hook.log"
mkdir -p "$(dirname "$LOG")"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLUGIN_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
PYTHON="$PLUGIN_ROOT/.venv/bin/python3"

if [ ! -f "$PYTHON" ]; then
    PYTHON="python3"
fi

INPUT=$(cat)
echo "$INPUT" | PYTHONPATH="$PLUGIN_ROOT/src" "$PYTHON" "$PLUGIN_ROOT/hooks/scripts/stop_save.py" >> "$LOG" 2>&1

exit 0
