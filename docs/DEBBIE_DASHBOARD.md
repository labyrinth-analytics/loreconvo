# Debbie's Action Dashboard

Single source of truth for everything that needs Debbie's attention.
Updated by Jacqueline (daily) or manually. Last updated: 2026-04-08 (Jacqueline daily run).

---

## TODAY -- 2026-04-08 (Wednesday)

### STABILITY MANDATE: IN PROGRESS -- Feature Freeze STILL IN EFFECT

CLAUDE.md has 1 remaining open TODO for the Stability Mandate:
1. Fix plugin install.sh -- LoreConvo must run `pip install .` (not just requirements.txt); LoreDocs needs install.sh added from scratch. Ron's next session priority.
2. ~~Fix fallback script DB discovery~~ -- DONE by Ron (fbfdd11, Apr 7). Meg verified correct. Brock confirmed security-positive. **Awaiting Debbie's Cowork end-to-end confirmation.**

Nothing ships until TODO #1 is complete AND Debbie confirms Cowork MCP tools are callable and sessions persist.

**Overnight summary (agents for Apr 7-8):**
- Ron: Ran Apr 7 5:08 PM. Fixed Stability Mandate TODO #2 -- DB discovery now checks mounted paths first (fbfdd11). Meg + Brock verified.
- Meg: Ran Apr 7 6:36 PM. YELLOW. 359 tests pass. MEG-052 (combined pytest) open. MEG-053 (glob sort advisory, INFO).
- Brock: Ran Apr 8 12:39 AM. NEEDS ATTENTION (stable). 0 CVEs. SEC-023 (INFO, same glob sort edge case). pip-audit clean.
- Competitive Intel: Debbie ran Cowork session Apr 7. MemPalace (ChromaDB vector + SQLite temporal KG, multi-LLM) added as HIGH threat.
- John: Ran Apr 7 4:47 AM. Created missing LoreConvo INSTALL.md.
- Madison: Ran Apr 7 12:40 AM. Fixed blog #2 (all 3 Debbie feedback items applied, ready for review). Created blog #3 draft.
- Jacqueline: Running now (Apr 8 1:38 AM)

### IMMEDIATE ACTION: Apply 8 Pending Commits

8 agent commits are stuck in pending_commits.json (git push blocked from Cowork VM).
Run from your Mac: `python scripts/safe_git.py apply`

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

### 5. DECIDED: Gina architecture review dispositions (2026-04-04)

**Architecture proposals:**
- OPP-015 (Data Catalog Lite): APPROVED
- OPP-013 (Data Pipeline Test Harness): ON HOLD
- OPP-016 (ETL Pattern Library): ON HOLD

**Gina product review findings -- add ALL to Ron's TODO:**
- GINA-001, GINA-002: Add to Ron's TODO
- LoreConvo v0.3.0: Add H1, H2, H3 and all 5 MEDIUM findings to Ron's TODO
- LoreDocs v0.1.0: Add H1, H2, H3 and all 5 MEDIUM findings to Ron's TODO
- BROCK-REVIEW items: Add to Brock's next review scope

All products should use Lore branding consistently.

### 6. DECIDED: Scout opportunity dispositions batch 2 (2026-04-04)

- OPP-017 (LoreEval): Not triaged yet
- OPP-018 (LangGraph Workflow Inspector): Not triaged yet
- OPP-019 (FinNorm - Brokerage CSV Normalizer): APPROVED
- OPP-020 (LoreCheck - Data Quality CLI): APPROVED
- OPP-021 (Chain Lens - Prompt Chain Observability): APPROVED

### 7. DECIDED: Agent governance updates (2026-04-04)

- All agents now use safe_git.py for git operations (no more raw git commands)
- Turn budgets enforced: Ron 30, Meg/Brock 25, others 20. Hard cap 50.
- Agent Communication Protocol added to CLAUDE.md (structured LoreConvo sessions)
- Business email for marketplace: info@labyrinthanalyticsconsulting.com (not Gmail)

### 8. DECIDED: Test files should NOT be in public repos (2026-04-04)

Meg's test scripts are being tracked in git and would be included in subtree pushes to public repos. Add tests/ to public repo .gitignore or exclude from subtree pushes. Ron to fix before next subtree push.

---

## Things Only Debbie Can Do

### TOP PRIORITY

