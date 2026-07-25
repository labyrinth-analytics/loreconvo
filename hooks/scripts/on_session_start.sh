#!/bin/bash
# LoreConvo SessionStart hook - auto-loads recent session context
# Receives JSON via stdin with session_id and cwd
# Outputs context summary to stdout (Claude Code injects it into the session)
#
# Production version: stdout goes to Claude, stderr goes to log

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLUGIN_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
# Unified uvx runtime (spec 2026-07-24): same pinned env as the MCP server.
# Hooks must never break a session: if uv is missing, warn and no-op.
PIN=$(cat "$PLUGIN_ROOT/.runtime-pin" 2>/dev/null)
if [ -z "$PIN" ] || ! command -v uvx >/dev/null 2>&1; then
    echo "[$(date)] loreconvo hook skipped: uv/uvx not available or .runtime-pin missing (install uv: https://docs.astral.sh/uv/)" >> ~/.loreconvo/hook.log 2>/dev/null
    exit 0
fi
RUN_PYTHON="uvx --from loreconvo==$PIN python"

# Read stdin once, log session ID, pipe to Python loader
INPUT=$(cat)
echo "[$(date)] Session load: $(echo "$INPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('session_id','?'))" 2>/dev/null)" >> ~/.loreconvo/hook.log 2>/dev/null

# stdout from auto_load.py goes to Claude Code (injected as context)
# stderr goes to hook.log for debugging
# $RUN_PYTHON is intentionally unquoted: it must word-split into command + args
echo "$INPUT" | PYTHONPATH="$PLUGIN_ROOT/src" $RUN_PYTHON "$PLUGIN_ROOT/hooks/scripts/auto_load.py" 2>> ~/.loreconvo/hook.log

exit 0
