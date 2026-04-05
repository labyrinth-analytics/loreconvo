# Security Report - 2026-04-04

**Agent:** Brock (Cybersecurity Expert)
**Date:** 2026-04-04
**Prior Report:** security_report_2026_04_03_b.md
**Overall Rating:** NEEDS ATTENTION
**Active Findings:** 8 (0 CRITICAL, 0 HIGH, 3 MEDIUM, 2 LOW, 3 INFO)

---

## Executive Summary

Today's review focused on two areas: (1) four BROCK-REVIEW items flagged by Gina in
her 2026-04-04 architecture review, and (2) new code from Ron's commits -- specifically
`scripts/local_model_preprocess.py` and the `get_tier`/`get_license_tier` MCP tools.

Key outcomes:
- SEC-014 (missing cryptography dependency): RESOLVED by Ron in commit aecf64a.
- Stability TODO #2 (get_tier MCP tool): COMPLETED correctly and safely.
- Four BROCK-REVIEW items from Gina assessed. None critical for current local-only deployment.
  One (SEC-017) has a known TODO fix; two (SEC-016, SEC-018) should be addressed before
  any multi-user or cloud deployment.
- New local_model_preprocess.py code: CLEAN. No secrets, no injection risks.
- pip-audit: CLEAN on both LoreConvo and LoreDocs.

---

## Finding Status Table

| ID | Title | Severity | Status | Owner |
|----|-------|----------|--------|-------|
| SEC-001 | Anthropic API key in .env file | INFO | Open | Debbie |
| SEC-006 | CreditManager race condition | LOW | Open | Ron |
| SEC-009 | Conda/pip mixing risk | INFO | Open | Debbie |
| SEC-011 | TOCTOU race in LoreDocs export | MEDIUM | Open | Ron |
| SEC-014 | Missing cryptography dependency | MEDIUM | RESOLVED (2026-04-04) | Ron |
| SEC-015 | Personal email in marketplace.json | LOW | Open | Debbie |
| SEC-016 | auto_save hook bypasses session limit | LOW | New (2026-04-04) | Ron |
| SEC-017 | vault_set_tier has no license validation | MEDIUM | New (2026-04-04) | Ron |
| SEC-018 | vault_import_dir/vault_export: no path restriction | INFO | New (2026-04-04) | Ron |
| SEC-019 | Duplicated license.py across both products | LOW | New (2026-04-04) | Ron |

**Resolved this session:** 1 (SEC-014)
**New findings:** 4 (SEC-016, SEC-017, SEC-018, SEC-019)
**Cumulative resolved:** 10

---

## New Code Review

### local_model_preprocess.py (scripts/)

Commits reviewed: d7f2480, 51de381, 48b9a7f, 513d489, 865d383

This script orchestrates Ollama subprocess calls for agent preprocessing. Added features:
`--save-to-loreconvo` flag, JSON extraction, output formatting, config loading.

| Check | Result | Notes |
|-------|--------|-------|
| Subprocess injection | PASS | Uses list form of subprocess.run(), not shell=True. Model name passed as list element -- no shell injection even with special characters. |
| Secrets | PASS | No hardcoded API keys, tokens, or credentials. |
| YAML deserialization | PASS | Uses yaml.safe_load (not yaml.load). |
| JSON deserialization | PASS | json.loads only; no pickle, eval, or exec. |
| Input validation | PASS | argparse with constrained choices for --agent and --task. |
| Error handling | PASS | All subprocess exceptions caught gracefully. Failures are non-fatal. |
| LoreConvo integration | PASS | save_preprocessing_to_loreconvo() uses the standard scripts/save_to_loreconvo.py pattern. |

**Verdict:** CLEAN. No security issues found.

### get_tier / get_license_tier MCP Tools (Ron commit aecf64a)

Both LoreConvo server.py and LoreDocs server.py received new diagnostic MCP tools that
call get_license_status() from the respective license module.

| Check | Result | Notes |
|-------|--------|-------|
| Information leakage | PASS | Returns tier, mode, product, expiry, email -- no secrets or private key material exposed. Error messages are helpful but do not reveal internal state. |
| License bypass | PASS | Read-only tool. Cannot modify tier or validate/invalidate keys. |
| pyproject.toml dep | PASS | cryptography>=41.0.0 added to both pyproject.toml files (resolves SEC-014). |

---

## BROCK-REVIEW Items from Gina (gina_lore_review_2026_04_04.md)

### SEC-016: LoreConvo auto_save Hook Bypasses Session Limit

**Severity:** LOW (local single-user context); MEDIUM (if deployed multi-user)
**Status:** New - Open
**Owner:** Ron

**Finding:** The `hooks/scripts/auto_save.py` hook writes session records directly to
SQLite using its own `save_to_db()` function. It does not call `SessionDatabase.save_session()`,
which is where the free-tier session limit (`session_limit`) is enforced. As a result, each
Claude Code session that triggers the SessionEnd hook creates a record unconditionally, with
no check against the free tier cap.

