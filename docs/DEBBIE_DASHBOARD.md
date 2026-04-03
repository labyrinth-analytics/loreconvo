# Debbie's Action Dashboard

Single source of truth for everything that needs Debbie's attention.
Updated by Jacqueline (daily) or manually. Last updated: 2026-04-03.

---

## TODAY -- 2026-04-03 (Friday)

### RESOLVED: Plugin Install Flow -- Most Issues Fixed (Ron 4/3)

Ron completed the marketplace + plugin distribution block overnight on 4/3:
- Marketplace repo structure built (marketplace/claude-plugins/ with marketplace.json)
- Both .mcp.json files fixed: PRO defaults changed from "1" to "" (free tier)
- Both plugin READMEs updated with full install flow: marketplace add, plugin install, /install enable, CLAUDE.md snippet, Cowork mount instructions
- Both plugin.json files updated with homepage/repository fields, LoreDocs license fixed to BSL-1.1
- Both .plugin zips rebuilt with all fixes
- SEC-012 fixed (anthropic 0.86.0 -> 0.87.0 in SQL Optimizer)
- SEC-013 fixed (.gitignore added to SQL Optimizer)

**Still needs Debbie:**
- Create GitHub repo labyrinth-analytics/claude-plugins and push marketplace/ contents
- Test the full install flow end-to-end
- Review rebuilt .plugin files

**Still needs Ron (next session):**
- License key validation for Pro tier (env var alone is bypassable)

### Madison Blog Post #2 Ready for Review

"Building a Reference Library for AI Projects: How LoreDocs Vault Architecture Works"
- 1400+ words, covers semantic vaults, episodic vs reference knowledge, LoreConvo cross-reference
- File: docs/marketing/blog_drafts/blog_loredocs_vault_architecture_2026_04_03.md
- Madison's content calendar has 8 weeks planned through May 9

### Stripe Checking Account Setup (DEBBIE ACTION)

Credit union account still pending as of 4/2. Not blocking Ron -- marketplace repo comes first.
Once the account is open: business verification, bank account for payouts, EIN for Labyrinth Analytics.

