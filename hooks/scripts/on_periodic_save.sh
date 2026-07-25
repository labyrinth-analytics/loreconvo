#!/bin/bash
# LoreConvo PostToolUse periodic-save hook.
# Saves a rolling snapshot every LORECONVO_CAPTURE_INTERVAL tool calls.
# Disabled by default (LORECONVO_CAPTURE_INTERVAL=0 or unset).

# Fast exit when disabled -- avoids Python startup cost on every tool call
INTERVAL="${LORECONVO_CAPTURE_INTERVAL:-0}"
if [ "$INTERVAL" -le 0 ] 2>/dev/null; then
    exit 0
fi

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
# Unified uvx runtime (spec 2026-07-24): same pinned env as the MCP server.
# Hooks must never break a session: if uv is missing, warn and no-op.
PIN=$(cat "$PLUGIN_ROOT/.runtime-pin" 2>/dev/null)
if [ -z "$PIN" ] || ! command -v uvx >/dev/null 2>&1; then
    echo "[$(date)] loreconvo hook skipped: uv/uvx not available or .runtime-pin missing (install uv: https://docs.astral.sh/uv/)" >> ~/.loreconvo/hook.log
    exit 0
fi
RUN_PYTHON="uvx --from loreconvo==$PIN python"

INPUT=$(cat)
# $RUN_PYTHON is intentionally unquoted: it must word-split into command + args
echo "$INPUT" | PYTHONPATH="$PLUGIN_ROOT/src" $RUN_PYTHON "$PLUGIN_ROOT/hooks/scripts/periodic_save.py" >> "$LOG" 2>&1

exit 0
