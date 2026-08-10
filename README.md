# LoreConvo v0.10.1

Your memory follows your identity, not your tool — with your consent.

LoreConvo is the only AI memory that carries your context across Claude Code, Codex, Cursor, and Hermes Agent. One install, one memory, everywhere you code.

> Install directly from Claude Code's plugin marketplace, or via PyPI: `uvx loreconvo`

## Why LoreConvo?

### Works wherever you work

LoreConvo works across Claude Code, Cursor, Codex, and Hermes -- the same memory
layer, no matter which client you reach for. When you switch mid-project, your
context travels with you automatically.

Most tools wall off memory by machine or workspace. LoreConvo stores everything
locally in a SQLite database you own, and surfaces it wherever you are. Capture
happens two ways: explicitly via the save tools, or automatically at session end
if you install the optional hooks. Either way, you can inspect, edit, or delete
any memory at any time.

### You control what gets saved

LoreConvo puts you in control: automatic capture only runs if you choose to install the session hooks, every save is inspectable, and you can delete any memory at any time.

Every memory shows you exactly where it came from — which surface captured it, when, what project context it belongs to, and which skill generated it. No mystery. Full provenance.

### Your memory stays on your machine

LoreConvo stores everything in a SQLite database on your own machine. Your data stays local unless you explicitly enable the optional AI summarization feature (Pro, off by default), which sends a transcript excerpt to the Anthropic API using your own key. No cloud accounts. No vendor with access to your session history.

Your sessions live in `~/.loreconvo/sessions.db` -- a file you own, can back up, and can delete whenever you want.

### Structured memory, not raw transcripts

LoreConvo captures two types of memory for each session:

- **Episodic memory:** what happened -- summaries, artifacts created, open questions left behind
- **Semantic memory:** what was decided -- stable conclusions about the project that persist across sessions

Together these give Claude a structured, searchable record of your project's history, not just a pile of chat transcripts.

## Recall Benchmark

LoreConvo's FTS5 search is benchmarked against a 60-session synthetic corpus (6 topic areas, 36 labeled queries).

| Variant | Recall@5 | MRR |
|---------|----------|-----|
| FTS5 + compound token expansion (default) | **88.9%** | **0.875** |
| FTS5 baseline (no expansion) | 72.2% | 0.708 |

Compound token expansion (camelCase / snake_case query preprocessing) lifts Recall@5 by **+35.7 pp** on queries using technical identifiers like `autoSave`, `pipeline_tracker`, and `get_context_for`.

[Full benchmark report](docs/agent-reports/benchmarks/loreconvo_recall_benchmark_20260522.md) |
[Reproduce](scripts/run_loreconvo_recall_benchmark.py)

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

Once loaded, Claude has access to all 39 LoreConvo MCP tools automatically. Ask Claude to "save this session" or "recall what we discussed about X" and it will use the tools on its own.

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
Claude Code  (~/.claude/settings.json via `claude mcp add`)
  |-- SessionEnd hook --> auto_save.py --> ~/.loreconvo/sessions.db
  |-- SessionStart hook <-- auto_load.py <-+
                                           |
Cursor       (.cursor/mcp.json) <--MCP-----+
Codex        (~/.codex/config.toml) <--MCP-+
Hermes Agent (~/.hermes/config.yaml) <-MCP-+
  All surfaces: save_session / get_recent_sessions / search_sessions

Claude Chat (web)
  |-- export-to-chat.sh --> clipboard --> paste into Chat
```

**Claude Code** is the primary surface. The hooks run automatically:

- When a session ends, `auto_save.py` captures the conversation and saves a structured summary (decisions, artifacts, open questions, tags) to the local SQLite database.
- When a new session starts, `auto_load.py` queries the database, scores recent sessions by signal quality, and injects the most relevant context into the session as system context. Sessions with open questions and decisions score highest; low-signal sessions are filtered out. It also indexes any MEMORY.md found in the project directory (see [MEMORY.md Auto-Indexing](#memorymd-auto-indexing) below).

**Cursor** connects via `.cursor/mcp.json` in the project root -- the same MCP protocol as Claude Code. See INSTALL.md for setup details.

**OpenAI Codex** connects via `~/.codex/config.toml` using a `[mcp_servers.<name>]` section. See INSTALL.md for setup details.

**Hermes Agent** connects via `~/.hermes/config.yaml` under the `mcp_servers:` key. See INSTALL.md for setup details.

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

# Add persistent project instructions (optional)
create_project(
    "my-api",
    description="REST API project",
    instructions="Python 3.10+, SQLite only. No cloud dependencies. Deploy via Docker."
)

# See recent sessions, skill usage, and open questions for the project
get_project("my-api")

# Search scoped to the project
search_sessions("auth design", project="my-api")
```

