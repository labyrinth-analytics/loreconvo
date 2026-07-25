#!/bin/bash
# LoreConvo SessionEnd hook - auto-saves session transcript to vault
# Receives JSON via stdin with session_id and transcript_path
#
# Production version: slim logging, errors visible in hook.log

LOG="$HOME/.loreconvo/hook.log"
mkdir -p "$(dirname "$LOG")"

# OPP-008: Log rotation -- keep log under 1 MB (rotate up to 3 copies)
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

# Read stdin -- OPP-008: log only session_id (no raw content or PII)
INPUT=$(cat)
SESSION_ID=$(echo "$INPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('session_id','?'))" 2>/dev/null || echo "unknown")
echo "[$(date)] session_id: $SESSION_ID" >> "$LOG" 2>/dev/null

# $RUN_PYTHON is intentionally unquoted: it must word-split into command + args
echo "$INPUT" | PYTHONPATH="$PLUGIN_ROOT/src" $RUN_PYTHON "$PLUGIN_ROOT/hooks/scripts/auto_save.py" >> "$LOG" 2>&1
EXIT_CODE=$?

# OPP-011: Propagate Python exit code so callers can detect failures
if [ "$EXIT_CODE" -ne 0 ]; then
    echo "[$(date)] status: failed (exit $EXIT_CODE)" >> "$LOG"
fi

exit $EXIT_CODE