#### Apply 8 Pending Git Commits
Run from your Mac: `python scripts/safe_git.py apply`
Includes Ron's DB discovery fix (fbfdd11), Meg QA Apr 7, Brock security Apr 7, John INSTALL.md, Gina product review Apr 5, Madison blog fixes, governance updates.

#### [DONE] Silent Agent Investigation -- Resolved
Ron, Meg, and Brock all ran successfully on Apr 7 with sessions logged. The cd path fix
from your April 5 session is confirmed working. Remove this item -- no longer a concern.

#### Triage 2 remaining Scout opportunities (OPP-017, OPP-018)
OPP-019 (FinNorm), OPP-020 (LoreCheck), OPP-021 (Chain Lens) already pre-approved.
Still need your decision on:

#### Triage 5 new Scout opportunities (OPP-017 to OPP-021)
Scout surfaced these on Friday Apr 3. Decide: Approve / Needs Info / Defer / Reject for each.

| OPP | Name | Effort | Est. MRR M12 | Scout Notes |
|-----|------|--------|--------------|-------------|
| OPP-017 | LoreEval (AI Agent Test Runner) | 3 | ~$900 | pytest-style LLM eval CLI |
| OPP-018 | LangGraph Workflow Inspector | 5 | ~$700 | Debug LangGraph state machines |
| OPP-019 | FinNorm (Brokerage CSV Normalizer) | 3 | ~$600 | Schwab/YNAB/Buildium normalizer |
| OPP-020 | LoreCheck (Data Quality CLI) | 5 | ~$1,200 | Great Expectations alternative |
| OPP-021 | Chain Lens (Prompt Chain Observability) | 5 | ~$800 | Observe multi-step LLM chains |

#### Create GitHub repo + push marketplace
- `marketplace.json` owner.email confirmed correct: info@labyrinthanalyticsconsulting.com (SEC-015 RESOLVED)
- Create `labyrinth-analytics/claude-plugins` on GitHub
- Push `marketplace/` directory contents
- Test: `/plugin marketplace add labyrinth-analytics/claude-plugins`
  followed by: `/plugin install loreconvo@labyrinth-analytics-claude-plugins`
  then: `/install loreconvo`
Where tracked: `CLAUDE.md` Debbie TODO #6

### MEDIUM PRIORITY

#### Review rebuilt .plugin files (ready -- all fixes applied)
Ron fixed all install flow issues on Apr 3:
- Both .mcp.json files now ship with empty PRO defaults (MEG-037 RESOLVED)
- READMEs have full install flow docs (marketplace add, /install step, CLAUDE.md snippet, Cowork mount)
- Both plugin.json files updated (homepage/repository fields, LoreDocs license fixed to BSL-1.1)
- Both .plugin zips rebuilt
Where tracked: `CLAUDE.md` Debbie TODO #3

#### Activate live Stripe account
- Sandbox already set up (2026-03-22). LoreDocs `tiers.py` has TierEnforcer ready.
- Credit union account still pending (technical issue as of 4/2)
- What's needed: business verification, bank account for payouts, EIN for Labyrinth Analytics
Where tracked: `CLAUDE.md` Debbie TODO #5

#### Publish Madison blog post #2 -- READY FOR REVIEW
- "Building a Reference Library for AI Projects: A Vault Blueprint for Reliable AI Development"
- File: `docs/internal/marketing/blog_drafts/blog_loredocs_vault_architecture_2026_04_03.md`
- Blog #1 published successfully on Apr 2
- **STATUS: All fixes applied 2026-04-07. Ready for Debbie review.**
- **FIXES APPLIED BY MADISON (2026-04-07):**
  1. Frontmatter format: `date` now quoted, `keywords` and `products` converted to multi-line YAML list format, `status: draft` field removed
  2. Version number: "LoreDocs v0.1.0" removed, replaced with "LoreDocs is production-ready for storing and organizing reference knowledge..."
  3. Competitor naming: Kept direct naming (Confluence/Notion/Google Drive) as defensible -- these are general tools, not direct AI competitors.
  4. Minor polish: AI Workflow narrated-session paragraph split into two shorter paragraphs for better pacing.
  Full review saved to LoreConvo (session 8f296a1e).

