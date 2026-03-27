#!/bin/bash
# LoreConvo SessionEnd hook - auto-saves session transcript to vault
# Receives JSON via stdin with session_id and transcript_path
#
# Production version: slim logging, errors visible in hook.log

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLUGIN_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
PYTHON="$PLUGIN_ROOT/.venv/bin/python3"

# Fall back to system python3 if venv doesn't exist
if [ ! -f "$PYTHON" ]; then
    PYTHON="python3"
fi

# Read stdin, log session ID, pipe to Python parser
INPUT=$(cat)
echo "[$(date)] Session save: $(echo "$INPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('session_id','?'))" 2>/dev/null)" >> ~/.loreconvo/hook.log 2>/dev/null

echo "$INPUT" | PYTHONPATH="$PLUGIN_ROOT/src" "$PYTHON" "$PLUGIN_ROOT/hooks/scripts/auto_save.py" >> ~/.loreconvo/hook.log 2>&1

exit 0
