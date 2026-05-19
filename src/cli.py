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
@click.version_option(version="0.6.0", prog_name="loreconvo")
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
@click.option("--external-tool", "external_tool_session", is_flag=True, default=False,
              help="Mark as an external tool session (excluded from auto-load and search by default)")
def save(title, surface, summary, project, decisions, skills, tags, external_tool_session):
    """Save a session to memory."""
    session = Session(
        title=title,
        surface=surface,
        summary=summary,
        project=project,
        decisions=list(decisions),
        skills_used=list(skills),
        tags=list(tags),
        external_tool_session=external_tool_session,
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
@click.option("--semantic", is_flag=True, default=False,
              help="Use LanceDB hybrid (vector + BM25) search. Pro tier only.")
def search(query, persona, project, skill, limit, semantic):
    """Search session memory."""
    skills_list = [skill] if skill else None
    results = db.search_sessions(query, persona, skills=skills_list, project=project, limit=limit, semantic=semantic)
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
              type=click.Choice(["markdown", "json", "shared", "anthropic-v1"]), default="markdown",
              help="Output format. 'shared' creates a team-shareable bundle (Pro only). "
                   "'anthropic-v1' exports to Anthropic managed-agents format (Pro only).")
@click.option("--project", "-p", help="Filter by project (shared and anthropic-v1 formats)")
@click.option("--session-ids", "session_ids",
              help="Comma-separated session IDs to include (shared and anthropic-v1 formats)")
@click.option("--all", "export_all", is_flag=True,
              help="Export all sessions (shared and anthropic-v1 formats, use with care)")
@click.option("--out", "out_path", help="Output file path (for shared and anthropic-v1 formats)")
@click.option("--days-back", "days_back", type=int, default=None,
              help="Limit export to sessions from the last N days (anthropic-v1 only).")
def export(session_id, last, fmt, project, session_ids, export_all, out_path, days_back):
    """Export a session for pasting into Chat or other tools.

    With --format shared, exports a JSON bundle for teammates to import via
    'loreconvo merge'. With --format anthropic-v1, exports to Anthropic
    managed-agents memory format. Both require LoreConvo Pro.
    """
    if fmt == "anthropic-v1":
        if not db.config.is_pro:
            click.echo(
                "error: Export format 'anthropic-v1' requires LoreConvo Pro. "
                "Get a license at labyrinthanalyticsconsulting.com."
            )
            sys.exit(1)

        id_filter = [s.strip() for s in (session_ids or "").split(",") if s.strip()]
        sessions = db.get_sessions_for_shared_export(
            project=project,
            session_id_filter=id_filter if id_filter else None,
            export_all=export_all or (not id_filter and not project),
        )

        if days_back is not None:
            from datetime import timedelta
            cutoff = (datetime.now(timezone.utc) - timedelta(days=days_back)).isoformat().replace("+00:00", "Z")
            sessions = [s for s in sessions if s.start_date >= cutoff]

        entries = []
        for s in sessions:
            entries.append({
                "id": s.id,
                "content": s.summary or "",
                "created_at": s.created_at,
                "tags": s.tags or [],
                "metadata": {
                    "title": s.title,
                    "surface": s.surface,
                    "project": s.project,
                },
            })

        export_obj = {
            "format": "anthropic-memory-v1",
            "source": "loreconvo",
            "exported_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "schema_note": (
                "Preliminary field mapping -- validate against Anthropic beta API "
                "docs before submitting to Anthropic memory stores."
            ),
            "entry_count": len(entries),
            "entries": entries,
        }

        data_str = json.dumps(export_obj, indent=2)
        if out_path:
            resolved = Path(out_path).expanduser().resolve()
            home = Path.home().resolve()
            if not str(resolved).startswith(str(home)):
                click.echo("error: output path must be within the home directory")
                sys.exit(1)
            if resolved.suffix.lower() != ".json":
                click.echo("error: output path must end with .json")
                sys.exit(1)
            resolved.write_text(data_str, encoding="utf-8")
            click.echo(f"Exported {len(entries)} session(s) to {resolved} (anthropic-memory-v1)")
        else:
            click.echo(data_str)
        return

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
                "decisions": s.decisions,
                "open_questions": s.open_questions,
                "artifacts": safe_artifacts,
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