#### New blog post #3 -- DRAFT READY FOR REVIEW
- "Your AI's Knowledge Stack: Why LoreDocs, Obsidian, and NotebookLM Complement Each Other"
- File: `docs/internal/marketing/blog_drafts/blog_knowledge_stack_venn_2026_04_07.md`
- Created by Madison Apr 7. Positions LoreDocs alongside complementary tools (Obsidian, NotebookLM). Not competing, complementing.

### ON HOLD

#### File USPTO trademarks for LoreConvo & LoreDocs
- ON HOLD per Debbie 2026-04-02: wait until products gain traction (repo views, users, revenue)
- Class 009, estimated $350 each. Names are TESS-clean and Google-clean.
Where tracked: `CLAUDE.md` Debbie TODOs #1 and #2

---

## Ron Action Items (CURRENT)

### TOP PRIORITY for next Ron session

1. **Fix SEC-014:** Add `cryptography>=42.0.0` to [project.dependencies] in both
   `ron_skills/loreconvo/pyproject.toml` and `ron_skills/loredocs/pyproject.toml`.
   Without this, Pro license validation fails with ModuleNotFoundError on fresh installs.

2. **Clean stale git locks (first):** `find .git -name "*.lock" -mmin +30 -delete`
   Then commit untracked files:
   - `scripts/generate_license_key.py`
   - `scripts/test_generate_license_key.py`
   - `docs/internal/security/security_report_2026_04_03_b.md`