**Project Instructions** (optional): When you create a project, you can store persistent instructions or constraints that Claude will see at session start. This is useful for enforcing project-wide standards without repeating them in every CLAUDE.md file. Instructions are displayed in the auto-load context before recent session summaries.

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

## Plans: Free vs Pro

LoreConvo is local-first and free to use. Pro ($8/mo) removes the session limit and
unlocks LLM-quality summaries, hybrid retrieval search, and cross-product linking.
Everything runs on your machine on either plan -- Pro adds no cloud component.

Free tier search: keyword (FTS5) + recency ordering.
Pro tier search: hybrid retrieval -- vector (BGE-small-en-v1.5), BM25 full-text, and
recency reranking combined via RRF fusion. Finds sessions by meaning, not just keywords.

| | Free | Pro ($8/mo) |
|---|---|---|
| Saved sessions | 50 | Unlimited |
| Full-text search (FTS5) | Yes | Yes |
| MEMORY.md auto-indexing | Yes | Yes |
| Project tagging, session linking, skill history | Yes | Yes |
| Auto-load / auto-save hooks | Yes | Yes |
| Local-first, no cloud, zero API costs | Yes | Yes |
| Related-session discovery | Keyword co-occurrence | Embedding-based (BGE-small-en-v1.5) |
| LLM async session summarization | -- | Yes (Claude Haiku, opt-in) |
| Hybrid retrieval: vector + BM25 + recency reranking (`rebuild_index`) | -- | Yes (Pro) |
| Cross-product document linking (`get_docs_for_session`, `session_link_doc`) | -- | Yes (also requires LoreDocs Pro) |
| Team memory -- export/merge sessions across machines | -- | Yes |
| Anthropic managed-agent export (`export_for_anthropic`) | -- | Yes |

Check your current tier and usage with `get_tier`. Activate a Pro license with
`vault_set_tier`.

## Features

- **Automatic session capture**: Sessions save at session end and load at session start via Claude Code hooks -- no manual `save_session` call required
- **Cross-client memory**: Your context follows you across Claude Code, Cursor, Codex, and Hermes -- not locked to one IDE or machine
- **Structured sessions**: Captures decisions, artifacts, open questions -- not just raw text; optional reasoning_notes field stores agent reasoning chains
- **Project organization**: Group sessions by project with expected skill sets
- **Skill tracking**: Record which skills were used for smart filtering
- **Persona tagging**: Hierarchical personas for agent-specific memory (e.g., `ron-bot:sql`)
- **Full-text search**: SQLite FTS5 for fast keyword search across all sessions
- **MEMORY.md auto-indexing**: Your project MEMORY.md is automatically indexed at session start and is searchable alongside regular sessions via `search_sessions`
- **LLM async session summarization (Pro)**: Auto-saved sessions are upgraded to LLM-quality summaries in the background using Claude Haiku. Opt in by setting `LORECONVO_ANTHROPIC_API_KEY`. A daily cap (`LORECONVO_SUMMARIZER_DAILY_CAP`, default 100) prevents runaway API spend. Pro tier only.
- **Embedding-based related session discovery (Pro)**: `get_related_sessions` automatically discovers sessions with similar content using BGE-small-en-v1.5 embeddings (cosine >= 0.75). Up to 10 bidirectional auto-links per save, same-project scoped. Free tier gets keyword co-occurrence links. Set `LORECONVO_EMBEDDING_LINKS=0` to disable embedding links.
- **Cross-product document linking (Pro)**: Automatically discovers and links the LoreDocs documents most relevant to any session, and vice versa. Uses two new tools: `get_docs_for_session` and `session_link_doc`. Requires both LoreConvo Pro and LoreDocs Pro.
- **Local-first**: SQLite database, no cloud dependency, zero API costs

## Tiers

**Free - 50 sessions**
- Full feature set: auto-load, full-text search, tagging, session linking, export and import
- Local SQLite storage -- your data, your machine, no cloud account required
- One-click install via the Anthropic Marketplace

**Pro - $8/month**
- Unlimited sessions
- Team memory: share sessions with teammates (local-first async export/import, no server required)
- Related session discovery and semantic search
- Anthropic managed-agents export
- LLM-quality session summarization in the background (async)

