# Security Report - 2026-03-29
**Agent:** Brock (Cybersecurity Expert)
**Run Time:** 2026-03-29 (automated daily scan)
**Overall Posture:** NEEDS ATTENTION

---

## Executive Summary

This is the first security report for the Project Ron side_hustle repo. The codebase is
in generally good shape from a code-level security standpoint -- no SQL injection, no command
injection, no insecure deserialization, and no secrets committed to git history. The most
significant hardening work was done in commit `55a3b4f` (2026-03-29): CORS wildcard fixed,
rate limiting added to the admin endpoint, security headers middleware added, and input
validation tightened. Dependency audit returned zero CVEs across all products. LiteLLM
supply chain attack (versions 1.82.7/1.82.8) is NOT present -- confirmed clean.

The primary outstanding concern is an **EXISTING CRITICAL finding** that has not been
resolved: a real Anthropic API key lives in the on-disk `.env` file for the SQL Query
Optimizer API. The key is NOT in git history (gitignore is working), but it has been on
disk since 2026-03-21 and must be revoked at console.anthropic.com immediately. Secondary
findings include non-critical gaps: missing `hmac.compare_digest` for timing-safe
comparisons, unpinned dependencies in pyproject.toml files, email PII in logs, missing
rate limits on two API endpoints, and a `.gitignore` gap for `*.db` files.

Path traversal protections in LoreDocs are solid (OPP-006 hardening verified intact).
Admin endpoint is protected by `ADMIN_SECRET` environment variable. CORS is now
environment-variable-driven with no wildcard. Security headers are fully implemented.

---

## !! CRITICAL - ACTION REQUIRED !!

**Finding: Exposed Anthropic API Key (On-Disk, Not Revoked)**

The file `ron_skills/sql_query_optimizer/api/.env` contains a real Anthropic API key:
`ANTHROPIC_API_KEY=sk-ant-api03-9ffeAe8zLrMng8GIMC-fcs4rSDvRycGY9vw_4...`

This key:
- Has been on disk since at least 2026-03-21 (file mtime)
- Is NOT in git history (gitignore coverage confirmed)
- Is NOT in `.env.example` (that file shows only `sk-ant-your-key-here`)
- Must still be assumed COMPROMISED because anyone with disk access has seen it

**Remediation (Debbie must do this -- not automatable):**
1. Go to console.anthropic.com -> API keys
2. Find the key matching `sk-ant-api03-9ffeAe8zLrMng8GIMC-fcs...`
3. Click "Revoke" immediately
4. Generate a new key for Ron
5. Update `.env` with the new key
6. Verify nothing is currently calling the old key in production

