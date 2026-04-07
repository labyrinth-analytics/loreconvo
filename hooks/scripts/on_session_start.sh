#!/bin/bash
# LoreConvo SessionStart hook - auto-loads recent session context
# Receives JSON via stdin with session_id and cwd
# Outputs context summary to stdout (Claude Code injects it into the session)
#
# Production version: stdout goes to Claude, stderr goes to log

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLUGIN_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
PYTHON="$PLUGIN_ROOT/.venv/bin/python3"

# Fall back to system python3 if venv doesn't exist
if [ ! -f "$PYTHON" ]; then
    PYTHON="python3"
fi

# Read stdin once, log session ID, pipe to Python loader
INPUT=$(cat)
echo "[$(date)] Session load: $(echo "$INPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('session_id','?'))" 2>/dev/null)" >> ~/.loreconvo/hook.log 2>/dev/null

# stdout from auto_load.py goes to Claude Code (injected as context)
# stderr goes to hook.log for debugging
echo "$INPUT" | PYTHONPATH="$PLUGIN_ROOT/src" "$PYTHON" "$PLUGIN_ROOT/hooks/scripts/auto_load.py" 2>> ~/.loreconvo/hook.log

exit 0
