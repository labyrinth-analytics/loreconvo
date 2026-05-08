"""Session Bridge CLI - human interface for session memory."""

import json
import sys
import os
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import click
from core.models import Session
from core.database import SessionDatabase, _MAX_IMPORT_BYTES, _MAX_SESSIONS_PER_FILE
from core.config import Config

db = SessionDatabase(Config())


@click.group()
@click.version_option(version="0.4.0", prog_name="loreconvo")
def cli():
    """LoreConvo - vault your Claude conversations. Never re-explain yourself again."""
    pass


@cli.command()
@click.option("--title", "-t", required=True, help="Session title")
@click.option("--surface", "-s", type=click.Choice(["cowork", "code", "chat"]), required=True)
@click.option("--summary", "-m", required=True, help="Session summary")
@click.option("--project", "-p", help="Project name")
@click.option("--decisions", "-d", multiple=True, help="Key decisions (repeatable)")
@click.option("--skills", multiple=True, help="Skills used (repeatable)")
@click.option("--tags", multiple=True, help="Tags (repeatable)")
def save(title, surface, summary, project, decisions, skills, tags):
    """Save a session to memory."""
    session = Session(
        title=title,
        surface=surface,
        summary=summary,
        project=project,
        decisions=list(decisions),
        skills_used=list(skills),
        tags=list(tags),
    )
    session_id = db.save_session(session)
    click.echo(f"Saved session: {session_id}")
    click.echo(f"  Title: {title}")
    click.echo(f"  Surface: {surface}")
    if project:
        click.echo(f"  Project: {project}")


@cli.command(name="list")
@click.option("--limit", "-n", default=10, help="Max sessions to show")
@click.option("--days", "-d", default=30, help="Days to look back")
@click.option("--project", "-p", help="Filter by project")
@click.option("--skill", help="Filter by skill")
def list_sessions(limit, days, project, skill):
    """List recent sessions."""
    sessions = db.get_recent_sessions(limit, days, project, skill)
    if not sessions:
        click.echo("No sessions found.")
        return

    for s in sessions:
        project_str = f" [{s.project}]" if s.project else ""
        skills_str = f" skills:{','.join(s.skills_used)}" if s.skills_used else ""
        click.echo(f"  {s.start_date[:10]}  {s.surface:6s}{project_str}  {s.title}{skills_str}")
        click.echo(f"           id: {s.id}")
    click.echo(f"\n{len(sessions)} session(s)")


@cli.command()
@click.argument("query")
@click.option("--persona", help="Filter by persona")
@click.option("--project", "-p", help="Filter by project")
@click.option("--skill", help="Filter by skill")
@click.option("--limit", "-n", default=10, help="Max results")
def search(query, persona, project, skill, limit):
    """Search session memory."""
    skills_list = [skill] if skill else None
    results = db.search_sessions(query, persona, skills=skills_list, project=project, limit=limit)
    if not results:
        click.echo(f'No sessions found for "{query}"')
        return

    for r in results:
        s = r.session
        click.echo(f"  [{r.match_score:.1f}] {s.start_date[:10]}  {s.title}")
        if s.decisions:
            for d in s.decisions[:2]:
                click.echo(f"         [decision] {d}")
        click.echo(f"         id: {s.id}")
    click.echo(f"\n{len(results)} result(s)")


@cli.command()
@click.argument("session_id", required=False)
@click.option("--last", is_flag=True, help="Export the most recent session")
@click.option("--format", "fmt",
              type=click.Choice(["markdown", "json", "shared"]), default="markdown",
              help="Output format. 'shared' creates a team-shareable bundle (Pro only).")
@click.option("--project", "-p", help="Filter by project (shared format)")
@click.option("--session-ids", "session_ids",
              help="Comma-separated session IDs to include (shared format)")
@click.option("--all", "export_all", is_flag=True,
              help="Export all sessions (shared format, use with care)")
