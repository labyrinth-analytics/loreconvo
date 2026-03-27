# LoreDocs

> A searchable, organized knowledge base for your AI projects. Store documents, tag them, search across them, and inject context into any Claude conversation.

**By [Labyrinth Analytics Consulting](https://labyrinthanalyticsconsulting.com)**

---

## Quick Install

**Requires [uv](https://docs.astral.sh/uv/getting-started/installation/) -- a fast Python package manager.**

```bash
# Install uv (one time, if you don't have it)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install via the Labyrinth Analytics marketplace
/plugin install loredocs@labyrinth-analytics-claude-plugins
```

Or add directly as an MCP server in Claude Code's `.claude/settings.json`:

```json
{
  "mcpServers": {
    "loredocs": {
      "command": "uvx",
      "args": ["loredocs"]
    }
  }
}
```

---

## The Problem

AI projects accumulate knowledge fast -- architecture decisions, API specs, configuration guides, meeting notes, runbooks. That knowledge lives in scattered files, chat histories, and people's heads. When you start a new Claude session, you're starting from scratch.

LoreDocs gives your AI projects a persistent, searchable brain.

---

## How It Works

```mermaid
graph TD
    A[Your Documents\nspecs, configs, guides\nnotes, runbooks] -->|vault_add_doc| B[(LoreDocs DB\n~/.loredocs/\nloredocs.db)]

    B -->|vault_search| C[Search Results\nwith relevance ranking]
    B -->|vault_inject_summary| D[Claude Context\ninjects relevant docs\nat session start]
    B -->|vault_export_manifest| E[Manifest Export\nshare or version\nyour vault]

    F[Claude Code / Cowork] -->|MCP tools| B
```

**Add once, use everywhere.** Store a document in the vault and it's searchable from any Claude session -- Code, Cowork, or Chat (via export).

**Inject on demand.** Ask Claude to inject the vault summary at the start of a session and it automatically loads the most relevant context for the conversation you're about to have.

**Organize by project.** Group documents into named vaults (one per project), tag them, link related docs, and version-track changes over time.

---

## What You Can Store

LoreDocs handles text extraction from all common document types:

- Markdown and plain text (`.md`, `.txt`)
- Word documents (`.docx`)
- PDFs
- Excel spreadsheets (`.xlsx`)
- PowerPoint presentations (`.pptx`)
- Code files and configs

---

## MCP Tools Reference

**Vault management**

| Tool | What it does |
|---|---|
| `vault_create` | Create a new named vault for a project |
| `vault_list` | List all vaults |
| `vault_get` | Get vault details |
| `vault_delete` | Delete a vault and its documents |
| `vault_tier_status` | Check your current tier and limits |

**Document operations**

| Tool | What it does |
|---|---|
| `vault_add_doc` | Add a document to a vault (extracts text automatically) |
| `vault_get_doc` | Retrieve a specific document |
| `vault_list_docs` | List documents in a vault |
| `vault_update_doc` | Update document content or metadata |
| `vault_delete_doc` | Remove a document from the vault |
| `vault_link_doc` | Link two related documents |
| `vault_unlink_doc` | Remove a link between documents |
| `vault_find_related` | Find documents related to a given doc |

**Search and inject**

| Tool | What it does |
|---|---|
| `vault_search` | Full-text search across all vaults or a specific one |
| `vault_inject_summary` | Generate a context summary for Claude to load at session start |
| `vault_export_manifest` | Export a vault manifest for sharing or versioning |
| `vault_suggest` | Proactive suggestions on what context might be relevant |

**Tagging and organization**

| Tool | What it does |
|---|---|
| `vault_add_tag` | Tag a document |
| `vault_remove_tag` | Remove a tag |
| `vault_search_by_tag` | Find all documents with a given tag |
| `vault_get_doc_history` | See version history for a document |
| `vault_restore_doc_version` | Restore a previous version of a document |

---

## Supported Platforms

| Platform | Support | Notes |
|---|---|---|
| **Claude Code** | Full | All 34 MCP tools available |
| **Cowork** | Full | Use vault_inject_summary at session start for automatic context |
| **Chat (web)** | Partial | Use vault_export_manifest and paste output into Chat |

---

## Free vs Pro

| Feature | Free | Pro ($9/mo) |
|---|---|---|
| Vaults | 3 | Unlimited |
| Documents per vault | 50 | Unlimited |
| Document size | 1 MB | 10 MB |
| Version history | 5 versions | Unlimited |
| Search results | Top 10 | All results |
| Export formats | Markdown | Markdown + JSON |

Pro upgrade: [labyrinthanalyticsconsulting.com](https://labyrinthanalyticsconsulting.com)

---

## Companion Product

**[LoreConvo](https://github.com/labyrinth-analytics/loreconvo)** -- Cross-surface persistent memory for Claude sessions. Where LoreDocs stores *documents*, LoreConvo remembers *conversations* -- decisions made, artifacts created, questions left open. They complement each other well.

---

## Data and Privacy

LoreDocs is **local-first**. All data lives in `~/.loredocs/` on your machine. Nothing is sent to any external server. You own your data.

---

## Issues and Feedback

[github.com/labyrinth-analytics/loredocs/issues](https://github.com/labyrinth-analytics/loredocs/issues)
