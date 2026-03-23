# ConvoVault Plugin

Cross-surface persistent memory for Claude sessions. Vault conversations from Code, Cowork, and Chat -- recall decisions, artifacts, and context in any future session. Never re-explain yourself again.

## Supported Platforms

| Platform | Support | Notes |
|---|---|---|
| **Cowork** | Full | Plugin installs natively; skills work end-to-end |
| **Claude Code** | Full | Install as an MCP server; all 12 tools available |
| **Chat (web)** | Partial | No plugin support, but use `export-to-chat.sh` to bridge context |

ConvoVault runs as a local MCP server on your machine. Any Claude surface that supports MCP (Claude Code, Cowork) gets the full experience. Chat users can bridge context using the export script.

## What It Does

ConvoVault gives Claude persistent memory across sessions. Instead of re-explaining context every time you start a new conversation, ConvoVault captures what happened and makes it available later.

- **Save Sessions** -- Structured capture of decisions, artifacts, open questions, and tags
- **Search & Recall** -- Full-text search across all saved sessions
- **Project Organization** -- Group sessions by project with expected skill sets
- **Skill Tracking** -- Record which skills were used for smart filtering
- **Persona Tagging** -- Hierarchical personas for agent-specific memory (e.g., `ron-bot:sql`)
- **Session Linking** -- Connect related sessions with continues/related/supersedes relationships
- **Cross-Surface** -- Sessions saved in Code appear instantly in Cowork and vice versa

## How It Works Across Surfaces

The persistence chain:

1. **Claude Code**: SessionEnd hook auto-saves to ConvoVault DB. SessionStart hook auto-loads recent context.
2. **Cowork**: MCP tools read/write the same SQLite database. Mount `~/.convovault` to share data with Code.
3. **Chat**: Run `export-to-chat.sh` to copy session context to clipboard, then paste into Chat.

All three surfaces share a single SQLite database at `~/.convovault/sessions.db`.

## Companion Product: ProjectVault

ConvoVault stores your *conversation history*. **ProjectVault** stores your *project documents*.

Use them together for complete AI memory:

- **ConvoVault** -- "What did we decide last week about the auth approach?"
- **ProjectVault** -- "What does my spec say about the authentication flow?"

Both products are local-first, SQLite-backed, and work across Claude Code and Cowork.

## Prerequisites

You need **Python 3.10 or higher** and the ConvoVault source installed.

Install from the `side_hustle` monorepo:

```bash
git clone https://github.com/labyrinth-analytics/side_hustle.git
cd side_hustle/ron_skills/convovault
bash install.sh
```

This creates a virtual environment, installs dependencies, and verifies everything works.

## Installation

### In Cowork

1. Install ConvoVault (see Prerequisites above)
2. Install this plugin in Cowork
3. Mount your `~/.convovault` folder so Cowork can access the shared database
4. Restart Cowork

### In Claude Code

Add ConvoVault as an MCP server in your Claude Code config:

```json
{
  "mcpServers": {
    "convovault": {
      "command": "/path/to/side_hustle/ron_skills/convovault/.venv/bin/python3",
      "args": ["/path/to/side_hustle/ron_skills/convovault/src/server.py"],
      "env": {
        "PYTHONPATH": "/path/to/side_hustle/ron_skills/convovault/src"
      }
    }
  }
}
```

Replace `/path/to/side_hustle` with wherever you cloned the repo.

### In Chat

No install needed. Run this in your terminal:

```bash
cd /path/to/side_hustle/ron_skills/convovault
bash export-to-chat.sh
```

This exports your last session and copies it to your clipboard (macOS). Paste into Chat to prime the conversation.

## Skills

| Skill | Description |
|-------|-------------|
| `recall` | Search and retrieve context from past sessions |
| `save` | Capture current session context for future recall |

## Available MCP Tools (12 total)

| Tool | What It Does |
|------|-------------|
| `save_session` | Save a session with decisions, artifacts, and tags |
| `get_recent_sessions` | List recent sessions, optionally filtered by surface |
| `get_session` | Retrieve a specific session by ID |
| `search_sessions` | Full-text search across all saved sessions |
| `get_context_for` | Pull relevant context for a topic |
| `tag_session` | Add a persona tag to a session |
| `link_sessions` | Connect related sessions with a relationship type |
| `create_project` | Create a named project with expected skills |
| `get_project` | Get project details and associated sessions |
| `list_projects` | List all projects |
| `get_skill_history` | See which sessions used a specific skill |
| `vault_suggest` | Get context-aware session suggestions |

## Where Data Is Stored

Sessions are stored locally in SQLite at `~/.convovault/sessions.db`. Override with the `CONVOVAULT_DB` environment variable. All data stays on your machine -- no cloud dependency, zero API costs.

## License

MIT -- Labyrinth Analytics Consulting
Contact: info@labyrinthanalyticsconsulting.com
