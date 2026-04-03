"""
Tests for LoreConvo license key validation (src/core/license.py).

Uses a dedicated TEST keypair -- the production signing key is never embedded
in source or tests. Tests patch the module-level public key constant so they
are completely isolated from production keys.
"""

import base64
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

# Add src/ to path so we can import core modules (same pattern as other tests)
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# ---------------------------------------------------------------------------
# Test keypair (generated for tests only -- NOT the production signing key)
# ---------------------------------------------------------------------------

TEST_PUBLIC_KEY_B64 = "nTuyInWLiA0jY37WsOziSY41NfWplU5BDNiKGW4tjmU="

# Pre-signed test license keys generated with the test private key above.
# These are stable -- they do not change unless the test keypair changes.

LC_KEY = (
    "LAB-eyJlbWFpbCI6InRlc3RAZXhhbXBsZS5jb20iLCJleHAiOiIyMDk5LTAxLTAxIiwi"
    "aXNzIjoiMS4wIiwicHJvZHVjdCI6ImxvcmVjb252byIsInRpZXIiOiJwcm8ifQ.UP9r6D"
    "qf0J9D3ZIl7wunUHhzb27HNCily236UL4bCSKE8-uSvae7M2VTOuU6nEBCcx1L_0w_rrF"
    "TPB84KW8oDg"
)
SUITE_KEY = (
    "LAB-eyJlbWFpbCI6InRlc3RAZXhhbXBsZS5jb20iLCJleHAiOiIyMDk5LTAxLTAxIiwi"
    "aXNzIjoiMS4wIiwicHJvZHVjdCI6ImxvcmVfc3VpdGUiLCJ0aWVyIjoicHJvIn0.uSHq4"
    "BIx80u_Ai6kfs2alrlgrMpz0XoVyjOV7vkrROQQD_oVJkPHE7o0WCFiloJFs6z6gtaQFv"
    "Cb9N0PjVWEBQ"
)
EXPIRED_KEY = (
    "LAB-eyJlbWFpbCI6InRlc3RAZXhhbXBsZS5jb20iLCJleHAiOiIyMDIwLTAxLTAxIiwi"
    "aXNzIjoiMS4wIiwicHJvZHVjdCI6ImxvcmVjb252byIsInRpZXIiOiJwcm8ifQ.-5oYjz"
    "Z5aPx66h5Ws3h1FC2FKQ36m8RPPwd8Q_6HvbJLJEYo75kp91lhVrpQHxeCUKxrG-qmIc4"
    "7aANUt6CAAA"
)
WRONG_PROD_KEY = (
    "LAB-eyJlbWFpbCI6InRlc3RAZXhhbXBsZS5jb20iLCJleHAiOiIyMDk5LTAxLTAxIiwi"
    "aXNzIjoiMS4wIiwicHJvZHVjdCI6ImxvcmVkb2NzIiwidGllciI6InBybyJ9.ezyOm0OD"
    "A4eC1YwSmXfifltCFIf2mlO6hhZdtsUDGeaH6xIQtHf5Qd-Poe6ewN3wwCq6XFcN4Q_H"
    "aOFqoE-9Cg"
)
NEVER_KEY = (
    "LAB-eyJlbWFpbCI6InRlc3RAZXhhbXBsZS5jb20iLCJleHAiOiJuZXZlciIsImlzcyI6"
    "IjEuMCIsInByb2R1Y3QiOiJsb3JlY29udm8iLCJ0aWVyIjoicHJvIn0.7hSl1H0lKvc3"
    "Bu_xeLUWSenBgq-RcQKIrmtGAucEuakK7-Jo7f735F1L_hOGl7zyv5swl8k9ANq9dKLAO"
    "-BkCQ"
)


def _patch_pubkey():
    """Swap in the test public key so tests never depend on the production key."""
    import core.license as lic_mod
    return patch.object(lic_mod, "_LAB_PUBLIC_KEY_B64", TEST_PUBLIC_KEY_B64)


