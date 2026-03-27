"""
Tests for LoreDocs tier gating logic.

Covers:
- TierEnforcer.check_vault_count (free limit = 3)
- TierEnforcer.check_doc_count   (free limit = 50 per vault)
- TierEnforcer.check_storage     (free limit = 500 MB total)
- TierEnforcer.check_version_count (free limit = 5 per doc)
- get_tier / set_tier persistence
- Storage integration: create_vault raises when over limit
- Storage integration: add_document raises when over limit
- Pro tier: all checks pass even at limit values
"""

import json
import tempfile
from pathlib import Path

import pytest

from loredocs.tiers import (
    FREE_LIMITS,
    PRO_LIMITS,
    TierEnforcer,
    TierLimitError,
    get_tier,
    set_tier,
    TIER_FREE,
    TIER_PRO,
)
from loredocs.storage import VaultStorage


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_root(tmp_path):
    """Provide a fresh temp directory as the loredocs root."""
    return tmp_path


@pytest.fixture
def free_enforcer(tmp_root):
    """TierEnforcer on a free-tier root (default)."""
    return TierEnforcer(tmp_root)


@pytest.fixture
def pro_enforcer(tmp_root):
    """TierEnforcer on a pro-tier root."""
    set_tier(tmp_root, TIER_PRO)
    return TierEnforcer(tmp_root)


@pytest.fixture
def storage(tmp_root):
    """VaultStorage on a fresh temp root (free tier)."""
    return VaultStorage(root=tmp_root)


# ---------------------------------------------------------------------------
# get_tier / set_tier
# ---------------------------------------------------------------------------

class TestTierConfig:
    def test_default_is_free(self, tmp_root):
        assert get_tier(tmp_root) == TIER_FREE

    def test_set_pro(self, tmp_root):
        set_tier(tmp_root, TIER_PRO)
        assert get_tier(tmp_root) == TIER_PRO

    def test_set_free(self, tmp_root):
        set_tier(tmp_root, TIER_PRO)
        set_tier(tmp_root, TIER_FREE)
        assert get_tier(tmp_root) == TIER_FREE

    def test_invalid_tier_raises(self, tmp_root):
        with pytest.raises(ValueError, match="Invalid tier"):
            set_tier(tmp_root, "enterprise")

    def test_config_written_to_disk(self, tmp_root):
        set_tier(tmp_root, TIER_PRO)
        config = json.loads((tmp_root / "config.json").read_text())
        assert config["tier"] == TIER_PRO

    def test_corrupted_config_defaults_to_free(self, tmp_root):
        (tmp_root / "config.json").write_text("{bad json", encoding="utf-8")
        assert get_tier(tmp_root) == TIER_FREE

    def test_unknown_tier_in_config_defaults_to_free(self, tmp_root):
        (tmp_root / "config.json").write_text(
            json.dumps({"tier": "platinum"}), encoding="utf-8"
        )
        assert get_tier(tmp_root) == TIER_FREE


# ---------------------------------------------------------------------------
# TierEnforcer -- Free tier checks
# ---------------------------------------------------------------------------

class TestFreeVaultCount:
    def test_under_limit_passes(self, free_enforcer):
        free_enforcer.check_vault_count(FREE_LIMITS.max_vaults - 1)

    def test_at_limit_raises(self, free_enforcer):
        with pytest.raises(TierLimitError):
            free_enforcer.check_vault_count(FREE_LIMITS.max_vaults)

    def test_over_limit_raises(self, free_enforcer):
        with pytest.raises(TierLimitError):
            free_enforcer.check_vault_count(FREE_LIMITS.max_vaults + 5)

    def test_error_message_contains_limit(self, free_enforcer):
        with pytest.raises(TierLimitError) as exc_info:
            free_enforcer.check_vault_count(FREE_LIMITS.max_vaults)
        assert str(FREE_LIMITS.max_vaults) in str(exc_info.value)

    def test_error_has_upgrade_hint(self, free_enforcer):
        with pytest.raises(TierLimitError) as exc_info:
            free_enforcer.check_vault_count(FREE_LIMITS.max_vaults)
        assert exc_info.value.upgrade_hint


class TestFreeDocCount:
    def test_under_limit_passes(self, free_enforcer):
        free_enforcer.check_doc_count(FREE_LIMITS.max_docs_per_vault - 1)

    def test_at_limit_raises(self, free_enforcer):
        with pytest.raises(TierLimitError):
            free_enforcer.check_doc_count(FREE_LIMITS.max_docs_per_vault)

    def test_vault_name_in_message(self, free_enforcer):
        with pytest.raises(TierLimitError) as exc_info:
            free_enforcer.check_doc_count(FREE_LIMITS.max_docs_per_vault, vault_name="My Vault")
        assert "My Vault" in str(exc_info.value)


class TestFreeStorage:
    def test_under_limit_passes(self, free_enforcer):
        free_enforcer.check_storage(0, FREE_LIMITS.max_storage_bytes - 1)

    def test_exactly_at_limit_raises(self, free_enforcer):
        with pytest.raises(TierLimitError):
            free_enforcer.check_storage(0, FREE_LIMITS.max_storage_bytes + 1)

    def test_combined_over_limit_raises(self, free_enforcer):
        half = FREE_LIMITS.max_storage_bytes // 2
        with pytest.raises(TierLimitError):
            free_enforcer.check_storage(half, half + 1)

    def test_combined_under_limit_passes(self, free_enforcer):
        half = FREE_LIMITS.max_storage_bytes // 2
        free_enforcer.check_storage(half - 1, half - 1)