def export(session_id, last, fmt, project, session_ids, export_all):
    """Export a session for pasting into Chat or other tools.

    With --format shared, exports a JSON bundle for teammates to import via
    'loreconvo merge'. Requires LoreConvo Pro.
    """
    if fmt == "shared":
        # SEC-00067: Pro gate at command entry
        if not db.config.is_pro:
            click.echo(
                "error: Export format 'shared' requires LoreConvo Pro. "
                "Get a license at labyrinthanalyticsconsulting.com."
            )
            sys.exit(1)

        import socket as _socket
        user_id = os.environ.get("LORECONVO_USER_ID", "") or _socket.gethostname()

        id_filter = [s.strip() for s in (session_ids or "").split(",") if s.strip()]
        sessions = db.get_sessions_for_shared_export(
            project=project,
            session_id_filter=id_filter if id_filter else None,
            export_all=export_all,
        )

        session_list = []
        for s in sessions:
            import os as _os
            # SEC-00070: strip artifacts to basename only
            safe_artifacts = [_os.path.basename(a) for a in s.artifacts]
            session_list.append({
                "id": s.id,
                "title": s.title,
                "summary": s.summary,
                "surface": s.surface,
                "project": s.project,
                "tags": s.tags,
                "created_at": s.created_at,
                "origin_machine": s.origin_machine or user_id,
                "content_hash": s.content_hash or db.compute_content_hash(
                    s.title, s.summary, s.created_at
                ),
            })

        click.echo(json.dumps({
            "loreconvo_export_version": "1.0",
            "exported_by": user_id,
            "exported_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "project_filter": project,
            "sessions": session_list,
        }, indent=2))
        return

    # Standard single-session export (markdown / json)
    if last and not session_id:
        sessions = db.get_recent_sessions(limit=1, days_back=365)
        if not sessions:
            click.echo("No sessions found.")
            return
        session = sessions[0]
    elif session_id:
        session = db.get_session(session_id)
        if not session:
            click.echo(f"Session {session_id} not found.")
            return
    else:
        click.echo("Provide a session_id or use --last")
        return

    if fmt == "json":
        click.echo(json.dumps({
            "id": session.id,
            "title": session.title,
            "surface": session.surface,
            "project": session.project,
            "start_date": session.start_date,
            "summary": session.summary,
            "decisions": session.decisions,
            "artifacts": session.artifacts,
            "open_questions": session.open_questions,
            "skills_used": session.skills_used,
            "tags": session.tags,
        }, indent=2))
    else:
        lines = [
            "# Context from Previous Session",
            "",
            f"**Title:** {session.title}",
            f"**Date:** {session.start_date[:10]}",
            f"**Surface:** {session.surface}",
        ]
        if session.project:
            lines.append(f"**Project:** {session.project}")
        if session.skills_used:
            lines.append(f"**Skills Used:** {', '.join(session.skills_used)}")
        lines.append("")
        lines.append("## Summary")
        lines.append(session.summary)
        if session.decisions:
            lines.append("")
            lines.append("## Key Decisions")
            for d in session.decisions:
                lines.append(f"- {d}")
        if session.artifacts:
            lines.append("")
            lines.append("## Artifacts")
            for a in session.artifacts:
                lines.append(f"- {a}")
        if session.open_questions:
            lines.append("")
            lines.append("## Open Questions")
            for q in session.open_questions:
                lines.append(f"- {q}")
        click.echo("\n".join(lines))


@cli.command()
@click.argument("file", type=click.Path(exists=True, dir_okay=False, readable=True))
def merge(file):
    """Import sessions from a shared export file. LoreConvo Pro required.

    FILE is a JSON file produced by 'loreconvo export --format shared'.
    Duplicate sessions (by UUID or content hash) are skipped automatically.
    """
    # SEC-00067: Pro gate at command entry
    if not db.config.is_pro:
        click.echo(
            "error: Team merge requires LoreConvo Pro. "
            "Get a license at labyrinthanalyticsconsulting.com."
        )
        sys.exit(1)

    path = Path(file)

    # SEC-00068: file size cap
    if path.stat().st_size > _MAX_IMPORT_BYTES:
        click.echo("error: Import file too large. Max: 50 MB.")
        sys.exit(1)

    try:
        wrapper = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        click.echo(f"error: Could not parse export file: {exc}")
        sys.exit(1)

    # SEC-00072: schema version check
    _SUPPORTED_VERSIONS = {"1.0"}
    version = wrapper.get("loreconvo_export_version", "1.0")
    if version not in _SUPPORTED_VERSIONS:
        click.echo(f"error: Unsupported export version '{version}'.")
        sys.exit(1)

    sessions_data = wrapper.get("sessions", [])
    exported_by = str(wrapper.get("exported_by", "unknown") or "unknown")

    # SEC-00068: session count cap
    if len(sessions_data) > _MAX_SESSIONS_PER_FILE:
        click.echo(f"error: Export file contains too many sessions. Max: {_MAX_SESSIONS_PER_FILE}.")
        sys.exit(1)

    imported = 0
    skipped = 0
    for session_dict in sessions_data:
        result = db.merge_session(session_dict, shared_by=exported_by)
        if result == "imported":
            imported += 1
        else:
            skipped += 1

    click.echo(f"Imported {imported} new session(s), skipped {skipped} duplicate(s).")


@cli.command()
@click.argument("skill_name")
@click.option("--days", "-d", default=90, help="Days to look back")
def skill_history(skill_name, days):
    """Show all sessions that used a specific skill."""
    sessions = db.get_skill_history(skill_name, days)
    if not sessions:
        click.echo(f'No sessions found using skill "{skill_name}"')
        return
    for s in sessions:
        click.echo(f"  {s.start_date[:10]}  {s.surface:6s}  {s.title}")
    click.echo(f"\n{len(sessions)} session(s) used '{skill_name}'")


@cli.group()
def skills():
    """Commands for browsing skill usage history."""
    pass


@skills.command(name="list")
def skills_list():
    """List all distinct skills recorded in session memory, sorted by usage count."""
    all_skills = db.list_all_skills()
    if not all_skills:
        click.echo("No skills recorded yet.")
        return
    for entry in all_skills:
        click.echo(f"  {entry['session_count']:4d}  {entry['skill_name']}")
    click.echo(f"\n{len(all_skills)} distinct skill(s)")


@cli.command()
def stats():
    """Show session memory statistics."""
    total = db.session_count()
    projects = db.list_projects()
    click.echo(f"Total sessions: {total}")
    click.echo(f"Projects: {len(projects)}")
    if projects:
        for p in projects:
            click.echo(f"  {p['name']}: {p['session_count']} sessions")

    recent = db.get_recent_sessions(limit=1, days_back=365)
    if recent:
        click.echo(f"Most recent: {recent[0].title} ({recent[0].start_date[:10]})")


if __name__ == "__main__":
    cli()
