# Security Report -- 2026-04-09

**Agent:** Brock (Automated Security Agent)
**Posture:** NEEDS ATTENTION (1 new dependency CVE + BROCK-REVIEW assessment complete)
**CVEs found this run:** 1 (SEC-024, MEDIUM -- cryptography 46.0.6 in both products)
**New findings:** 2 (SEC-024 MEDIUM; BROCK-REVIEW/LORECONVO-ENH-001 assessment)
**Resolved this run:** 0

---

## Summary

Two items drive this session's NEEDS ATTENTION rating. First, pip-audit found a known
vulnerability (CVE-2026-39892) in `cryptography==46.0.6` pinned in both LoreConvo and
LoreDocs lock files; the fix is a minor version bump to 46.0.7 with no breaking changes.
Second, Gina's product_review_2026_04_08 assigned Brock a BROCK-REVIEW on the proposed
LORECONVO-ENH-001 feature (Claude API data egress in save_session). That assessment is
complete and documented below -- the feature is CONDITIONALLY APPROVED with three required
safeguards before Ron implements it.

All other scan dimensions are clean: no secrets in recent diffs, no new OWASP code
findings, run_agent_code.sh script looks structurally sound. SEC-023 (glob sort ambiguity)
carries forward unchanged as INFO.

---

## Commits Reviewed (HEAD~2..HEAD)

| Hash    | Summary                                                   | Security Impact            |
|---------|-----------------------------------------------------------|----------------------------|
| 67db03f | pm: Jacqueline executive dashboard + DEBBIE_DASHBOARD update | None (docs/dashboard only) |
| 416219a | updated agent architecture                                | Low -- see run_agent_code.sh review |

**Files changed of security interest:**
- `scripts/run_agent_code.sh` -- modified (see OWASP review below)
- `.claude/settings.json` -- modified (diff empty; no secrets detected)
- `docs/internal/other documentation/agent prompts/` -- agent prompt text; no code

---

## Dependency Audit

### LoreConvo (requirements-lock.txt)

```
pip-audit: Found 1 known vulnerability in 1 package
  cryptography 46.0.6  CVE-2026-39892  Fix: 46.0.7
```

### LoreDocs (requirements-lock.txt)

```
pip-audit: Found 1 known vulnerability in 1 package
  cryptography 46.0.6  CVE-2026-39892  Fix: 46.0.7
```

Both products share the same pinned cryptography version and share the same finding.
All other packages in both lock files are clean.

---

## New Finding: SEC-024

### SEC-024 (MEDIUM): cryptography 46.0.6 -- CVE-2026-39892

**Products affected:** LoreConvo v0.3.0 AND LoreDocs v0.1.0
**Files:**
  `ron_skills/loreconvo/requirements-lock.txt` line 9: `cryptography==46.0.6`
  `ron_skills/loredocs/requirements-lock.txt` line 11: `cryptography==46.0.6`
**CVE:** CVE-2026-39892
**Fix version:** cryptography 46.0.7 (minor bump, no breaking changes expected)

**Severity rationale:** MEDIUM in single-user local context. The cryptography package is
used transitively by FastMCP's TLS and JWT dependencies. On a single-user Mac with no
inbound network exposure, exploitability is low. Rated MEDIUM rather than LOW because
a fix is immediately available with no breaking changes -- there is no reason to stay on
a vulnerable pin when the patch is a one-line lock file change.

**Recommended fix:**
```
# In ron_skills/loreconvo/:
pip install "cryptography==46.0.7" && pip freeze > requirements-lock.txt

# In ron_skills/loredocs/:
pip install "cryptography==46.0.7" && pip freeze > requirements-lock.txt
```
Then re-run `pip-audit` to confirm clean. Assign to Ron, next available session.
**Estimated fix effort:** < 5 minutes. Not blocked by feature freeze (dependency update).

---

## OWASP Code Review: run_agent_code.sh

The modified `scripts/run_agent_code.sh` is the local cron runner for all scheduled agents.

### Findings

**1. bypassPermissions mode (INFO -- by design)**
```bash
"$CLAUDE_BIN" --print --permission-mode bypassPermissions ...
```
The Claude CLI runs with `bypassPermissions`. This means the scheduled agent can call
any tool (file read/write, bash, web fetch) without user approval prompts. This is
architecturally required for non-interactive scheduled execution and is intentional.
Risk is contained because only Debbie controls the cron schedule and the SKILL.md files
that define agent prompts. Classify as INFO (known, accepted, documented).

**2. AGENT variable in path construction (INFO)**
```bash
SKILL_FILE="/Users/debbieshapiro/Documents/Claude/Scheduled/$AGENT/SKILL.md"
LOG_FILE="$LOG_DIR/${AGENT}_${TIMESTAMP}.log"
```
`$AGENT` comes from `$1` (cron argument). If `$AGENT` contained a path traversal
sequence (e.g. `../../etc`), the skill file path could resolve outside the Scheduled/
directory. In the current deployment, cron entries are written by Debbie with hardcoded
agent names (e.g. `run_agent_code.sh ron-daily`). No user-supplied input reaches this
variable. Classify as INFO in local-only context. If this script is ever exposed to
external input, add: `[[ "$AGENT" =~ ^[a-zA-Z0-9_-]+$ ]]` validation before use.

**3. Timeout detection logic (POSITIVE change)**
The MEG-055 finding (missing timeout) is addressed. The script now detects `timeout`
or `gtimeout` and applies a 3600-second cap, with a warning logged if neither is found.
This is a correct and complete fix. No security issues introduced.

