#!/bin/bash
# LoreConvo - One-command installation
# Usage: bash install.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"

echo "============================================"
echo "  LoreConvo Installer"
echo "  Vault your Claude conversations."
echo "============================================"
echo ""

# Check Python 3
if ! command -v python3 &> /dev/null; then
    echo "[ERROR] Python 3 is required but not found."
    echo "Install it via: brew install python3"
    exit 1
fi

PYTHON_VERSION=$(python3 --version 2>&1)
echo "[OK] Found $PYTHON_VERSION"

# Create virtual environment
if [ -d "$VENV_DIR" ]; then
    echo "[OK] Virtual environment already exists at .venv/"
else
    echo "[..] Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
    echo "[OK] Virtual environment created at .venv/"
fi

# Install dependencies
echo "[..] Installing dependencies..."
"$VENV_DIR/bin/pip3" install -q -r "$SCRIPT_DIR/requirements.txt"
echo "[OK] Dependencies installed (mcp, click)"

# Create database directory
mkdir -p "$HOME/.loreconvo"
echo "[OK] Database directory ready at ~/.loreconvo/"

# Verify server starts
echo "[..] Testing MCP server..."
"$VENV_DIR/bin/python3" -c "
import sys
sys.path.insert(0, '$SCRIPT_DIR/src')
from core.database import SessionDatabase
from core.config import Config
db = SessionDatabase(Config())
print(f'[OK] Database initialized at {Config().db_path}')
print(f'[OK] {db.session_count()} sessions in vault')
"

echo ""
echo "============================================"
echo "  Installation complete!"
echo "============================================"
echo ""
echo "  To use with Claude Code:"
echo "    claude --plugin-dir $SCRIPT_DIR"
echo ""
echo "  To use the CLI:"
echo "    $VENV_DIR/bin/python3 $SCRIPT_DIR/src/cli.py stats"
echo ""
echo "  To export last session for Chat:"
echo "    bash $SCRIPT_DIR/export-to-chat.sh"
echo ""
