"""Core logic for the loreconvo_onboard MCP tool."""

import datetime
import json
from pathlib import Path
from typing import Optional

from .database import SessionDatabase


def _config_path(db: SessionDatabase) -> Path:
    return Path(db.config.db_path).parent / "onboard_config.json"


def _load_config(path: Path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_config(path: Path, config: dict) -> None:
    config["last_updated"] = datetime.datetime.now().isoformat()
    path.write_text(json.dumps(config, indent=2), encoding="utf-8")


def _generate_reference_doc(config: dict) -> str:
    name = config.get("name", "My Workspace")
    projects = config.get("projects", ["general"])
    agents = config.get("agents", [])
    tag_style = config.get("tag_style", "simple")
    surfaces = config.get("surfaces", ["code", "cowork", "chat"])

    surface_labels = {
        "code": "Claude Code CLI",
        "cowork": "Claude.ai Projects",
        "chat": "Claude.ai chat",
        "codex": "Codex CLI",
    }

    lines = [
        "# My LoreConvo Setup",
        "Last updated: " + str(datetime.date.today()),
        "",
        "## Workspace",
        "Name: " + name,
        "Surfaces I use:",
    ]
    for s in surfaces:
        lines.append("- " + s + ": " + surface_labels.get(s, s))

    lines += ["", "## Projects"]
    for p in projects:
        lines.append("- " + p)

    lines += [
        "",
        "## Tag Conventions",
        "### Status",
        "- status:active, status:completed, status:on-hold",
        "",
        "### Priority",
        "- priority:high, priority:medium, priority:low",
    ]

    if tag_style == "detailed":
        lines += [
            "",
            "### Effort",
            "- effort:1 (trivial) through effort:5 (major)",
            "",
            "### Date markers",
            "- scout-run:YYYY-MM-DD (automated research runs)",
            "- Avoid raw dates as standalone tags -- use start_date field instead",
        ]

    if agents:
        lines += ["", "## Agents"]
        for a in agents:
            lines.append("- agent:" + a + ": " + a + " agent sessions")

    lines += [
        "",
        "## How to use this",
        "At session start: get_context_for() or search_sessions(project='...')",
        "Save sessions: save_session(project='...', tags=['status:active', ...])",
        "Surface values identify the platform, not the agent.",
        "Agents tag sessions with agent:<name> in the tags field.",
    ]

    return "\n".join(lines)


def run_onboard(
    db: SessionDatabase,
    name: Optional[str] = None,
    projects: Optional[list] = None,
    agents: Optional[list] = None,
    tag_style: str = "simple",
) -> dict:
    path = _config_path(db)
    config = _load_config(path)
    is_first_run = not path.exists()

    if name:
        config["name"] = name
    elif "name" not in config:
        config["name"] = "My Workspace"

    if projects:
        existing = set(config.get("projects", []))
        config["projects"] = sorted(existing | set(projects))
    elif "projects" not in config:
        config["projects"] = ["general"]

    if agents:
        existing = set(config.get("agents", []))
        config["agents"] = sorted(existing | set(agents))
    elif "agents" not in config:
        config["agents"] = []

    config["tag_style"] = tag_style

    if "surfaces" not in config:
        config["surfaces"] = ["code", "cowork", "chat"]

    created_projects = []
    for p in config["projects"]:
        existing_proj = db.get_project(p)
        if not existing_proj:
            db.create_project(p, description="Project: " + p)
            created_projects.append(p)

    _save_config(path, config)

    return {
        "status": "initialized" if is_first_run else "configured",
        "config_path": str(path),
        "projects_registered": created_projects,
        "reference_doc": _generate_reference_doc(config),
        "setup_tip": (
            "Paste the reference_doc into your CLAUDE.md or a LoreDocs vault "
            "so your AI assistant can use your tag conventions consistently."
        ),
    }
