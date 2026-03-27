#!/usr/bin/env python3
"""Integration tests for LoreDocs Phase 2 features:
vault_link_doc, vault_unlink_doc, vault_find_related, vault_suggest, vault_export_manifest.
"""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from loredocs.storage import VaultStorage


def _setup(tmpdir: str) -> tuple:
    """Create a storage instance with two vaults and three documents."""
    root = Path(tmpdir) / ".loredocs"
    storage = VaultStorage(root=root)

    v1 = storage.create_vault("Tax Docs", description="2025 tax docs", tags=["tax"])
    v2 = storage.create_vault("Rental Docs", description="Rental property docs", tags=["rental"])

    d1 = storage.add_document_from_text(
        v1["id"], "Depreciation Schedule",
        "Annual depreciation: $10,227",
        tags=["depreciation"], category="reference"
    )
    d2 = storage.add_document_from_text(
        v1["id"], "Schedule E Summary",
        "Total rental income: $73,200",
        tags=[], category="report"
    )
    d3 = storage.add_document_from_text(
        v2["id"], "Centaur Property Details",
        "Virginia Ave triplex, purchased 2019.",
        tags=[], category="reference"
    )
    return storage, v1, v2, d1, d2, d3


def test_link_doc_basic():
    """Test creating a link between two documents."""
    with tempfile.TemporaryDirectory() as tmpdir:
        storage, v1, v2, d1, d2, d3 = _setup(tmpdir)

        print("[1] Linking d1 -> d3 (cross-vault)...")
        result = storage.link_doc(d1["id"], d3["id"], label="references")
        assert result is not None, "link_doc returned None"
        assert result["source_doc_id"] == d1["id"]
        assert result["target_doc_id"] == d3["id"]
        assert result["label"] == "references"
        assert result.get("already_existed") is False
        print(f"    [OK] Link created: {result['id']}")

        # Should be idempotent -- second call returns already_existed=True
        print("[2] Linking same pair again (idempotency check)...")
        result2 = storage.link_doc(d1["id"], d3["id"], label="references")
        assert result2 is not None
        assert result2.get("already_existed") is True
        print("    [OK] Second link call was idempotent")

        # Link d1 -> d2 as well
        storage.link_doc(d1["id"], d2["id"], label="related")
        print("    [OK] Added second link d1 -> d2")


def test_find_related():
    """Test finding related documents."""
    with tempfile.TemporaryDirectory() as tmpdir:
        storage, v1, v2, d1, d2, d3 = _setup(tmpdir)

        storage.link_doc(d1["id"], d3["id"], label="references")
        storage.link_doc(d1["id"], d2["id"], label="related")

        print("[3] Finding docs related to d1...")
        related = storage.find_related_docs(d1["id"])
        assert len(related) == 2
        related_ids = {r["id"] for r in related}
        assert d2["id"] in related_ids
        assert d3["id"] in related_ids
        print(f"    [OK] Found {len(related)} related docs")

        # Bidirectional: d3 should see d1 as related
        print("[4] Checking bidirectionality (d3 -> d1)...")
        from_d3 = storage.find_related_docs(d3["id"])
        assert len(from_d3) == 1
        assert from_d3[0]["id"] == d1["id"]
        print("    [OK] Bidirectional link confirmed")

        # Unlinked doc has no related
        print("[5] Unlinked doc has no related docs...")
        from_d2_initially = storage.find_related_docs(d2["id"])
        # d2 was linked from d1, so it sees d1 as related
        assert len(from_d2_initially) == 1
        assert from_d2_initially[0]["id"] == d1["id"]
        print("    [OK] d2 sees d1 as related (bidirectional)")


