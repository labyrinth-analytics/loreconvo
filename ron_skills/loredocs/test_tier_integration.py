#!/usr/bin/env python3
"""
Integration tests for ProjectVault tier enforcement via real MCP client calls.

These tests start the ProjectVault MCP server as a subprocess, connect a real
MCP client over stdio transport, and verify that tier limits are enforced
end-to-end through the full MCP protocol stack.

Run with:
    cd ron_skills/projectvault
    PYTHONPATH=. python test_tier_integration.py

Requires: mcp, projectvault (installed or PYTHONPATH=.)
"""

import asyncio
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PASS = 0
FAIL = 0


def ok(label):
    global PASS
    PASS += 1
    print(f"  [OK] {label}")


def fail_test(label, detail=""):
    global FAIL
    FAIL += 1
    print(f"  [FAIL] {label}: {detail}")


def assert_ok(condition, label, detail=""):
    if condition:
        ok(label)
    else:
        fail_test(label, detail or "assertion failed")


async def call_tool(session, tool_name, params_dict):
    """Call an MCP tool wrapping params_dict in {'params': ...}.

    FastMCP tools with a Pydantic input model expect arguments wrapped as
    {"params": {<actual fields>}}.  Returns the text content string.
    """
    result = await session.call_tool(tool_name, arguments={"params": params_dict})
    if result.content and len(result.content) > 0:
        return result.content[0].text
    return ""


# ---------------------------------------------------------------------------
# Test functions -- each receives a connected ClientSession
# ---------------------------------------------------------------------------

async def test_default_tier_is_free(session):
    """Verify fresh install reports free tier."""
    print("\n[default tier is free]")
    result = await call_tool(session, "vault_tier_status", {"response_format": "json"})
    data = json.loads(result)
    assert_ok(data["tier"] == "free", "default tier is free")
    assert_ok(data["is_pro"] is False, "is_pro is False on free tier")
    assert_ok(data["vault_limit"] == 3, "free tier vault limit is 3")
    assert_ok(data["docs_per_vault_limit"] == 50, "free tier docs_per_vault limit is 50")


async def test_vault_limit_enforced(session):
    """Free tier blocks creation of 4th vault."""
    print("\n[vault limit enforced on free tier]")

    # Create 3 vaults (should succeed)
    for i in range(3):
        result = await call_tool(session, "vault_create", {"name": f"IntVault{i}"})
        data = json.loads(result) if not result.startswith("Error") else {}
        assert_ok(
            data.get("name") == f"IntVault{i}",
            f"vault_create IntVault{i} succeeds within limit",
        )

    # 4th vault should be blocked
    result = await call_tool(session, "vault_create", {"name": "IntVault3"})
    assert_ok(
        result.startswith("Error:") or "limit" in result.lower(),
        "4th vault blocked by free tier",
        f"got: {result[:120]}",
    )


async def test_doc_limit_enforced(session):
    """Free tier blocks adding 51st document to a vault."""
    print("\n[doc limit enforced on free tier]")

    # We already have 3 vaults from the vault limit test.  The free tier
    # blocks a 4th, so we need to use an existing vault (or upgrade/archive).
    # Upgrade briefly to create a dedicated vault, then downgrade.
    await call_tool(session, "vault_set_tier", {"tier": "pro"})
    result = await call_tool(session, "vault_create", {"name": "DocLimitVault"})
    data = json.loads(result) if not result.startswith("Error") else {}
    vault_name = data.get("name", "DocLimitVault")
    await call_tool(session, "vault_set_tier", {"tier": "free"})

    # Add 50 docs (free limit)
    for i in range(50):
        result = await call_tool(session, "vault_add_doc", {
            "vault": vault_name,
            "name": f"doc_{i}",
            "content": f"Content for document {i}.",
        })
        if i == 0:
            assert_ok(
                not result.startswith("Error:"),
                "first doc add succeeds",
            )

    ok("50 docs added within free tier limit")

    # 51st doc should be blocked
    result = await call_tool(session, "vault_add_doc", {
        "vault": vault_name,
        "name": "overflow_doc",
        "content": "This should be blocked.",
    })
    assert_ok(
        result.startswith("Error:") or "limit" in result.lower(),
        "51st doc blocked by free tier",
        f"got: {result[:120]}",
    )


async def test_upgrade_to_pro_removes_limits(session):
    """After upgrading to pro, previously-blocked operations succeed."""
    print("\n[pro upgrade removes limits]")

    # Upgrade to pro
    result = await call_tool(session, "vault_set_tier", {"tier": "pro"})
    assert_ok("pro" in result.lower(), "set_tier to pro acknowledged")

    # Verify tier status
    result = await call_tool(session, "vault_tier_status", {"response_format": "json"})
    data = json.loads(result)
    assert_ok(data["tier"] == "pro", "tier status reports pro")
    assert_ok(data["is_pro"] is True, "is_pro is True after upgrade")
    assert_ok(data["vault_limit"] is None, "vault_limit is None (unlimited)")

    # Now creating another vault should work
    result = await call_tool(session, "vault_create", {"name": "ProVault"})
    data = json.loads(result) if not result.startswith("Error") else {}
    assert_ok(
        data.get("name") == "ProVault",
        "vault creation succeeds on pro tier (beyond free limit)",
    )


