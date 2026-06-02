---
name: using-loreconvo
description: >
  Overview and orientation for LoreConvo. Use this skill when the user asks
  "what is LoreConvo", "how do I use LoreConvo", "how does LoreConvo work",
  "show me what LoreConvo can do", "tour LoreConvo", "intro to LoreConvo",
  or any other overview or orientation request about the product.
  Does NOT trigger on action phrases like "save this session" or "search my sessions"
  -- those go directly to the loreconvo action skill.
metadata:
  version: "0.7.1"
  author: "Labyrinth Analytics Consulting"
---

# Using LoreConvo

## What LoreConvo does

LoreConvo is a persistent memory system for Claude sessions. It lets you and your
agents pick up exactly where you left off -- across sessions, surfaces (Claude Code,
Cowork, and Chat), and agent roles -- without needing to re-explain context every
time.

LoreConvo captures two types of memory: episodic (what happened -- summaries,
artifacts, open questions) and semantic (what was decided -- stable conclusions that
persist across sessions). Together they give Claude a structured, searchable record
of your project history that survives context windows, restarts, and surface switches.

Data lives locally in `~/.loreconvo/sessions.db`. Nothing leaves your machine.

## When to reach for LoreConvo

Use LoreConvo when:
- A session is ending and contains valuable context (decisions made, work done,
  open questions left unresolved)
- You want to continue work in a new session from where you left off
- You need to recall what was decided or done in a past session
- You are switching between Claude surfaces (Code -> Cowork -> Chat) and need
  to carry context across

Use it proactively. The auto-load hook (SessionStart) and auto-save hook (SessionEnd)
handle most of this automatically when you have hooks configured. If hooks are not
set up, save manually at the end of each significant session.

## The action skills

LoreConvo ships these action skills. Each handles a specific operation:

| Skill | Trigger phrases | What it does |
|-------|----------------|-------------|
| `loreconvo` | "save this session", "vault this", "remember this", "search sessions", "recall X", "load context" | Core action skill: save, search, recall, link, tag sessions. Start here for most operations. |
| `lore-onboard` | "set up loreconvo", "verify loreconvo", "onboard", "/lore-onboard" | First-install verification: checks MCP connection, DB access, hook config, and runs a test save/load cycle. |

Use `using-loreconvo` (this skill) for orientation. Use the action skills above for
actual operations.

## Key conventions

**Project tagging is mandatory on every save.** Always pass `--project <name>` when
saving a session. The value is the snake_case name of the current working directory
(e.g., `side_hustle`, `secret_agent_man`). Sessions saved without a project tag are
hard to recall and pollute cross-project search results.

**MCP first, fallback second.** LoreConvo works through MCP tools when available.
When the MCP server is unavailable, the bundled scripts (`save_to_loreconvo.py`) do
the same job silently. You do not need to do anything special -- the `loreconvo`
action skill handles the switch transparently.

**Vault surface tags.** The `surface` field identifies where the session ran: `code`,
`cowork`, `chat`. Agents use surface to filter relevant sessions when loading context.

**Agent tag convention.** Agents save sessions with `tags: ["agent:<name>"]` so their
sessions are discoverable by role (e.g., `search_sessions("agent:ron-builder")`).

## Common gotchas

- **DB lives at `~/.loreconvo/sessions.db`** -- not inside the project directory. If
  you moved the plugin or changed the home directory, the DB may be at a different
  path. Run `loreconvo-cli list --limit 1` to verify the DB is accessible.

- **Hooks require setup.** Auto-save and auto-load only run if the SessionStart and
  SessionEnd hooks are installed in your `.claude/settings.json`. Run the
  `lore-onboard` skill to verify hook status after first install.

- **The MCP server parks open in some clients.** The Claude desktop app sometimes
  keeps the MCP server process running after a session ends, holding the SQLite write
  lock. If you see "database is locked" errors, look for a stale `python src/server.py`
  process and kill it.

- **FTS5 search tips.** Use bare keywords for broad matches (`architecture decisions`).
  Use double quotes for exact phrases (`"session end"`). Prefix with `AND`/`OR` for
  boolean logic. Avoid special characters in queries.

## Verify install

Ask Claude to run:
```
get_recent_sessions(limit=3)
```

If you see session results (or an empty list with no error), LoreConvo is connected
and working. If you get a tool-not-found error, the plugin is not loaded. If you get
a DB error, run the `lore-onboard` skill for diagnosis.

## Free vs Pro

Free tier covers unlimited session saving, searching, and recall. Pro unlocks
semantic search (embedding-based, using BGE-small-en-v1.5), related session
discovery, Anthropic managed-agents export, and longer history windows.

Activate Pro by setting the `LORECONVO_PRO` environment variable to your license key.
