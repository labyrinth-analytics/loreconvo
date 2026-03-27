#!/bin/bash
# LoreConvo - Auto-install dependencies on session start
# Uses CLAUDE_PLUGIN_DATA for persistent storage across sessions

PLUGIN_DATA="${CLAUDE_PLUGIN_DATA:-$HOME/.loreconvo}"
MARKER="$PLUGIN_DATA/.deps-installed"
REQUIREMENTS="${CLAUDE_PLUGIN_ROOT}/requirements.txt"

# Create data directory if needed
mkdir -p "$PLUGIN_DATA"

# Only install if requirements have changed or never installed
if [ ! -f "$MARKER" ] || ! diff -q "$REQUIREMENTS" "$PLUGIN_DATA/requirements.txt" >/dev/null 2>&1; then
    echo "LoreConvo: Installing dependencies..."
    pip3 install -q -r "$REQUIREMENTS" --break-system-packages 2>/dev/null || pip3 install -q -r "$REQUIREMENTS" 2>/dev/null
    if [ $? -eq 0 ]; then
        cp "$REQUIREMENTS" "$PLUGIN_DATA/requirements.txt"
        touch "$MARKER"
        echo "LoreConvo: Dependencies installed successfully."
    else
        echo "LoreConvo: Warning - could not install dependencies. Run: pip install mcp click"
    fi
fi
