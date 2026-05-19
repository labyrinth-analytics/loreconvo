# LoreConvo v0.6.0

Vault your Claude conversations. Never re-explain yourself again.

Persistent cross-surface memory for Claude. Capture session context across Code, Cowork, and Chat. Organize by project, skill, and persona.

> **Available on the Anthropic Marketplace.** Install directly from Claude, or via PyPI: `uvx loreconvo`

## Why LoreConvo?

### Your memory stays on your machine

Unlike cloud-based memory tools, LoreConvo stores everything in a SQLite database on your
own machine. No data leaves your computer. No subscription to a memory cloud. No vendor with
access to your session history.

Your sessions live in `~/.loreconvo/sessions.db` -- a file you own, can back up, and can
delete any time.

### Works wherever Claude works

LoreConvo works across Claude Code, Claude.ai, and Cowork -- not just in one IDE.
When you switch surfaces mid-project, your context travels with you automatically.

### Structured memory, not raw transcripts

LoreConvo captures two types of memory for each session:

- **Episodic memory:** what happened -- summaries, artifacts created, open questions left behind
- **Semantic memory:** what was decided -- stable conclusions about the project that persist
  across sessions

Together these give Claude a structured, searchable record of your project's history,
not just a pile of chat transcripts.

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

Replace `/path/to/loreconvo` with wherever you saved the source folder.

After making code changes, use `/reload-plugins` to refresh without restarting.