class TestValidateLicenseKey(unittest.TestCase):
    """validate_license_key() with the test signing key."""

    def test_valid_loreconvo_key(self):
        from core.license import validate_license_key
        with _patch_pubkey():
            payload = validate_license_key(LC_KEY)
        self.assertEqual(payload["product"], "loreconvo")
        self.assertEqual(payload["tier"], "pro")
        self.assertEqual(payload["exp"], "2099-01-01")

    def test_valid_lore_suite_key(self):
        from core.license import validate_license_key
        with _patch_pubkey():
            payload = validate_license_key(SUITE_KEY)
        self.assertEqual(payload["product"], "lore_suite")

    def test_never_expiry_key(self):
        from core.license import validate_license_key
        with _patch_pubkey():
            payload = validate_license_key(NEVER_KEY)
        self.assertEqual(payload["exp"], "never")

    def test_expired_key_raises(self):
        from core.license import validate_license_key, LicenseError
        with _patch_pubkey():
            with self.assertRaises(LicenseError) as ctx:
                validate_license_key(EXPIRED_KEY)
        self.assertIn("expired", str(ctx.exception).lower())

    def test_wrong_product_raises(self):
        from core.license import validate_license_key, LicenseError
        with _patch_pubkey():
            with self.assertRaises(LicenseError) as ctx:
                validate_license_key(WRONG_PROD_KEY)
        self.assertIn("loredocs", str(ctx.exception))

    def test_missing_prefix_raises(self):
        from core.license import validate_license_key, LicenseError
        with _patch_pubkey():
            with self.assertRaises(LicenseError) as ctx:
                validate_license_key("not-a-lab-key")
        self.assertIn("LAB-", str(ctx.exception))

    def test_empty_string_raises(self):
        from core.license import validate_license_key, LicenseError
        with _patch_pubkey():
            with self.assertRaises(LicenseError):
                validate_license_key("")

    def test_tampered_payload_raises(self):
        """Changing the payload should invalidate the signature."""
        from core.license import validate_license_key, LicenseError
        parts = LC_KEY[4:].split(".")
        tampered_payload = base64.urlsafe_b64encode(b"tampered").rstrip(b"=").decode()
        tampered_key = f"LAB-{tampered_payload}.{parts[1]}"
        with _patch_pubkey():
            with self.assertRaises(LicenseError) as ctx:
                validate_license_key(tampered_key)
        self.assertIn("invalid", str(ctx.exception).lower())

    def test_tampered_signature_raises(self):
        """Changing the signature should fail verification."""
        from core.license import validate_license_key, LicenseError
        parts = LC_KEY[4:].split(".")
        bad_sig = base64.urlsafe_b64encode(b"x" * 64).rstrip(b"=").decode()
        tampered_key = f"LAB-{parts[0]}.{bad_sig}"
        with _patch_pubkey():
            with self.assertRaises(LicenseError) as ctx:
                validate_license_key(tampered_key)
        self.assertIn("invalid", str(ctx.exception).lower())

    def test_malformed_no_dot_raises(self):
        from core.license import validate_license_key, LicenseError
        with _patch_pubkey():
            with self.assertRaises(LicenseError) as ctx:
                validate_license_key("LAB-nodothere")
        self.assertIn("Malformed", str(ctx.exception))

    def test_wrong_pubkey_rejects_valid_key(self):
        """A key signed with the test private key must not validate under the prod key."""
        # This test uses the REAL production public key (default) to verify test keys.
        # Since test keys were signed by a DIFFERENT private key, they must be rejected.
        from core.license import validate_license_key, LicenseError
        # Do NOT patch pubkey -- let it use the real production key
        with self.assertRaises(LicenseError):
            validate_license_key(LC_KEY)


class TestIsProLicensed(unittest.TestCase):
    """is_pro_licensed() env var integration."""

    def test_empty_env_is_free(self):
        from core.license import is_pro_licensed
        with patch.dict(os.environ, {"LORECONVO_PRO": ""}, clear=False):
            self.assertFalse(is_pro_licensed())

    def test_no_env_is_free(self):
        from core.license import is_pro_licensed
        env = {k: v for k, v in os.environ.items() if k != "LORECONVO_PRO"}
        with patch.dict(os.environ, env, clear=True):
            self.assertFalse(is_pro_licensed())

    def test_valid_key_is_pro(self):
        from core.license import is_pro_licensed
        with _patch_pubkey():
            with patch.dict(os.environ, {"LORECONVO_PRO": LC_KEY, "LAB_DEV_MODE": ""}, clear=False):
                self.assertTrue(is_pro_licensed())

    def test_expired_key_is_free(self):
        from core.license import is_pro_licensed
        with _patch_pubkey():
            with patch.dict(os.environ, {"LORECONVO_PRO": EXPIRED_KEY, "LAB_DEV_MODE": ""}, clear=False):
                self.assertFalse(is_pro_licensed())

    def test_dev_bypass_with_dev_mode(self):
        """LORECONVO_PRO=1 + LAB_DEV_MODE=1 -> Pro (internal agents)."""
        from core.license import is_pro_licensed
        with patch.dict(os.environ, {"LORECONVO_PRO": "1", "LAB_DEV_MODE": "1"}, clear=False):
            self.assertTrue(is_pro_licensed())

    def test_dev_value_without_dev_mode_is_free(self):
        """LORECONVO_PRO=1 without LAB_DEV_MODE must NOT grant Pro."""
        from core.license import is_pro_licensed
        env = {k: v for k, v in os.environ.items() if k not in ("LORECONVO_PRO", "LAB_DEV_MODE")}
        env["LORECONVO_PRO"] = "1"
        with patch.dict(os.environ, env, clear=True):
            self.assertFalse(is_pro_licensed())

    def test_invalid_key_format_is_free(self):
        """An env var value that is not a valid LAB-... key must not grant Pro."""
        from core.license import is_pro_licensed
        env = {k: v for k, v in os.environ.items() if k not in ("LORECONVO_PRO", "LAB_DEV_MODE")}
        env["LORECONVO_PRO"] = "not-a-key"
        with patch.dict(os.environ, env, clear=True):
            self.assertFalse(is_pro_licensed())


