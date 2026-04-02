# Debbie's Action Dashboard

Single source of truth for everything that needs Debbie's attention.
Updated by Jacqueline (daily) or manually. Last updated: 2026-04-01.

---

## URGENT — Security (from Brock 2026-03-31)

~~**Revoke the Anthropic API key** at console.anthropic.com.~~ DONE (2026-03-31).
Debbie rotated the key. SEC-001 can be closed in Brock's next report.

---

## TODAY -- 2026-04-01

### Stripe Checking Account Setup (DEBBIE ACTION -- by Friday 4/3)

Open a new checking account at your credit union for Labyrinth Analytics Stripe payouts.
Credit union had a technical issue 3/31; account creation in progress as of 4/1.
Expected ready: 4/2 or 4/3. Not blocking Ron -- marketplace repo build comes first.

Once the account is open:
1. Log in to Stripe Dashboard (dashboard.stripe.com)
2. Settings -> Business settings -> Complete business verification (EIN for Labyrinth Analytics)
3. Settings -> Payouts -> Add the new checking account as payout destination
4. Switch from Sandbox to Live mode

This unblocks: marketplace payment collection, LoreConvo/LoreDocs Pro tier billing.

### New Agent: Madison (Marketing)
Madison has been added to the agent team. She runs Tuesday + Friday at 1:00 AM.
First run: tomorrow (Tuesday 4/2). All content goes to `docs/marketing/blog_drafts/`
as drafts for your review. She will NOT publish anything without your approval.

### Pipeline Process Fix
All agent CLAUDE.md instructions updated to require PipelineDB usage.
Ron's top priority tonight is syncing your 3/31 decisions to the pipeline DB,
then building the marketplace repo. Gina should see approved items on her
Saturday 4/4 run.

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

### 5. File USPTO trademark for LoreConvo
- Class 009, estimated $350
- Both names are TESS-clean and Google-clean (verified 2026-03-25)
- Where this is tracked: `CLAUDE.md` Debbie TODO #1

### 6. File USPTO trademark for LoreDocs
- Class 009, estimated $350
- Where this is tracked: `CLAUDE.md` Debbie TODO #2

### 7. Activate live Stripe account
- Sandbox already set up (2026-03-22). LoreDocs `tiers.py` has TierEnforcer ready.
- What's needed: business verification, bank account for payouts, EIN for Labyrinth Analytics
- Now unblocked by marketplace decision (#2 above) -- proceed when marketplace repo is ready
- Where this is tracked: `CLAUDE.md` Debbie TODO #5

### 8. Review rebuilt .plugin files (DEFERRED)
- Deferred until after Ron completes BSL license changes and rebuilds plugins
- Plugin READMEs in loreconvo-plugin/ and loredocs-plugin/ directories are APPROVED
- Ron still needs to fix: LoreConvo README.md personal path (`~/projects/side_hustle/...` should be generic like `~/path/to/loreconvo`), add Linux clipboard support mention to export-to-chat docs, and create a LoreDocs README.md (currently missing from repo)
- Where this is tracked: `CLAUDE.md` Debbie TODO #4

---

## Ron Action Items (from this review)

These are for Ron's next session, in addition to his existing TODO list:

1. **LoreConvo README.md fixes:**
   - Replace personal path `~/projects/side_hustle/ron_skills/loreconvo` with generic example like `~/path/to/loreconvo`
   - Update Claude Chat section to mention Linux support (script falls back to printing output when `pbcopy` is unavailable; could also detect `xclip`/`wl-copy`)
   - Update license line from "MIT" to "BSL 1.1"

2. **LoreDocs README.md:** Create one (currently missing from the repo entirely)

3. **Pipeline IDs:** Assign OPP-006 through OPP-010 to the latest Scout opportunities

4. **Process improvement:** Add Brock architectural security review step -- Brock reviews Gina's architecture proposals for security concerns before they go to Ron

5. **Gina follow-up:** Request Gina create a data model showing how all LoreSuite tools' SQLite tables relate to each other

---

## Reviews Waiting (Agent Reports)

### Meg QA -- 2026-03-31 (YELLOW)
227 tests passing, 0 failing. One MEDIUM finding:
- **MEG-031:** SQL Optimizer version mismatch -- CLAUDE.md says v0.1.0, SKILL.md says 1.0.0
- Two LOW findings (FTS schema drift, auto_save schema) -- no action needed from you
- Full report: `docs/qa/qa_report_2026_03_31.md`

### Brock Security -- 2026-03-31 (NEEDS ATTENTION)
- **SEC-001 (INFO):** API key rotation -- DONE by Debbie 2026-03-31
- **SEC-010 (HIGH):** Partial API key in git history -- Ron needs to commit the redacted file
- **SEC-011 (MEDIUM, NEW):** TOCTOU race in LoreDocs file export -- Ron will fix before multi-user
- **SEC-003 (RESOLVED):** Dependency pinning done for all products
- Full report: `docs/security/security_report_2026_03_31.md`

### Jacqueline PM Dashboard -- 2026-03-31
- Interactive dashboard: `docs/pm/executive_dashboard_2026_03_31.html`

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
