"""
Tests for .mcp.json PRO tier defaults -- validates that PUBLIC-FACING
plugin .mcp.json files default to free tier (empty LORECONVO_PRO/LOREDOCS_PRO).

MEG-037: The -plugin .mcp.json files (the ones that ship to external users)
MUST default to free tier. Only the dev .mcp.json (loreconvo/.mcp.json) may
have PRO=1 since that is used internally.

See CLAUDE.md TODOs #2 and #3.
"""

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent


class TestLoreConvoPluginMcpJson:
    """Test the public-facing LoreConvo plugin .mcp.json."""

    @pytest.fixture
    def mcp_data(self):
        path = REPO_ROOT / "ron_skills" / "loreconvo-plugin" / ".mcp.json"
        assert path.exists(), f".mcp.json not found at {path}"
        return json.loads(path.read_text())

    def test_pro_default_should_be_free_tier(self, mcp_data):
        """PUBLIC plugin must NOT ship with LORECONVO_PRO=1.

        Fixed in commit following MEG-037 (2026-04-03).
        Public plugin .mcp.json must default to "" (free tier).
        License keys are set by users after purchasing Pro.
        """
        env = mcp_data.get("mcpServers", {}).get("loreconvo", {}).get("env", {})
        pro_val = env.get("LORECONVO_PRO", "")
        assert pro_val == "", (
            f"PUBLIC plugin .mcp.json must default LORECONVO_PRO to '' (free tier), "
            f"got '{pro_val}'. External users should start on free tier."
        )


class TestLoreDocsPluginMcpJson:
    """Test the public-facing LoreDocs plugin .mcp.json."""

    @pytest.fixture
    def mcp_data(self):
        path = REPO_ROOT / "ron_skills" / "loredocs-plugin" / ".mcp.json"
        assert path.exists(), f".mcp.json not found at {path}"
        return json.loads(path.read_text())

    def test_pro_default_should_be_free_tier(self, mcp_data):
        """PUBLIC plugin must NOT ship with LOREDOCS_PRO=1.

        Fixed in commit following MEG-037 (2026-04-03).
        Public plugin .mcp.json must default to "" (free tier).
        License keys are set by users after purchasing Pro.
        """
        env = mcp_data.get("mcpServers", {}).get("loredocs", {}).get("env", {})
        pro_val = env.get("LOREDOCS_PRO", "")
        assert pro_val == "", (
            f"PUBLIC plugin .mcp.json must default LOREDOCS_PRO to '' (free tier), "
            f"got '{pro_val}'. External users should start on free tier."
        )


class TestDevMcpJsonProIsOk:
    """Dev .mcp.json files are internal -- PRO=1 is expected and correct."""

    def test_loreconvo_dev_mcp_has_pro(self):
        path = REPO_ROOT / "ron_skills" / "loreconvo" / ".mcp.json"
        assert path.exists()
        data = json.loads(path.read_text())
        env = data.get("mcpServers", {}).get("loreconvo", {}).get("env", {})
        assert env.get("LORECONVO_PRO") == "1", "Dev .mcp.json should have PRO=1 for internal agents"
