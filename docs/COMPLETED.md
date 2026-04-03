# Completed Work

Historical log of completed items. Ron appends here when finishing TODOs.
For full details, see git log.

## Rebrand -- Lore Product Family (2026-03-25 through 2026-03-26)

ConvoVault -> LoreConvo | ProjectVault -> LoreDocs | Brand umbrella: Lore
Both names TESS-clean and Google-clean. 24 of 28 items completed.

- [x] Rename `ron_skills/convovault/` -> `ron_skills/loreconvo/` (2026-03-26)
- [x] Rename `ron_skills/projectvault/` -> `ron_skills/loredocs/` (2026-03-26)
- [x] Rename `ron_skills/convovault-plugin/` -> `ron_skills/loreconvo-plugin/` (2026-03-26)
- [x] Rename `ron_skills/projectvault-plugin/` -> `ron_skills/loredocs-plugin/` (2026-03-26)
- [x] Update all Python imports, module names, and package references (2026-03-26)
- [x] Update CLI command names (2026-03-26)
- [x] Update database paths: `~/.convovault/` -> `~/.loreconvo/`, `~/.projectvault/` -> `~/.loredocs/` (2026-03-26)
- [x] Update .mcp.json server entries with new names (2026-03-26)
- [x] Update CLAUDE.md (2026-03-26)
- [x] Update README.md for both products (2026-03-26)
- [x] Update INSTALL.md for both products (2026-03-26)
- [x] Update SKILL.md for both products (2026-03-26)
- [x] Update plugin README files (2026-03-26)
- [x] Update marketplace listings (docs/marketplace_listing.md) for both (2026-03-26)
- [x] Update docs/PUBLISHING.md references (2026-03-26)
- [x] Update product_comparison_brief.md (2026-03-26)
- [x] Update Venn diagram HTML (2026-03-26)
- [x] Update IP_Protection_Strategy_Labyrinth.docx with new names (2026-03-26, Debbie)
- [x] Rename GitHub repos: convovault -> loreconvo, projectvault -> loredocs (2026-03-25)
- [x] Update ~/.claude/settings.json MCP server paths (2026-03-26, Debbie)
- [x] Update hook scripts (auto_load.py, auto_save.py) references (2026-03-26)
- [x] Push LoreConvo and LoreDocs repos to GitHub (2026-03-25)
- [x] GitHub repos made public (2026-03-26, Debbie)

## Lore Rebrand Finishing (2026-03-27)

- [x] Migration script for existing users (scripts/migrate_lore.py, commit 19fa791, 2026-03-27)
- [x] Rebuild loreconvo-v0.3.0.plugin with Lore names (plugin.json name: loreconvo, mcp server: loreconvo, 2026-03-27)
- [x] Rebuild loredocs-v0.1.0.plugin with Lore names (plugin.json name: loredocs, mcp server: loredocs, 2026-03-27)
- [x] Revenue projection Excel renamed: ConvoVault_Revenue_Projection.xlsx -> LoreConvo_Revenue_Projection.xlsx, old file removed from git (2026-03-27)

## LoreConvo Milestones

- [x] vault_suggest tool (commit 636dcf5, 2026-03-22)
- [x] Marketplace listing draft -- APPROVED (2026-03-22)
- [x] Marketplace listing revised per Debbie feedback (2026-03-22)
- [x] Revenue projection Excel -- APPROVED (2026-03-22)
- [x] Cowork plugin packaging (2026-03-23)
- [x] Marketplace publishing research + PUBLISHING.md (2026-03-24)
- [x] Improved SessionStart hook context quality: scoring, filtering, 4000 char cap, 23 tests (2026-03-24)
- [x] README.md "How it works across surfaces" section (2026-03-24)

## LoreDocs Milestones

- [x] Phase 2 tools: vault_link_doc, vault_unlink_doc, vault_find_related, vault_suggest, vault_export_manifest (commit ddf7f91, 2026-03-22)
- [x] Free/Pro tier gating: tiers.py + TierEnforcer + vault_tier_status + vault_set_tier, 35 tests (2026-03-22)
- [x] Cowork plugin packaging -- APPROVED (2026-03-22)
- [x] Plugin README with platform table (2026-03-22)
- [x] MCP tool-layer test suite: 43 tests (2026-03-22)
- [x] Bug fix: vault_create/vault_add_doc return error strings for TierLimitError (2026-03-22)
- [x] Marketplace listing draft -- APPROVED (2026-03-22)
- [x] Marketplace publishing research + PUBLISHING.md (2026-03-24)
- [x] Integration tests for tier enforcement: 29 tests (2026-03-25)
- [x] LOREDOCS_ROOT env var support for test isolation (2026-03-25)

