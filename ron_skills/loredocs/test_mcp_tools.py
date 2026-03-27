#!/usr/bin/env python3
"""MCP tool-layer tests for LoreDocs.

These tests call the async tool functions directly, bypassing the MCP transport
layer, to verify that each tool correctly delegates to storage and returns the
expected output format.

Run with:
    PYTHONPATH=. python test_mcp_tools.py
"""

import asyncio
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent))

from loredocs.storage import VaultStorage
from loredocs.server import (
    # Vault management
    vault_create, VaultCreateInput,
    vault_list, VaultListInput,
    vault_info, VaultIdInput,
    vault_archive, VaultArchiveInput,
    vault_delete, VaultDeleteInput,
    vault_link_project, VaultLinkProjectInput,
    # Document management
    vault_add_doc, DocAddInput,
    vault_get_doc, DocGetInput,
    vault_update_doc, DocUpdateInput,
    vault_remove_doc, DocIdInput,
    vault_list_docs, DocListInput,
    vault_tag_doc, TagDocInput,
    vault_categorize, CategorizeInput,
    vault_set_priority, SetPriorityInput,
    # Search
    vault_search, SearchInput,
    vault_search_by_tag, SearchByTagInput,
    # Context injection
    vault_inject, InjectInput,
    vault_inject_summary, InjectSummaryInput,
    # Tiers
    vault_tier_status, VaultTierStatusInput,
    vault_set_tier, VaultSetTierInput,
)

PASS = 0
FAIL = 0


def make_ctx(storage: VaultStorage) -> MagicMock:
    """Create a mock MCP Context that provides the given storage instance."""
    ctx = MagicMock()
    ctx.request_context.lifespan_context = {"storage": storage}
    return ctx


def run(coro):
    """Run an async coroutine synchronously."""
    return asyncio.run(coro)


def ok(label: str):
    global PASS
    PASS += 1
    print(f"  [OK] {label}")


def fail_test(label: str, detail: str):
    global FAIL
    FAIL += 1
    print(f"  [FAIL] {label}: {detail}")


def assert_ok(condition: bool, label: str, detail: str = ""):
    if condition:
        ok(label)
    else:
        fail_test(label, detail or "assertion failed")


# ---------------------------------------------------------------------------
# Test groups
# ---------------------------------------------------------------------------

def test_vault_lifecycle(tmpdir: Path):
    """Test create, list, info, link_project, archive, delete."""
    print("\n[vault lifecycle]")
    root = tmpdir / ".loredocs"
    storage = VaultStorage(root=root)
    ctx = make_ctx(storage)

    # vault_create - success
    result = run(vault_create(VaultCreateInput(name="Alpha", description="Test vault", tags=["a", "b"]), ctx))
    data = json.loads(result)
    vault_id = data["id"]
    assert_ok(data["name"] == "Alpha", "vault_create returns new vault JSON with correct name")

    # vault_list - markdown
    result = run(vault_list(VaultListInput(), ctx))
    assert_ok("Alpha" in result, "vault_list shows created vault in markdown")

    # vault_list - JSON format
    result = run(vault_list(VaultListInput(response_format="json"), ctx))
    vaults = json.loads(result)
    assert_ok(len(vaults) == 1, "vault_list JSON format returns list with one entry")

    # vault_list - empty
    storage2 = VaultStorage(root=(tmpdir / "empty" / ".pv"))
    ctx2 = make_ctx(storage2)
    result = run(vault_list(VaultListInput(), ctx2))
    assert_ok("no vaults" in result.lower() or "create" in result.lower(),
              "vault_list with no vaults returns helpful message")

    # vault_info - by name
    result = run(vault_info(VaultIdInput(vault="Alpha"), ctx))
    assert_ok("Alpha" in result, "vault_info by name")

    # vault_info - by id
    result = run(vault_info(VaultIdInput(vault=vault_id), ctx))
    assert_ok("Alpha" in result, "vault_info by id")

    # vault_info - not found
    result = run(vault_info(VaultIdInput(vault="nonexistent_xyz"), ctx))
    assert_ok(result.startswith("Error:"), "vault_info returns error for unknown vault")

    # vault_link_project
    result = run(vault_link_project(VaultLinkProjectInput(vault="Alpha", project_name="ProjectX"), ctx))
    assert_ok("ProjectX" in result, "vault_link_project associates project name")

    # vault_archive
    result = run(vault_archive(VaultArchiveInput(vault="Alpha"), ctx))
    assert_ok("archived" in result.lower(), "vault_archive soft-deletes vault")

    # vault_archive - not found
    result = run(vault_archive(VaultArchiveInput(vault="nonexistent_xyz"), ctx))
    assert_ok(result.startswith("Error:"), "vault_archive returns error for unknown vault")

    # vault_delete - requires confirm
    # Create a second vault to test delete flow (archived vaults are not resolvable by name)
    res2 = run(vault_create(VaultCreateInput(name="ToDelete"), ctx))
    del_id = json.loads(res2)["id"]
    result = run(vault_delete(VaultDeleteInput(vault=del_id, confirm=False), ctx))
    assert_ok(result.startswith("Error:"), "vault_delete requires confirm=True")

    # vault_delete - with confirm
    result = run(vault_delete(VaultDeleteInput(vault=del_id, confirm=True), ctx))
    assert_ok("deleted" in result.lower(), "vault_delete with confirm=True permanently deletes")