class TestFreeVersionCount:
    def test_under_limit_passes(self, free_enforcer):
        free_enforcer.check_version_count(FREE_LIMITS.max_versions_per_doc - 1)

    def test_at_limit_raises(self, free_enforcer):
        with pytest.raises(TierLimitError):
            free_enforcer.check_version_count(FREE_LIMITS.max_versions_per_doc)

    def test_doc_name_in_message(self, free_enforcer):
        with pytest.raises(TierLimitError) as exc_info:
            free_enforcer.check_version_count(FREE_LIMITS.max_versions_per_doc, doc_name="spec.md")
        assert "spec.md" in str(exc_info.value)


# ---------------------------------------------------------------------------
# TierEnforcer -- Pro tier (no limits)
# ---------------------------------------------------------------------------

class TestProTierNoLimits:
    def test_vault_count_unlimited(self, pro_enforcer):
        # Should not raise at any count
        pro_enforcer.check_vault_count(10_000)

    def test_doc_count_unlimited(self, pro_enforcer):
        pro_enforcer.check_doc_count(100_000)

    def test_storage_unlimited(self, pro_enforcer):
        pro_enforcer.check_storage(10 * 1024 ** 3, 10 * 1024 ** 3)  # 20 GB

    def test_version_count_unlimited(self, pro_enforcer):
        pro_enforcer.check_version_count(10_000)


# ---------------------------------------------------------------------------
# TierEnforcer -- status_dict
# ---------------------------------------------------------------------------

class TestStatusDict:
    def test_free_status(self, free_enforcer):
        status = free_enforcer.status_dict(vault_count=1, total_bytes=10 * 1024 * 1024)
        assert status["tier"] == TIER_FREE
        assert status["is_pro"] is False
        assert status["vault_count"] == 1
        assert status["vault_limit"] == FREE_LIMITS.max_vaults
        assert status["storage_used_mb"] == pytest.approx(10.0, abs=0.1)
        assert status["storage_limit_mb"] == FREE_LIMITS.max_storage_bytes // (1024 * 1024)
        assert isinstance(status["vault_usage_pct"], float)

    def test_pro_status_has_none_limits(self, pro_enforcer):
        status = pro_enforcer.status_dict(vault_count=100, total_bytes=0)
        assert status["tier"] == TIER_PRO
        assert status["is_pro"] is True
        assert status["vault_limit"] is None
        assert status["storage_limit_mb"] is None
        assert status["vault_usage_pct"] is None


# ---------------------------------------------------------------------------
# Storage integration
# ---------------------------------------------------------------------------

class TestStorageVaultLimit:
    def test_create_up_to_limit(self, storage):
        for i in range(FREE_LIMITS.max_vaults):
            storage.create_vault(name=f"Vault {i}")

    def test_create_over_limit_raises(self, storage):
        for i in range(FREE_LIMITS.max_vaults):
            storage.create_vault(name=f"Vault {i}")
        with pytest.raises(TierLimitError):
            storage.create_vault(name="One Too Many")

    def test_archived_vault_not_counted(self, storage):
        # Create max vaults, archive one, then create again -- should succeed
        ids = []
        for i in range(FREE_LIMITS.max_vaults):
            v = storage.create_vault(name=f"Vault {i}")
            ids.append(v["id"])
        storage.archive_vault(ids[0])
        # Now count is back under limit
        storage.create_vault(name="After Archive")

    def test_pro_tier_no_vault_limit(self, storage):
        set_tier(storage.root, TIER_PRO)
        for i in range(FREE_LIMITS.max_vaults + 5):
            storage.create_vault(name=f"Vault {i}")


class TestStorageDocLimit:
    def test_add_up_to_doc_limit_passes(self, storage):
        vault = storage.create_vault(name="Test Vault")
        for i in range(FREE_LIMITS.max_docs_per_vault):
            result = storage.add_document_from_text(
                vault["id"], name=f"doc_{i}", text_content=f"content {i}",
                filename=f"doc_{i}.md"
            )
            assert result is not None

    def test_add_over_doc_limit_raises(self, storage):
        vault = storage.create_vault(name="Test Vault")
        for i in range(FREE_LIMITS.max_docs_per_vault):
            storage.add_document_from_text(
                vault["id"], name=f"doc_{i}", text_content=f"content {i}"
            )
        with pytest.raises(TierLimitError):
            storage.add_document_from_text(vault["id"], name="overflow", text_content="x")

    def test_pro_tier_no_doc_limit(self, storage):
        set_tier(storage.root, TIER_PRO)
        vault = storage.create_vault(name="Big Vault")
        for i in range(FREE_LIMITS.max_docs_per_vault + 5):
            result = storage.add_document_from_text(
                vault["id"], name=f"doc_{i}", text_content=f"content {i}"
            )
            assert result is not None
