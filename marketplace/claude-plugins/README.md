# Labyrinth Analytics Claude Plugins

Claude plugins from [Labyrinth Analytics Consulting](https://labyrinthanalyticsconsulting.com). Persistent memory and knowledge management for your Claude sessions.

---

## Available Plugins

| Plugin | Version | Description |
|--------|---------|-------------|
| **LoreConvo** | v0.3.0 | Cross-surface persistent memory for Claude sessions |
| **LoreDocs** | v0.1.0 | Searchable knowledge base for AI projects |

---

## Installation

### Step 1: Add this marketplace

In Claude Code, run:

```
/plugin marketplace add labyrinth-analytics/claude-plugins
```

### Step 2: Install a plugin

```
/plugin install loreconvo@labyrinth-analytics-claude-plugins
```

or

```
/plugin install loredocs@labyrinth-analytics-claude-plugins
```

### Step 3: Enable the plugin

After installing, you must enable the plugin's MCP server:

```
/install loreconvo
```

or

```
/install loredocs
```

### Step 4: Set up your CLAUDE.md

For LoreConvo, add the following to your project's `CLAUDE.md` (or global `~/.claude/CLAUDE.md`):

```markdown
## LoreConvo Session Memory

At the start of every session, call `get_recent_sessions` to load context from prior sessions.
At the end of every session, call `save_session` to preserve decisions, artifacts, and open questions.
```

For LoreDocs, add:

```markdown
## LoreDocs Knowledge Base

At the start of every session, call `vault_list` then `vault_inject_summary` to load relevant project knowledge.
When you create or update significant documentation, call `vault_add_doc` to store it in the knowledge base.
```

### Step 5: Mount your data directory (Cowork only)

If you use Cowork, mount the data directory so Cowork sessions can access the database:

- **LoreConvo:** Mount `~/.loreconvo` to your Cowork project
- **LoreDocs:** Mount `~/.loredocs` to your Cowork project

---

## Plugin Details

### LoreConvo

Cross-surface persistent memory for Claude sessions. Save conversations from Code, Cowork, and Chat -- recall decisions, artifacts, and context in any future session. Never re-explain yourself again.

**Key features:**
- 12 MCP tools for saving, searching, and recalling sessions
- Automatic SessionEnd/SessionStart hooks (Claude Code)
- Full-text search across all session summaries
- Tag-based filtering and persona support
- Local-first: all data on your machine

**Requires:** Python 3.10+, [uv](https://docs.astral.sh/uv/getting-started/installation/)

[Full documentation](https://github.com/labyrinth-analytics/loreconvo)

### LoreDocs

Searchable, organized knowledge base for your AI projects. Store documents, tag them, search across them, and inject context into any Claude conversation.

**Key features:**
- 34 MCP tools for document management, search, and context injection
- Supports .md, .txt, .docx, .pdf, .xlsx, .pptx, and code files
- Version history and document linking
- Vault-based organization (one vault per project)
- Local-first: all data on your machine

**Requires:** Python 3.10+, [uv](https://docs.astral.sh/uv/getting-started/installation/)

[Full documentation](https://github.com/labyrinth-analytics/loredocs)

---

## Free vs Pro

Both plugins offer a free tier with generous limits. Pro tiers unlock unlimited usage.

| Feature | LoreConvo Free | LoreConvo Pro ($8/mo) |
|---------|---------------|----------------------|
| Sessions | Last 50 | Unlimited |
| Search | 7 days | All time |
| Personas | 1 | Unlimited |

| Feature | LoreDocs Free | LoreDocs Pro ($9/mo) |
|---------|--------------|---------------------|
| Vaults | 3 | Unlimited |
| Docs/vault | 50 | Unlimited |
| Doc size | 1 MB | 10 MB |

Pro upgrade: [labyrinthanalyticsconsulting.com](https://labyrinthanalyticsconsulting.com)

---

## The Lore Ecosystem

LoreConvo and LoreDocs are companion products. LoreConvo remembers *conversations* -- decisions made, artifacts created, questions left open. LoreDocs stores *documents* -- specs, configs, guides, and reference material. Together they give your Claude sessions a persistent, searchable brain.

---

## Data and Privacy

Both plugins are **local-first**. All data lives on your machine. Nothing is sent to any external server.

---

## Support

- LoreConvo issues: [github.com/labyrinth-analytics/loreconvo/issues](https://github.com/labyrinth-analytics/loreconvo/issues)
- LoreDocs issues: [github.com/labyrinth-analytics/loredocs/issues](https://github.com/labyrinth-analytics/loredocs/issues)
- Website: [labyrinthanalyticsconsulting.com](https://labyrinthanalyticsconsulting.com)