[Upgrade to Pro -- $8/month](https://buy.stripe.com/9B65kv1VOgk3ekr7VD7N600)

## MCP Tools

LoreConvo provides 39 MCP tools that Claude calls automatically during sessions.
The table below shows the most commonly used ones -- see [MCP Tool Catalog](docs/mcp_tool_catalog.md) for the complete reference.

| Tool | What it does |
|------|-------------|
| `save_session` | Save a session summary with decisions, artifacts, and tags |
| `get_recent_sessions` | List recent sessions, optionally filtered by surface |
| `get_session` | Retrieve a specific session by ID |
| `search_sessions` | Full-text search across all saved sessions |
| `get_context_for` | Pull relevant context for a topic (best for "recall" use) |
| `tag_session` | Add a persona tag to a session |
| `link_sessions` | Connect related sessions with a relationship type |
| `get_related_sessions` | Find sessions related to a given session |
| `create_project` | Create a named project with expected skills |
| `get_project` | Get project details and associated sessions |
| `list_projects` | List all projects |
| `get_skill_history` | See which sessions used a specific skill |
| `vault_suggest` | Proactive suggestions for relevant context to load |
| `get_tier` | Check current tier and license key status |
| `vault_set_tier` | Set the active tier (free or pro) |
| `export_sessions` | Export sessions to a portable JSON format |
| `import_sessions` | Import sessions from a previously exported JSON file |
| `consolidate_memories` | Merge related sessions into persistent memory entries (Recall) |
| `get_memory_digest` | Inject a condensed memory digest into the current session (Recall) |
| `set_session_expiry` | Mark a session to expire and be pruned after a given date |
| `get_stats` | Show usage statistics (session count, surface breakdown) |
| `inspect_sessions` | Inspect session internals for debugging |
| `export_for_anthropic` | Export sessions in Anthropic managed-agent format (Pro) |
| `rebuild_index` | Rebuild the LanceDB semantic search index (Pro) |
| `loreconvo_onboard` | First-time setup wizard |
| `get_dream_log` | View the consolidation activity log |
| `get_docs_for_session` | Retrieve LoreDocs documents linked to a specific session (Pro -- requires LoreDocs Pro) |
| `session_link_doc` | Manually create a link between a session and a LoreDocs document (Pro -- requires LoreDocs Pro) |
| `pin_session` | Pin or unpin a session to exclude it from automated cleanup |
| `get_anti_patterns` | List sessions tagged as anti-patterns (approaches to avoid) |
| `tag_as_anti_pattern` | Tag a session as an anti-pattern so future recalls flag it |
| `untag_anti_pattern` | Remove an anti-pattern tag from a session |
| `save_memory_item` | Save a structured memory item: a decision, open question, or artifact |
| `query_memory_items` | Query structured memory items by type, project, status, and recency |
| `transition_memory_item` | Move a memory item through its lifecycle (retire, answer, wont-answer) |
| `update_memory_item` | Correct a memory item's title, body, tags, or metadata, or move it between projects |
| `configure_agent_context` | Store or update a named topic config so an agent auto-loads targeted context at session start |
| `inject_agent_context` | Return targeted session context for an agent, using stored or call-time topics |
| `graph_session_map` | Export a Mermaid knowledge graph of sessions and their links |

## Requirements

- Python 3.10+
- macOS or Linux
- `mcp` and `click` (auto-installed by `install.sh`)

## Data and Privacy

LoreConvo is **local-first**. All data lives in `~/.loreconvo/sessions.db` on your machine.

- **Data collected:** Session titles, summaries, tags, surface identifiers, project names, and skill names you provide when saving. No telemetry, usage analytics, or identifiers are collected automatically.
- **Storage:** SQLite database at `~/.loreconvo/sessions.db`. No cloud storage. Override the path with the `LORECONVO_DB` environment variable.
- **Third-party sharing:** None by default. Data leaves your machine only if you enable optional AI summarization (Pro) by setting `LORECONVO_ANTHROPIC_API_KEY`, which sends a bounded transcript excerpt to the Anthropic API under your own key. Leave the key unset and everything stays local.
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

## What's New

<!-- WHATS_NEW:START -->

## v0.10.1 (2026-08-09)

### Fixed: The v0.10.0 notes gave the wrong command

The v0.10.0 release notes and README told you to run `loreconvo license clear`.
That does not clear anything -- `loreconvo` is the MCP server, so the command
just starts a server and waits. The command you want is:

```
python -m loreconvo.cli license clear
```

Sorry for the confusion. Nothing changed in the software; only the
documentation was wrong.

<!-- WHATS_NEW:END -->

See the full [changelog](docs/CHANGELOG.md) for the complete release history.

## License

Business Source License 1.1 (BSL 1.1) - Labyrinth Analytics Consulting

Free for personal/non-commercial use (up to 50 sessions). Commercial use requires
a paid license. Converts to Apache 2.0 on 2030-03-31. See [LICENSE](LICENSE) for details.
