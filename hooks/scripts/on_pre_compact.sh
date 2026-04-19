#!/bin/bash
# LoreConvo PreCompact hook - saves session transcript before context compaction
# Receives JSON via stdin with session_id, transcript_path, and trigger
# Fires before both manual (/compact) and auto (context limit) compaction

LOG="$HOME/.loreconvo/hook.log"
mkdir -p "$(dirname "$LOG")"

# Log rotation -- keep log under 1 MB (rotate up to 3 copies)
MAX_LOG_BYTES=1048576
if [ -f "$LOG" ] && [ "$(wc -c < "$LOG")" -gt "$MAX_LOG_BYTES" ]; then
    [ -f "${LOG}.2" ] && mv "${LOG}.2" "${LOG}.3"
    [ -f "${LOG}.1" ] && mv "${LOG}.1" "${LOG}.2"
    mv "$LOG" "${LOG}.1"
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLUGIN_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
PYTHON="$PLUGIN_ROOT/.venv/bin/python3"

# Fall back to system python3 if venv doesn't exist
if [ ! -f "$PYTHON" ]; then
    PYTHON="python3"
fi

# Read stdin once, log session ID and trigger
INPUT=$(cat)
SESSION_ID=$(echo "$INPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('session_id','?'))" 2>/dev/null || echo "unknown")
TRIGGER=$(echo "$INPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('trigger','auto'))" 2>/dev/null || echo "auto")
echo "[$(date)] pre-compact ($TRIGGER): $SESSION_ID" >> "$LOG" 2>/dev/null

echo "$INPUT" | PYTHONPATH="$PLUGIN_ROOT/src" "$PYTHON" "$PLUGIN_ROOT/hooks/scripts/pre_compact_save.py" >> "$LOG" 2>&1
EXIT_CODE=$?

if [ "$EXIT_CODE" -ne 0 ]; then
    echo "[$(date)] pre-compact save failed (exit $EXIT_CODE)" >> "$LOG"
fi

exit $EXIT_CODE