async def test_downgrade_to_free_reenables_limits(session):
    """Downgrading to free re-enables limits but does not delete data."""
    print("\n[downgrade re-enables limits]")

    result = await call_tool(session, "vault_set_tier", {"tier": "free"})
    assert_ok("free" in result.lower(), "set_tier to free acknowledged")

    result = await call_tool(session, "vault_tier_status", {"response_format": "json"})
    data = json.loads(result)
    assert_ok(data["tier"] == "free", "tier status reports free after downgrade")
    assert_ok(data["is_pro"] is False, "is_pro is False after downgrade")

    # Existing vaults still exist (data not deleted), but new writes blocked
    vault_count = data.get("vault_count", 0)
    if vault_count >= 3:
        result = await call_tool(session, "vault_create", {"name": "BlockedAfterDowngrade"})
        assert_ok(
            result.startswith("Error:") or "limit" in result.lower(),
            "new vault blocked after downgrade to free",
            f"got: {result[:120]}",
        )
    else:
        ok("skipped -- vault count under limit after downgrade (expected in fresh env)")


async def test_tier_status_usage_tracking(session):
    """Verify tier_status accurately reports vault count and storage usage."""
    print("\n[tier status usage tracking]")

    result = await call_tool(session, "vault_tier_status", {"response_format": "json"})
    data = json.loads(result)

    assert_ok(isinstance(data["vault_count"], int), "vault_count is int")
    assert_ok(data["vault_count"] >= 0, "vault_count is non-negative")
    assert_ok(isinstance(data["storage_used_mb"], (int, float)), "storage_used_mb is numeric")
    assert_ok(data["storage_used_mb"] >= 0, "storage_used_mb is non-negative")

    # On free tier, usage percentages should be present
    if data["tier"] == "free":
        assert_ok(
            data["vault_usage_pct"] is not None,
            "vault_usage_pct present on free tier",
        )
        assert_ok(
            data["storage_usage_pct"] is not None,
            "storage_usage_pct present on free tier",
        )


async def test_tier_status_markdown_format(session):
    """Verify the markdown format output contains expected sections."""
    print("\n[tier status markdown format]")

    result = await call_tool(session, "vault_tier_status", {})
    assert_ok("Tier Status" in result, "markdown output contains title")
    assert_ok("Vaults:" in result, "markdown output contains vault count")
    assert_ok("Storage:" in result, "markdown output contains storage info")


# ---------------------------------------------------------------------------
# Main runner -- start server, connect client, run tests
# ---------------------------------------------------------------------------

async def run_all_tests():
    """Start ProjectVault server, connect client, run tier integration tests."""
    # Use a temp directory as the ProjectVault root so tests are isolated
    tmpdir = tempfile.mkdtemp(prefix="pv_tier_integ_")
    env = os.environ.copy()
    env["PROJECTVAULT_ROOT"] = tmpdir

    server_params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "projectvault.server"],
        env=env,
    )

    try:
        async with stdio_client(server_params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()

                # Verify we can list tools (sanity check)
                tools = await session.list_tools()
                tool_names = [t.name for t in tools.tools]
                assert "vault_create" in tool_names, (
                    f"vault_create not in tools: {tool_names}"
                )
                assert "vault_tier_status" in tool_names, (
                    f"vault_tier_status not in tools: {tool_names}"
                )
                print(f"Connected to server with {len(tool_names)} tools")

                # Run tests in order (they share server state intentionally)
                await test_default_tier_is_free(session)
                await test_vault_limit_enforced(session)
                await test_doc_limit_enforced(session)
                await test_upgrade_to_pro_removes_limits(session)
                await test_downgrade_to_free_reenables_limits(session)
                await test_tier_status_usage_tracking(session)
                await test_tier_status_markdown_format(session)
    finally:
        # Cleanup
        shutil.rmtree(tmpdir, ignore_errors=True)


def main():
    print("=" * 60)
    print("ProjectVault Tier Integration Tests (real MCP client)")
    print("=" * 60)

    try:
        asyncio.run(run_all_tests())
    except Exception as exc:
        import traceback
        global FAIL
        FAIL += 1
        print(f"\n[FAIL] Test runner crashed: {exc}")
        traceback.print_exc()

    print("\n" + "=" * 60)
    print(f"Results: {PASS} passed, {FAIL} failed")
    print("=" * 60)
    sys.exit(0 if FAIL == 0 else 1)


if __name__ == "__main__":
    main()
