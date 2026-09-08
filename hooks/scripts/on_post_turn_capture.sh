#!/bin/bash
# LoreConvo opt-in PostToolUse capture hook.

# Fast exit before runtime startup or filesystem access when disabled.
if [ "${LORECONVO_POST_TURN_CAPTURE:-0}" != "1" ]; then
    exit 0
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLUGIN_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
PIN=$(cat "$PLUGIN_ROOT/.runtime-pin" 2>/dev/null)
if [ -z "$PIN" ] || ! command -v uvx >/dev/null 2>&1; then
    LOG="$HOME/.loreconvo/hook.log"
    mkdir -p "$(dirname "$LOG")"
    echo "[$(date)] loreconvo hook skipped: uv/uvx not available or .runtime-pin missing (install uv: https://docs.astral.sh/uv/)" >> "$LOG"
    exit 0
fi

LOG="$HOME/.loreconvo/hook.log"
mkdir -p "$(dirname "$LOG")"
RUN_PYTHON="uvx --from loreconvo==$PIN python"
INPUT=$(cat)
# $RUN_PYTHON is intentionally unquoted: it must word-split into command + args.
printf '%s' "$INPUT" | PYTHONPATH="$PLUGIN_ROOT/src" $RUN_PYTHON \
    "$PLUGIN_ROOT/hooks/scripts/post_turn_capture.py" >> "$LOG" 2>&1

exit 0