**Exploitability:** Low. The hook fires only for Claude Code CLI sessions. A user on free tier
could accumulate unlimited auto-saved sessions by using Code instead of Cowork. In the current
single-user deployment, this is low risk because Debbie IS the developer. Before any public
distribution where real free/paid tier separation matters, this should be fixed.

**Recommended fix:** In `auto_save.py::save_to_db()`, check the current session count before
inserting. If `SELECT COUNT(*) FROM sessions` exceeds `LORECONVO_SESSION_LIMIT` (default 50)
and the product is not in pro mode, skip the insert and log a warning. This matches the
behavior of `SessionDatabase.save_session()`.

**Note:** The dedup guard (checking `WHERE id = session_uuid` before inserting) is correctly
implemented and prevents duplicate hook fires from creating duplicate records.

---

### SEC-017: LoreDocs vault_set_tier Has No License Validation

**Severity:** MEDIUM
**Status:** New - Open (known planned fix)
**Owner:** Ron

**Finding:** The `vault_set_tier` MCP tool sets the tier to 'pro' (or 'free') without
verifying any license key. The tool's own docstring acknowledges this:

  "Note: In a future release this will verify a license key. For now it trusts
  the caller (suitable for single-user local installs)."

This means any LoreDocs user can call `vault_set_tier(tier='pro')` to unlock all limits
without a paid license. The `get_license_tier` tool correctly reads the license key and
reports tier, but the actual enforcement path (`set_tier`) ignores it.

**Exploitability:** Medium. In a public plugin distribution, any user who discovers this
tool can bypass the paywall by calling it directly. The MCP transport itself (stdio) does
not add authentication.

**Contrast with LoreConvo:** LoreConvo does not have a `set_tier` tool -- tier is determined
exclusively by the license key validation in `license.py`. LoreDocs has a parallel license.py
that validates the `LOREDOCS_PRO` env var, but vault_set_tier ignores it.

**Recommended fix:** In `vault_set_tier()`, require that `params.tier == 'pro'` is only
accepted if `get_license_status()['is_pro']` is True. For tier='free', no validation needed.
This aligns LoreDocs enforcement with LoreConvo's model.

**GINA-REVIEW:** The architectural inconsistency between the two products' tier enforcement
models (LoreConvo: env-var-only, LoreDocs: set_tier tool) warrants a cross-product design
decision. Should LoreDocs remove vault_set_tier entirely and follow LoreConvo's model?

---

### SEC-018: vault_import_dir / vault_export Have No Path Restriction

**Severity:** INFO (local single-user context); MEDIUM (multi-user/cloud)
**Status:** New - Open
**Owner:** Ron (before any multi-user deployment)

**Finding:** Both `vault_import_dir` and `vault_export` accept arbitrary absolute paths
via their `directory` field. No allowlisting, chroot-style restriction, or path sanitization
is applied. A user can import files from any readable path or export to any writable path.

**Exploitability in current context:** None. The only user is Debbie, who owns the machine.
This is intentional for a local personal tool -- the user should be able to import from
~/Documents or export to /tmp freely.

**Exploitability in future multi-user/cloud context:** High. If LoreDocs ever runs as a
shared server or cloud service, an authenticated user could read arbitrary files visible
to the server process (e.g., /etc/passwd, ~/.ssh/id_rsa) by importing them into a vault,
or write arbitrary paths by exporting there.

**Recommended approach (before any multi-user deployment):**
- Add an allowed_roots config option (list of allowed base directories).
- Validate that the resolved path starts with one of the allowed roots before proceeding.
- Default allowed_roots for local mode: home directory.

**GINA-REVIEW:** This is an architectural design decision that should be evaluated alongside
any cloud sync or team deployment planning.

---

### SEC-019: Duplicated license.py Across Both Products (Same Public Key)

**Severity:** LOW
**Status:** New - Open
**Owner:** Ron

**Finding:** `ron_skills/loreconvo/src/core/license.py` and
`ron_skills/loredocs/loredocs/license.py` contain nearly identical code with the same
Ed25519 public key embedded in both:

  `_LAB_PUBLIC_KEY_B64 = "2Y++SKM6ZVAz1T8f0EGinoLWlQ9wdZFwEelAYDb1hT0="`

The only meaningful differences are:
- `_VALID_PRODUCTS = {"loreconvo", "lore_suite"}` vs `{"loredocs", "lore_suite"}`
- The env var checked (`LORECONVO_PRO` vs `LOREDOCS_PRO`)

**Security implications:**
1. Key rotation risk: If the private key is ever compromised, both products need coordinated
   key rotation. Any update to one license.py must be manually mirrored to the other.