## SQL Query Optimizer Milestones

- [x] Backend built: analyzer + server, 34 tests passing (commit adfd10d, 2026-03-22)

## Security Hardening - Brock Report Fixes (2026-03-30)

- [x] SEC-002: Timing-safe admin token comparison using hmac.compare_digest (main.py)
- [x] SEC-004: Mask email PII in logs -- credits.py now logs masked emails
- [x] SEC-005: Rate limits on /v1/optimize (30/min) and /v1/credits (60/min)
- [x] SEC-007: Added *.db and *.sqlite patterns to .gitignore
- [x] SEC-008: Added --reload development-only warning to QUICKSTART.md

## QA Fix - Meg Report (2026-03-30)

- [x] LOW: Fixed auto_save.py Skill tool input None handling -- now uses `(block.get("input") or {})` with isinstance check

## Infrastructure

- [x] Stripe sandbox account created (2026-03-22)

## Ron Daily - 2026-03-31

### Security
- [x] SEC-010: Redacted partial API key from security_report_2026_03_29.md and security_report_2026_03_30.md (replaced with sk-ant-***REDACTED***)

### Infrastructure (TODOs #5, #6, #7)
- [x] Generated LoreDocs requirements.txt from pyproject.toml dependencies
- [x] Generated requirements-lock.txt for LoreConvo (from .venv metadata, 29 pinned packages)
- [x] Generated requirements-lock.txt for LoreDocs (from .venv metadata, 47 pinned packages)
- [x] Created scripts/setup_venvs.sh for setting up missing .venvs (SQL Optimizer needs Mac execution)
- [x] Ran pip-audit: found CVE-2026-34073 (cryptography) and CVE-2026-4539 (Pygments), bumped in lock files
- [x] All 3 products now pass pip-audit with 0 CVEs
- [x] 179 existing tests verified passing

## Ron Daily - 2026-03-31 (BSL License Switch)

### Rebrand Finishing (TODO #3)
- [x] Created ron_skills/loreconvo/LICENSE -- BSL 1.1, Change Date 2030-03-31, Apache 2.0, 50-session free grant
- [x] Created ron_skills/loredocs/LICENSE -- BSL 1.1, Change Date 2030-03-31, Apache 2.0, 3-vault free grant
- [x] Updated ron_skills/loreconvo/pyproject.toml -- license = { file = "LICENSE" }, classifier updated
- [x] Updated ron_skills/loredocs/pyproject.toml -- license = { file = "LICENSE" }, classifier updated
- [x] Updated ron_skills/loreconvo/README.md -- License section now references BSL 1.1
- [x] Updated ron_skills/loreconvo/docs/PUBLISHING.md -- license field: MIT -> BSL-1.1
- [x] Updated ron_skills/loreconvo/docs/marketplace_listing.md -- License row updated
- [x] Updated ron_skills/loredocs/docs/PUBLISHING.md -- license field: MIT -> BSL-1.1
- [x] Updated ron_skills/loredocs/docs/marketplace_listing.md -- License row updated
- [x] Updated ron_skills/loreconvo/.claude-plugin/plugin.json -- license: MIT -> BSL-1.1
- [x] Rebuilt ron_skills/loreconvo-v0.3.0.plugin -- plugin.json license: MIT -> BSL-1.1
- [x] Rebuilt ron_skills/loredocs-v0.1.0.plugin -- plugin.json license: MIT -> BSL-1.1

## Ron Daily - 2026-04-01

### Meg/Brock Fixes
- [x] MEG-031: Fixed SQL Optimizer version mismatch -- SKILL.md 1.0.0 -> 0.1.0 to match CLAUDE.md
- [x] MEG-032: Fixed FTS schema drift between database.py and auto_save.py -- auto_save.py now matches database.py (title, summary, decisions only, unquoted params)
- [x] MEG-033: Added NOT NULL to id column in auto_save.py ensure_tables() to match database.py

