# Security Report -- 2026-04-06

**Agent:** Brock (Automated Security Agent)
**Posture:** NEEDS ATTENTION (stable, no new critical/high)
**CVEs found this run:** 0
**New findings:** 1 (SEC-022, INFO)
**Resolved this run:** 1 (GINA-003, previously tracked as MEDIUM)

---

## Summary

Steady state. Today's commits were narrowly scoped: GINA-003 license.py fix, hook
script chmod corrections, and a blog draft rewrite (no security impact). Dependency
audit clean on both products. No secrets found in recent diffs. The two BROCK-REVIEW
items raised by Gina's 2026-04-06 architecture report are assessed below -- both
resolved at INFO severity with documentation guidance for Ron.

---

## Commits Reviewed (HEAD~5..HEAD)

| Hash    | Summary                                                              | Security Impact |
|---------|----------------------------------------------------------------------|-----------------|
| 29d7052 | Meg QA run B report                                                  | None (report only) |
| 3b9e9b7 | Blog rewrite: loredocs vault architecture                            | None (marketing content) |
| 95fb0da | Fix GINA-003/MEG-050: license.py env_value guard + test dedup       | POSITIVE (security fix) |
| 983b096 | Fix: chmod hook scripts in install.sh for both products              | POSITIVE (correctness) |
| 5b48bf3 | Updated marketing docs, fixed hook executable status                 | None |
| fcba32a | Fix: chmod hook scripts in install.sh (LoreConvo)                   | POSITIVE (correctness) |

---

## BROCK-REVIEW Assessment (from Gina's product_review_2026_04_06.md)

### BROCK-REVIEW-1: LoreDocs dev_mode behavior -- is LAB_DEV_MODE behavior intentional?

**Gina's question:** Is it intentional for LAB_DEV_MODE=1 to grant Pro access with
no key set? The gate is "env var can be set by attacker" -- so the dev bypass may
be moot for security. Document the intended behavior.

**Brock's assessment:**

After Ron's GINA-003 fix (commit 95fb0da), the behavior is:

```
LAB_DEV_MODE=1 + LOREDOCS_PRO empty  --> Free tier (no bypass). CORRECT.
LAB_DEV_MODE=1 + LOREDOCS_PRO = non-empty non-key string --> Pro bypass (dev mode).
LAB_DEV_MODE=1 + LOREDOCS_PRO = valid key --> Normal key validation path.
LAB_DEV_MODE not set + any LOREDOCS_PRO --> Normal key validation path.
```

**Is this intentional?** Yes. The behavior is a dual-gate pattern:
- Gate 1: LAB_DEV_MODE=1 must be set (not in public .mcp.json -- internal agent use only)
- Gate 2: LOREDOCS_PRO must be non-empty (prevents silent bypass on unconfigured installs)

**Gina's "attacker who can set env vars" concern:** Valid observation. If an attacker
has write access to the environment, LAB_DEV_MODE=1 unlocks dev bypass. However:
- Single-user local deployment: env access == full machine access. This is not an
  additional attack surface -- it is already game over.
- LAB_DEV_MODE is excluded from all public .mcp.json templates (confirmed). External
  users cannot accidentally enable it.
- The dev bypass exists solely so internal scheduled agents (Ron, Meg, etc.) can run
  without a real license key. It is not a customer-facing feature.

**Verdict:** LOW actual risk. Behavior is intentional and appropriate for the current
deployment model. No code change needed. Recommend Ron add a docstring clarifying the
dual-gate intent (see SEC-022 below).

**The two license.py files are now consistent:** Both LoreConvo and LoreDocs license.py
have the `env_value and` guard after the GINA-003 fix. The files are reconciled.

### BROCK-REVIEW-2: GINA-003 reconciliation of two license.py files

**Status: RESOLVED.** Commit 95fb0da applied the identical `env_value and` guard to
both is_pro_licensed() and get_license_status() in LoreDocs license.py. The behavioral
difference that prompted GINA-003 no longer exists. LoreConvo and LoreDocs dev_mode
handling is now identical. No further action required beyond the documentation note
(SEC-022).

---

## Vulnerability Scan

### Dependency Audit

| Product   | Lock file                         | Result                     |
|-----------|-----------------------------------|----------------------------|
| LoreConvo | requirements-lock.txt             | No known vulnerabilities   |
| LoreDocs  | requirements-lock.txt             | No known vulnerabilities   |

**CVE count this run:** 0

### Secrets Scan

Recent diffs (HEAD~5..HEAD) scanned for hardcoded secrets: **Clean.**
- No API keys, passwords, tokens, or private keys found in committed code.
- SEC-001 (Anthropic API key in sql_optimizer .env) remains gitignored and not in
  recent commits. No change.

### Install Script Review

LoreDocs install.sh addition (commit 983b096):
```bash
chmod +x "$HOOKS_DIR"/*.sh 2>/dev/null || true
```
Assessment: SAFE. The chmod is scoped to the plugin's own hooks directory using an
absolute path derived from $SCRIPT_DIR. The `|| true` prevents install failure if
no .sh files exist. No privilege escalation. No curl/wget/remote execution.

LoreConvo install.sh had identical chmod fix applied earlier (commit fcba32a).
Both are correct and do not introduce new attack surface.

---

## Security Architecture Review

### Hook Scripts (on_session_start.sh, on_session_end.sh)

No logic changes in today's commits -- only file permission fixes (chmod).
Prior architecture assessment stands:

- **Log sanitization:** on_session_end.sh logs only session_id, never transcript
  content or PII. Correct behavior.
