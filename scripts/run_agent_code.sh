#!/bin/bash
# run_agent_code.sh -- wrapper for scheduled Claude Code (local) agents
#
# Usage: run_agent_code.sh <agent-name>
#
# Reads the agent's SKILL.md from:
#   ~/Documents/Claude/Scheduled/<agent-name>/SKILL.md
# and runs it as a non-interactive claude -p session rooted at
#   /Users/debbieshapiro/projects/side_hustle
#
# Logs to: /Users/debbieshapiro/projects/side_hustle/logs/<agent>_YYYYMMDD_HHMMSS.log
# Logs older than 14 days are purged automatically.

set -uo pipefail

AGENT="${1:-}"
if [ -z "$AGENT" ]; then
    echo "Usage: $0 <agent-name>" >&2
    exit 1
fi

SKILL_FILE="/Users/debbieshapiro/Documents/Claude/Scheduled/$AGENT/SKILL.md"
PROJECT_DIR="/Users/debbieshapiro/projects/side_hustle"
LOG_DIR="$PROJECT_DIR/logs"
CLAUDE_BIN="/Users/debbieshapiro/.local/bin/claude"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_FILE="$LOG_DIR/${AGENT}_${TIMESTAMP}.log"

# Create log directory if it doesn't exist (safe in cron)
mkdir -p "$LOG_DIR"

# Cron strips most environment variables -- rebuild the essentials
export HOME="/Users/debbieshapiro"
export PATH="/Users/debbieshapiro/.local/bin:/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"
export LANG="en_US.UTF-8"

# Source nvm/pyenv/conda shims if present so python/pip resolve correctly
[ -f "$HOME/.nvm/nvm.sh" ] && source "$HOME/.nvm/nvm.sh" --no-use 2>/dev/null || true
[ -f "$HOME/.profile" ] && source "$HOME/.profile" 2>/dev/null || true

# Purge logs older than 14 days to avoid unbounded disk growth
find "$LOG_DIR" -name "${AGENT}_*.log" -mtime +14 -delete 2>/dev/null || true

# Validate prerequisites
if [ ! -f "$SKILL_FILE" ]; then
    echo "$(date): ERROR -- SKILL.md not found: $SKILL_FILE" >> "$LOG_FILE"
    exit 1
fi

if [ ! -f "$CLAUDE_BIN" ]; then
    echo "$(date): ERROR -- claude binary not found: $CLAUDE_BIN" >> "$LOG_FILE"
    exit 1
fi

# Log session header
{
    echo "================================================================"
    echo "Agent:  $AGENT"
    echo "Start:  $(date)"
    echo "SKILL:  $SKILL_FILE"
    echo "CWD:    $PROJECT_DIR"
    echo "================================================================"
} >> "$LOG_FILE"

# Diagnostic: log environment so failures are traceable
{
    echo "DIAG: PATH=$PATH"
    echo "DIAG: HOME=$HOME"
    echo "DIAG: CLAUDE_BIN=$CLAUDE_BIN"
    echo "DIAG: claude version: $("$CLAUDE_BIN" --version 2>&1 || echo '[version check failed]')"
} >> "$LOG_FILE"

echo "DIAG: [step] cd to project dir" >> "$LOG_FILE"
cd "$PROJECT_DIR"
echo "DIAG: [step] cd OK -- pwd=$(pwd)" >> "$LOG_FILE"

# macOS does not ship GNU timeout; Homebrew coreutils provides gtimeout.
# Detect whichever is available; run without time limit if neither is found.
TIMEOUT_CMD=""
if command -v timeout &>/dev/null; then
    TIMEOUT_CMD="timeout"
elif command -v gtimeout &>/dev/null; then
    TIMEOUT_CMD="gtimeout"
else
    echo "DIAG: WARNING -- timeout/gtimeout not found, running without time limit (brew install coreutils to fix)" >> "$LOG_FILE"
fi
echo "DIAG: TIMEOUT_CMD=${TIMEOUT_CMD:-[none -- running without limit]}" >> "$LOG_FILE"

echo "DIAG: [step] launching claude" >> "$LOG_FILE"
if [ -n "$TIMEOUT_CMD" ]; then
    "$TIMEOUT_CMD" 3600 "$CLAUDE_BIN" \
        --print \
        --permission-mode bypassPermissions \
        --output-format text \
        < "$SKILL_FILE" \
        >> "$LOG_FILE" 2>&1
else
    "$CLAUDE_BIN" \
        --print \
        --permission-mode bypassPermissions \
        --output-format text \
        < "$SKILL_FILE" \
        >> "$LOG_FILE" 2>&1
fi

EXIT_CODE=$?
if [ $EXIT_CODE -eq 124 ]; then
    echo "TIMEOUT: agent exceeded time limit" >> "$LOG_FILE"
fi

{
    echo "================================================================"
    echo "End:    $(date)"
    echo "Exit:   $EXIT_CODE"
    echo "================================================================"
} >> "$LOG_FILE"

exit $EXIT_CODE
