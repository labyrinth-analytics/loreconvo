"""
Tests for plugin.json hook structure -- validates the hooks format
is correct after the recent flattening fix.

The SessionStart and SessionEnd hooks must be flat arrays of hook objects,
not nested {hooks: [...]} wrappers.
"""

import json
from pathlib import Path

import pytest

PLUGIN_JSON = Path(__file__).resolve().parent.parent / ".claude-plugin" / "plugin.json"


@pytest.fixture
def plugin_data():
    """Load plugin.json as dict."""
    assert PLUGIN_JSON.exists(), f"plugin.json not found at {PLUGIN_JSON}"
    return json.loads(PLUGIN_JSON.read_text())


class TestPluginJsonHookStructure:

    def test_session_start_hooks_are_flat(self, plugin_data):
        """SessionStart hooks should be direct hook objects, not nested."""
        hooks = plugin_data.get("hooks", {}).get("SessionStart", [])
        for hook in hooks:
            assert "type" in hook, f"Hook missing 'type' key: {hook}"
            assert "command" in hook, f"Hook missing 'command' key: {hook}"
            # Must NOT have a nested 'hooks' key
            assert "hooks" not in hook, f"Hook has nested 'hooks' -- structure is wrong: {hook}"

    def test_session_end_hooks_are_flat(self, plugin_data):
        """SessionEnd hooks should be direct hook objects, not nested."""
        hooks = plugin_data.get("hooks", {}).get("SessionEnd", [])
        for hook in hooks:
            assert "type" in hook, f"Hook missing 'type' key: {hook}"
            assert "command" in hook, f"Hook missing 'command' key: {hook}"
            assert "hooks" not in hook, f"Hook has nested 'hooks' -- structure is wrong: {hook}"

    def test_session_start_has_two_hooks(self, plugin_data):
        """SessionStart should have setup + on_session_start hooks."""
        hooks = plugin_data.get("hooks", {}).get("SessionStart", [])
        assert len(hooks) == 2, f"Expected 2 SessionStart hooks, got {len(hooks)}"

    def test_session_end_has_one_hook(self, plugin_data):
        """SessionEnd should have on_session_end hook."""
        hooks = plugin_data.get("hooks", {}).get("SessionEnd", [])
        assert len(hooks) == 1, f"Expected 1 SessionEnd hook, got {len(hooks)}"

    def test_session_end_has_timeout(self, plugin_data):
        """SessionEnd hook should have a timeout."""
        hooks = plugin_data.get("hooks", {}).get("SessionEnd", [])
        assert len(hooks) > 0
        assert "timeout" in hooks[0], "SessionEnd hook missing timeout"

    def test_hook_commands_use_claude_plugin_root(self, plugin_data):
        """All hook commands should use ${CLAUDE_PLUGIN_ROOT} variable."""
        for event_name in ["SessionStart", "SessionEnd"]:
            hooks = plugin_data.get("hooks", {}).get(event_name, [])
            for hook in hooks:
                cmd = hook.get("command", "")
                assert "${CLAUDE_PLUGIN_ROOT}" in cmd, (
                    f"{event_name} hook command does not use "
                    f"${{CLAUDE_PLUGIN_ROOT}}: {cmd}"
                )


class TestPluginJsonMetadata:

    def test_license_is_bsl(self, plugin_data):
        assert plugin_data.get("license") == "BSL-1.1"

    def test_version_is_present(self, plugin_data):
        assert "version" in plugin_data
        assert plugin_data["version"] == "0.3.0"

    def test_has_required_fields(self, plugin_data):
        for field in ["name", "version", "description", "author", "keywords"]:
            assert field in plugin_data, f"Missing required field: {field}"
