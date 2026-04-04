#!/usr/bin/env python3
"""populate_pipeline.py - One-time migration script to seed pipeline_tracker.db
with all existing decisions, opportunities, findings, and action items.

Run from repo root:
    python scripts/populate_pipeline.py

This uses pipeline_tracker.py commands internally. Safe to re-run -- it skips
items that already exist (ref_id is PRIMARY KEY).
"""

import subprocess
import sys
from pathlib import Path

TRACKER = str(Path(__file__).parent / "pipeline_tracker.py")


def run(cmd_args):
    """Run pipeline_tracker.py with given args, print output."""
    result = subprocess.run(
        [sys.executable, TRACKER] + cmd_args,
        capture_output=True, text=True
    )
    out = (result.stdout or "").strip()
    err = (result.stderr or "").strip()
    if out:
        print(out)
    if result.returncode != 0 and err:
        print(f"  [WARN] {err}")
    return result.returncode


def add(ref, typ, desc, agent, priority="", product="", status=None, note=None):
    """Add an item and optionally update its status."""
    args = ["add", "--ref", ref, "--type", typ, "--desc", desc, "--agent", agent]
    if priority:
        args += ["--priority", priority]
    if product:
        args += ["--product", product]
    rc = run(args)
    if status and status != "new":
        update_args = ["update", "--ref", ref, "--status", status, "--agent", agent]
        if note:
            update_args += ["--note", note]
        run(update_args)
    elif note:
        run(["update", "--ref", ref, "--status", "new", "--agent", agent, "--note", note])


def block(ref, blocker, agent="debbie"):
    run(["block", "--ref", ref, "--blocker", blocker, "--agent", agent])


def depend(ref, blocks):
    run(["depend", "--ref", ref, "--blocks", blocks])


