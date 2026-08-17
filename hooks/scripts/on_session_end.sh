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

# SH-100629: timestamp before launch so the breadcrumb fallback can tell
# whether the hook's own handler already wrote a fresher one.
SINCE_EPOCH=$(date +%s)
# $RUN_PYTHON is intentionally unquoted: it must word-split into command + args
echo "$INPUT" | PYTHONPATH="$PLUGIN_ROOT/src" $RUN_PYTHON "$PLUGIN_ROOT/hooks/scripts/auto_save.py" >> "$LOG" 2>&1
EXIT_CODE=$?

# SH-13440: Log failure but exit 0 unconditionally.
# Hooks must never break a customer session. The uvx invocation is
# network-capable (first-run package download, PyPI reachability, etc.),
# and a hook failure must not surface as a session error to the user.
if [ "$EXIT_CODE" -ne 0 ]; then
    echo "[$(date)] status: failed (exit $EXIT_CODE)" >> "$LOG"
    # SH-100629: a failure this early could be a module-scope import error
    # that died before auto_save.py's own BootstrapError handler ever ran --
    # fall back to a generic breadcrumb via plain python3 (no package import
    # needed). No-ops if a richer breadcrumb was already written this run.
    python3 "$PLUGIN_ROOT/hooks/scripts/_write_generic_failure_breadcrumb.py" \
        "auto_save" "$EXIT_CODE" "$SINCE_EPOCH" >> "$LOG" 2>&1
fi

exit 0
