# Debbie's Action Dashboard

Single source of truth for everything that needs Debbie's attention.
Updated by Jacqueline (daily) or manually. Last updated: 2026-04-02.

---

## TODAY -- 2026-04-02

### CRITICAL: Plugin Install Flow is Broken

Debbie tested the full plugin install path on 2026-04-02 and it does NOT work:
- `/plugin install loreconvo@labyrinth-analytics-claude-plugins` downloads but the marketplace doesn't exist
- `/install loreconvo` to enable the plugin doesn't work
- `.mcp.json` files default to PRO tier (should be free)
- READMEs are missing the `/install` enable step, CLAUDE.md snippet, and directory mounting instructions

**Ron's #1 priority is fixing this.** Items #22, #35-39 are now one consolidated block.
Nothing else ships until external users can actually install and use the plugins.

### Stripe Checking Account Setup (DEBBIE ACTION -- by Friday 4/3)

Credit union account still not ready as of 4/2. Not blocking Ron -- marketplace repo build comes first.

Once the account is open:
1. Log in to Stripe Dashboard (dashboard.stripe.com)
2. Settings -> Business settings -> Complete business verification (EIN for Labyrinth Analytics)
3. Settings -> Payouts -> Add the new checking account as payout destination
4. Switch from Sandbox to Live mode

This unblocks: marketplace payment collection, LoreConvo/LoreDocs Pro tier billing.

### Madison Blog Post -- APPROVED
Debbie reviewed and approved "Why Your Claude Sessions Start From Zero" on 2026-04-02.
Debbie is publishing via the Labyrinth Analytics website project.
Email promo template also approved but blocked on no marketing/email list yet.