def main():
    print("=" * 60)
    print("Populating pipeline database with existing items")
    print("=" * 60)

    # =========================================================
    # SCOUT OPPORTUNITIES (OPP-001 through OPP-021)
    # =========================================================
    print("\n--- Scout Opportunities ---")

    add("OPP-001", "opportunity", "SQL Query Optimizer MCP",
        "scout", "P3", "sql_query_optimizer", "on-hold",
        "On hold -- no local SQL Server")
    block("OPP-001", "No local SQL Server", "debbie")

    add("OPP-002", "opportunity", "AI Cost Attribution MCP",
        "scout", "P2", "", "approved",
        "Approved 2026-03-31. Brock should review architectural plans.")

    add("OPP-003", "opportunity", "Prompt Template Manager - LorePrompts",
        "scout", "P2", "loreprompts", "approved",
        "Approved 2026-03-31. Product name: LorePrompts. Pricing: $10/mo.")

    add("OPP-004", "opportunity", "Analytics Scope Dashboard - LoreScope",
        "scout", "P2", "lorescope", "approved",
        "Approved 2026-03-31. Product name: LoreScope.")

    add("OPP-005", "opportunity", "SSIS Package Analyzer",
        "scout", "P3", "", "on-hold",
        "On hold -- no local SQL Server")
    block("OPP-005", "No local SQL Server", "debbie")

    add("OPP-006", "opportunity", "SSIS Packager Analyzer",
        "scout", "P3", "", "on-hold",
        "On hold -- no local SQL Server (Decision #3)")
    block("OPP-006", "No local SQL Server", "debbie")

    add("OPP-007", "opportunity", "Data Pipeline Test Harness MCP",
        "scout", "P2", "", "approved-for-review",
        "Approved for architectural review 2026-03-31")

    add("OPP-008", "opportunity", "Schema Diff & Migration MCP",
        "scout", "P3", "", "on-hold",
        "On hold -- no local SQL Server (Decision #3)")
    block("OPP-008", "No local SQL Server", "debbie")

    add("OPP-009", "opportunity", "Data Catalog Lite MCP",
        "scout", "P1", "", "approved-for-review",
        "Approved for architectural review 2026-03-31, P1 priority")

    add("OPP-010", "opportunity", "ETL Pattern Library Skill",
        "scout", "P3", "", "approved-for-review",
        "Approved for architectural review 2026-03-31, P3 priority")

    # OPP-011 through OPP-016 -- filling in from context
    add("OPP-011", "opportunity", "Pipeline opportunity (details in Scout report)",
        "scout", "", "", "new",
        "Check Scout report for details")

    add("OPP-012", "opportunity", "Pipeline opportunity (SQL Server related)",
        "scout", "", "", "on-hold",
        "On hold -- SQL Server dependency")
    block("OPP-012", "No local SQL Server", "debbie")

    add("OPP-013", "opportunity", "Data Pipeline Test Harness - Architecture Review",
        "gina", "P2", "", "on-hold",
        "Architecture proposal complete. Debbie decision 2026-04-04: ON HOLD. Moderate compatibility, dual-DB pattern.")

    add("OPP-014", "opportunity", "Pipeline opportunity (SQL Server related)",
        "scout", "", "", "on-hold",
        "On hold -- SQL Server dependency")
    block("OPP-014", "No local SQL Server", "debbie")

    add("OPP-015", "opportunity", "Data Catalog Lite - Architecture Review",
        "gina", "P1", "", "approved",
        "Architecture proposal complete. Debbie approved 2026-04-04. HIGH compatibility with Lore architecture. $10/mo Pro.")

    add("OPP-016", "opportunity", "ETL Pattern Library - Architecture Review",
        "gina", "P3", "", "on-hold",
        "Architecture proposal complete. Debbie decision 2026-04-04: ON HOLD. Gina recommends scope rethink -- SQL-Server-only too narrow.")

    add("OPP-017", "opportunity", "LoreEval - AI Agent Test Runner",
        "scout", "", "", "new",
        "pytest-style LLM eval CLI. Effort: 3, Est MRR M12: ~$900. Not triaged yet.")

    add("OPP-018", "opportunity", "LangGraph Workflow Inspector",
        "scout", "", "", "new",
        "Debug LangGraph state machines. Effort: 5, Est MRR M12: ~$700. Not triaged yet.")

    add("OPP-019", "opportunity", "FinNorm - Brokerage CSV Normalizer",
        "scout", "P2", "", "approved",
        "Schwab/YNAB/Buildium normalizer. Debbie approved 2026-04-04.")

    add("OPP-020", "opportunity", "LoreCheck - Data Quality CLI",
        "scout", "P2", "", "approved",
        "Great Expectations alternative. Debbie approved 2026-04-04.")

    add("OPP-021", "opportunity", "Chain Lens - Prompt Chain Observability",
        "scout", "P2", "", "approved",
        "Observe multi-step LLM chains. Debbie approved 2026-04-04.")

    # =========================================================
    # SECURITY FINDINGS (Brock)
    # =========================================================
    print("\n--- Security Findings ---")

    add("SEC-006", "security", "CreditManager race condition in SQL Optimizer",
        "brock", "", "sql_query_optimizer", "on-hold",
        "LOW. Product on hold.")

    add("SEC-011", "security", "TOCTOU race in LoreDocs file export",
        "brock", "", "loredocs", "acknowledged",
        "MEDIUM. Low risk in single-user context.")

    add("SEC-012", "security", "anthropic package outdated",
        "brock", "", "", "completed",
        "RESOLVED by Ron. Bumped to 0.87.0.")

    add("SEC-013", "security", "SQL Optimizer missing .gitignore",
        "brock", "", "sql_query_optimizer", "completed",
        "RESOLVED by Ron. .gitignore created.")

    add("SEC-014", "security", "cryptography missing from pyproject.toml (both products)",
        "brock", "P1", "loreconvo", "acknowledged",
        "MEDIUM. Blocks Pro tier for fresh installs. Ron to fix next session.")

    add("SEC-015", "security", "Personal Gmail in marketplace.json owner.email",
        "brock", "", "", "completed",
        "RESOLVED 2026-04-04. Email changed to info@labyrinthanalyticsconsulting.com")

    # =========================================================
    # QA FINDINGS (Meg)
    # =========================================================
    print("\n--- QA Findings ---")

    add("MEG-036", "bug", "SQL Credits concurrency test failures",
        "meg", "", "sql_query_optimizer", "on-hold",
        "YELLOW. Pre-existing. Product on hold.")

    add("MEG-037", "bug", "Plugin .mcp.json ships with PRO defaults set",
        "meg", "", "loreconvo", "completed",
        "RESOLVED by Ron 2026-04-03. Empty PRO defaults now ship correctly.")

    add("MEG-038", "bug", "Unused import in loreconvo/license.py",
        "meg", "", "loreconvo", "acknowledged",
        "LOW. One-line fix: remove unused Encoding, PublicFormat imports.")

    add("MEG-039", "bug", "Stale git index with .git/*.lock files",
        "meg", "", "", "completed",
        "ADVISORY. Resolved by safe_git.py 2026-04-04.")

    add("MEG-040", "bug", "generate_license_key.py not committed to git",
        "meg", "", "", "acknowledged",
        "ADVISORY. Safe to commit.")

    # =========================================================
    # GINA ARCHITECTURE FINDINGS
    # =========================================================
    print("\n--- Gina Architecture Findings ---")

    add("GINA-001", "architecture", "LoreDocs vault_set_tier bypasses license validation",
        "gina", "P1", "loredocs", "acknowledged",
        "MEDIUM. get_tier() reads config.json fallback before license check. Must fix before marketplace publish. Assigned to Ron.")

    add("GINA-002", "architecture", "LoreConvo /lore-onboard skill not in .plugin bundle",
        "gina", "P1", "loreconvo", "acknowledged",
        "MEDIUM. Users installing from marketplace won't get onboarding command. Ron must rebuild .plugin zip.")

    # =========================================================
    # RON BUILD TASKS
    # =========================================================
    print("\n--- Ron Build Tasks ---")

    add("RON-001", "task", "LoreConvo CLI entry point (save-session, list, search)",
        "ron", "P1", "loreconvo", "new",
        "Migrate logic from scripts/save_to_loreconvo.py into product CLI.")

    add("RON-002", "task", "LoreDocs CLI entry point (vault commands)",
        "ron", "P2", "loredocs", "new",
        "Migrate logic from scripts/query_loredocs.py into product CLI.")

    add("RON-003", "task", "Slim agent prompts to reference CLIs",
        "ron", "P3", "", "new",
        "Remove inline Python from agent prompts. Reference product CLIs instead.")
    depend("RON-001", "RON-003")
    depend("RON-002", "RON-003")

    add("RON-004", "task", "Update monorepo scripts to thin wrappers",
        "ron", "P3", "", "new",
        "save_to_loreconvo.py and query_loredocs.py call product CLIs.")
    depend("RON-003", "RON-004")

    add("RON-005", "task", "Fix SEC-014: add cryptography to pyproject.toml",
        "ron", "P1", "loreconvo", "new",
        "Add cryptography>=42.0.0 to both products. Blocks Pro tier on fresh install.")

    add("RON-006", "task", "Fix GINA-001: vault_set_tier license bypass",
        "ron", "P1", "loredocs", "new",
        "get_tier() config.json fallback must not override license check.")

    add("RON-007", "task", "Fix GINA-002: rebuild .plugin with /lore-onboard",
        "ron", "P1", "loreconvo", "new",
        "Include onboarding skill in marketplace .plugin bundle.")

    add("RON-008", "task", "Fix MEG-038: unused import in license.py",
        "ron", "P3", "loreconvo", "new",
        "Remove unused Encoding, PublicFormat from loreconvo/license.py.")

    add("RON-009", "task", "Add tests/ to product .gitignore files",
        "ron", "P1", "", "new",
        "Decision #8: test files should not be in public repos. Add tests/ to both loreconvo and loredocs .gitignore before next subtree push.")

    add("RON-010", "task", "Build Financial Report Generator skill",
        "ron", "P4", "financial_report_generator", "new",
        "FastMCP backend. Not started.")

    add("RON-011", "task", "Build CSV/Excel Data Transformer skill",
        "ron", "P4", "csv_excel_transformer", "new",
        "FastMCP backend. Not started.")

    # =========================================================
    # DEBBIE ACTION ITEMS
    # =========================================================
    print("\n--- Debbie Action Items ---")

    add("DEBBIE-001", "debbie-action", "File USPTO trademark for LoreConvo",
        "debbie", "P5", "loreconvo", "deferred",
        "ON HOLD per Debbie 2026-04-02: wait until products gain traction.")

    add("DEBBIE-002", "debbie-action", "File USPTO trademark for LoreDocs",
        "debbie", "P5", "loredocs", "deferred",
        "ON HOLD per Debbie 2026-04-02: wait until products gain traction.")

    add("DEBBIE-003", "debbie-action", "Review and approve rebuilt .plugin files",
        "debbie", "P2", "", "new",
        "Rebuilt 2026-04-03 with fixed .mcp.json, READMEs, plugin.json.")

    add("DEBBIE-004", "debbie-action", "Save license signing private key to password manager",
        "debbie", "P1", "", "new",
        "URGENT. Ed25519 key in LoreConvo session log. Without it, no Pro keys can be generated.")

    add("DEBBIE-005", "debbie-action", "Activate live Stripe account",
        "debbie", "P3", "", "new",
        "Business verification, bank account, EIN. Sandbox ready since 2026-03-22.")

    add("DEBBIE-006", "debbie-action", "Create GitHub repo and push marketplace",
        "debbie", "P2", "", "new",
        "Create labyrinth-analytics/claude-plugins, push marketplace/ contents, test install flow.")

    add("DEBBIE-007", "debbie-action", "Triage OPP-017 and OPP-018",
        "debbie", "P2", "", "new",
        "LoreEval and LangGraph Workflow Inspector not yet triaged.")

    # =========================================================
    # PRODUCT-LEVEL ITEMS
    # =========================================================
    print("\n--- Product Items ---")

    add("PROD-001", "product", "LoreConvo v0.3.0",
        "ron", "P1", "loreconvo", "in-progress",
        "PRODUCTION. 12 MCP tools. Auto-save/load hooks working.")

    add("PROD-002", "product", "LoreDocs v0.1.0",
        "ron", "P1", "loredocs", "in-progress",
        "ALPHA. 34 tools. Tier gating ready.")

    add("PROD-003", "product", "SQL Query Optimizer v0.1.0",
        "ron", "", "sql_query_optimizer", "on-hold",
        "ON HOLD. No local SQL Server to test against.")
    block("PROD-003", "No local SQL Server", "debbie")

    add("PROD-004", "product", "LorePrompts",
        "ron", "P2", "loreprompts", "approved",
        "Approved 2026-03-31. Prompt template management. $10/mo.")

    add("PROD-005", "product", "LoreScope",
        "ron", "P2", "lorescope", "approved",
        "Approved 2026-03-31. Analytics scope dashboard.")

    # =========================================================
    # SUMMARY
    # =========================================================
    print("\n" + "=" * 60)
    print("Migration complete! Listing all items:")
    print("=" * 60)
    run(["list"])


if __name__ == "__main__":
    main()
