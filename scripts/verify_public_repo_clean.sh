#!/bin/bash
# ============================================================
# verify_public_repo_clean.sh
# Pre-push check: verifies no sensitive files are tracked in
# the loreconvo or loredocs product directories.
#
# Run this BEFORE any subtree push to public repos.
#
# USAGE:
#   cd ~/projects/side_hustle
#   bash scripts/verify_public_repo_clean.sh
# ============================================================

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

FAIL=0

echo -e "${YELLOW}=== Pre-Push Public Repo Verification ===${NC}"
echo ""

# Patterns that should NEVER be tracked in product directories
BLOCKED_PATTERNS=(
    "Revenue_Projection"
    "build_revenue_projection"
    "PUBLISHING.md"
    "marketplace_listing.md"
    "session-bridge-prd.md"
    "Product_Spec.md"
    "CLAUDE.md"
    ".tar.gz"
    ".xlsx"
)

for PRODUCT in loreconvo loredocs; do
    DIR="ron_skills/$PRODUCT"
    echo -e "${YELLOW}Checking $PRODUCT...${NC}"

    # Get tracked files
    TRACKED=$(git ls-files "$DIR" 2>/dev/null)

    for PATTERN in "${BLOCKED_PATTERNS[@]}"; do
        MATCHES=$(echo "$TRACKED" | grep -i "$PATTERN" 2>/dev/null || true)
        if [ -n "$MATCHES" ]; then
            echo -e "  ${RED}[BLOCKED] Found tracked file matching '$PATTERN':${NC}"
            echo "$MATCHES" | while read -r f; do echo "    $f"; done
            FAIL=1
        fi
    done

    # Check .gitignore exists
    if [ ! -f "$DIR/.gitignore" ]; then
        echo -e "  ${RED}[MISSING] No .gitignore in $DIR${NC}"
        FAIL=1
    else
        echo -e "  ${GREEN}[OK] .gitignore present${NC}"
    fi
done

echo ""
if [ "$FAIL" -eq 1 ]; then
    echo -e "${RED}=== FAILED: Do NOT push until issues are resolved ===${NC}"
    echo "Run: git rm --cached <file> for each blocked file"
    exit 1
else
    echo -e "${GREEN}=== PASSED: Safe to push to public repos ===${NC}"
    exit 0
fi