class TestGetLicenseStatus(unittest.TestCase):
    """get_license_status() mode/field checks."""

    def test_free_mode(self):
        from core.license import get_license_status
        with patch.dict(os.environ, {"LORECONVO_PRO": ""}, clear=False):
            s = get_license_status()
        self.assertFalse(s["is_pro"])
        self.assertEqual(s["mode"], "free")

    def test_licensed_mode(self):
        from core.license import get_license_status
        with _patch_pubkey():
            with patch.dict(os.environ, {"LORECONVO_PRO": LC_KEY, "LAB_DEV_MODE": ""}, clear=False):
                s = get_license_status()
        self.assertTrue(s["is_pro"])
        self.assertEqual(s["mode"], "licensed")
        self.assertEqual(s["product"], "loreconvo")
        self.assertEqual(s["exp"], "2099-01-01")
        self.assertEqual(s["email"], "test@example.com")

    def test_dev_bypass_mode(self):
        from core.license import get_license_status
        with patch.dict(os.environ, {"LORECONVO_PRO": "1", "LAB_DEV_MODE": "1"}, clear=False):
            s = get_license_status()
        self.assertTrue(s["is_pro"])
        self.assertEqual(s["mode"], "dev_bypass")

    def test_invalid_key_mode(self):
        from core.license import get_license_status
        env = {k: v for k, v in os.environ.items() if k not in ("LORECONVO_PRO", "LAB_DEV_MODE")}
        env["LORECONVO_PRO"] = "LAB-garbage.trash"
        with _patch_pubkey():
            with patch.dict(os.environ, env, clear=True):
                s = get_license_status()
        self.assertFalse(s["is_pro"])
        self.assertEqual(s["mode"], "invalid_key")
        self.assertIn("error", s)

    def test_expired_key_invalid_mode(self):
        from core.license import get_license_status
        env = {k: v for k, v in os.environ.items() if k not in ("LORECONVO_PRO", "LAB_DEV_MODE")}
        env["LORECONVO_PRO"] = EXPIRED_KEY
        with _patch_pubkey():
            with patch.dict(os.environ, env, clear=True):
                s = get_license_status()
        self.assertFalse(s["is_pro"])
        self.assertEqual(s["mode"], "invalid_key")

    def test_suite_key_accepted(self):
        """lore_suite keys should also work for LoreConvo."""
        from core.license import get_license_status
        with _patch_pubkey():
            with patch.dict(os.environ, {"LORECONVO_PRO": SUITE_KEY, "LAB_DEV_MODE": ""}, clear=False):
                s = get_license_status()
        self.assertTrue(s["is_pro"])
        self.assertEqual(s["product"], "lore_suite")


class TestConfigIsProProperty(unittest.TestCase):
    """Config.is_pro uses the license validator."""

    def test_config_is_pro_with_valid_key(self):
        from core.config import Config
        with _patch_pubkey():
            with patch.dict(os.environ, {"LORECONVO_PRO": LC_KEY, "LAB_DEV_MODE": ""}, clear=False):
                cfg = Config()
                self.assertTrue(cfg.is_pro)

    def test_config_is_pro_free_with_empty_env(self):
        from core.config import Config
        with patch.dict(os.environ, {"LORECONVO_PRO": ""}, clear=False):
            cfg = Config()
            self.assertFalse(cfg.is_pro)

    def test_config_is_pro_with_dev_bypass(self):
        from core.config import Config
        with patch.dict(os.environ, {"LORECONVO_PRO": "1", "LAB_DEV_MODE": "1"}, clear=False):
            cfg = Config()
            self.assertTrue(cfg.is_pro)

    def test_config_old_env_var_1_without_dev_mode_is_free(self):
        """The old pattern LORECONVO_PRO=1 alone must NOT grant Pro any more."""
        from core.config import Config
        env = {k: v for k, v in os.environ.items() if k not in ("LORECONVO_PRO", "LAB_DEV_MODE")}
        env["LORECONVO_PRO"] = "1"
        with patch.dict(os.environ, env, clear=True):
            cfg = Config()
            self.assertFalse(cfg.is_pro)


if __name__ == "__main__":
    unittest.main()
