"""
LoreConvo backend for Anthropic's memory_20250818 API tool.

Usage::

    from loreconvo import LoreConvoMemoryBackend
    import anthropic

    client = anthropic.Anthropic()
    memory_tool = LoreConvoMemoryBackend()
    message = client.beta.messages.run_tools(
        model="claude-opus-4-7",
        messages=[{"role": "user", "content": "Remember that I prefer Python 3.12"}],
        tools=[memory_tool],
    ).until_done()

Sessions written by this bridge use surface='memory_bridge' and are NOT marked as
external_tool_session -- they are first-class LoreConvo sessions, searchable via
FTS5 and (on Pro) semantic search.
"""

import hashlib
import uuid
from datetime import datetime, timezone
from typing import Optional

from anthropic.types.beta import (
    BetaMemoryTool20250818CreateCommand,
    BetaMemoryTool20250818DeleteCommand,
    BetaMemoryTool20250818InsertCommand,
    BetaMemoryTool20250818RenameCommand,
    BetaMemoryTool20250818StrReplaceCommand,
    BetaMemoryTool20250818ViewCommand,
)
from anthropic.tools.memory import BetaAbstractMemoryTool
from anthropic.lib.tools import ToolError

from .core.config import Config
from .core.database import SessionDatabase, SessionLimitReachedError
from .core.models import Session

_SURFACE = "memory_bridge"


def _path_to_id(path: str) -> str:
    """Deterministic UUID from a /memories/ path.

    The same path always returns the same ID, so view/create/str_replace
    all resolve to the same session without a lookup by title.
    """
    digest = hashlib.md5(path.encode("utf-8")).hexdigest()
    return str(uuid.UUID(digest))


def _path_to_title(path: str) -> str:
    """Strip /memories/ prefix and .md suffix to get a human-readable title."""
    name = path.rstrip("/").rsplit("/", 1)[-1]
    if name.endswith(".md"):
        name = name[:-3]
    return name or path


def _normalize_memory_path(path: str) -> str:
    """Normalize memory paths to consistently end with .md for stable ID hashing.

    Ensures /memories/foo and /memories/foo.md always resolve to the same session.
    The root /memories and directory-style paths (trailing /) are left unchanged.
    """
    if path and path != "/memories" and not path.endswith("/") and not path.endswith(".md"):
        return path + ".md"
    return path


