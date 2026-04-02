# LoreConvo Cowork Restore Workflow

Cowork does not currently support session lifecycle hooks. This means LoreConvo's automatic
context loading (SessionStart) and session saving (SessionEnd) do not run in Cowork.

Until Cowork adds hook support, use the manual workaround below.

## Recommended Workaround: CLAUDE.md Instructions

The most reliable approach is to add LoreConvo instructions to your project's `CLAUDE.md`
file. Claude reads this file at the start of every session, so it will always know to
check LoreConvo.

Add this to your project CLAUDE.md (the one in the folder you select in Cowork):

```markdown
## LoreConvo (persistent session memory)

At session start:
1. Call `get_recent_sessions` to check for recent context relevant to the current work.
2. Use this context to avoid re-explaining things already discussed in prior sessions.

During the session:
- If important decisions are made or domain knowledge is shared, note it for the session summary.

At session end:
- Call `save_session` with a summary of what was accomplished, key decisions, open questions,
  and any artifacts created. Use appropriate tags (e.g., project name, surface).
```

## Shared Database Access

Cowork runs in a sandboxed VM and cannot see your Mac's filesystem by default. To read
sessions saved by Claude Code, you need to mount the LoreConvo database folder.

Ask Claude in Cowork:

> "Mount my ~/.loreconvo folder"

Once mounted, Cowork reads and writes to the same database as Claude Code.

## Quick Restore (manual, per-session)

If you prefer not to modify CLAUDE.md, say this to Claude at the start of a Cowork session:

> "Check LoreConvo for my recent sessions and restore context for [topic]"

Claude will call the LoreConvo MCP tools to search for relevant sessions and inject context.

## LoreConvo MCP Tools Available in Cowork

These are the correct tool names Claude uses in Cowork:

| Tool | Purpose |
|------|---------|
| `get_recent_sessions` | List recent sessions (optionally filter by surface) |
| `search_sessions` | Full-text search across all saved sessions |
| `get_context_for` | Pull relevant context for a topic |
| `get_session` | Retrieve a specific session by ID |
| `save_session` | Save a session summary with decisions and tags |
| `vault_suggest` | Get proactive suggestions for relevant context to load |

## Example Conversation Starters

**Resume where you left off:**
> "What was I working on in my last Code session? Check LoreConvo."

**Find a specific session:**
> "Search LoreConvo for sessions about the rental property depreciation schedules"

**Restore project context:**
> "Load LoreConvo context for the last 3 sessions in the side_hustle project"

**Save before ending:**
> "Save this session to LoreConvo with project side_hustle and tags cowork, tax-prep"

## Future: Automatic Hooks

When Anthropic ships Cowork session hooks, LoreConvo will add automatic context loading
and session saving -- eliminating the manual steps entirely. The CLAUDE.md workaround
will continue to work alongside hooks for users who want both.