### Overnight Summary (from Jacqueline 4/2 dashboard)
- Ron completed 7 TODOs (#23-26, #28-29, plugin license fix)
- Meg: YELLOW (286 tests, 2 pre-existing failures in SQL Optimizer test isolation)
- Brock: NEEDS ATTENTION (SEC-012: CVE in anthropic SDK 0.86.0, one-line bump to 0.87.0 -- non-urgent, product on hold)
- All agents ran successfully, git push done by Debbie AM 4/2

---

## Decisions Made

### 1. DECIDED: BSL 1.1 licensing for Lore products (2026-03-31)

**Decision:** Switch from MIT to BSL 1.1. Parameters confirmed by Debbie:
- **Change Date:** 4 years (each version converts to open source 4 years after release)
- **Change License:** Apache 2.0
- **Additional Use Grant:** LoreConvo: free for individual non-commercial use with up to 50 sessions. LoreDocs: free for individual non-commercial use with up to 3 vaults.

**Background:** The IP Protection Strategy (`docs/IP_Protection_Strategy_Labyrinth.docx`,
Section 6) recommended BSL 1.1 to prevent competitors from forking and reselling. Both
repos are already public on GitHub under MIT. Code already published under MIT stays MIT
for anyone who already has it; the license change applies going forward only.

**Ron handles:** Create LICENSE files, update pyproject.toml, update all doc references.
This is now unblocked as `CLAUDE.md` Ron TODO #3.

**Debbie steps (after Ron finishes the file changes):**
1. Review the LICENSE files Ron creates in each product directory
2. Push the changes from your Mac (`git push origin master`) since Cowork can't push
3. Consider the IP strategy doc's advice to consult an IP attorney for the MIT-to-BSL transition on already-public repos

Note: GitHub auto-detects the license from the LICENSE file, so no manual repo settings change is needed.

### 2. DECIDED: Self-hosted GitHub marketplace (2026-03-31)

**Decision:** Proceed with self-hosted GitHub marketplace (labyrinth-analytics/claude-plugins).
The official Claude marketplace has "knowledge-work-plugins" reserved by Anthropic, so
self-hosted is the path forward. Can submit to the official marketplace later if it opens up.

**Ron handles:** Build out the GitHub marketplace repo, package plugins for distribution,
integrate Stripe billing.

**This unblocks:**
- Stripe billing integration (Debbie TODO #5 -- activate live Stripe account)
- Revenue collection for both LoreConvo and LoreDocs
- SQL Optimizer paid API backend

### 3. DECIDED: Pipeline opportunity dispositions (2026-03-31)

**Scout opportunities (should be assigned OPP-006 through OPP-010):**
- OPP-006: SSIS Packager Analyzer -- ON HOLD (no local SQL Server installation)
- OPP-007: Data Pipeline Test Harness MCP -- APPROVED for architectural review, P2
- OPP-008: Schema Diff & Migration MCP -- ON HOLD (no local SQL Server installation)
- OPP-009: Data Catalog Lite MCP -- APPROVED for architectural review, P1
- OPP-010: ETL Pattern Library Skill -- APPROVED for architectural review, P3

**Gina architecture items:**
- OPP-001: ON HOLD (no local SQL Server installation)
- OPP-002: APPROVED. Brock should review architectural plans for security concerns going forward.
- OPP-003: Already documented. Product name: **LorePrompts**. Pricing: $10/mo. Deployment: same route as all LoreSuite tools unless compelling reason otherwise. Follow-up for Gina: create a data model showing how all LoreSuite tools' tables relate in the SQLite DB.
- OPP-004: APPROVED. Product name: **LoreScope**.

### 4. DECIDED: SQL Query Optimizer on hold (2026-03-31)

Project on hold -- no local SQL Server installation to test against. API key has been
rotated (SEC-001 resolved). Will resume when SQL Server is available.

---

## Things Only Debbie Can Do

### 5. File USPTO trademarks for LoreConvo & LoreDocs (ON HOLD)
- ON HOLD per Debbie 2026-04-02: wait until products gain traction (repo views, users trying it out, revenue). Landscape shifting rapidly, $700 not justified yet.
- Class 009, estimated $350 each. Names are TESS-clean and Google-clean.

### 6. Activate live Stripe account
- Sandbox already set up (2026-03-22). LoreDocs `tiers.py` has TierEnforcer ready.
- Credit union account still pending (technical issue 3/31, not ready as of 4/2)
- What's needed: business verification, bank account for payouts, EIN for Labyrinth Analytics
- Where this is tracked: `CLAUDE.md` Debbie TODO #5

### 7. Review rebuilt .plugin files (BLOCKED on Ron)
- Debbie reviewed 2026-04-02 and found install flow is broken (see CRITICAL section above)
- Ron must fix marketplace, .mcp.json defaults, and README instructions before Debbie can meaningfully re-test
- Where this is tracked: `CLAUDE.md` Debbie TODO #4

### 8. Publish Madison's blog post (IN PROGRESS)
- "Why Your Claude Sessions Start From Zero" approved 2026-04-02
- Debbie publishing via Labyrinth Analytics website project

---

## Ron Action Items (TOP PRIORITY -- from Debbie's 4/2 plugin review)

**THE INSTALL FLOW IS BROKEN. Fix this before anything else.**

Ron's next session must focus entirely on the marketplace + plugin distribution block:

1. **Build the marketplace repo** (`labyrinth-analytics/claude-plugins`): create the GitHub repo with `marketplace.json`, package both .plugin files, write install instructions. TEST the full flow end-to-end.

2. **Fix .mcp.json PRO defaults:** Both LoreConvo and LoreDocs ship with PRO=1. Change to "" (free tier) for public distribution.

3. **Fix README install instructions (both products):**
   - Add the `/install <name>` enable step after `/plugin install`
   - Add CLAUDE.md snippet for session start/end rules
   - Document mounting .loreconvo/.loredocs directory to projects/Desktop for Cowork access
   - Only document install paths that ACTUALLY WORK. Mark anything not yet built as "Coming Soon"

4. **Design license key validation:** Users can currently bypass Pro tier by setting env var. Need Stripe -> license key -> validation. Can build alongside marketplace but design it now.

### Previous Ron action items (lower priority, do after marketplace works)
5. **Gina follow-up:** Request Gina create a data model showing how all LoreSuite tools' SQLite tables relate
6. **Process improvement:** Brock reviews Gina architecture proposals for security before they go to Ron

---

## Reviews Waiting (Agent Reports)

### Meg QA -- 2026-04-02 (YELLOW)
286 tests passing (+25 from yesterday). One MEDIUM finding:
- **MEG-036:** Test isolation bug in SQL Optimizer credit tests -- 2 tests fail in aggregate runs due to cross-file `os.environ` pollution. Meg wrote isolated replacement tests. Ron should fix the original file. (Non-urgent: SQL Optimizer is ON HOLD)
- Full report: check `docs/qa/` for latest

### Brock Security -- 2026-04-02 (NEEDS ATTENTION)
- **SEC-012 (MEDIUM, NEW):** CVEs in anthropic==0.86.0 (SQL Optimizer). CVE-2026-34450 (world-readable memory files) and CVE-2026-34452 (async symlink escape). Fix: bump to 0.87.0. Low actual risk on single-user Mac, and product is on hold.
- **SEC-013 (LOW, NEW):** SQL Optimizer missing product-level .gitignore
- LoreConvo and LoreDocs: 0 CVEs, OWASP all PASS
- Full report: check `docs/security/` for latest

### Jacqueline PM Dashboard -- 2026-04-02
- Interactive dashboard: `docs/pm/executive_dashboard_2026_04_02.html`
- NOTE: Jacqueline's task updated 2026-04-02 to also update this DEBBIE_DASHBOARD.md daily and fix day-of-week bug (was showing Wednesday for Thursday)

---

## Pipeline Items Awaiting Your Review

Scout finds opportunities on Mondays; Gina writes architecture proposals on Wed/Sat.
Your review points in the pipeline:

1. **Scouted items** -- pick winners, move to `approved-for-review` with priority (P1-P5)
2. **Architecture-proposed items** -- review Gina's proposals, move to `approved` or `rejected`
3. **Completed items** -- verify Ron's finished work

To check current pipeline status, ask any Claude session to run:
```python
from pipeline_helpers import PipelineDB
db = PipelineDB()
db.get_by_status("scouted")        # Items waiting for your first review
db.get_by_status("architecture-proposed")  # Gina's proposals waiting for approval
db.get_by_status("completed")      # Finished work waiting for verification
```

---

## Pending Items (Other Projects -- from global CLAUDE.md)

These are tracked in the global `~/.claude/CLAUDE.md` under "Pending Items":

- ~~K-1 parser~~ -- COMPLETED, taxes mailed for 2025
- **Portfolio maker/checker validation** -- in progress
- **Crypto price API** -- connected. ATOM unstaked. ETH unstaking in progress.
- **Portfolio_Master remaining tabs** -- in progress
- ~~Recalculate projected federal tax~~ -- COMPLETED
- **2024 Amended Return (1040-X)** -- filed Feb 25, 2026; waiting on IRS processing

---

## Where Things Live (Quick Reference)

| What | Where |
|------|-------|
| This dashboard | `docs/DEBBIE_DASHBOARD.md` |
| Agent instructions + Ron/Debbie TODOs (source of truth) | `CLAUDE.md` (repo root) |
| Completed work log | `docs/COMPLETED.md` |
| QA reports (Meg) | `docs/qa/qa_report_YYYY_MM_DD.md` |
| Security reports (Brock) | `docs/security/security_report_YYYY_MM_DD.md` |
| PM dashboard (Jacqueline) | `docs/pm/executive_dashboard_YYYY_MM_DD.html` |
| Pipeline data | LoreConvo DB (`~/.loreconvo/sessions.db`, surface='pipeline') |
| Product details | Per-product CLAUDE.md in `ron_skills/<product>/CLAUDE.md` |
| Global project context | `~/.claude/CLAUDE.md` |
| Product roadmap | `Project_Ron_Product_Roadmap.html` |
