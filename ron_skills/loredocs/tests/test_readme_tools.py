"""Verify LoreDocs README tool table matches actual server tool registrations.

Ensures tool counts and tool names in documentation stay synchronized
with the actual MCP server implementation.
"""

import re
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent.parent


class TestReadmeToolTable:
    """Check that README.md tool documentation matches server.py."""

    @pytest.fixture(autouse=True)
    def load_files(self):
        self.readme = (ROOT / "README.md").read_text()
        self.server_src = (ROOT / "loredocs" / "server.py").read_text()

    def _server_tool_names(self):
        """Extract tool names from @mcp.tool(name=...) decorators in server.py."""
        # LoreDocs uses @mcp.tool(name="vault_xyz", annotations={...})
        return re.findall(r'@mcp\.tool\(\s*name\s*=\s*"(\w+)"', self.server_src)

    def _readme_tool_names(self):
        """Extract tool names from README.md backtick-delimited tool table."""
        # Pattern: | `vault_xyz` |
        return re.findall(r"\|\s*`(\w+)`\s*\|", self.readme)

    def test_tool_count_matches_34(self):
        names = self._server_tool_names()
        assert len(names) == 34, (
            f"Expected 34 @mcp.tool decorators in server.py, found {len(names)}"
        )

    def test_readme_claims_34_tools(self):
        assert "34 MCP tools" in self.readme, (
            "README should state '34 MCP tools'"
        )

    def test_readme_table_lists_all_tools(self):
        server_names = set(self._server_tool_names())
        readme_names = set(self._readme_tool_names())
        missing_from_readme = server_names - readme_names
        extra_in_readme = readme_names - server_names
        assert not missing_from_readme, (
            f"Tools in server.py but not in README: {missing_from_readme}"
        )
        assert not extra_in_readme, (
            f"Tools in README but not in server.py: {extra_in_readme}"
        )

    def test_readme_tool_count_equals_server(self):
        server_count = len(self._server_tool_names())
        readme_count = len(self._readme_tool_names())
        assert server_count == readme_count, (
            f"server.py has {server_count} tools, README table has {readme_count}"
        )


class TestReadmeLicenseSection:
    """Verify README reflects BSL 1.1 license."""

    @pytest.fixture(autouse=True)
    def load_readme(self):
        self.readme = (ROOT / "README.md").read_text()

    def test_mentions_bsl(self):
        assert "BSL 1.1" in self.readme or "Business Source License" in self.readme, (
            "README should mention BSL 1.1 license"
        )

    def test_mentions_free_tier_limit(self):
        assert "3 vaults" in self.readme, (
            "README should mention free tier limit of 3 vaults"
        )

    def test_mentions_apache_conversion(self):
        assert "Apache 2.0" in self.readme, (
            "README should mention Apache 2.0 conversion"
        )