def test_document_management(tmpdir: Path):
    """Test add, get, update, list, tag, categorize, prioritize, remove documents."""
    print("\n[document management]")
    root = tmpdir / ".loredocs"
    storage = VaultStorage(root=root)
    ctx = make_ctx(storage)

    # Setup vault
    res = run(vault_create(VaultCreateInput(name="Docs"), ctx))
    vault_id = json.loads(res)["id"]

    # vault_add_doc
    result = run(vault_add_doc(DocAddInput(
        vault="Docs",
        name="Tax Notes",
        content="Section 179 deduction limit is $1,160,000 for 2023.",
        tags=["tax", "deduction"],
        category="reference",
        priority="authoritative"
    ), ctx))
    assert_ok("Tax Notes" in result, "vault_add_doc returns confirmation with doc name")

    # vault_add_doc - vault not found
    result = run(vault_add_doc(DocAddInput(vault="Nonexistent", name="X", content="Y"), ctx))
    assert_ok(result.startswith("Error:"), "vault_add_doc returns error for unknown vault")

    # vault_list_docs
    result = run(vault_list_docs(DocListInput(vault="Docs"), ctx))
    assert_ok("Tax Notes" in result, "vault_list_docs shows added document")

    # Get the doc ID from storage directly (list_documents returns a paginated dict)
    docs_result = storage.list_documents(vault_id)
    docs = docs_result["documents"]
    assert len(docs) == 1, f"expected 1 doc, got {len(docs)}"
    doc_id = docs[0]["id"]

    # vault_get_doc - by doc ID (uses doc_id field, not vault+doc)
    result = run(vault_get_doc(DocGetInput(doc_id=doc_id), ctx))
    assert_ok("Section 179" in result, "vault_get_doc by id returns content")

    # vault_get_doc - metadata only
    result = run(vault_get_doc(DocGetInput(doc_id=doc_id, include_content=False), ctx))
    assert_ok("Tax Notes" in result, "vault_get_doc with include_content=False returns metadata")

    # vault_get_doc - not found
    result = run(vault_get_doc(DocGetInput(doc_id="zzz_nonexistent_id"), ctx))
    assert_ok(result.startswith("Error:") or "not found" in result.lower(),
              "vault_get_doc returns error for unknown doc id")

    # vault_update_doc - uses doc_id field
    result = run(vault_update_doc(DocUpdateInput(
        doc_id=doc_id,
        content="Updated: Section 179 limit is $1,220,000 for 2024."
    ), ctx))
    assert_ok("updated" in result.lower() or "Updated" in result or doc_id in result,
              "vault_update_doc updates document content")

    # vault_tag_doc - uses doc_id + add_tags
    result = run(vault_tag_doc(TagDocInput(doc_id=doc_id, add_tags=["sec179", "2024"]), ctx))
    assert_ok("tag" in result.lower() or "sec179" in result.lower() or "updated" in result.lower(),
              "vault_tag_doc adds tags")

    # vault_categorize - uses doc_id + category
    result = run(vault_categorize(CategorizeInput(doc_id=doc_id, category="reference"), ctx))
    assert_ok(not result.startswith("Error:"), "vault_categorize sets category")

    # vault_set_priority - uses doc_id + priority
    result = run(vault_set_priority(SetPriorityInput(doc_id=doc_id, priority="authoritative"), ctx))
    assert_ok(not result.startswith("Error:"), "vault_set_priority sets priority")

    # vault_remove_doc - uses doc_id field
    result = run(vault_remove_doc(DocIdInput(doc_id=doc_id), ctx))
    assert_ok("removed" in result.lower() or "deleted" in result.lower() or doc_id in result,
              "vault_remove_doc removes document")

    # Confirm it's gone (list_documents returns paginated dict; check total count)
    docs_after = storage.list_documents(vault_id)
    assert_ok(docs_after["total"] == 0, "vault_remove_doc actually removes document from storage")