2. The duplication is intentional by design -- a single Labyrinth Analytics keypair signs
   all product licenses, with product differentiation via the `product` field in the
   license payload and `_VALID_PRODUCTS` validation. This is a sound design choice.
3. Risk of the two copies drifting: If a bug fix is applied to one file but not the other,
   the products have inconsistent license validation behavior.

**Recommended fix:** Extract license.py into a shared `labyrinth_licensing` package or
a vendored copy that is git-subtree'd into both products. If sharing is not feasible,
add a test that asserts the public key constant is identical in both files.

**GINA-REVIEW:** Gina flagged this as a shared library vs. vendored copy architectural
decision. The security posture favors a shared library (single place to update) but
the distribution model (separate .plugin files, separate PyPI packages) favors vendoring.

---

## Infrastructure Review

| Area | Status | Notes |
|------|--------|-------|
| pip-audit (LoreConvo) | CLEAN | No known CVEs in pinned dependencies |
| pip-audit (LoreDocs) | CLEAN | No known CVEs in pinned dependencies |
| .gitignore coverage | GOOD | All .env files covered by root .gitignore |
| sql_query_optimizer API key | INFO | Real key in api/.env, properly gitignored, not in git history |
| Git history (key scan) | CLEAN | No .env files tracked; no key patterns found in history |
| pending_commits.json | INFO | 3 pending commits present (safe_git.py workaround, not a security issue) |
| Public repo hygiene | GOOD | Internal docs remain in docs/internal/ (not pushed to public repos) |
| Debug mode | CLEAN | No DEBUG=True or app.debug in application code |

---

## Resolved Findings Tracker

| ID | Title | Resolved | Commit |
|----|-------|----------|--------|
| SEC-002 | SQL injection in search | 2026-03-31 | early commits |
| SEC-003 | Pickle deserialization | 2026-03-31 | early commits |
| SEC-004 | Path traversal in read | 2026-03-31 | early commits |
| SEC-005 | Missing rate limiting | 2026-04-01 | security hardening |
| SEC-007 | CORS wildcard | 2026-04-01 | security hardening |
| SEC-008 | Admin auth missing | 2026-04-01 | security hardening |
| SEC-010 | LiteLLM supply chain risk | 2026-03-24 | audited clean, no dep |
| SEC-012 | shell=True subprocess | 2026-04-02 | removed |
| SEC-013 | FTS injection | 2026-04-02 | parameterized |
| SEC-014 | Missing cryptography dep | 2026-04-04 | aecf64a |

---

## Recommendations (Prioritized)

1. **Ron (before marketplace launch -- MEDIUM):** Fix vault_set_tier to validate license
   before accepting tier='pro' (SEC-017). Without this fix, paying for LoreDocs Pro is
   optional for any user who reads the MCP tool list.

2. **Ron (before marketplace launch -- LOW):** Add session limit check to auto_save hook
   (SEC-016). The free/paid tier enforcement gap should be closed before paying customers
   are onboarded.

3. **Ron (near-term -- MEDIUM):** Fix TOCTOU race in LoreDocs export (SEC-011). Low
   urgency for local use but clean it up before v0.2.0.

4. **Ron (near-term -- LOW):** Add cross-product license.py consistency test or extract
   to shared library (SEC-019). At minimum, add a test asserting both public key constants
   are equal.

5. **Debbie (before creating GitHub marketplace repo):** Replace personal email in
   marketplace.json with business contact (SEC-015).

6. **Ron (LOW -- before production):** Address CreditManager race condition (SEC-006).

7. **Debbie (low urgency):** Rotate Anthropic API key in sql_query_optimizer/api/.env
   at next convenient opportunity (SEC-001). File is gitignored and not in history.
   Rotation is low-urgency but good hygiene.

---

## Report Comparison vs 2026-04-03 (Run B)

| Metric | Run B | Today | Change |
|--------|-------|-------|--------|
| Total active findings | 6 | 8 | +4 new, -1 resolved (net +3) |
| CRITICAL | 0 | 0 | No change |
| HIGH | 0 | 0 | No change |
| MEDIUM | 2 | 3 | +1 (SEC-017) |
| LOW | 2 | 2 | +1 (SEC-016/019), -1 carryover |
| INFO | 2 | 3 | +1 (SEC-018) |
| CVEs found | 0 | 0 | No change |
| Resolved (cumulative) | 9 | 10 | +1 (SEC-014) |

**Trend:** All four BROCK-REVIEW items from Gina assessed. None require immediate action
for the current local-only deployment. SEC-017 (vault_set_tier bypass) is the highest
priority fix before any paying customers are onboarded. Overall posture stable at
NEEDS ATTENTION. No regressions introduced.

---

*Report generated by Brock (automated security agent) - 2026-04-04*
*Next scheduled run: 2026-04-05 03:00 AM*
