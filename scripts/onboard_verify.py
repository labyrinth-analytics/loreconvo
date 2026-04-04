#!/usr/bin/env python3
"""LoreConvo onboarding verification script.

Runs a series of checks to verify LoreConvo is correctly installed and
functioning. Can be invoked standalone from the command line or imported
and called programmatically.

Usage:
    python scripts/onboard_verify.py [--cleanup] [--json]

Options:
    --cleanup   Delete the test session after verification
    --json      Output results as JSON instead of formatted text
"""

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class CheckResult:
    """Result of a single verification check."""
    name: str
    step: str
    status: str  # PASS, FAIL, SKIP, SUGGEST
    message: str = ""
    detail: str = ""


@dataclass
class OnboardReport:
    """Full onboarding verification report."""
    results: list = field(default_factory=list)
    test_session_id: Optional[str] = None
    all_critical_pass: bool = False

    def add(self, result: CheckResult):
        self.results.append(result)

    def to_dict(self):
        return {
            "results": [
                {
                    "name": r.name,
                    "step": r.step,
                    "status": r.status,
                    "message": r.message,
                    "detail": r.detail,
                }
                for r in self.results
            ],
            "test_session_id": self.test_session_id,
            "all_critical_pass": self.all_critical_pass,
        }


def _find_src_path():
    """Locate the LoreConvo src directory."""
    # Try relative to this script first
    script_dir = Path(__file__).resolve().parent
    src_path = script_dir.parent / "src"
    if src_path.exists():
        return str(src_path)

    # Try CLAUDE_PLUGIN_ROOT
    plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT", "")
    if plugin_root:
        candidate = Path(plugin_root) / "src"
        if candidate.exists():
            return str(candidate)

    return None


def check_database_access(report: OnboardReport):
    """Step 1+2: Verify database is accessible and schema is correct."""
    try:
        src = _find_src_path()
        if not src:
            report.add(CheckResult(
                name="MCP Server Connection",
                step="1",
                status="FAIL",
                message="Cannot locate LoreConvo src directory",
                detail="Looked in script parent and CLAUDE_PLUGIN_ROOT",
            ))
            return None

        if src not in sys.path:
            sys.path.insert(0, src)

        from core.config import Config
        from core.database import SessionDatabase

        config = Config()
        config.ensure_db_dir()
        db = SessionDatabase(config)

        report.add(CheckResult(
            name="MCP Server Connection",
            step="1",
            status="PASS",
            message="LoreConvo database accessible",
            detail="DB path: %s" % config.db_path,
        ))

        # Step 2: List projects to verify schema
        projects = db.list_projects()
        report.add(CheckResult(
            name="Database Access",
            step="2",
            status="PASS",
            message="Database schema valid, %d projects found" % len(projects),
        ))

        return db

    except Exception as e:
        report.add(CheckResult(
            name="Database Access",
            step="1-2",
            status="FAIL",
            message="Database error: %s" % str(e),
        ))
        return None


def check_save_load(db, report: OnboardReport):
    """Step 3: Test save/load/search cycle."""
    if db is None:
        for sub in ("3a", "3b", "3c"):
            report.add(CheckResult(
                name="Save/Load Cycle",
                step=sub,
                status="SKIP",
                message="Skipped -- database not available",
            ))
        return

    src = _find_src_path()
    if src and src not in sys.path:
        sys.path.insert(0, src)

    from core.models import Session

    # 3a: Save test session
    try:
        test_session = Session(
            title="LoreConvo Onboarding Test",
            surface="code",
            summary=(
                "Automated onboarding verification. This session confirms "
                "that LoreConvo can save and retrieve sessions correctly. "
                "Safe to delete."
            ),
            decisions=["LoreConvo onboarding test completed successfully"],
            tags=["onboarding", "test"],
        )
        session_id = db.save_session(test_session)
        report.test_session_id = session_id
        report.add(CheckResult(
            name="Save Session",
            step="3a",
            status="PASS",
            message="Test session saved",
            detail="session_id: %s" % session_id,
        ))
    except Exception as e:
        report.add(CheckResult(
            name="Save Session",
            step="3a",
            status="FAIL",
            message="Save failed: %s" % str(e),
        ))
        return

    # 3b: Load test session back
    try:
        loaded = db.get_session(session_id)
        if loaded and loaded.title == "LoreConvo Onboarding Test":
            report.add(CheckResult(
                name="Load Session",
                step="3b",
                status="PASS",
                message="Test session retrieved with correct title",
            ))
        else:
            report.add(CheckResult(
                name="Load Session",
                step="3b",
                status="FAIL",
                message="Session retrieved but title mismatch or empty",
                detail="Got: %s" % (loaded.title if loaded else "None"),
            ))
    except Exception as e:
        report.add(CheckResult(
            name="Load Session",
            step="3b",
            status="FAIL",
            message="Load failed: %s" % str(e),
        ))

    # 3c: Search for test session (FTS5)
    try:
        results = db.search_sessions("onboarding test", limit=5)
        found = any(
            r.session.title == "LoreConvo Onboarding Test"
            for r in results
        )
        if found:
            report.add(CheckResult(
                name="Search (FTS5)",
                step="3c",
                status="PASS",
                message="FTS5 search found the test session",
            ))
        else:
            report.add(CheckResult(
                name="Search (FTS5)",
                step="3c",
                status="FAIL",
                message="FTS5 search did not find test session",
                detail="Got %d results but none matched" % len(results),
            ))
    except Exception as e:
        report.add(CheckResult(
            name="Search (FTS5)",
            step="3c",
            status="FAIL",
            message="Search failed: %s" % str(e),
        ))