def test_search(tmpdir: Path):
    """Test full-text search and tag search."""
    print("\n[search]")
    root = tmpdir / ".loredocs"
    storage = VaultStorage(root=root)
    ctx = make_ctx(storage)

    run(vault_create(VaultCreateInput(name="SearchVault"), ctx))
    run(vault_add_doc(DocAddInput(
        vault="SearchVault",
        name="Passive Loss Rules",
        content="Passive activity losses can only be used to offset passive income under IRC 469.",
        tags=["passive", "tax"]
    ), ctx))
    run(vault_add_doc(DocAddInput(
        vault="SearchVault",
        name="Depreciation",
        content="MACRS depreciation schedule for residential rental property is 27.5 years.",
        tags=["depreciation", "rental"]
    ), ctx))

    # vault_search - hit
    result = run(vault_search(SearchInput(query="passive activity losses"), ctx))
    assert_ok("Passive Loss Rules" in result or "passive" in result.lower(),
              "vault_search returns matching documents")

    # vault_search - miss
    result = run(vault_search(SearchInput(query="xyzzy_no_such_term_12345"), ctx))
    assert_ok("no" in result.lower() or "0" in result or "found" in result.lower(),
              "vault_search returns empty result for no match")

    # vault_search - scoped to a vault that exists
    result = run(vault_search(SearchInput(query="depreciation", vault="SearchVault"), ctx))
    assert_ok("Depreciation" in result or "depreciation" in result.lower(),
              "vault_search scoped to vault returns matching doc")

    # vault_search_by_tag - uses singular "tag" field
    result = run(vault_search_by_tag(SearchByTagInput(tag="rental"), ctx))
    assert_ok("Depreciation" in result or "rental" in result.lower(),
              "vault_search_by_tag returns matching documents")

    # vault_search_by_tag - scoped to vault
    result = run(vault_search_by_tag(SearchByTagInput(tag="tax", vault="SearchVault"), ctx))
    assert_ok("Passive" in result or "tax" in result.lower(),
              "vault_search_by_tag scoped to vault returns matching doc")

    # vault_search_by_tag - miss
    result = run(vault_search_by_tag(SearchByTagInput(tag="zz_nonexistent_tag_zz"), ctx))
    assert_ok("no" in result.lower() or "0" in result or "found" in result.lower() or len(result) < 50,
              "vault_search_by_tag returns empty result for unknown tag")


