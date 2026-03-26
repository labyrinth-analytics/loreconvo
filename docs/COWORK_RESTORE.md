# LoreConvo Cowork Restore Workflow

Until Cowork adds session lifecycle hooks, use this manual workflow to bridge context between sessions.

## Quick restore (start of any Cowork session)

Say this to Claude at the start of a Cowork session:

> "Check LoreConvo for my recent sessions and restore context for [topic]"

Claude will call the LoreConvo MCP tools to search for relevant sessions and inject the context.

## How it works

LoreConvo exposes these MCP tools that Cowork can call:

1. **vault_search** - Search sessions by keyword (e.g., "LoreDocs", "tax prep")
2. **vault_list_sessions** - List recent sessions with project names and summaries
3. **vault_get_session** - Get full session details including summary, tools used, and files modified
4. **vault_inject** - Load session context directly into the conversation

## Example conversation starters

**Resume where you left off:**
> "What was I working on in my last Code session? Check LoreConvo."

**Find a specific session:**
> "Search LoreConvo for sessions about the rental property depreciation schedules"

**Restore project context:**
> "Load LoreConvo context for the secret_agent_man project from the last 3 sessions"

## Saving from Cowork (manual)

At the end of a Cowork session, say:

> "Save this session to LoreConvo with project [name] and tags [tag1, tag2]"

Claude will call the LoreConvo MCP tools to save the current session's key context.

## Phase 2: Auto-restore via Cowork plugin start skill

When Cowork adds lifecycle hooks, LoreConvo will ship a `start` skill that automatically:
1. Checks for recent sessions in the same project directory
2. Injects a brief context summary at session init
3. Offers to restore specific sessions if multiple are relevant

This eliminates the manual step entirely. Target: when Anthropic ships Cowork session hooks.
