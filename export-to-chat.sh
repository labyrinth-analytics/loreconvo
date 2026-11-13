#!/bin/bash
# LoreConvo - Export last session to clipboard for pasting into Claude Chat
# Usage: bash export-to-chat.sh [search term]
#
# Examples:
#   bash export-to-chat.sh              # exports last session
#   bash export-to-chat.sh "tax prep"   # exports most relevant match

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON="$SCRIPT_DIR/.venv/bin/python3"
CLI="$SCRIPT_DIR/src/cli.py"

if [ ! -f "$PYTHON" ]; then
    echo "Error: Run install.sh first."
    exit 1
fi

if [ -n "$1" ]; then
    # Search mode: export matching session
    OUTPUT=$("$PYTHON" "$CLI" search "$1" 2>&1)
    echo "$OUTPUT"
    echo ""
    echo "---"
    echo "To export a specific session, use its ID with the CLI."
else
    # Default: export last session to clipboard
    # Capture stdout only -- stderr (e.g. the network-filesystem warning logged
    # by src/core/database.py) must reach the terminal, not the clipboard.
    OUTPUT=$("$PYTHON" "$CLI" export --last --format markdown)
    STATUS=$?

    if [ $STATUS -ne 0 ] || [ -z "$OUTPUT" ] || [ "$OUTPUT" = "No sessions found." ]; then
        echo "No sessions saved yet -- nothing to export."
        exit 1
    fi

    if command -v pbcopy &> /dev/null; then
        echo "$OUTPUT" | pbcopy
        echo "[OK] Last session copied to clipboard!"
        echo ""
        echo "Now switch to Claude Chat and paste (Cmd+V)."
        echo ""
        echo "--- Preview ---"
        echo "$OUTPUT" | head -20
        if [ $(echo "$OUTPUT" | wc -l) -gt 20 ]; then
            echo "... (truncated, full content on clipboard)"
        fi
    else
        # No pbcopy (Linux), just print
        echo "$OUTPUT"
        echo ""
        echo "Copy the above and paste into Claude Chat."
    fi
fi
