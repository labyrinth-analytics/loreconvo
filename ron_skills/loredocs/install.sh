#!/bin/bash
# LoreDocs - One-command installation
# Usage: bash install.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"

echo "============================================"
echo "  LoreDocs Installer"
echo "  Your AI project knowledge vault."
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
echo "[..] Installing LoreDocs package..."
"$VENV_DIR/bin/pip3" install -q "$SCRIPT_DIR"
echo "[OK] LoreDocs package installed (entry point: $VENV_DIR/bin/loredocs)"

# Create database directory
mkdir -p "$HOME/.loredocs"
echo "[OK] Database directory ready at ~/.loredocs/"

# Verify entry point was created
if [ ! -f "$VENV_DIR/bin/loredocs" ]; then
    echo "[ERROR] Entry point not created at $VENV_DIR/bin/loredocs"
    echo "        Try: $VENV_DIR/bin/pip3 install $SCRIPT_DIR"
    exit 1
fi
echo "[OK] Entry point verified at $VENV_DIR/bin/loredocs"

# Ensure hook scripts are executable (git does not preserve execute bits)
HOOKS_DIR="$SCRIPT_DIR/hooks/scripts"
if [ -d "$HOOKS_DIR" ]; then
    chmod +x "$HOOKS_DIR"/*.sh 2>/dev/null || true
    echo "[OK] Hook scripts marked executable at hooks/scripts/"
fi

# Verify server starts
echo "[..] Testing MCP server import..."
"$VENV_DIR/bin/python3" -c "
from loredocs.storage import VaultStorage
from loredocs.tiers import TierEnforcer
print('[OK] LoreDocs modules imported successfully')
"

echo ""
echo "============================================"
echo "  Installation complete!"
echo "============================================"
echo ""
echo "  To use with Claude Code:"
echo "    claude --plugin-dir $SCRIPT_DIR"
echo ""
echo "  To use the CLI (coming soon):"
echo "    $VENV_DIR/bin/loredocs --help"
echo ""
echo "  Vault data is stored at: ~/.loredocs/"
echo ""