### Rebrand Cleanup (TODO #20)
- [x] Renamed convovault_projectvault_diagram.html -> loreconvo_loredocs_diagram.html
- [x] Renamed convovault_projectvault_sketch.html -> loreconvo_loredocs_sketch.html

### Documentation (TODO #21)
- [x] Created LoreDocs README.md -- tagline, quick start, Code/Cowork usage, all 34 tools listed by category, LoreConvo cross-reference, troubleshooting, license

## 2026-04-02 -- Pipeline Sync & Plugin Onboarding UX

### Pipeline Sync (TODO #23)
- [x] Synced Debbie's 2026-03-31 pipeline decisions to PipelineDB: OPP-002/003/004 approved, OPP-013 approved-for-review P2, OPP-015 approved-for-review P1, OPP-016 approved-for-review P3

### Plugin Onboarding & Auto-Load Fixes (TODOs #24-26, #28-29)
- [x] TODO #24: Fixed LoreConvo plugin.json -- flattened nested hooks array, added on_session_start.sh as second SessionStart hook so auto_load.py actually runs
- [x] TODO #25: Added "Recommended CLAUDE.md Setup" and "Verify Installation" sections to LoreConvo README.md. Also fixed personal path reference.
- [x] TODO #26: Added "Recommended CLAUDE.md Setup" and "Verify Installation" sections to LoreDocs README.md
- [x] TODO #28: Verify Installation sections added to both READMEs with quick test commands
- [x] TODO #29: Rewrote COWORK_RESTORE.md with correct tool names, CLAUDE.md workaround as primary recommendation, manual restore as fallback
- [x] Fixed loreconvo-plugin plugin.json license from MIT to BSL-1.1

### Fallback Scripts (TODOs #30-32)
- [x] TODO #30: Created cleaned save_to_loreconvo.py in ron_skills/loreconvo/scripts/ (no internal refs)
- [x] TODO #31: Created cleaned query_loredocs.py in ron_skills/loredocs/scripts/ (no internal refs)
- [x] TODO #32: Documented fallback scripts in both product READMEs
- [x] TODO #33/34: Moved to #40/#41 (cleanup phase, after marketplace is working)

## 2026-04-02 -- Bulk TODO cleanup (Debbie)

Moved all completed items from CLAUDE.md to this file. The following sections
were entirely completed and removed from the active TODO list:

- Rebrand Finishing (#1-4): migration script, revenue Excel, BSL 1.1 switch, plugin rebuilds
- Infrastructure (#5-7): venvs, dependency pinning, pip-audit
- LoreConvo CLI Fixes (#8-10): entry point, Skill detection, skills list subcommand
- Pipeline Improvements (#11-13): set_hold_reason, README/INSTALL fixes
- Security Fixes (#14-19): API key reclassified, CORS, rate limiting, input validation, security headers
- Rebrand Cleanup (#20): marketing HTML file renames
- Documentation (#21): LoreDocs README
- Debbie TODO #3: Copyright registration with new names (LoreConvo, LoreDocs)

## Ron Daily Session - 2026-04-03

Marketplace & plugin distribution block (TODOs #1-6 partial):

- [x] Build self-hosted GitHub marketplace repo structure (marketplace/claude-plugins/) with marketplace.json listing both LoreConvo and LoreDocs (2026-04-03)
- [x] Fix LoreConvo .mcp.json: LORECONVO_PRO default changed from "1" to "" (free tier) (2026-04-03)
- [x] Fix LoreDocs .mcp.json: LOREDOCS_PRO default changed from "1" to "" (free tier) (2026-04-03)
- [x] Add missing installation instructions to LoreConvo plugin README: marketplace add, /install step, CLAUDE.md snippet, Cowork mount step (2026-04-03)
- [x] Add missing installation instructions to LoreDocs plugin README: same improvements (2026-04-03)
- [x] Add homepage and repository fields to both plugin.json files (2026-04-03)
- [x] Fix LoreDocs plugin.json license from MIT to BSL-1.1 (2026-04-03)
- [x] Rebuild both .plugin zip files with all fixes (2026-04-03)

Security fixes (Brock report 2026-04-02):

- [x] SEC-012: Bump anthropic from 0.86.0 to 0.87.0 in SQL Optimizer requirements (CVE-2026-34450, CVE-2026-34452) (2026-04-03)
- [x] SEC-013: Add .gitignore to ron_skills/sql_query_optimizer/ and api/ subdirectory (2026-04-03)
