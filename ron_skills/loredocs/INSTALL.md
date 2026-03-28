# LoreDocs Installation Guide

**LoreDocs** gives you a searchable, organized, version-tracked knowledge base for your AI projects. Works with Claude Code and Cowork.

---

## Prerequisites

You need **[uv](https://docs.astral.sh/uv/getting-started/installation/)** -- a fast Python package manager that handles everything for you.

**Install uv (one time):**
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

> **Windows users:** See [uv installation docs](https://docs.astral.sh/uv/getting-started/installation/) for the PowerShell installer.

---

## Option A: Install as a Cowork Plugin (Coming Soon)

> **Note:** The Cowork plugin marketplace is not yet live. This option will be available when the marketplace launches. Use Option C (developer install) in the meantime.

Once the marketplace is live, install with:

```
/plugin install loredocs@labyrinth-analytics-claude-plugins
```

---

## Option B: Install as a Claude Code MCP Server (Coming Soon)

> **Note:** LoreDocs has not yet been published to PyPI, so `uvx loredocs` will not work yet. Use Option C (developer install) in the meantime.

Once published, you will be able to add LoreDocs with:

```bash
claude mcp add loredocs -- uvx loredocs
```

Or add it manually to `~/.claude/settings.json`:

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

## Option C: Developer Install (Build from Source)

If you want to modify LoreDocs or contribute:

```bash
git clone https://github.com/labyrinth-analytics/loredocs.git
cd loredocs
uv venv
uv pip install -e .
```

Then add to Claude Code using the venv Python:

```bash
claude mcp add loredocs -- /path/to/loredocs/.venv/bin/python -m loredocs.server
```

Or in `~/.claude/settings.json`:

```json
{
  "mcpServers": {
    "loredocs": {
      "command": "/path/to/loredocs/.venv/bin/python",
      "args": ["-m", "loredocs.server"]
    }
  }
}
```

---

## Quick Start: Your First Vault

Once connected, try these commands in a Claude conversation:

**Create a vault:**
> "Create a new vault called 'Tax Reference 2025' with tags tax and 2025"

**Add a document:**
> "Add a document to the Tax Reference 2025 vault called 'Depreciation Schedule' with this content: [paste your text]"

**Search your vault:**
> "Search my vaults for 'depreciation'"

**Import files from a folder:**
> "Import all files from /Users/you/Documents/tax-docs into the Tax Reference 2025 vault"

**Tag documents:**
> "Tag the depreciation schedule document with 'schedule-e' and 'rental-property'"

---

## Where Are My Files Stored?

LoreDocs stores everything locally on your computer at:

```
~/.loredocs/
    loredocs.db         (search index and metadata)
    vaults/
        {vault-id}/
            docs/
                {doc-id}/
                    current.md          (your document)
                    extracted.txt       (text extracted for search)
                    metadata.json       (tags, category, notes)
                    history/            (previous versions)
```

Your documents are plain files on disk. You can back them up with any backup tool, version control them with git, open and edit them with any text editor, or copy the entire `~/.loredocs/` folder to another computer.

---

## Troubleshooting

### "uvx: command not found"

uv isn't installed or isn't in your PATH. Re-run the installer:
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```
Then restart your terminal.

### "No matching distribution found for loredocs"

The package hasn't been published to PyPI yet. Use the developer install (Option C) instead, or install the `.plugin` file directly if you have access to the monorepo.

### "Permission denied" during install

Use a virtual environment:
```bash
uv venv
uv pip install -e .
```

### PDF/DOCX files aren't searchable

Make sure the extraction libraries are installed. They should come automatically, but if not:
```bash
uv pip install pdfplumber python-docx openpyxl python-pptx
```

Text extraction works on files that contain actual text, not images of text (scanned PDFs).

### I want to start fresh

Delete the LoreDocs data directory:
```bash
rm -rf ~/.loredocs
```
The next time you use LoreDocs, it will create a new empty database.

---

## Uninstalling

**If installed via uvx:** No uninstall needed -- uvx runs tools ephemerally.

**If installed via pip:**
```bash
pip uninstall loredocs
```

**Remove from Claude Code:**
```bash
claude mcp remove loredocs
```

**Optionally, delete your data:**
```bash
rm -rf ~/.loredocs
```

---

## MCP Tools Reference (34 total)

**Vault management (6)**

| Tool | What it does |
|---|---|
| `vault_create` | Create a new named vault for a project |
| `vault_list` | List all vaults (optionally include archived) |
| `vault_info` | Get vault details and stats |
| `vault_archive` | Archive a vault (soft delete, reversible) |
| `vault_delete` | Permanently delete a vault and its documents |
| `vault_link_project` | Link a vault to a Claude Project name |

**Document operations (10)**

| Tool | What it does |
|---|---|
| `vault_add_doc` | Add a document to a vault (extracts text automatically) |
| `vault_get_doc` | Retrieve a specific document with content |
| `vault_list_docs` | List documents in a vault (sort, filter, paginate) |
| `vault_update_doc` | Update document content or metadata (auto-versions) |
| `vault_remove_doc` | Remove a document from the vault |
| `vault_copy_doc` | Copy a document to another vault |
| `vault_move_doc` | Move a document to another vault |
| `vault_link_doc` | Link two related documents with a label |
| `vault_unlink_doc` | Remove a link between documents |
| `vault_find_related` | Find documents related to a given doc |

**Search and context injection (6)**

| Tool | What it does |
|---|---|
| `vault_search` | Full-text search across all vaults or a specific one |
| `vault_search_by_tag` | Find all documents with a given tag |
| `vault_inject` | Inject specific documents into the conversation by ID |
| `vault_inject_by_tag` | Inject all documents matching a tag |
| `vault_inject_summary` | Generate a context summary for Claude to load at session start |
| `vault_suggest` | Proactive suggestions on what context might be relevant |

**Tagging and organization (6)**

| Tool | What it does |
|---|---|
| `vault_tag_doc` | Add or remove tags on a document |
| `vault_bulk_tag` | Add or remove tags on multiple documents at once |
| `vault_categorize` | Set a document's category |
| `vault_set_priority` | Set a document's priority/status |
| `vault_add_note` | Attach a note to a document |
| `vault_doc_history` | See version history for a document |

**Versioning and bulk operations (4)**

| Tool | What it does |
|---|---|
| `vault_doc_restore` | Restore a previous version of a document |
| `vault_import_dir` | Import all files from a directory into a vault |
| `vault_export` | Export a vault's documents to a directory |
| `vault_export_manifest` | Export a vault manifest for sharing or versioning |

**Tier management (2)**

| Tool | What it does |
|---|---|
| `vault_tier_status` | Check your current tier and usage limits |
| `vault_set_tier` | Upgrade or change your tier (free/pro) |

---

## Supported Platforms

| Platform | Support | Notes |
|---|---|---|
| **Claude Code** | Full | All 34 MCP tools available |
| **Cowork** | Full | Use vault_inject_summary at session start for automatic context |
| **Chat (web)** | Partial | Use vault_export_manifest and paste output into Chat |

---

## Companion Product

**[LoreConvo](https://github.com/labyrinth-analytics/loreconvo)** -- Cross-surface persistent memory for Claude sessions. Where LoreDocs stores *documents*, LoreConvo remembers *conversations* -- decisions made, artifacts created, questions left open. They complement each other well.