@cli.command()
@click.argument("session_id", required=False)
@click.option("--search", help="Full-text search query")
@click.option("--tag", help="Filter by tag substring (e.g. 'agent:ron')")
@click.option("--surface", help="Filter by surface (code, cowork, chat)")
@click.option("--since", help="Show sessions since YYYY-MM-DD")
@click.option("--limit", "-n", default=20, help="Max sessions to show")
@click.option("--show-stats", is_flag=True, help="Show aggregate statistics")
@click.option("--delete", "delete_id", metavar="ID", help="Delete a session by ID (prompts for confirmation)")
def inspect(session_id, search, tag, surface, since, limit, show_stats, delete_id):
    """Inspect stored sessions: list, filter, view detail, or delete.

    Without arguments, lists recent sessions.
    With SESSION_ID, shows full detail for that session.
    Use --delete ID to remove a session after confirmation.
    Use --show-stats to add aggregate counts to the listing.
    """
    if delete_id:
        session = db.get_session(delete_id)
        if not session:
            click.echo(f"Session {delete_id} not found.")
            sys.exit(1)
        click.echo(f"Session to delete: [{session.start_date[:10]}] {session.title}")
        if not click.confirm("Delete this session?"):
            click.echo("Cancelled.")
            return
        if db.delete_session(delete_id):
            click.echo(f"Deleted session {delete_id}.")
        else:
            click.echo("Delete failed.")
            sys.exit(1)
        return

    if session_id:
        session = db.get_session(session_id)
        if not session:
            click.echo(f"Session {session_id} not found.")
            sys.exit(1)
        click.echo(f"Title:   {session.title}")
        click.echo(f"Date:    {session.start_date[:16]}")
        click.echo(f"Surface: {session.surface}")
        if session.project:
            click.echo(f"Project: {session.project}")
        if session.tags:
            click.echo(f"Tags:    {', '.join(session.tags)}")
        click.echo("")
        click.echo("Summary:")
        click.echo(session.summary)
        if session.decisions:
            click.echo("\nDecisions:")
            for d in session.decisions:
                click.echo(f"  - {d}")
        if session.artifacts:
            click.echo("\nArtifacts:")
            for a in session.artifacts:
                click.echo(f"  - {a}")
        if session.open_questions:
            click.echo("\nOpen Questions:")
            for q in session.open_questions:
                click.echo(f"  - {q}")
        return

    sessions = db.inspect_sessions(
        search=search, tag=tag, surface=surface, since=since, limit=limit
    )

    if show_stats:
        stats_data = db.get_inspect_stats()
        click.echo(f"Total sessions: {stats_data['total']}")
        if stats_data["by_surface"]:
            parts = ", ".join(f"{k} ({v})" for k, v in stats_data["by_surface"].items())
            click.echo(f"By surface:     {parts}")
        if stats_data["by_project"]:
            parts = ", ".join(
                f"{k} ({v})" for k, v in list(stats_data["by_project"].items())[:5]
            )
            click.echo(f"By project:     {parts}")
        click.echo(f"With open questions: {stats_data['with_open_questions']}")
        click.echo("")

    if not sessions:
        click.echo("No sessions found.")
        return

    click.echo(f"{'ID':<8}  {'DATE':<10}  {'SURFACE':<8}  {'TAGS':<30}  TITLE")
    click.echo("-" * 90)
    for s in sessions:
        sid = s.id[:8] if s.id else "?"
        date = s.start_date[:10] if s.start_date else "?"
        surf = s.surface[:8] if s.surface else ""
        tags_str = ",".join(s.tags)[:30] if s.tags else ""
        title = s.title[:40] if s.title else ""
        click.echo(f"{sid:<8}  {date:<10}  {surf:<8}  {tags_str:<30}  {title}")
    click.echo(f"\n{len(sessions)} session(s)")


@cli.command(name="rebuild-index")
def rebuild_index():
    """Rebuild the LanceDB semantic search index. Pro tier required.

    Downloads BAAI/bge-small-en-v1.5 (~130MB) on first run if not cached.
    Run once after first Pro activation, or to recover a corrupted index.
    Subsequent searches with --semantic will use this index.
    """
    if not db.config.is_pro:
        click.echo("error: rebuild-index requires LoreConvo Pro. "
                   "Get a license at labyrinthanalyticsconsulting.com.")
        sys.exit(1)
    click.echo("Rebuilding semantic search index (may take 1-2 minutes on first run)...")
    try:
        result = db.rebuild_lance_index()
        if "error" in result:
            click.echo(f"error: {result['error']}")
            sys.exit(1)
        click.echo(f"[OK] Index built: {result['indexed']} session(s) indexed "
                   f"(of {result['total_in_db']} total in database).")
    except Exception as exc:
        click.echo(f"error: rebuild failed: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    cli()