def check_hooks(report: OnboardReport):
    """Step 4: Verify hooks are configured."""
    # Check multiple possible locations
    plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT", "")
    script_dir = Path(__file__).resolve().parent
    hooks_dir = script_dir.parent / "hooks" / "scripts"

    if plugin_root:
        hooks_dir = Path(plugin_root) / "hooks" / "scripts"

    start_hook = hooks_dir / "on_session_start.sh"
    end_hook = hooks_dir / "on_session_end.sh"

    start_exists = start_hook.exists()
    end_exists = end_hook.exists()

    if start_exists and end_exists:
        report.add(CheckResult(
            name="Hooks Configured",
            step="4",
            status="PASS",
            message="Both SessionStart and SessionEnd hooks found",
            detail="Hooks dir: %s" % str(hooks_dir),
        ))
    elif not hooks_dir.exists():
        report.add(CheckResult(
            name="Hooks Configured",
            step="4",
            status="FAIL",
            message="Hooks directory not found",
            detail="Looked in: %s" % str(hooks_dir),
        ))
    else:
        missing = []
        if not start_exists:
            missing.append("on_session_start.sh")
        if not end_exists:
            missing.append("on_session_end.sh")
        report.add(CheckResult(
            name="Hooks Configured",
            step="4",
            status="FAIL",
            message="Missing hook files: %s" % ", ".join(missing),
            detail="Hooks dir: %s" % str(hooks_dir),
        ))


def check_claude_md(report: OnboardReport, project_dir: Optional[str] = None):
    """Step 5: Check for CLAUDE.md integration."""
    if project_dir is None:
        project_dir = os.getcwd()

    claude_md = Path(project_dir) / "CLAUDE.md"

    if not claude_md.exists():
        report.add(CheckResult(
            name="CLAUDE.md Integration",
            step="5",
            status="SKIP",
            message="No CLAUDE.md found in project directory",
            detail="Checked: %s" % str(claude_md),
        ))
        return

    try:
        content = claude_md.read_text(encoding="utf-8")
        lower_content = content.lower()
        if "loreconvo" in lower_content or "save_session" in lower_content:
            report.add(CheckResult(
                name="CLAUDE.md Integration",
                step="5",
                status="PASS",
                message="CLAUDE.md already mentions LoreConvo",
            ))
        else:
            report.add(CheckResult(
                name="CLAUDE.md Integration",
                step="5",
                status="SUGGEST",
                message="CLAUDE.md exists but does not mention LoreConvo",
                detail="Consider adding LoreConvo integration instructions",
            ))
    except Exception as e:
        report.add(CheckResult(
            name="CLAUDE.md Integration",
            step="5",
            status="FAIL",
            message="Could not read CLAUDE.md: %s" % str(e),
        ))


def run_onboard(project_dir: Optional[str] = None, cleanup: bool = False):
    """Run the full onboarding verification.

    Args:
        project_dir: Directory to check for CLAUDE.md (defaults to cwd)
        cleanup: If True, delete the test session after verification

    Returns:
        OnboardReport with all check results
    """
    report = OnboardReport()

    # Steps 1-2: Database access
    db = check_database_access(report)

    # Step 3: Save/load cycle
    check_save_load(db, report)

    # Step 4: Hooks
    check_hooks(report)

    # Step 5: CLAUDE.md
    check_claude_md(report, project_dir)

    # Determine overall status (steps 1-4 are critical)
    critical_results = [r for r in report.results if r.step in ("1", "2", "3a", "3b", "3c", "4")]
    report.all_critical_pass = all(r.status == "PASS" for r in critical_results)

    # Cleanup if requested
    if cleanup and report.test_session_id and db:
        try:
            db.conn.execute("DELETE FROM sessions WHERE id = ?", (report.test_session_id,))
            db.conn.commit()
        except Exception:
            pass  # Best effort cleanup

    if db:
        db.close()

    return report


def format_report(report: OnboardReport) -> str:
    """Format the report as a human-readable string."""
    lines = ["", "LoreConvo Onboarding Verification", "=" * 34, ""]

    for r in report.results:
        status_marker = {"PASS": "[OK]", "FAIL": "[FAIL]", "SKIP": "[SKIP]", "SUGGEST": "[!]"}.get(r.status, "[?]")
        lines.append("Step %s: %s %s" % (r.step, status_marker, r.name))
        lines.append("        %s" % r.message)
        if r.detail:
            lines.append("        %s" % r.detail)
        lines.append("")

    lines.append("-" * 34)
    if report.all_critical_pass:
        lines.append("[OK] LoreConvo is fully operational!")
        lines.append("Sessions will be automatically saved and loaded.")
    else:
        failed = [r for r in report.results if r.status == "FAIL"]
        lines.append("[FAIL] %d check(s) need attention:" % len(failed))
        for r in failed:
            lines.append("  - Step %s (%s): %s" % (r.step, r.name, r.message))

    if report.test_session_id:
        lines.append("")
        lines.append("Test session ID: %s" % report.test_session_id)

    lines.append("")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="LoreConvo onboarding verification")
    parser.add_argument("--cleanup", action="store_true", help="Delete test session after verification")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--project-dir", type=str, default=None, help="Project directory to check for CLAUDE.md")
    args = parser.parse_args()

    report = run_onboard(project_dir=args.project_dir, cleanup=args.cleanup)

    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(format_report(report))

    sys.exit(0 if report.all_critical_pass else 1)


if __name__ == "__main__":
    main()