### Overnight Summary (from Jacqueline 4/3 dashboard)
- Ron: DID NOT RUN on 4/3. Last session was 4/2 (7 TODOs completed: #23-26, #28-29, plugin.json fix)
- Meg: YELLOW -- 304 tests (+18 from yesterday), 2 pre-existing failures. NEW: MEG-037 (HIGH) confirms PRO defaults still broken
- Brock: NEEDS ATTENTION (trending positive) -- SEC-012 and SEC-013 RESOLVED. 0 new CVEs. Report generated but no LoreConvo session saved.
- Madison: Blog #2 drafted (LoreDocs vault architecture). Content calendar updated through May 9.
- Blog #1 ("Why Your Claude Sessions Start From Zero") published on Labyrinth Analytics website 4/2

---

## Decisions Made

### 1. DECIDED: BSL 1.1 licensing for Lore products (2026-03-31)

**Decision:** Switch from MIT to BSL 1.1. Parameters confirmed by Debbie:
- **Change Date:** 4 years (each version converts to open source 4 years after release)
- **Change License:** Apache 2.0
- **Additional Use Grant:** LoreConvo: free for individual non-commercial use with up to 50 sessions. LoreDocs: free for individual non-commercial use with up to 3 vaults.

**Status:** COMPLETED by Ron on 2026-03-31. LICENSE files created, pyproject.toml updated, all doc references updated, plugins rebuilt.

### 2. DECIDED: Self-hosted GitHub marketplace (2026-03-31)

**Decision:** Proceed with self-hosted GitHub marketplace (labyrinth-analytics/claude-plugins).
The official Claude marketplace has "knowledge-work-plugins" reserved by Anthropic, so
self-hosted is the path forward. Can submit to the official marketplace later if it opens up.

**Status:** COMPLETED by Ron on 2026-04-03. Marketplace structure built locally (marketplace/claude-plugins/). Debbie needs to create the GitHub repo and push.

### 3. DECIDED: Pipeline opportunity dispositions (2026-03-31)

**Scout opportunities:**
- OPP-006: SSIS Packager Analyzer -- ON HOLD (no local SQL Server)
- OPP-007: Data Pipeline Test Harness MCP -- APPROVED for architectural review, P2
- OPP-008: Schema Diff & Migration MCP -- ON HOLD (no local SQL Server)
- OPP-009: Data Catalog Lite MCP -- APPROVED for architectural review, P1
- OPP-010: ETL Pattern Library Skill -- APPROVED for architectural review, P3

**Gina architecture items:**
- OPP-001: ON HOLD (no local SQL Server)
- OPP-002: APPROVED. Brock should review architectural plans for security concerns going forward.
- OPP-003: Already documented. Product name: **LorePrompts**. Pricing: $10/mo.
- OPP-004: APPROVED. Product name: **LoreScope**.

### 4. DECIDED: SQL Query Optimizer on hold (2026-03-31)

Project on hold -- no local SQL Server installation to test against.

---

## Things Only Debbie Can Do

### 5. File USPTO trademarks for LoreConvo & LoreDocs (ON HOLD)
- ON HOLD per Debbie 2026-04-02: wait until products gain traction (repo views, users trying it out, revenue). Landscape shifting rapidly, $700 not justified yet.
- Class 009, estimated $350 each. Names are TESS-clean and Google-clean.

### 6. Activate live Stripe account
- Sandbox already set up (2026-03-22). LoreDocs `tiers.py` has TierEnforcer ready.
- Credit union account still pending (technical issue 3/31, not ready as of 4/2)
- What's needed: business verification, bank account for payouts, EIN for Labyrinth Analytics
- Where this is tracked: `CLAUDE.md` Debbie TODO #4

### 7. Review rebuilt .plugin files (BLOCKED on Ron)
- Debbie reviewed 2026-04-02 and found install flow is broken (see CRITICAL section above)
- Ron must fix marketplace, .mcp.json defaults, and README instructions before Debbie can meaningfully re-test
- Where this is tracked: `CLAUDE.md` Debbie TODO #3

### 8. Publish Madison's blog post #2 (NEW -- ready for review)
- "Building a Reference Library for AI Projects: How LoreDocs Vault Architecture Works"
- File: docs/marketing/blog_drafts/blog_loredocs_vault_architecture_2026_04_03.md
- Blog #1 published successfully on 4/2

---

## Ron Action Items (TOP PRIORITY -- from Debbie's 4/2 plugin review)

**THE INSTALL FLOW IS BROKEN. Fix this before anything else.**

Ron's next session must focus entirely on the marketplace + plugin distribution block:

1. **Build the marketplace repo** (`labyrinth-analytics/claude-plugins`): create the GitHub repo with `marketplace.json`, package both .plugin files, write install instructions. TEST the full flow end-to-end.

2. **Fix .mcp.json PRO defaults:** Both LoreConvo and LoreDocs ship with PRO=1. Change to "" (free tier) for public distribution. MEG-037 (HIGH) confirms this is still broken as of 4/3.

3. **Fix README install instructions (both products):**
   - Add the `/install <name>` enable step after `/plugin install`
   - Add CLAUDE.md snippet for session start/end rules (DONE 4/2)
   - Document mounting .loreconvo/.loredocs directory to projects/Desktop for Cowork access
   - Only document install paths that ACTUALLY WORK. Mark anything not yet built as "Coming Soon"

4. **Design license key validation:** Users can currently bypass Pro tier by setting env var. Need Stripe -> license key -> validation. Can build alongside marketplace but design it now.

5. **Commit staged Brock fixes:** SEC-012 (anthropic bump) and SEC-013 (.gitignore) are staged but not committed.

### Previous Ron action items (lower priority, do after marketplace works)
6. **Gina follow-up:** Request Gina create a data model showing how all LoreSuite tools' SQLite tables relate
7. **Process improvement:** Brock reviews Gina architecture proposals for security before they go to Ron
8. **Stale worktree cleanup:** .claude/worktrees/pedantic-bardeen/ should be removed

---

## Reviews Waiting (Agent Reports)

### Meg QA -- 2026-04-03 (YELLOW)
304 tests passing (+18 from yesterday). 24 new tests written. Findings:
- **MEG-037 (HIGH, NEW):** Plugin .mcp.json files (loreconvo-plugin, loredocs-plugin) ship with PRO=1. Must be "" for public distribution. Cross-validates Debbie's 4/2 finding. Ron TODOs #2/#3.
- **MEG-036 (MEDIUM, EXISTING):** SQL Optimizer test isolation bug -- 2 tests fail in aggregate runs. Meg wrote isolated replacements. Non-urgent (product ON HOLD).
- Full report: `docs/qa/qa_report_2026_04_03.md`

### Brock Security -- 2026-04-03 (NEEDS ATTENTION, trending positive)
- **SEC-012 RESOLVED:** anthropic bumped to 0.87.0 (staged, pending commit)
- **SEC-013 RESOLVED:** SQL Optimizer .gitignore created (staged, pending commit)
- **SEC-011 (MEDIUM, EXISTING):** TOCTOU race in LoreDocs file export -- low risk on single-user machine
- **SEC-006 (LOW, EXISTING):** CreditManager race condition -- product on hold
- LoreConvo: 0 CVEs | LoreDocs: 0 CVEs | SQL Optimizer: 0 CVEs (after bump)
- Full report: `docs/security/security_report_2026_04_03.md`

### Jacqueline PM Dashboard -- 2026-04-03
- Interactive dashboard: `docs/pm/executive_dashboard_2026_04_03.html`

---

## Pipeline Items Awaiting Your Review

Scout finds opportunities on Mondays; Gina writes architecture proposals on Wed/Sat.
Your review points in the pipeline:

1. **Scouted items** -- pick winners, move to `approved-for-review` with priority (P1-P5)
2. **Architecture-proposed items** -- review Gina's proposals, move to `approved` or `rejected`
3. **Completed items** -- verify Ron's finished work

**Current pipeline state (17 items):**
- 3 awaiting architecture review: OPP-015 (Data Catalog Lite, P1), OPP-013 (Test Harness, P2), OPP-016 (ETL Patterns, P3)
- 3 approved: OPP-002 (AI Cost Attribution), OPP-003 (LorePrompts), OPP-004 (LoreScope)
- 5 completed: security hardening (OPP-006 through OPP-011)
- 4 on hold: OPP-001, OPP-005, OPP-012, OPP-014 (SQL Server dependency)

Gina runs next on Saturday 4/4 -- should produce architecture proposals for the 3 awaiting items.

To check current pipeline status, ask any Claude session to run:
```python
from pipeline_helpers import PipelineDB
db = PipelineDB()
db.get_by_status("scouted")
db.get_by_status("architecture-proposed")
db.get_by_status("completed")
```

---

## Pending Items (Other Projects -- from global CLAUDE.md)

These are tracked in the global `~/.claude/CLAUDE.md` under "Pending Items":

- **Portfolio maker/checker validation** -- in progress
- **Crypto price API** -- connected. ATOM unstaked. ETH unstaking in progress.
- **Portfolio_Master remaining tabs** -- in progress
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
| Marketing blog drafts | `docs/marketing/blog_drafts/` |
| Content calendar | `docs/marketing/content_calendar_madison.md` |