3. **LoreConvo CLI entry point (TODO #1):** Add `ron_skills/loreconvo/src/cli/` with
   save-session, list-sessions, search commands. Migrate logic from scripts/save_to_loreconvo.py.

4. **Fix GINA-001 (MEDIUM):** Fix `vault_set_tier` bypass in LoreDocs -- get_tier() reads config.json fallback before license check. Must be fixed before marketplace publish.

5. **Fix GINA-002 (MEDIUM):** Rebuild LoreConvo .plugin bundle to include the `/lore-onboard` skill. Users installing from marketplace won't get the onboarding command without this fix.

6. **Fix MEG-038 (LOW):** Remove unused import (Encoding, PublicFormat) in `ron_skills/loreconvo/src/core/license.py`.

### AFTER CLI ENTRY POINTS

5. LoreDocs CLI entry point (TODO #2)
6. Slim down agent prompts to reference product CLIs (TODO #3)
7. Update monorepo scripts to be thin wrappers (TODO #4)
8. Update CLAUDE.md agent paths (TODO #5, cleanup)

---

## Reviews Waiting (Agent Reports)

### Gina Architecture -- 2026-04-04 (RAN -- 3 proposals)
Architecture proposals for all 3 waiting items. Full proposals in `docs/internal/architecture/`.

**OPP-015 (Data Catalog Lite, P1):** HIGH COMPATIBILITY with Lore architecture. Reuses TierEnforcer pattern. $10/mo Pro. Gina recommends APPROVE.

**OPP-013 (Data Pipeline Test Harness, P2):** MODERATE COMPATIBILITY. New pattern (dual-DB connections). $15/mo Pro. Review carefully before approving.

**OPP-016 (ETL Pattern Library, P3):** Gina recommends scope RETHINK -- SQL-Server-only is too narrow. Reframe to two-dialect (T-SQL + Python) or pure Python. Needs your decision on scope before she can approve.

**Product review findings (2 MEDIUM):**
- **GINA-001 (MEDIUM):** LoreDocs `vault_set_tier('pro')` via MCP bypasses license validation. Ron must fix before publish.
- **GINA-002 (MEDIUM):** `/lore-onboard` skill not packaged in .plugin bundle. Ron must rebuild .plugin zip.

Full report: `docs/internal/architecture/product_review_2026_04_04.md`

### John Tech Docs -- 2026-04-04 (FIRST RUN)
John created baseline documentation for both products:
- LoreConvo: `cli_reference.md`, `mcp_tool_catalog.md`, `quickstart.md`, `CHANGELOG.md`
- LoreDocs: `mcp_tool_catalog.md`, `quickstart.md`, `CHANGELOG.md`
- SEC-014 noted in LoreDocs CHANGELOG as known issue
- Full report: `docs/internal/technical/tech_docs_report_2026_04_04.md`

### Meg QA -- 2026-04-07 (YELLOW)
359 tests pass (204 LoreConvo + 39 LoreDocs + 116 internal).
- **MEG-052 (YELLOW):** Combined pytest still fails -- duplicate test_license.py basenames. Run suites separately.
- **MEG-053 (INFO/ADVISORY):** Glob sort ambiguity in DB discovery (same as SEC-023). Low risk.
- **DB discovery fix (fbfdd11) VERIFIED CORRECT** by Meg -- Stability Mandate TODO #2 logic confirmed.
- Full report: `docs/internal/qa/qa_report_2026_04_07.md`

### Brock Security -- 2026-04-07/08 (NEEDS ATTENTION, stable)
- **SEC-023 (INFO):** Glob sort ambiguity in DB discovery. Data routing edge case, not a vulnerability.
- **SEC-014 (MEDIUM, open):** cryptography still missing from pyproject.toml -- RON-005. Frozen.
- **DB discovery fix SECURITY-POSITIVE:** fbfdd11 routes writes to Mac-backed mount. Confirmed.
- 0 CVEs. pip-audit clean on both products.
- Full report: `docs/internal/security/security_report_2026_04_07.md`

### Jacqueline PM -- 2026-04-08 (Today)
- Daily dashboard: `docs/internal/pm/executive_dashboard_2026_04_08.html`

---

## Pipeline Items Awaiting Your Review

Scout finds opportunities on Mondays (and supplemental sessions); Gina writes architecture proposals on Wed/Sat.
Your review points in the pipeline:

1. **Scouted items** -- pick winners, move to `approved-for-review` with priority (P1-P5)
2. **Architecture-proposed items** -- review Gina's proposals, move to `approved` or `rejected`
3. **Completed items** -- verify Ron's finished work

**Current pipeline state (21 items):**
- 5 untriaged (NEW): OPP-017 to OPP-021 (Scout Apr 3 -- AI observability and data quality)
- 3 architecture-proposed: OPP-015 (P1 -- approve), OPP-013 (P2 -- review), OPP-016 (P3 -- needs scope rethink decision)
- 3 approved: OPP-002 (AI Cost Attribution), OPP-003 (LorePrompts), OPP-004 (LoreScope)
- 4 on hold: OPP-001, OPP-005, OPP-012, OPP-014 (SQL Server dependency)

Gina ran Saturday Apr 4 and produced all 3 architecture proposals. See Reviews Waiting above for details. Debbie needs to Approve or Reject each proposal.

---

## Pending Items (Other Projects -- from global CLAUDE.md)

These are tracked in the global `~/.claude/CLAUDE.md` under "Pending Items":

- **Portfolio maker/checker validation** -- in progress
- **Crypto price API** -- connected. ATOM unstaked. ETH unstaking in progress.
- **Portfolio_Master remaining tabs** -- in progress
- **2024 Amended Return (1040-X)** -- filed Feb 25, 2026; waiting on IRS processing (check after Mar 18)

---

## Where Things Live (Quick Reference)

| What | Where |
|------|-------|
| This dashboard | `docs/DEBBIE_DASHBOARD.md` |
| Agent instructions + Ron/Debbie TODOs (source of truth) | `CLAUDE.md` (repo root) |
| Completed work log | `docs/COMPLETED.md` |
| QA reports (Meg) | `docs/internal/qa/qa_report_YYYY_MM_DD.md` |
| Security reports (Brock) | `docs/internal/security/security_report_YYYY_MM_DD.md` |
| PM dashboard (Jacqueline) | `docs/internal/pm/executive_dashboard_YYYY_MM_DD.html` |
| Weekly roadmap (Jacqueline) | `docs/internal/pm/labyrinth_product_roadmap_YYYY_MM_DD.html` |
| Architecture proposals (Gina) | `docs/internal/architecture/OPP-xxx_product_name.md` |
| Architecture product reviews (Gina) | `docs/internal/architecture/product_review_YYYY_MM_DD.md` |
| Tech docs report (John) | `docs/internal/technical/tech_docs_report_YYYY_MM_DD.md` |
| Pipeline data | LoreConvo DB (`~/.loreconvo/sessions.db`, surface='pipeline') |
| Product details | Per-product CLAUDE.md in `ron_skills/<product>/CLAUDE.md` |
| Global project context | `~/.claude/CLAUDE.md` |
| Marketing blog drafts | `docs/internal/marketing/blog_drafts/` |
| Content calendar | `docs/internal/marketing/content_calendar_madison.md` |
