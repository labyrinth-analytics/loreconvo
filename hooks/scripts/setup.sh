#!/bin/bash
# LoreConvo - one-time uv prerequisite check (spec 2026-07-24).
# The MCP server and hooks run via uvx; nothing is pip-installed anymore.

PLUGIN_DATA="${CLAUDE_PLUGIN_DATA:-$HOME/.loreconvo}"
MARKER="$PLUGIN_DATA/.uv-check-shown"
mkdir -p "$PLUGIN_DATA"

if ! command -v uv >/dev/null 2>&1 && [ ! -f "$MARKER" ]; then
    echo "LoreConvo: 'uv' is required but not installed. Install it with:"
    echo "  curl -LsSf https://astral.sh/uv/install.sh | sh"
    echo "then restart Claude Code. (This message shows once.)"
    touch "$MARKER"
fi
exit 0
