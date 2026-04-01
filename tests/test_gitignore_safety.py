"""Verify .gitignore blocks sensitive files from being tracked in public repos.

Tests that the safety nets are in place to prevent internal business
documents from being accidentally committed to public-facing product
directories (LoreConvo and LoreDocs).
"""

import fnmatch
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent.parent


class TestGitignoreSafety:
    """Verify .gitignore patterns block sensitive file types."""

    @pytest.fixture(autouse=True)
    def load_gitignore(self):
        gitignore_path = ROOT / ".gitignore"
        assert gitignore_path.exists(), ".gitignore must exist in product directory"
        self.patterns = [
            line.strip() for line in gitignore_path.read_text().splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]

    def test_blocks_claude_md(self):
        assert "CLAUDE.md" in self.patterns, (
            ".gitignore must block CLAUDE.md (contains internal agent instructions)"
        )

    def test_blocks_xlsx_files(self):
        assert "*.xlsx" in self.patterns, (
            ".gitignore must block *.xlsx (revenue projections)"
        )

    def test_blocks_env_files(self):
        assert "*.env" in self.patterns, (
            ".gitignore must block *.env (secrets)"
        )

    def test_blocks_database_files(self):
        assert "*.db" in self.patterns, (
            ".gitignore must block *.db (local databases)"
        )

    def test_blocks_venv(self):
        assert ".venv/" in self.patterns or "venv/" in self.patterns, (
            ".gitignore must block virtual environments"
        )

    def test_no_sensitive_files_exist_unignored(self):
        """Verify no sensitive files exist in the product directory (belt and suspenders)."""
        sensitive_patterns = [
            "*Revenue*", "*PUBLISHING*", "*marketplace_listing*",
            "*Product_Spec*", "*session-bridge-prd*"
        ]
        found = []
        for p in ROOT.rglob("*"):
            if ".venv" in str(p) or "__pycache__" in str(p):
                continue
            for pattern in sensitive_patterns:
                if fnmatch.fnmatch(p.name, pattern):
                    found.append(str(p.relative_to(ROOT)))
        assert not found, (
            f"Sensitive files found in product directory: {found}"
        )