**Status:** EXISTING (first flagged in CLAUDE.md TODO #14, 2026-03-29). NOT RESOLVED.

---

## Findings

### SEC-001: Anthropic API Key Not Revoked
- **Severity:** CRITICAL
- **Category:** Secrets
- **Status:** EXISTING (not resolved)
- **Location:** `ron_skills/sql_query_optimizer/api/.env` (line 5)
- **Description:** Real Anthropic API key present on disk. Not in git history. Key
  has been on disk since 2026-03-21.
- **Remediation:** Revoke immediately at console.anthropic.com, regenerate, update .env.

---

### SEC-002: Admin Token Comparison Not Timing-Safe
- **Severity:** MEDIUM
- **Category:** Auth
- **Status:** NEW
- **Location:** `ron_skills/sql_query_optimizer/api/main.py` line 242
- **Description:** Admin secret comparison uses `token != admin_secret`, which is a
  plain Python string comparison. Python strings are not compared in constant time --
  an attacker making many requests can use timing differences to brute-force the secret
  one character at a time. This is a textbook timing side-channel vulnerability.
- **Current code:**
  ```python
  if token != admin_secret:
  ```
- **Remediation:** Replace with `hmac.compare_digest`:
  ```python
  import hmac
  if not hmac.compare_digest(token, admin_secret):
  ```

---

### SEC-003: Unpinned Dependencies in pyproject.toml Files
- **Severity:** MEDIUM
- **Category:** Dependencies
- **Status:** NEW
- **Location:**
  - `ron_skills/loreconvo/pyproject.toml` (all dependencies use `>=`)
  - `ron_skills/loredocs/pyproject.toml` (all dependencies use `>=`)
  - `ron_skills/loreconvo/requirements.txt` (uses `>=` instead of exact pins)
- **Description:** The `pyproject.toml` files for LoreConvo and LoreDocs use minimum
  version constraints (`mcp[cli]>=1.0.0`, `pydantic>=2.0.0`, etc.) rather than pinned
  versions. This means a `pip install` could pull in a newly released version with a
  vulnerability before it is caught by a dependency audit. The SQL optimizer API
  `requirements.txt` is correctly pinned (all exact versions). LoreDocs/LoreConvo do
  not have a pinned lockfile.
- **Remediation for Ron:**
  1. Run `pip freeze > requirements-lock.txt` inside each product venv
  2. Use the lockfile for reproducible installs
  3. Consider adding exact versions to `pyproject.toml` `dependencies` list or
     maintaining a `requirements-prod.txt` with pinned versions

---

### SEC-004: Email PII Logged Unmasked
- **Severity:** MEDIUM
- **Category:** Logging / Privacy
- **Status:** NEW
- **Location:** `ron_skills/sql_query_optimizer/api/credits.py` line 91
- **Description:** When generating a new API key, the customer's email address is
  logged in plaintext: `logger.info("Generated new %s key for %s", plan, email or "unknown")`.
  Log files can persist and may be readable to anyone with file system access. Email
  addresses are PII and should not appear in application logs.
- **Remediation:** Mask the email before logging:
  ```python
  masked = email[:3] + "***" if email else "unknown"
  logger.info("Generated new %s key for %s", plan, masked)
  ```

---

### SEC-005: Missing Rate Limits on /v1/optimize and /v1/credits
- **Severity:** LOW
- **Category:** API Security
- **Status:** NEW
- **Location:** `ron_skills/sql_query_optimizer/api/main.py` lines 156 and 210
- **Description:** The `/v1/optimize` and `/v1/credits` endpoints have no
  `@limiter.limit()` decorator. Only `/admin/generate-key` is rate-limited. While
  `/v1/optimize` is gated by API key auth and credit deduction (which provide natural
  throttling), `/v1/credits` can be polled at unlimited rate by any valid key holder.
  A bad actor who obtains a valid key could also hammer `/v1/optimize` to exhaust
  another user's credits quickly before credit deduction kicks in under concurrent
  requests (race condition risk in the file-based CreditManager).
- **Remediation:**
  - Add `@limiter.limit("30/minute")` to `/v1/optimize`
  - Add `@limiter.limit("60/minute")` to `/v1/credits`
  - Consider adding atomic credit deduction in CreditManager to prevent
    race conditions under concurrent requests

---

### SEC-006: CreditManager Has Race Condition Under Concurrency
- **Severity:** LOW
- **Category:** Business Logic / Data Integrity
- **Status:** NEW
- **Location:** `ron_skills/sql_query_optimizer/api/credits.py` -- `use_credit()` method
- **Description:** The CreditManager reads the JSON file, modifies it, and writes it
  back in separate operations with no locking. Under concurrent requests:
  1. Request A reads credits = 1
  2. Request B reads credits = 1
  3. Request A deducts to 0, writes
  4. Request B deducts to 0 (from its stale read), writes
  Both requests succeed with 1 credit, effectively doubling usage. At low volume this
  is unlikely to matter, but it becomes exploitable once the service has real traffic.
- **Remediation:** Use `filelock` or a threading lock around the load/modify/save
  cycle. Or migrate CreditManager to SQLite (WAL mode provides atomic writes).

---

### SEC-007: .gitignore Missing *.db and *.sqlite Patterns
- **Severity:** LOW
- **Category:** Infrastructure
- **Status:** NEW
- **Location:** `.gitignore`
- **Description:** LoreConvo and LoreDocs both use SQLite databases that store
  potentially sensitive session and document data. These DB files are not currently
  committed to git (confirmed via `git ls-files`), but the `.gitignore` has no
  explicit rule for `*.db` or `*.sqlite`. If a developer runs either product and
  then accidentally does `git add -A`, the DB could be committed.
- **Remediation:** Add to `.gitignore`:
  ```
  # SQLite databases (may contain session/document data)
  *.db
  *.sqlite
  ```

---

### SEC-008: --reload Flag in QUICKSTART.md
- **Severity:** INFO
- **Category:** Config
- **Status:** NEW
- **Location:** `ron_skills/sql_query_optimizer/QUICKSTART.md` line 66
- **Description:** The quickstart guide shows `uvicorn main:app --reload` which
  enables auto-reload (development mode). This flag should never be used in production
  as it scans for file changes and restarts the server, which has overhead and
  security implications. The production `start.py` does not use `--reload`, so
  this is documentation-only risk, but could mislead someone deploying manually.
- **Remediation:** Add a note in QUICKSTART.md:
  `# NOTE: --reload is for development only. Remove this flag in production.`

---

### SEC-009: SQL Dynamic Clause Construction in LoreDocs (Mitigated)
- **Severity:** INFO
- **Category:** Injection (Mitigated)
- **Status:** NEW (informational only -- mitigated by code structure)
- **Location:** `ron_skills/loredocs/loredocs/storage.py` lines 641-644, 754-764
- **Description:** Several SQL queries use f-strings to build dynamic `SET` clauses
  and `WHERE` clauses. On review, these are safe:
  - `set_clause`: Keys come from a hardcoded `updates` dict, not user input
  - `where_clause`: Parts are static strings; user values go through `?` parameterization
  - `sort_by` / `sort_order`: Both validated against whitelists before interpolation
  - `vault_filter`: Static string `"AND d.vault_id = ?"`
  No actual SQL injection risk exists, but the pattern warrants a note for future
  code reviewers so these lines don't get flagged unnecessarily.
- **Remediation:** No fix required. Consider adding a comment on line 641 to document
  why the f-string is safe (keys are internal, not user-supplied).

---

## Dependency Audit Results

| Product | Requirements File | pip-audit Result | Notes |
|---------|------------------|-----------------|-------|
| SQL Query Optimizer | `api/requirements.txt` | PASS - 0 CVEs | All versions pinned exactly |
| LoreConvo | `requirements.txt` | PASS - 0 CVEs | Versions unpinned (>=) -- see SEC-003 |
| LoreDocs | `pyproject.toml` | Not audited (no requirements.txt) | pyproject.toml has >= versions |
| All products | LiteLLM check | CLEAN | LiteLLM not present in any product |

---

## Secrets Scan Results

| Check | Result | Details |
|-------|--------|---------|
| `.env` committed to git | PASS | .gitignore line 2: `*.env` covers it |
| `.env` in git history | PASS | `git log --all -p -- "*.env"` returned nothing |
| Real key in `.env` on disk | **FAIL** | `sk-ant-api03-...` present in `api/.env` (SEC-001) |
| Hardcoded keys in Python source | PASS | No hardcoded keys found in tracked files |
| AWS credentials | PASS | No AKIA patterns found |
| Private keys / PEM files | PASS | No RSA/EC private keys found |
| Stripe live keys | PASS | Only placeholder comments found |
| `.env.example` contents | PASS | Contains placeholder values only |

---

## Previously Resolved Findings (from commit 55a3b4f, 2026-03-29)

These were flagged in `CLAUDE.md` and fixed by Ron before Brock's first run:

| Finding | Severity | Fix |
|---------|---------|-----|
| Wildcard CORS (`allow_origins=["*"]`) | HIGH | RESOLVED - env-var-driven origin list |
| Unpinned `slowapi` in requirements.txt | HIGH | RESOLVED - pinned to `slowapi==0.1.9` |
| No rate limit on `/admin/generate-key` | HIGH | RESOLVED - `@limiter.limit("5/minute")` |
| No `max_length` on SQL query input | MEDIUM | RESOLVED - `max_length=50000` in Field |
| Missing security headers | MEDIUM | RESOLVED - `SecurityHeadersMiddleware` added |

---

## Recommendations (Prioritized)

1. **Debbie (immediate):** Revoke the Anthropic API key at console.anthropic.com.
   This is the only item that requires human action and cannot wait.

2. **Ron (next session):** Fix timing-safe admin comparison (SEC-002) -- 5 minutes,
   one-line change with `hmac.compare_digest`.

3. **Ron (next session):** Mask email in logs (SEC-004) -- 2 minutes.

4. **Ron (near-term):** Add `*.db` and `*.sqlite` to `.gitignore` (SEC-007) -- 2 minutes.

5. **Ron (near-term):** Add rate limits to `/v1/optimize` and `/v1/credits` (SEC-005).

6. **Ron (before production):** Address CreditManager race condition (SEC-006) by
   adding file locking or migrating to SQLite-backed storage.

7. **Ron (before release):** Generate `requirements-lock.txt` for LoreConvo and
   LoreDocs (SEC-003).

8. **Ron (documentation pass):** Add `--reload` warning to QUICKSTART.md (SEC-008).

---

*Report generated by Brock (automated security agent) - 2026-03-29*
*Next scheduled run: 2026-03-30 04:00 AM*
