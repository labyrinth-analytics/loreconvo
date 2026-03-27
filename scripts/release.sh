#!/bin/bash
# release.sh -- Sync a product from the private monorepo to its public GitHub repo
# and publish the Python package to PyPI.
#
# Usage:
#   ./scripts/release.sh <product> <version>
#
#   <product>  : loreconvo | loredocs
#   <version>  : version tag, e.g. 0.3.1
#
# Examples:
#   ./scripts/release.sh loreconvo 0.3.1
#   ./scripts/release.sh loredocs 0.2.0
#
# Prerequisites (one-time setup):
#   1. Public GitHub repos already exist:
#        github.com/labyrinth-analytics/loreconvo
#        github.com/labyrinth-analytics/loredocs
#   2. Create a PyPI account at pypi.org
#   3. Install build tools:  pip install build twine
#   4. Configure PyPI token:  ~/.pypirc  (or use TWINE_PASSWORD env var)
#
# What this script does:
#   1. Validates input
#   2. Runs the product's test suite
#   3. Bumps the version in plugin.json and pyproject.toml
#   4. Pushes the plugin directory to the public GitHub repo
#   5. Creates a git tag in the public repo
#   6. Builds and uploads the Python package to PyPI

set -e

PRODUCT="$1"
VERSION="$2"

MONOREPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# ---- Validate inputs ----
if [ -z "$PRODUCT" ] || [ -z "$VERSION" ]; then
    echo "Usage: $0 <product> <version>"
    echo "       $0 loreconvo 0.3.1"
    echo "       $0 loredocs 0.2.0"
    exit 1
fi

if [ "$PRODUCT" != "loreconvo" ] && [ "$PRODUCT" != "loredocs" ]; then
    echo "ERROR: product must be 'loreconvo' or 'loredocs'"
    exit 1
fi

PLUGIN_DIR="$MONOREPO_ROOT/ron_skills/${PRODUCT}-plugin"
SOURCE_DIR="$MONOREPO_ROOT/ron_skills/${PRODUCT}"
PUBLIC_REMOTE="git@github.com:labyrinth-analytics/${PRODUCT}.git"
PUBLIC_CLONE="/tmp/release_${PRODUCT}"

echo ""
echo "=== Releasing ${PRODUCT} v${VERSION} ==="
echo "  Plugin dir:   $PLUGIN_DIR"
echo "  Source dir:   $SOURCE_DIR"
echo "  Public repo:  $PUBLIC_REMOTE"
echo ""

# ---- Run tests ----
echo "[1/5] Running tests..."
cd "$SOURCE_DIR"
python -m pytest tests/ -q --tb=short
echo "      Tests passed."

# ---- Update version in plugin.json ----
echo "[2/5] Updating version to $VERSION..."
PLUGIN_JSON="$PLUGIN_DIR/.claude-plugin/plugin.json"
# Use python for safe JSON editing (no jq dependency)
python3 -c "
import json, sys
with open('$PLUGIN_JSON') as f:
    data = json.load(f)
data['version'] = '$VERSION'
with open('$PLUGIN_JSON', 'w') as f:
    json.dump(data, f, indent=2)
    f.write('\n')
print('      plugin.json updated.')
"

# Update pyproject.toml version
PYPROJECT="$SOURCE_DIR/pyproject.toml"
python3 -c "
import re
with open('$PYPROJECT') as f:
    content = f.read()
content = re.sub(r'^version = \".*\"', 'version = \"$VERSION\"', content, flags=re.MULTILINE)
with open('$PYPROJECT', 'w') as f:
    f.write(content)
print('      pyproject.toml updated.')
"

# Commit version bump to private monorepo
cd "$MONOREPO_ROOT"
git add "$PLUGIN_JSON" "$PYPROJECT"
git commit -m "Bump ${PRODUCT} to v${VERSION}"

# ---- Sync plugin directory to public repo ----
echo "[3/5] Syncing plugin to public repo..."
rm -rf "$PUBLIC_CLONE"

# Clone the public repo (create it on GitHub first if it doesn't exist)
if git ls-remote "$PUBLIC_REMOTE" &>/dev/null; then
    git clone "$PUBLIC_REMOTE" "$PUBLIC_CLONE"
else
    echo "ERROR: Public repo not found: $PUBLIC_REMOTE"
    echo "       Create it on GitHub first (public, no README -- we will push one)."
    exit 1
fi

# Copy plugin files to public repo
rsync -av --delete \
    --exclude ".git" \
    --exclude "__pycache__" \
    --exclude "*.pyc" \
    --exclude ".venv" \
    --exclude "*.egg-info" \
    "$PLUGIN_DIR/" "$PUBLIC_CLONE/"

# Copy the Python package source (users don't need it, but it makes the repo
# browsable and matches what gets published to PyPI)
rsync -av --delete \
    --exclude ".git" \
    --exclude "__pycache__" \
    --exclude "*.pyc" \
    --exclude ".venv" \
    --exclude "*.egg-info" \
    --exclude "tests/" \
    --exclude "docs/PUBLISHING.md" \
    "$SOURCE_DIR/" "$PUBLIC_CLONE/src/"

# Commit and tag in the public repo
cd "$PUBLIC_CLONE"
git add -A
git commit -m "Release v${VERSION}"
git tag "v${VERSION}"
git push origin main
git push origin "v${VERSION}"
echo "      Pushed to public repo and tagged v${VERSION}."

# ---- Build and publish to PyPI ----
echo "[4/5] Building Python package..."
cd "$SOURCE_DIR"
rm -rf dist/ build/ *.egg-info
python -m build
echo "      Build complete."

echo "[5/5] Publishing to PyPI..."
echo "      (You will be prompted for your PyPI token if not configured in ~/.pypirc)"
python -m twine upload dist/*
echo "      Published to PyPI."

# ---- Cleanup ----
rm -rf "$PUBLIC_CLONE"

echo ""
echo "=== Release complete: ${PRODUCT} v${VERSION} ==="
echo ""
echo "Next steps:"
echo "  1. Update labyrinth-analytics/claude-plugins marketplace.json to ref v${VERSION}"
echo "  2. Announce the release to early adopters"
echo "  3. Test install with: uvx ${PRODUCT}@${VERSION}"
echo ""