Once loaded, Claude has access to all 17 LoreConvo MCP tools automatically. Ask Claude to "save this session" or "recall what we discussed about X" and it will use the tools on its own.

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
- When a new session starts, `auto_load.py` queries the database, scores recent sessions by signal quality, and injects the most relevant context into the session as system context. Sessions with open questions and decisions score highest; low-signal sessions are filtered out. It also indexes any MEMORY.md found in the project directory (see [MEMORY.md Auto-Indexing](#memorymd-auto-indexing) below).

**Cowork** (this desktop app) does not run hooks, but has full access to the same database via the 17 MCP tools. You can call `get_recent_sessions`, `search_sessions`, or `get_context_for` directly from a Cowork conversation to pull in context from any prior Code session.

**Claude Chat** (web) does not support plugins. The `export-to-chat.sh` script bridges the gap: it exports your most recent session to your clipboard so you can paste it directly into Chat. This gives Chat the same context that Code would have loaded automatically.

The result: when you switch surfaces mid-project, you never have to re-explain what you were doing.

## Your Data is Always Available

LoreConvo works through MCP tools when they are available and falls back to bundled scripts automatically when they are not. Your sessions are safe regardless of MCP status -- the same save, search, and recall operations work either way. You do not need to configure anything; the plugin skill handles the switch silently.

## Project Workspaces

LoreConvo projects are persistent workspaces -- every session, decision, and artifact
from your work on a project is searchable from any Claude surface.

```python
# Create a project workspace
create_project("my-api", "REST API project", expected_skills=["openapi", "python"])

# See recent sessions, skill usage, and open questions for the project
get_project("my-api")

# Search scoped to the project
search_sessions("auth design", project="my-api")
```

Used with [LoreDocs](https://github.com/labyrinth-analytics/loredocs), LoreConvo forms a
portable project workspace for all of Claude -- session memory AND structured knowledge,
entirely on your machine. Where cloud AI workspaces tie you to one ecosystem, the Lore
pair works across every Claude surface you already use.

## MEMORY.md Auto-Indexing

If your project has a `MEMORY.md` file, LoreConvo automatically indexes it at every session start. The contents become searchable alongside your regular sessions via `search_sessions`.

This means Claude can recall project conventions, team notes, or architectural decisions from MEMORY.md without you having to mention them. Search results from MEMORY.md are tagged `memory_md` and have `source='file_memory'` so you can tell them apart from regular session entries.

**Which directory is scanned?**

By default, LoreConvo scans the directory where Claude Code is running (the current working directory). To point it at a different directory, pass `LORECONVO_PROJECT_PATH` as an env flag in your `claude mcp add --scope user` command:

```bash
"--env=LORECONVO_PROJECT_PATH=/Users/YOUR_USERNAME/projects/my_project"
```

Replace `YOUR_USERNAME` and `my_project` with your actual values. Use the full absolute path -- do not use `~` or `$HOME`.

**Filtering MEMORY.md entries in search results**

To include MEMORY.md entries in a search, use `search_sessions` normally -- they appear automatically. To see only MEMORY.md entries, filter by tag:

> "Search LoreConvo sessions tagged memory_md for 'database conventions'."

The index is updated each time a session starts (idempotent -- no duplicates accumulate).

---

## Verify Installation

After installing, verify LoreConvo is working by asking Claude:

> "Run `get_recent_sessions` and show me the results."

If you see a list of sessions (or an empty list if this is your first time), LoreConvo is connected. If you get an error about missing tools, re-run `bash install.sh` and reload the plugin.

For hooks verification (Claude Code only):

> "Check if LoreConvo auto-loaded any context at the start of this session."

If the SessionStart hook is working, Claude will have received context from your recent sessions automatically.

## Recommended CLAUDE.md Setup

For the best experience, add the following snippet to your `~/.claude/CLAUDE.md` (global) or your project's `CLAUDE.md`. This tells Claude how to use LoreConvo consistently across sessions.

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

**For Cowork users:** Cowork does not run hooks automatically. Add instructions to call `get_recent_sessions` at session start and `save_session` at session end in your project CLAUDE.md. See [COWORK_RESTORE.md](COWORK_RESTORE.md) for details.

## Features

- **Cross-surface memory**: Bridge context between Claude Code, Cowork, and Chat
- **Structured sessions**: Captures decisions, artifacts, open questions -- not just raw text
- **Project organization**: Group sessions by project with expected skill sets
- **Skill tracking**: Record which skills were used for smart filtering
- **Persona tagging**: Hierarchical personas for agent-specific memory (e.g., `ron-bot:sql`)
- **Full-text search**: SQLite FTS5 for fast keyword search across all sessions
- **MEMORY.md auto-indexing**: Your project MEMORY.md is automatically indexed at session start and is searchable alongside regular sessions via `search_sessions`
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

# Export for Chat paste (most recent session, markdown format)
.venv/bin/python3 src/cli.py export --last --format markdown

# Export a specific session by ID
.venv/bin/python3 src/cli.py export <session-id>

# Export as JSON
.venv/bin/python3 src/cli.py export --last --format json

# Skill history
.venv/bin/python3 src/cli.py skill-history rental-property-accounting

# List all skills by usage count
.venv/bin/python3 src/cli.py skills list

# Stats
.venv/bin/python3 src/cli.py stats
```

## MCP Tools

LoreConvo provides 17 MCP tools that Claude calls automatically during sessions:

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
| `get_tier` | Check current tier and license key status |
| `vault_set_tier` | Set the active tier (free, pro, team) |
| `export_sessions` | Export sessions to a portable JSON format |
| `import_sessions` | Import sessions from a previously exported JSON file |

## Requirements

- Python 3.10+
- macOS or Linux
- `mcp` and `click` (auto-installed by `install.sh`)

## Data and Privacy

LoreConvo is **local-first**. All data lives in `~/.loreconvo/sessions.db` on your machine.

- **Data collected:** Session titles, summaries, tags, surface identifiers, project names, and skill names you provide when saving. No telemetry, usage analytics, or identifiers are collected automatically.
- **Storage:** SQLite database at `~/.loreconvo/sessions.db`. No cloud storage. Override the path with the `LORECONVO_DB` environment variable.
- **Third-party sharing:** None. Data never leaves your machine.
- **Retention:** Data is retained until you delete it via `delete_session` or remove the database file manually. No automatic expiry.
- **Contact:** info@labyrinthanalyticsconsulting.com

Full privacy policy: https://labyrinthanalyticsconsulting.com/privacy

## Troubleshooting

**MCP tools not showing up in Claude Code?**
Make sure you ran `bash install.sh` first. The `.venv` must exist with dependencies installed.

**"No module named 'mcp'" error?**
The `.mcp.json` points to `.venv/bin/python3` inside the plugin folder. If you moved the folder, re-run `bash install.sh`.

**Cowork can't see sessions saved in Code?**
Ask Claude to "mount my ~/.loreconvo folder" so Cowork can access the shared database.

## Fallback Script (Direct DB Access)

If the MCP server is unreachable (e.g., in scheduled tasks or automation scripts), `scripts/save_to_loreconvo.py` provides the same core operations directly against the SQLite database.

```bash
# Save a session
python scripts/save_to_loreconvo.py \
    --title "Daily QA run" \
    --surface "qa" \
    --summary "Ran full test suite. All passing." \
    --tags '["qa", "automated"]'

# Read recent sessions
python scripts/save_to_loreconvo.py --read --limit 5

# Filter by surface
python scripts/save_to_loreconvo.py --read --surface code --limit 3

# Search sessions
python scripts/save_to_loreconvo.py --search "tax pipeline"
```

The script auto-discovers the database at `~/.loreconvo/sessions.db` (or pass `--db-path` explicitly). It generates proper UUIDs and writes the same schema as the MCP `save_session` tool.

## License

Business Source License 1.1 (BSL 1.1) - Labyrinth Analytics Consulting

Free for personal/non-commercial use (up to 50 sessions). Commercial use requires
a paid license. Converts to Apache 2.0 on 2030-03-31. See [LICENSE](LICENSE) for details.
