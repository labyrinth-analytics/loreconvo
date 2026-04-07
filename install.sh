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
    # Verify the existing venv is functional (stale symlinks can occur after a rebrand or move)
    if ! "$VENV_DIR/bin/python3" -c "import sys; print(sys.version)" &> /dev/null; then
        echo "[..] Existing .venv appears stale -- recreating..."
        rm -rf "$VENV_DIR"
        python3 -m venv "$VENV_DIR"
        echo "[OK] Virtual environment recreated at .venv/"
    else
        echo "[OK] Virtual environment already exists at .venv/"
    fi
else
    echo "[..] Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
    echo "[OK] Virtual environment created at .venv/"
fi

# Install package and dependencies
echo "[..] Installing LoreConvo package..."
"$VENV_DIR/bin/pip3" install -q "$SCRIPT_DIR"
echo "[OK] LoreConvo package installed (entry point: $VENV_DIR/bin/loreconvo)"

# Create database directory
mkdir -p "$HOME/.loreconvo"
echo "[OK] Database directory ready at ~/.loreconvo/"

# Verify entry point was created
if [ ! -f "$VENV_DIR/bin/loreconvo" ]; then
    echo "[ERROR] Entry point not created at $VENV_DIR/bin/loreconvo"
    echo "        Try: $VENV_DIR/bin/pip3 install $SCRIPT_DIR"
    exit 1
fi
echo "[OK] Entry point verified at $VENV_DIR/bin/loreconvo"

# Ensure hook scripts are executable (git does not preserve execute bits)
HOOKS_DIR="$SCRIPT_DIR/hooks/scripts"
if [ -d "$HOOKS_DIR" ]; then
    chmod +x "$HOOKS_DIR"/*.sh 2>/dev/null || true
    echo "[OK] Hook scripts marked executable at hooks/scripts/"
fi

# Verify server starts
echo "[..] Testing MCP server import..."
"$VENV_DIR/bin/python3" -c "
from loreconvo.core.database import SessionDatabase
from loreconvo.core.config import Config
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
echo "    $VENV_DIR/bin/loreconvo-cli stats"
echo ""
echo "  To export last session for Chat:"
echo "    bash $SCRIPT_DIR/export-to-chat.sh"
echo ""