def test_unlink_doc():
    """Test removing a link between two documents."""
    with tempfile.TemporaryDirectory() as tmpdir:
        storage, v1, v2, d1, d2, d3 = _setup(tmpdir)

        storage.link_doc(d1["id"], d3["id"], label="references")
        print("[6] Unlinking d1 <-> d3...")
        deleted = storage.unlink_doc(d1["id"], d3["id"])
        assert deleted == 2, f"Expected 2 rows deleted (bidirectional), got {deleted}"
        print(f"    [OK] Deleted {deleted} rows")

        related = storage.find_related_docs(d1["id"])
        assert len(related) == 0
        print("    [OK] d1 now has 0 related docs after unlink")

        # Unlink non-existent pair returns 0
        deleted2 = storage.unlink_doc(d1["id"], d3["id"])
        assert deleted2 == 0
        print("    [OK] Unlinking non-existent link returns 0")


def test_link_doc_invalid():
    """Test that link_doc returns None if a doc doesn't exist."""
    with tempfile.TemporaryDirectory() as tmpdir:
        storage, v1, v2, d1, d2, d3 = _setup(tmpdir)

        print("[7] Linking to non-existent doc ID...")
        result = storage.link_doc(d1["id"], "nonexistent-id-xxx", label="related")
        assert result is None
        print("    [OK] link_doc returned None for invalid doc ID")


def test_get_vault_manifest():
    """Test exporting a vault manifest."""
    with tempfile.TemporaryDirectory() as tmpdir:
        storage, v1, v2, d1, d2, d3 = _setup(tmpdir)

        storage.link_doc(d1["id"], d2["id"], label="related")

        print("[8] Generating manifest for v1...")
        manifest = storage.get_vault_manifest(v1["id"])
        assert manifest is not None
        assert manifest["document_count"] == 2
        assert manifest["link_count"] == 1  # one pair, stored bidirectionally
        assert "documents" in manifest
        assert "tag_counts" in manifest
        assert "category_counts" in manifest
        assert "depreciation" in manifest["tag_counts"]
        assert manifest["category_counts"].get("reference") == 1
        assert manifest["category_counts"].get("report") == 1
        print(f"    [OK] Manifest: {manifest['document_count']} docs, {manifest['link_count']} links")
        print(f"    [OK] Tags: {manifest['tag_counts']}")

        # Non-existent vault returns None
        assert storage.get_vault_manifest("no-such-vault") is None
        print("    [OK] Non-existent vault returns None")


def test_get_suggestions():
    """Test getting document suggestions."""
    with tempfile.TemporaryDirectory() as tmpdir:
        storage, v1, v2, d1, d2, d3 = _setup(tmpdir)

        print("[9] Getting suggestions across all vaults...")
        suggestions = storage.get_suggestions(limit=10)
        # All docs have no notes, so we should see at least one suggestion
        assert len(suggestions) > 0
        reasons = {s["reason"] for s in suggestions}
        assert "no_notes" in reasons
        print(f"    [OK] Got {len(suggestions)} suggestions, reasons: {reasons}")

        # Scope to v1 only
        print("[10] Getting suggestions for v1 only...")
        suggestions_v1 = storage.get_suggestions(vault_id=v1["id"], limit=10)
        vault_ids = {s["vault_id"] for s in suggestions_v1}
        assert all(vid == v1["id"] for vid in vault_ids), "Scoped suggestions leaked into other vault"
        print(f"    [OK] Scoped suggestions all in v1: {len(suggestions_v1)} items")

        # After adding notes/tags, doc should not appear in no_notes bucket
        storage.update_document(d1["id"], notes="Annual depreciation for Centaur/Minotaur properties")
        storage.tag_document(d1["id"], add_tags=["depreciation", "verified"])
        storage.link_doc(d1["id"], d2["id"], label="related")

        suggestions_after = storage.get_suggestions(vault_id=v1["id"], limit=10)
        d1_ids = [s["doc_id"] for s in suggestions_after if s["reason"] == "no_notes"]
        assert d1["id"] not in d1_ids, "d1 should not appear in no_notes after adding notes"
        print("    [OK] d1 no longer in no_notes suggestions after update")


if __name__ == "__main__":
    test_link_doc_basic()
    test_find_related()
    test_unlink_doc()
    test_link_doc_invalid()
    test_get_vault_manifest()
    test_get_suggestions()
    print("\n[ALL TESTS PASSED]")