class LoreConvoMemoryBackend(BetaAbstractMemoryTool):
    """LoreConvo storage backend for Anthropic's memory_20250818 API tool.

    Subclasses BetaAbstractMemoryTool so it drops in wherever a memory tool is
    accepted. Memories are stored as LoreConvo sessions with surface='memory_bridge'.
    Full FTS5 search and (Pro) semantic search work on these sessions out of the box.

    Parameters
    ----------
    db_path:
        Path to the LoreConvo SQLite database. Defaults to ~/.loreconvo/sessions.db
        or the LORECONVO_DB env var.
    project:
        Optional project tag for all memories written through this backend.
    """

    def __init__(
        self,
        db_path: Optional[str] = None,
        project: Optional[str] = None,
    ) -> None:
        super().__init__()
        config = Config(db_path=db_path) if db_path else Config()
        self._db = SessionDatabase(config)
        self._project = project

    def _require_memories_prefix(self, path: str) -> None:
        if not (path == "/memories" or path.startswith("/memories/")):
            raise ToolError(f"Path must start with /memories/, got: {path}")

    # ------------------------------------------------------------------
    # Abstract method implementations
    # ------------------------------------------------------------------

    def view(self, command: BetaMemoryTool20250818ViewCommand) -> str:
        path = _normalize_memory_path(command.path.rstrip("/"))

        if path == "/memories":
            return self._list_all()

        self._require_memories_prefix(path)
        session_id = _path_to_id(path)
        session = self._db.get_session(session_id)
        if not session:
            raise ToolError(
                f"Memory not found: {path}. "
                "Use 'create' to store a new memory at this path."
            )

        content = session.summary or ""
        if command.view_range and len(command.view_range) == 2:
            lines = content.splitlines()
            start = max(0, command.view_range[0] - 1)
            end = command.view_range[1] if command.view_range[1] != -1 else len(lines)
            content = "\n".join(lines[start:end])

        return content

    def create(self, command: BetaMemoryTool20250818CreateCommand) -> str:
        path = _normalize_memory_path(command.path)
        self._require_memories_prefix(path)

        session_id = _path_to_id(path)
        if self._db.get_session(session_id):
            raise ToolError(
                f"Memory already exists: {path}. "
                "Use str_replace to update an existing memory."
            )

        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        session = Session(
            id=session_id,
            title=_path_to_title(path),
            surface=_SURFACE,
            project=self._project,
            start_date=now,
            summary=command.file_text,
            external_tool_session=False,
        )
        try:
            self._db.save_session(session)
        except SessionLimitReachedError:
            raise ToolError(
                "Memory limit reached on free tier. "
                "Upgrade to Pro at labyrinthanalyticsconsulting.com for unlimited memories."
            )
        return f"Memory created: {path}"

    def str_replace(self, command: BetaMemoryTool20250818StrReplaceCommand) -> str:
        path = _normalize_memory_path(command.path)
        self._require_memories_prefix(path)
        session_id = _path_to_id(path)
        session = self._db.get_session(session_id)
        if not session:
            raise ToolError(f"Memory not found: {command.path}")

        content = session.summary or ""
        count = content.count(command.old_str)
        if count == 0:
            raise ToolError(
                f"No replacement performed: old_str not found in {command.path}."
            )
        if count > 1:
            raise ToolError(
                f"No replacement performed: old_str appears {count} times in "
                f"{command.path}. Make old_str more specific."
            )

        session.summary = content.replace(command.old_str, command.new_str, 1)
        try:
            self._db.save_session(session)
        except SessionLimitReachedError:
            raise ToolError(
                "Memory limit reached on free tier. "
                "Upgrade to Pro at labyrinthanalyticsconsulting.com for unlimited memories."
            )
        return f"Memory updated: {command.path}"

    def insert(self, command: BetaMemoryTool20250818InsertCommand) -> str:
        path = _normalize_memory_path(command.path)
        self._require_memories_prefix(path)
        session_id = _path_to_id(path)
        session = self._db.get_session(session_id)
        if not session:
            raise ToolError(f"Memory not found: {command.path}")

        lines = (session.summary or "").splitlines()
        if command.insert_line < 0 or command.insert_line > len(lines):
            raise ToolError(
                f"Invalid insert_line {command.insert_line} for memory with "
                f"{len(lines)} lines."
            )

        lines.insert(command.insert_line, command.insert_text.rstrip("\n"))
        session.summary = "\n".join(lines)
        try:
            self._db.save_session(session)
        except SessionLimitReachedError:
            raise ToolError(
                "Memory limit reached on free tier. "
                "Upgrade to Pro at labyrinthanalyticsconsulting.com for unlimited memories."
            )
        return f"Memory updated: {command.path}"

    def delete(self, command: BetaMemoryTool20250818DeleteCommand) -> str:
        raise ToolError(
            "Memory deletion is not supported in LoreConvoMemoryBackend v1. "
            "To remove a memory manually, run: python -m loreconvo.cli inspect --delete <id>"
        )

    def rename(self, command: BetaMemoryTool20250818RenameCommand) -> str:
        raise ToolError(
            "Memory rename is not supported in LoreConvoMemoryBackend v1."
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _list_all(self) -> str:
        rows = self._db.conn.execute(
            "SELECT id, title, start_date FROM sessions "
            "WHERE surface = ? AND (source IS NULL OR source NOT IN ('periodic', 'file_memory')) "
            "ORDER BY start_date DESC LIMIT 200",
            (_SURFACE,),
        ).fetchall()

        if not rows:
            return "No memories stored yet. Use 'create' to store a memory."

        lines = ["Stored memories (most recent first):\n"]
        for row in rows:
            lines.append(f"  /memories/{row['title']}.md  ({row['start_date'][:10]})")
        return "\n".join(lines)
