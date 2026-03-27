# LoreConvo

Vault your Claude conversations. Never re-explain yourself again.

Persistent cross-surface memory for Claude. Capture session context across Code, Cowork, and Chat. Organize by project, skill, and persona.

## Quick Start

One command to install:

```bash
bash install.sh
```

This creates a virtual environment, installs dependencies, and verifies everything works. No system Python changes, no manual pip commands.

## Using LoreConvo

### Claude Code (Terminal)

**Start a session with the plugin loaded:**

```bash
claude --plugin-dir /path/to/loreconvo
```

**Or load it inside an existing session:**

```
/plugin add /path/to/loreconvo
```

Replace `/path/to/loreconvo` with wherever you saved the source folder (e.g., `~/projects/side_hustle/ron_skills/loreconvo`).

After making code changes, use `/reload-plugins` to refresh without restarting.

Once loaded, Claude has access to all 12 LoreConvo MCP tools automatically. Ask Claude to "save this session" or "recall what we discussed about X" and it will use the tools on its own.

### Cowork (Desktop App)

1. Click the **+** button next to the prompt box
2. Select **Plugins**
3. Select **Add plugin**
4. Browse to the `loreconvo` source folder

**Important: Shared Database Access**

Cowork runs in a sandboxed VM and can't see your Mac's filesystem by default. To read sessions saved by Claude Code, ask Claude in Cowork:

> "Mount my ~/.loreconvo folder"

Once mounted, Cowork reads and writes to the same database as Claude Code. Sessions saved in Code appear instantly in Cowork.

### Claude Chat (Web)

Chat doesn't support plugins, so LoreConvo provides a one-command bridge. Run this in your terminal:

```bash
bash export-to-chat.sh
```

This exports your last session and copies it to your clipboard (macOS). Switch to Chat and paste (Cmd+V). Chat instantly has the context from your Code or Cowork session.

To search for a specific session:

```bash
bash export-to-chat.sh "tax prep"
```

## How It Works Across Surfaces

The core value of LoreConvo is that context persists across Claude surfaces automatically. Here is the full chain:

```
Claude Code (terminal)
  |-- SessionEnd hook --> auto_save.py --> ~/.loreconvo/sessions.db
  |-- SessionStart hook <-- auto_load.py <-- ~/.loreconvo/sessions.db
                                               ^
Cowork (desktop app) <--MCP tools-------------|
  save_session / get_recent_sessions / search_sessions

Claude Chat (web)
  |-- export-to-chat.sh --> clipboard --> paste into Chat
```

**Claude Code** is the primary surface. The hooks run automatically:

- When a session ends, `auto_save.py` captures the conversation and saves a structured summary (decisions, artifacts, open questions, tags) to the local SQLite database.
- When a new session starts, `auto_load.py` queries the database, scores recent sessions by signal quality, and injects the most relevant context into the session as system context. Sessions with open questions and decisions score highest; low-signal sessions are filtered out.

**Cowork** (this desktop app) does not run hooks, but has full access to the same database via the 12 MCP tools. You can call `get_recent_sessions`, `search_sessions`, or `get_context_for` directly from a Cowork conversation to pull in context from any prior Code session.

**Claude Chat** (web) does not support plugins. The `export-to-chat.sh` script bridges the gap: it exports your most recent session to your clipboard so you can paste it directly into Chat. This gives Chat the same context that Code would have loaded automatically.

The result: when you switch surfaces mid-project, you never have to re-explain what you were doing.

## Features

- **Cross-surface memory**: Bridge context between Claude Code, Cowork, and Chat
- **Structured sessions**: Captures decisions, artifacts, open questions -- not just raw text
- **Project organization**: Group sessions by project with expected skill sets
- **Skill tracking**: Record which skills were used for smart filtering
- **Persona tagging**: Hierarchical personas for agent-specific memory (e.g., `ron-bot:sql`)
- **Full-text search**: SQLite FTS5 for fast keyword search across all sessions
- **Dual interface**: MCP tools (for LLM use) + CLI (for human use)
- **Local-first**: SQLite database, no cloud dependency, zero API costs

## CLI Reference

```bash
# Vault a session
.venv/bin/python3 src/cli.py save -t "Tax pipeline debugging" -s code -m "Fixed the K-1 parser..."

# List recent sessions
.venv/bin/python3 src/cli.py list --days 7

# Search the vault
.venv/bin/python3 src/cli.py search "rental insurance split"

# Export for Chat paste
.venv/bin/python3 src/cli.py export --last --format markdown

# Skill history
.venv/bin/python3 src/cli.py skill-history rental-property-accounting

# Stats
.venv/bin/python3 src/cli.py stats
```

## MCP Tools

LoreConvo provides 12 MCP tools that Claude calls automatically during sessions:

| Tool | What it does |
|------|-------------|
| `save_session` | Save a session summary with decisions, artifacts, and tags |
| `get_recent_sessions` | List recent sessions, optionally filtered by surface |
| `get_session` | Retrieve a specific session by ID |
| `search_sessions` | Full-text search across all saved sessions |
| `get_context_for` | Pull relevant context for a topic (best for "recall" use) |
| `tag_session` | Add a persona tag to a session |
| `link_sessions` | Connect related sessions with a relationship type |
| `create_project` | Create a named project with expected skills |
| `get_project` | Get project details and associated sessions |
| `list_projects` | List all projects |
| `get_skill_history` | See which sessions used a specific skill |
| `vault_suggest` | Proactive suggestions for relevant context to load |

## Requirements

- Python 3.10+
- macOS or Linux
- `mcp` and `click` (auto-installed by `install.sh`)

## Data Storage

Sessions are stored locally in SQLite at `~/.loreconvo/sessions.db`. Override with the `LORECONVO_DB` environment variable.

## Troubleshooting

**MCP tools not showing up in Claude Code?**
Make sure you ran `bash install.sh` first. The `.venv` must exist with dependencies installed.

**"No module named 'mcp'" error?**
The `.mcp.json` points to `.venv/bin/python3` inside the plugin folder. If you moved the folder, re-run `bash install.sh`.

**Cowork can't see sessions saved in Code?**
Ask Claude to "mount my ~/.loreconvo folder" so Cowork can access the shared database.

## License

MIT - Labyrinth Analytics Consulting
