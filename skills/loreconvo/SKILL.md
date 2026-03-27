---
name: loreconvo
description: >
  Vault your Claude conversations for cross-session recall. Use this skill when the user asks to
  "save this session", "vault this", "remember this", "what did we decide about", "load context for",
  "/vault save", "session history", "find past sessions", "export session", or wants to
  recall decisions, artifacts, or context from previous Code, Cowork, or Chat sessions.
  Also triggers on "tag as persona", "link sessions", "project context", or "skill history".
metadata:
  version: "0.3.0"
  author: "Labyrinth Analytics Consulting"
---

# LoreConvo

Vault your Claude conversations. Capture session context (decisions, artifacts, open questions) and recall it in future sessions across Code, Cowork, and Chat. Never re-explain yourself again.

## When to Vault a Session

Save a session when:
- The user explicitly requests it (`/vault save` or "vault this session")
- A significant decision was made
- The session is ending and contains valuable context
- The user switches topics or projects

## How to Vault

Call the `save_session` MCP tool with structured data extracted from the conversation:

1. **Title**: Short, descriptive (e.g., "LoreConvo PRD and architecture design")
2. **Surface**: Where this ran - `cowork`, `code`, or `chat`
3. **Summary**: 2-3 paragraphs covering what was done, why, and what matters for future sessions
4. **Decisions**: List every decision made, even small ones. These are the most searchable items.
5. **Artifacts**: Files created or modified, with paths
6. **Open questions**: Unresolved items to carry forward
7. **Skills used**: List all skills invoked during this session (check the conversation for "skill is loading" messages)
8. **Project**: Associate with a defined project if applicable
9. **Tags**: Freeform tags for additional categorization

## How to Recall Context

At the start of a session, or when the user asks about prior work:

- `get_context_for("topic")` - Get relevant excerpts for a topic
- `search_sessions("query")` - Keyword search across all sessions
- `get_recent_sessions()` - See what was done recently
- `get_project("project-name")` - Load project context with skill usage stats
- `get_skill_history("skill-name")` - Find sessions that used a specific skill

## Persona Tagging

Tag sessions for persona-specific recall:

- `tag_session(session_id, "ron-bot:sql")` - Tag for Ron's SQL Optimizer
- Search with persona filter: `search_sessions("query", persona="ron-bot")`
- Hierarchical: querying `ron-bot` returns sessions tagged `ron-bot`, `ron-bot:sql`, `ron-bot:finance`, etc.

## Session Linking

Link related sessions into chains:

- `link_sessions(from_id, to_id, "continues")` - This session continues another
- `link_sessions(from_id, to_id, "related")` - These sessions are related
- `link_sessions(from_id, to_id, "supersedes")` - This session replaces another

## Project Management

Projects group sessions and define expected skill sets:

- `create_project("project-ron", "Autonomous AI agent business", expected_skills=["sql-optimizer"])`
- `get_project("project-ron")` - See project details, recent sessions, skill usage breakdown
- Sessions using 2+ expected skills from a project can be auto-associated

## Export for Chat

When the user needs to continue in Chat (which cannot run MCP tools):

1. Call `get_session(session_id)` or `get_recent_sessions()`
2. Format the result as a markdown summary with a "Context for Claude" preamble
3. The user pastes this into Chat to prime the new conversation

CLI equivalent: `loreconvo export --last --format markdown`

## Reference Files

See `references/schema.md` for the full SQLite schema and `references/export-formats.md` for export template definitions.
