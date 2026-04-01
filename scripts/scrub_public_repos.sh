#!/bin/bash
# ============================================================
# scrub_public_repos.sh
# Removes sensitive internal documents from PUBLIC GitHub repo
# git history for LoreConvo and LoreDocs.
#
# WHAT THIS DOES:
#   1. Clones each public repo into a temp directory
#   2. Uses git-filter-repo to remove sensitive files from ALL commits
#   3. Force-pushes the cleaned history
#
# PREREQUISITES:
#   pip install git-filter-repo
#
# USAGE:
#   cd ~/projects/side_hustle
#   bash scripts/scrub_public_repos.sh
#
# WARNING: This rewrites git history and requires force push.
#   - Anyone who has cloned these repos will need to re-clone
#   - All commit hashes will change
#   - This cannot be undone
# ============================================================

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${YELLOW}=== Public Repo History Scrubber ===${NC}"
echo ""
echo "This will REWRITE git history on your public GitHub repos to remove"
echo "sensitive internal documents (revenue projections, PRDs, pricing, etc.)"
echo ""
echo -e "${RED}WARNING: This is destructive. All commit hashes will change.${NC}"
echo ""
read -p "Continue? (yes/no): " CONFIRM
if [ "$CONFIRM" != "yes" ]; then
    echo "Aborted."
    exit 0
fi

# Check for git-filter-repo
if ! command -v git-filter-repo &> /dev/null; then
    echo -e "${RED}ERROR: git-filter-repo is not installed.${NC}"
    echo "Install it with: pip install git-filter-repo --break-system-packages"
    exit 1
fi

WORK_DIR=$(mktemp -d)
echo -e "${GREEN}Working directory: $WORK_DIR${NC}"

# ============================================================
# LORECONVO
# ============================================================
echo ""
echo -e "${YELLOW}=== Scrubbing LoreConvo ===${NC}"

LORECONVO_FILES=(
    "CLAUDE.md"
    "docs/ConvoVault_Revenue_Projection.xlsx"
    "docs/LoreConvo_Revenue_Projection.xlsx"
    "docs/PUBLISHING.md"
    "docs/build_revenue_projection.py"
    "docs/marketplace_listing.md"
    "docs/session-bridge-prd.md"
)

cd "$WORK_DIR"
echo "Cloning labyrinth-analytics/loreconvo..."
git clone https://github.com/labyrinth-analytics/loreconvo.git
cd loreconvo

echo "Removing sensitive files from all history..."
FILTER_ARGS=""
for f in "${LORECONVO_FILES[@]}"; do
    FILTER_ARGS="$FILTER_ARGS --path $f"
done

git filter-repo --invert-paths $FILTER_ARGS --force

echo "Force-pushing cleaned history..."
git remote add origin https://github.com/labyrinth-analytics/loreconvo.git
git push origin --force --all
git push origin --force --tags

echo -e "${GREEN}LoreConvo scrubbed successfully.${NC}"

# ============================================================
# LOREDOCS
# ============================================================
echo ""
echo -e "${YELLOW}=== Scrubbing LoreDocs ===${NC}"

LOREDOCS_FILES=(
    "CLAUDE.md"
    "docs/PUBLISHING.md"
    "docs/marketplace_listing.md"
    "docs/LoreDocs_Product_Spec.md"
    "docs/ProjectVault_Product_Spec.md"
    "projectvault-v0.1.0.tar.gz"
)

cd "$WORK_DIR"
echo "Cloning labyrinth-analytics/loredocs..."
git clone https://github.com/labyrinth-analytics/loredocs.git
cd loredocs

echo "Removing sensitive files from all history..."
FILTER_ARGS=""
for f in "${LOREDOCS_FILES[@]}"; do
    FILTER_ARGS="$FILTER_ARGS --path $f"
done

git filter-repo --invert-paths $FILTER_ARGS --force

echo "Force-pushing cleaned history..."
git remote add origin https://github.com/labyrinth-analytics/loredocs.git
git push origin --force --all
git push origin --force --tags

echo -e "${GREEN}LoreDocs scrubbed successfully.${NC}"

# ============================================================
# CLEANUP
# ============================================================
echo ""
echo -e "${YELLOW}=== Post-Scrub Steps ===${NC}"
echo "1. Verify on GitHub that sensitive files are gone from all commits"
echo "2. In your local side_hustle repo, re-fetch the public remotes:"
echo "     cd ~/projects/side_hustle"
echo "     git fetch loreconvo"
echo "     git fetch loredocs"
echo "3. The local monorepo subtree refs will be out of sync."
echo "   Next subtree push will re-establish the connection."
echo ""
echo -e "${GREEN}Cleaning up temp directory...${NC}"
rm -rf "$WORK_DIR"
echo -e "${GREEN}Done! Both repos have been scrubbed.${NC}"
