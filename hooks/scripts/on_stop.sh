#!/bin/bash
# LoreConvo Stop hook auto-capture.
# Saves session state when the user halts execution mid-session.
# Provides feature parity with claude-mem auto-capture.

LOG="$HOME/.loreconvo/hook.log"
mkdir -p "$(dirname "$LOG")"

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

INPUT=$(cat)
# $RUN_PYTHON is intentionally unquoted: it must word-split into command + args
echo "$INPUT" | PYTHONPATH="$PLUGIN_ROOT/src" $RUN_PYTHON "$PLUGIN_ROOT/hooks/scripts/stop_save.py" >> "$LOG" 2>&1

exit 0