**4. No other injection vectors found.** The script does not eval, execute, or interpolate
SKILL.md content directly into shell commands -- it is piped to claude via stdin. Clean.

**Overall verdict:** run_agent_code.sh is structurally sound. Two INFO-level observations
(both accepted by design). No new action items.

---

## BROCK-REVIEW: LORECONVO-ENH-001 (Claude API Data Egress in save_session)

**From:** Gina, product_review_2026_04_08.md, Security Architecture Notes section
**Feature:** Optional `summarize=True` param in `save_session` -- sends session content
to the Anthropic Claude API for compression before persisting to SQLite.

**Verdict: CONDITIONALLY APPROVED**

The feature is acceptable to implement (when unfrozen) provided ALL three conditions are
met. Missing any condition makes the feature a security/privacy risk.

### Condition 1: Opt-in only -- no default, no silent enablement

`summarize=True` must be an explicit caller choice and must NEVER be the default value.
Session content may include Debbie's business decisions, product strategy, financial
projections, agent communications, and personal context. Sending this to an external
API without explicit opt-in violates the local-first architecture promise.

Required implementation:
- Function signature: `save_session(..., summarize: bool = False)`
- When `summarize=False` (default): existing behavior, no API call, no egress
- When `summarize=True`: data egress occurs; caller is explicitly requesting this
- INSTALL.md must include a Privacy Note section explaining that `summarize=True`
  sends session content to the Anthropic API and is subject to Anthropic's privacy policy

### Condition 2: Fallback to raw save on any API failure

If the Claude API call fails for any reason (no key, rate limit, timeout, network error),
`save_session` MUST fall back to saving the raw uncompressed content. Saves must NEVER
fail due to an optional enrichment feature. Losing session data because the compression
call timed out is a worse outcome than storing uncompressed text.

Required implementation:
```python
try:
    content = call_claude_api_compress(raw_summary)
except Exception:
    content = raw_summary  # fallback: save as-is
db.insert_session(content, ...)
```

### Condition 3: Use ANTHROPIC_API_KEY from environment -- no new key

The compression call should use the `ANTHROPIC_API_KEY` environment variable already
expected in Claude Code and Cowork environments. Do NOT introduce a separate
`LORECONVO_COMPRESS_KEY` or similar -- this adds user-facing friction and creates a
second credential to manage. If `ANTHROPIC_API_KEY` is not set, treat as if
`summarize=False` (fail open, not closed).

**API key management recommendation:**
```python
import os
api_key = os.environ.get("ANTHROPIC_API_KEY")
if not api_key:
    # No key available -- skip compression, save raw
    content = raw_summary
else:
    content = call_claude_api_compress(raw_summary, api_key)
```

### Summary for Gina's three questions

| Question                            | Answer                                                              |
|-------------------------------------|---------------------------------------------------------------------|
| Data egress -- local-first OK?      | OK IF opt-in only (`summarize=True` default False) + INSTALL notice |
| API key -- existing or new?         | Use existing ANTHROPIC_API_KEY; skip compression if absent          |
| Failure mode -- fallback or fail?   | MANDATORY fallback to raw save; saves must never fail silently       |

**Tagging:** GINA-REVIEW: ENH-001 conditions documented. Ron should implement all three
when unfreezing this feature. Architecture decision on "local-first with opt-in egress"
should be recorded in LoreDocs.

---

## Secrets Scan

- `.env` files: `ron_skills/sql_query_optimizer/api/.env` (SEC-001, INFO, unchanged,
  confirmed not tracked in git)
- `settings.json` diff was empty in git (no tracked changes to the API key blocks)
- No hardcoded secrets detected in files changed by commits 67db03f or 416219a
- No tokens, keys, or credentials in recent diffs

---

## Carry-Forward Findings

| ID      | Severity | Status | Description                                                          |
|---------|----------|--------|----------------------------------------------------------------------|
| SEC-001 | INFO     | Open   | .env file for SQL query optimizer (gitignored, local-only, accepted) |
| SEC-006 | LOW      | Open   | LoreConvo session FTS5 query injection -- mitigated by parameterization; edge case only |
| SEC-011 | MEDIUM   | Open   | TOCTOU race in LoreDocs export (fix before v1.0)                    |
| SEC-016 | LOW      | Open   | LoreDocs vault delete has no recycle bin / soft-delete               |
| SEC-019 | LOW      | Open   | No audit log for session deletes in LoreConvo                        |
| SEC-023 | INFO     | Open   | Glob sort ambiguity in DB discovery (single-session normal use; low risk) |
| SEC-024 | MEDIUM   | NEW    | cryptography 46.0.6 CVE-2026-39892 in both products -- fix: 46.0.7  |

---

## Pipeline Handoffs

- **RON:** Update `cryptography==46.0.6` to `cryptography==46.0.7` in both
  `ron_skills/loreconvo/requirements-lock.txt` and `ron_skills/loredocs/requirements-lock.txt`.
  Run pip-audit to confirm clean. Not blocked by feature freeze. (SEC-024)
- **RON:** When LORECONVO-ENH-001 is unfrozen, implement all three conditions in
  BROCK-REVIEW section above before merging.
- **GINA:** LORECONVO-ENH-001 BROCK-REVIEW complete. Conditions documented. Architecture
  decision needed: should "opt-in AI egress from a local-first product" be recorded as an
  ADR (Architecture Decision Record) in LoreDocs? Recommending yes.
- **JACQUELINE:** Posture is NEEDS ATTENTION (SEC-024 new dependency CVE). No critical/high
  blockers; SEC-024 fix is quick and assigned. BROCK-REVIEW on ENH-001 resolved.
