#!/usr/bin/env python3
"""Quick integration test for ProjectVault storage layer."""

import tempfile
import sys
from pathlib import Path

# Add project to path
sys.path.insert(0, str(Path(__file__).parent))

from projectvault.storage import VaultStorage


def test_full_workflow():
    """Test the complete vault lifecycle: create, add docs, search, tag, version, export."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir) / ".projectvault"
        storage = VaultStorage(root=root)

        print("[1] Creating vaults...")
        v1 = storage.create_vault("Tax Reference 2025", description="Tax documents for 2025 filing",
                                   tags=["tax", "2025"])
        v2 = storage.create_vault("Rental Properties", description="Property management docs",
                                   tags=["rental", "property"])
        assert v1["name"] == "Tax Reference 2025"
        assert v2["name"] == "Rental Properties"
        print(f"    [OK] Created vaults: {v1['id']}, {v2['id']}")

        print("[2] Listing vaults...")
        vaults = storage.list_vaults()
        assert len(vaults) == 2
        print(f"    [OK] Found {len(vaults)} vaults")

        print("[3] Adding documents...")
        d1 = storage.add_document_from_text(
            v1["id"], "Depreciation Schedule",
            "Annual depreciation for Centaur property: $10,227\nAnnual depreciation for Minotaur property: $8,500",
            tags=["depreciation", "schedule-e"], category="reference", priority="authoritative"
        )
        d2 = storage.add_document_from_text(
            v1["id"], "Rental Income Summary",
            "Centaur gross rents: $42,000\nMinotaur gross rents: $31,200\nTotal: $73,200",
            tags=["income", "schedule-e"], category="report"
        )
        d3 = storage.add_document_from_text(
            v2["id"], "Centaur Property Details",
            "Virginia Ave triplex, 3 units, purchased 2019.\nMortgage lender: Mr. Cooper.\nMonthly mortgage: $1,850.",
            tags=["centaur", "property-details"], category="reference"
        )
        assert d1 is not None
        assert d2 is not None
        assert d3 is not None
        print(f"    [OK] Added 3 documents: {d1['id']}, {d2['id']}, {d3['id']}")

        print("[4] Getting document with content...")
        doc = storage.get_document(d1["id"])
        content = storage.get_document_content(d1["id"])
        assert doc["name"] == "Depreciation Schedule"
        assert "Centaur" in content
        print(f"    [OK] Retrieved '{doc['name']}' with {len(content)} chars")

        print("[5] Listing documents in vault...")
        listing = storage.list_documents(v1["id"])
        assert listing["total"] == 2
        print(f"    [OK] Found {listing['total']} docs in Tax vault")

        print("[6] Full-text search (single vault)...")
        results = storage.search("depreciation", vault_id=v1["id"])
        assert results["count"] >= 1
        assert results["results"][0]["doc_name"] == "Depreciation Schedule"
        print(f"    [OK] Found {results['count']} results for 'depreciation'")

        print("[7] Cross-vault search...")
        results = storage.search("Centaur")
        assert results["count"] >= 2  # Should find in both vaults
        print(f"    [OK] Found {results['count']} results for 'Centaur' across all vaults")

        print("[8] Search by tag...")
        tagged = storage.search_by_tag("schedule-e")
        assert len(tagged) == 2
        print(f"    [OK] Found {len(tagged)} docs with tag 'schedule-e'")

        print("[9] Tagging documents...")
        new_tags = storage.tag_document(d1["id"], add_tags=["2025", "irs"])
        assert "2025" in new_tags
        assert "irs" in new_tags
        assert "depreciation" in new_tags  # Original tag preserved
        print(f"    [OK] Tags after add: {new_tags}")

        new_tags = storage.tag_document(d1["id"], remove_tags=["irs"])
        assert "irs" not in new_tags
        print(f"    [OK] Tags after remove: {new_tags}")

        print("[10] Bulk tagging...")
        count = storage.bulk_tag([d1["id"], d2["id"]], add_tags=["tax-2025"])
        assert count == 2
        print(f"    [OK] Bulk-tagged {count} documents")

        print("[11] Version history...")
        # Update content to trigger versioning
        storage.update_document(d1["id"], content=b"Updated depreciation: $10,500 Centaur, $8,700 Minotaur")
        storage.update_document(d1["id"], content=b"Final depreciation: $10,500 Centaur, $8,700 Minotaur, $500 equipment")
        doc = storage.get_document(d1["id"])
        assert doc["version_count"] == 3
        history = storage.get_doc_history(d1["id"])
        assert len(history) == 3
        print(f"    [OK] Document has {doc['version_count']} versions")

        print("[12] Cross-vault copy...")
        copied = storage.copy_document(d1["id"], v2["id"])
        assert copied is not None
        assert copied["vault_id"] == v2["id"]
        v2_docs = storage.list_documents(v2["id"])
        assert v2_docs["total"] == 2  # Original + copied
        print(f"    [OK] Copied doc to Rental vault, now has {v2_docs['total']} docs")

        print("[13] Cross-vault move...")
        moved = storage.move_document(d2["id"], v2["id"])
        assert moved is not None
        v1_docs = storage.list_documents(v1["id"])
        v2_docs = storage.list_documents(v2["id"])
        assert v1_docs["total"] == 1  # Only depreciation left
        assert v2_docs["total"] == 3
        print(f"    [OK] Moved doc. Tax vault: {v1_docs['total']}, Rental vault: {v2_docs['total']}")

        print("[14] Link project...")
        storage.link_project(v1["id"], "Tax Prep 2025")
        storage.link_project(v1["id"], "Property Accounting")
        vault = storage.get_vault(v1["id"])
        assert len(vault["linked_projects"]) == 2
        print(f"    [OK] Linked projects: {vault['linked_projects']}")

        print("[15] Find vault by name...")
        found = storage.find_vault_by_name("rental properties")
        assert found is not None
        assert found["name"] == "Rental Properties"
        print(f"    [OK] Found vault by name: {found['name']}")

        print("[16] Export vault...")
        export_dir = Path(tmpdir) / "export"
        count = storage.export_vault(v2["id"], export_dir)
        assert count == 3
        assert export_dir.exists()
        exported_files = list(export_dir.iterdir())
        print(f"    [OK] Exported {count} files: {[f.name for f in exported_files]}")

        print("[17] Import directory...")
        import_vault = storage.create_vault("Imported Docs")
        imported = storage.import_directory(import_vault["id"], export_dir, tags=["imported"])
        assert len(imported) == 3
        print(f"    [OK] Imported {len(imported)} files")

        print("[18] Archive vault...")
        storage.archive_vault(v2["id"])
        active_vaults = storage.list_vaults(include_archived=False)
        all_vaults = storage.list_vaults(include_archived=True)
        assert len(active_vaults) == len(all_vaults) - 1
        print(f"    [OK] Active: {len(active_vaults)}, Total: {len(all_vaults)}")

        print("[19] Soft delete document...")
        storage.remove_document(d1["id"])
        doc = storage.get_document(d1["id"])
        assert doc is None  # Hidden after soft delete
        v1_docs = storage.list_documents(v1["id"])
        assert v1_docs["total"] == 0
        print(f"    [OK] Soft-deleted doc is hidden from queries")

        print("[20] Delete vault...")
        storage.delete_vault(v1["id"])
        vault = storage.get_vault(v1["id"])
        assert vault is None
        print(f"    [OK] Vault permanently deleted")

        print()
        print("=" * 50)
        print("ALL 20 TESTS PASSED")
        print("=" * 50)


if __name__ == "__main__":
    test_full_workflow()
