"""GENERATED from scripts/lib/secret_redaction.py -- do not edit.

Regenerate with: .venv/bin/python scripts/generate_secret_redaction.py
The products ship standalone to PyPI and cannot import scripts/lib directly,
so this is a byte-identical copy of the canonical module's body
(CLAUDE.md drift rules 1, 3, 4: one human-edited source, products get a
generated copy). --check mode runs in safe_git.py and release.sh.
"""

import re

REDACTION_MARKER = "[REDACTED]"

# PEM body: base64 plus PEM header punctuation, not [\s\S] -- bounded at
# 16 KiB so a BEGIN with no matching END costs at most one bounded scan per
# start position [r4/ops-H2].
_PEM_BODY_CHARS = r"[A-Za-z0-9+/=\s:,\-]"

_PATTERNS = [
    # AWS access key ID
    re.compile(r"AKIA[0-9A-Z]{16}"),
    # Bare provider keys -- a key pasted standalone (no name=value wrapper)
    # was previously only caught inside an assignment [r4 gap]. Ordered
    # most-specific first so sk-ant- is consumed before the generic sk- match.
    re.compile(r"sk-ant-[A-Za-z0-9_-]{16,}"),   # Anthropic API key
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),       # OpenAI (sk- / sk-proj- / sk-svcacct-)
    re.compile(r"ghp_[A-Za-z0-9]{20,}"),        # GitHub classic PAT
    re.compile(r"xoxb-[A-Za-z0-9-]{20,}"),      # Slack bot token
    # Lore license key (SH-107003): LAB-{base64url(payload)}.{base64url(sig)}
    # per ron_skills/loreconvo/src/core/license.py. Real keys carry an ~80-130
    # char payload (it includes the customer email and expiry) and an 86-char
    # Ed25519 signature, so {20,} is a safe floor. Must run before the generic
    # assignment rule so LORECONVO_PRO=LAB-... is consumed whole, dot included.
    re.compile(r"LAB-[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}"),
    # AWS secret access key -- self-contained: the aws_secret_access_key
    # keyword is part of the match, so no cross-field pairing is needed or
    # claimed [r4/sec-H3].
    re.compile(
        r"(?i)aws[_-]?secret[_-]?(access[_-]?)?key\s*[=:]\s*['\"]?[A-Za-z0-9/+=]{40}"
    ),
    # Generic API-key/secret/password/token/license-key assignment. The Lore
    # Pro env names (LORECONVO_PRO / LOREDOCS_PRO, SH-107003) are listed so a
    # truncated or malformed key value (no "." so the bare rule above misses
    # it) is still redacted; a dev-mode LORECONVO_PRO=1 is too short to match.
    re.compile(
        r"(?i)(api[_-]?key|secret|password|token|license[_-]?key|lore(?:convo|docs)_pro)"
        r"\s*[=:]\s*['\"]?[A-Za-z0-9_\-]{16,}"
    ),
    # Bearer token.
    re.compile(r"(?i)bearer\s+[A-Za-z0-9_\-.]{20,}"),
    # JWT.
    re.compile(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"),
    # PEM private key block (OPENSSH PRIVATE KEY is covered by [A-Z ]*).
    re.compile(
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----"
        + _PEM_BODY_CHARS
        + r"{1,16384}?-----END [A-Z ]*PRIVATE KEY-----"
    ),
]


def redact_secrets(text):
    """Replace every matched credential shape in text with the generic marker.

    Returns (redacted_text, match_count). Pure function; caller decides what
    to do with match_count -- no I/O, no state. Never log the input or
    output of this call [r4/sec-H7]: a redaction path that logs raw text
    before redacting it defeats the control.
    """
    if not text:
        return text, 0
    count = 0
    for pattern in _PATTERNS:
        text, n = pattern.subn(REDACTION_MARKER, text)
        count += n
    return text, count


def redact_value(value):
    """Recursively redact string values inside nested dicts/lists.

    Dict KEYS and non-string scalars (int/float/bool/None) are returned
    unchanged -- a key is a field name, not a value [r4/dm-H1]. Returns
    (new_value, total_match_count).
    """
    if isinstance(value, str):
        return redact_secrets(value)
    if isinstance(value, dict):
        total = 0
        out = {}
        for key, sub_value in value.items():
            new_sub_value, n = redact_value(sub_value)
            out[key] = new_sub_value
            total += n
        return out, total
    if isinstance(value, list):
        total = 0
        out = []
        for item in value:
            new_item, n = redact_value(item)
            out.append(new_item)
            total += n
        return out, total
    return value, 0
