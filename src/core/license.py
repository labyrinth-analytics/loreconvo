"""
LoreConvo License Key Validation

Validates offline-verifiable Ed25519 license keys issued by Labyrinth Analytics.

License key format:
    LAB-{base64url(payload_utf8)}.{base64url(signature)}

Payload JSON fields:
    product  -- "loreconvo" | "loredocs" | "lore_suite"
    tier     -- "pro"
    exp      -- expiry date "YYYY-MM-DD" (or "never" for lifetime)
    iss      -- issuer version "1.0"
    email    -- optional, customer email for support reference

Verification steps:
    1. Split key on "." to get encoded_payload and encoded_sig
    2. Decode both from base64url (no padding)
    3. Verify Ed25519 signature of payload bytes using embedded public key
    4. Parse payload JSON
    5. Check product matches "loreconvo" or "lore_suite"
    6. Check expiry >= today (or "never")
    7. Return validated payload dict if all checks pass, else raise LicenseError

Dev bypass:
    If LAB_DEV_MODE=1 is set in the environment, any non-empty LORECONVO_PRO
    value activates Pro without license key validation.  This is for internal
    agent use only.  The public-facing plugin .mcp.json files must NOT include
    LAB_DEV_MODE.
"""

import base64
import json
import os
from datetime import date
from typing import Optional

# Ed25519 public key for license verification (base64-encoded raw bytes, 32 bytes).
# The corresponding private key is held securely by Labyrinth Analytics and is
# NEVER embedded in the product.  This public key can only verify keys; it cannot
# generate new ones.
_LAB_PUBLIC_KEY_B64 = "2Y++SKM6ZVAz1T8f0EGinoLWlQ9wdZFwEelAYDb1hT0="

# Products this module accepts in license keys.
_VALID_PRODUCTS = {"loreconvo", "lore_suite"}

# Minimum key prefix that all Labyrinth license keys start with.
_KEY_PREFIX = "LAB-"


class LicenseError(Exception):
    """Raised when a license key is invalid, expired, or wrong product."""


def _load_public_key():
    """Load the embedded Labyrinth Ed25519 public key."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
    raw = base64.b64decode(_LAB_PUBLIC_KEY_B64)
    return Ed25519PublicKey.from_public_bytes(raw)


def _b64url_decode(s: str) -> bytes:
    """Decode a base64url string (with or without padding)."""
    # Add padding if needed
    s = s + "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s)


def validate_license_key(key: str) -> dict:
    """Validate a Labyrinth license key for LoreConvo.

    Returns the payload dict on success.
    Raises LicenseError with a human-readable message on failure.

    Args:
        key: A LAB-... license key string.

    Returns:
        dict with fields: product, tier, exp, iss, email (optional).
    """
    from cryptography.exceptions import InvalidSignature

    if not key or not key.startswith(_KEY_PREFIX):
        raise LicenseError(
            "Invalid license key format. "
            "Keys must start with 'LAB-'. "
            "Get a license key at labyrinthanalyticsconsulting.com."
        )

    body = key[len(_KEY_PREFIX):]
    parts = body.split(".")
    if len(parts) != 2:
        raise LicenseError(
            "Malformed license key: expected LAB-{payload}.{signature}."
        )

    encoded_payload, encoded_sig = parts[0], parts[1]

    try:
        payload_bytes = _b64url_decode(encoded_payload)
        sig_bytes = _b64url_decode(encoded_sig)
    except Exception:
        raise LicenseError("License key contains invalid base64 encoding.")

    # Verify Ed25519 signature
    pub_key = _load_public_key()
    try:
        pub_key.verify(sig_bytes, payload_bytes)
    except InvalidSignature:
        raise LicenseError(
            "License key signature is invalid. "
            "The key may be corrupted or was not issued by Labyrinth Analytics."
        )

    # Parse payload
    try:
        payload = json.loads(payload_bytes.decode("utf-8"))
    except Exception:
        raise LicenseError("License key payload could not be decoded.")

    # Check product
    product = payload.get("product", "")
    if product not in _VALID_PRODUCTS:
        raise LicenseError(
            f"This license key is for '{product}', not LoreConvo. "
            "Please use the correct license key for this product."
        )

    # Check tier
    if payload.get("tier") != "pro":
        raise LicenseError(
            "License key does not grant Pro access. "
            "Contact support at labyrinthanalyticsconsulting.com."
        )

    # Check expiry
    exp = payload.get("exp", "")
    if exp != "never":
        try:
            exp_date = date.fromisoformat(exp)
        except ValueError:
            raise LicenseError(f"License key has invalid expiry date format: '{exp}'.")
        if exp_date < date.today():
            raise LicenseError(
                f"License key expired on {exp}. "
                "Renew at labyrinthanalyticsconsulting.com."
            )

    return payload


def is_pro_licensed(env_value: Optional[str] = None) -> bool:
    """Check whether the current environment has a valid Pro license.

    Reads LORECONVO_PRO from the environment if env_value is not provided.

    Returns:
        True if Pro is unlocked (valid key or dev bypass).
        False if free tier should apply.
    """
    if env_value is None:
        env_value = os.environ.get("LORECONVO_PRO", "").strip()

    if not env_value:
        return False

    # Dev bypass for internal agents only.
    # LAB_DEV_MODE=1 must ALSO be set -- it is not included in public .mcp.json files.
    dev_mode = os.environ.get("LAB_DEV_MODE", "").strip() == "1"
    if dev_mode and env_value and not env_value.startswith(_KEY_PREFIX):
        return True

    # Validate as a real license key
    try:
        validate_license_key(env_value)
        return True
    except LicenseError:
        return False


def get_license_status(env_value: Optional[str] = None) -> dict:
    """Return a dict describing the current license status.

    Useful for diagnostics and the MCP get_tier tool.

    Returns dict with keys:
        is_pro       -- bool
        mode         -- "dev_bypass" | "licensed" | "free" | "invalid_key"
        product      -- from payload (if licensed)
        exp          -- expiry (if licensed)
        email        -- customer email (if licensed, if present)
        error        -- error message (if invalid_key)
    """
    if env_value is None:
        env_value = os.environ.get("LORECONVO_PRO", "").strip()

    if not env_value:
        return {"is_pro": False, "mode": "free"}

    dev_mode = os.environ.get("LAB_DEV_MODE", "").strip() == "1"
    if dev_mode and not env_value.startswith(_KEY_PREFIX):
        return {"is_pro": True, "mode": "dev_bypass"}

    try:
        payload = validate_license_key(env_value)
        return {
            "is_pro": True,
            "mode": "licensed",
            "product": payload.get("product"),
            "exp": payload.get("exp"),
            "email": payload.get("email"),
        }
    except LicenseError as e:
        return {"is_pro": False, "mode": "invalid_key", "error": str(e)}