def test_inject(tmpdir: Path):
    """Test context injection tools."""
    print("\n[inject]")
    root = tmpdir / ".loredocs"
    storage = VaultStorage(root=root)
    ctx = make_ctx(storage)

    res = run(vault_create(VaultCreateInput(name="InjectVault"), ctx))
    vault_id = json.loads(res)["id"]

    run(vault_add_doc(DocAddInput(
        vault="InjectVault",
        name="Rule 1",
        content="Always use straight quotes in Python source."
    ), ctx))

    # Get doc ID for inject (list_documents returns a paginated dict)
    docs_result = storage.list_documents(vault_id)
    doc_id = docs_result["documents"][0]["id"]

    # vault_inject - takes doc_ids list (not vault)
    result = run(vault_inject(InjectInput(doc_ids=[doc_id]), ctx))
    assert_ok("Rule 1" in result or "Always use straight quotes" in result,
              "vault_inject loads document content by ID")

    # vault_inject - unknown doc ids should not crash
    result = run(vault_inject(InjectInput(doc_ids=["zzz_fake_doc_id_xyz"]), ctx))
    # Should return something (either empty or error message), not raise an exception
    assert_ok(isinstance(result, str), "vault_inject handles unknown doc IDs without crash")

    # vault_inject_summary - by vault name
    result = run(vault_inject_summary(InjectSummaryInput(vault="InjectVault"), ctx))
    assert_ok("InjectVault" in result, "vault_inject_summary returns vault overview")

    # vault_inject_summary - vault not found
    result = run(vault_inject_summary(InjectSummaryInput(vault="nonexistent_vault_xyz"), ctx))
    assert_ok(result.startswith("Error:") or "not found" in result.lower(),
              "vault_inject_summary returns error for unknown vault")


def test_tier_management(tmpdir: Path):
    """Test tier status and switching."""
    print("\n[tier management]")
    root = tmpdir / ".loredocs"
    storage = VaultStorage(root=root)
    ctx = make_ctx(storage)

    # vault_tier_status - default is free
    result = run(vault_tier_status(VaultTierStatusInput(), ctx))
    assert_ok("free" in result.lower() or "tier" in result.lower(),
              "vault_tier_status shows current tier")

    # vault_set_tier - upgrade to pro
    result = run(vault_set_tier(VaultSetTierInput(tier="pro"), ctx))
    assert_ok("pro" in result.lower(), "vault_set_tier upgrades to pro")

    # vault_tier_status - now pro
    result = run(vault_tier_status(VaultTierStatusInput(), ctx))
    assert_ok("pro" in result.lower(), "vault_tier_status shows pro after upgrade")

    # vault_set_tier - downgrade to free
    result = run(vault_set_tier(VaultSetTierInput(tier="free"), ctx))
    assert_ok("free" in result.lower(), "vault_set_tier downgrades to free")


def test_tier_limits(tmpdir: Path):
    """Test that free tier limits are enforced at the tool layer."""
    print("\n[tier limits]")
    root = tmpdir / ".loredocs"
    storage = VaultStorage(root=root)
    ctx = make_ctx(storage)

    # Free tier allows 3 vaults; create 3 and verify the 4th is blocked
    for i in range(3):
        result = run(vault_create(VaultCreateInput(name=f"Vault{i}"), ctx))
        assert_ok(json.loads(result)["name"] == f"Vault{i}",
                  f"vault_create Vault{i} succeeds (free tier, within limit)")

    result = run(vault_create(VaultCreateInput(name="Vault4"), ctx))
    assert_ok(result.startswith("Error:") or "limit" in result.lower(),
              "vault_create 4th vault is blocked by free tier limit")

    # Upgrade to pro and verify 4th vault now succeeds
    run(vault_set_tier(VaultSetTierInput(tier="pro"), ctx))
    result = run(vault_create(VaultCreateInput(name="Vault4"), ctx))
    assert_ok(not result.startswith("Error:"), "vault_create 4th vault allowed after pro upgrade")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print("LoreDocs MCP Tool-Layer Tests")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        base = Path(tmpdir)

        tests = [
            ("vault lifecycle", test_vault_lifecycle, base / "lifecycle"),
            ("document management", test_document_management, base / "docs"),
            ("search", test_search, base / "search"),
            ("inject", test_inject, base / "inject"),
            ("tier management", test_tier_management, base / "tiers"),
            ("tier limits", test_tier_limits, base / "limits"),
        ]

        for name, fn, path in tests:
            try:
                fn(path)
            except Exception as exc:
                import traceback
                global FAIL
                FAIL += 1
                print(f"  [FAIL] {name} test crashed: {exc}")
                traceback.print_exc()

    print("\n" + "=" * 60)
    print(f"Results: {PASS} passed, {FAIL} failed")
    print("=" * 60)
    sys.exit(0 if FAIL == 0 else 1)


if __name__ == "__main__":
    main()