- **Log rotation:** 1 MB cap with 3-copy rotation. Prevents unbounded disk growth.
- **Python isolation:** Both hooks use the product venv's python3 with PYTHONPATH
  scoped to the plugin root. Not inheriting arbitrary system packages.
- **Stdin handling:** Hooks read stdin once into $INPUT. No injection vector via
  session data because JSON is parsed only to extract session_id for logging.
- **Exit code propagation:** on_session_end.sh propagates the Python script's exit
  code. Callers can detect hook failures. Good.

One minor note: on_session_start.sh uses bare `python3 -c` (system python) for the
session_id extraction log line, while using the venv python for the actual auto_load.
This is cosmetic -- the system python is only extracting a log label from JSON, not
running any product code. No security concern.

### LoreDocs INSTALL.md Update

Ron added correct install guidance (commit 95fb0da). No security issues in the doc.
Confirms the install path uses pip install . (non-editable) -- avoids editable install
MAPPING bugs documented in the Stability Mandate. Positive change.

---

## New Findings

### SEC-022 (INFO): LoreDocs license.py dev_mode behavior undocumented

**Product:** LoreDocs
**File:** ron_skills/loredocs/loredocs/license.py
**Severity:** INFO
**Status:** Open

The module-level docstring at line 26-29 briefly mentions LAB_DEV_MODE but does not
describe the dual-gate pattern: LAB_DEV_MODE=1 AND non-empty LOREDOCS_PRO required
for dev bypass. This creates potential confusion for future maintainers about when
bypass can and cannot trigger.

**Recommended fix (Ron):** Update the module docstring to read:

```
Dev bypass gate (internal agents only):
  - LAB_DEV_MODE=1 must be set in the environment.
  - LOREDOCS_PRO must be a non-empty string (any value not starting with the key prefix).
  - Both conditions required. LAB_DEV_MODE alone with empty LOREDOCS_PRO = Free tier.
  - LAB_DEV_MODE is excluded from all public .mcp.json templates. Not customer-facing.
```

Apply the same documentation update to LoreConvo license.py for consistency.

---

## Open Findings Registry

| ID     | Owner  | Severity | Status   | Description                                              |
|--------|--------|----------|----------|----------------------------------------------------------|
| SEC-001 | Debbie | INFO    | Open     | Anthropic API key in sql_optimizer .env (local, gitignored) |
| SEC-006 | Ron   | LOW      | Open     | CreditManager race condition (LoreConvo)                 |
| SEC-011 | Ron   | MEDIUM   | Open     | TOCTOU race in LoreDocs export                           |
| SEC-016 | Ron   | LOW      | Open     | auto_save hook bypasses session limit (LoreConvo)        |
| SEC-018 | Ron   | INFO     | Open     | vault_import_dir/export: no path restriction (deferred)  |
| SEC-019 | Ron   | LOW      | Open     | Duplicated license.py: cross-product consistency test missing |
| SEC-020 | Ron   | INFO     | Open     | pipeline_tracker.py f-string SQL pattern (safe, note only) |
| SEC-022 | Ron   | INFO     | Open     | LoreDocs license.py dev_mode dual-gate behavior undocumented |

**Resolved this run:** GINA-003 (LoreDocs license.py env_value guard -- tracked as
MEDIUM in Gina's report, root cause addressed in commit 95fb0da)

**Closed (cumulative):** SEC-002 through SEC-010, SEC-012, SEC-013, SEC-014, SEC-015,
SEC-017, SEC-021, GINA-003

---

## Recommendations (Prioritized)

1. **Ron (before paying customers -- LOW):** Fix SEC-016 (auto_save session limit
   bypass in LoreConvo). Most relevant pre-launch tier enforcement gap.

2. **Ron (before v0.2.0 -- MEDIUM):** Fix SEC-011 (TOCTOU race in LoreDocs export).
   Not urgent locally but should be clean before next minor version.

3. **Ron (before marketplace -- LOW):** Fix SEC-019 (add cross-product license
   consistency test asserting both public key constants are equal).

4. **Ron (low effort -- INFO):** Fix SEC-022 (add dual-gate docstring to both
   license.py files). One or two lines each. Prevents future confusion.

5. **Ron (advisory -- INFO):** Add comment to pipeline_tracker.py line 250 noting
   f-string SQL is safe because column names are hardcoded (SEC-020).

6. **Debbie (low urgency):** Rotate Anthropic API key in sql_optimizer/.env at next
   opportunity (SEC-001). File is gitignored and clean. Good hygiene.

7. **Ron (near-term -- LOW):** Address CreditManager race condition (SEC-006) before
   LoreConvo Pro goes live.

---

## Report Comparison vs 2026-04-05

| Metric                 | 2026-04-05 | 2026-04-06 | Change                     |
|------------------------|-----------|-----------|----------------------------|
| Total active findings  | 7         | 8         | +1 (SEC-022 INFO added)    |
| CRITICAL               | 0         | 0         | No change                  |
| HIGH                   | 0         | 0         | No change                  |
| MEDIUM                 | 2         | 1         | -1 (GINA-003 resolved)     |
| LOW                    | 3         | 3         | No change                  |
| INFO                   | 4         | 4         | SEC-022 added, GINA-003 closed (net 0) |
| CVEs found             | 0         | 0         | No change                  |
| Resolved (cumulative)  | 11        | 12        | +1 (GINA-003)              |

**Trend:** Stable. GINA-003 (MEDIUM) resolved. SEC-022 added at INFO only. No regressions.
Hook chmod fixes are correct security hygiene. Posture: NEEDS ATTENTION (stable).

---

*Report generated by Brock (automated security agent) -- 2026-04-06*
*Next scheduled run: 2026-04-07*
