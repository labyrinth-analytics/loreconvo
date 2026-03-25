# ProjectVault Installation Guide

**ProjectVault** gives you a searchable, organized, version-tracked knowledge base for your AI projects. Works with Claude Code and Cowork.

---

## Prerequisites

You need **[uv](https://docs.astral.sh/uv/getting-started/installation/)** -- a fast Python package manager that handles everything for you.

**Install uv (one time):**
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

> **Windows users:** See [uv installation docs](https://docs.astral.sh/uv/getting-started/installation/) for the PowerShell installer.

---

## Option A: Install as a Cowork Plugin (Recommended)

If you use Claude's Cowork mode, install the plugin directly:

```bash
/plugin install projectvault@labyrinth-analytics-claude-plugins
```

That's it -- restart Cowork and ProjectVault is available.

---

## Option B: Install as a Claude Code MCP Server

Add ProjectVault to your Claude Code configuration:

```bash
claude mcp add projectvault -- uvx projectvault
```

**Verify it's connected:**
```bash
claude mcp list
```
You should see `projectvault` in the list.

Or add it manually to `~/.claude/settings.json`:

```json
{
  "mcpServers": {
    "projectvault": {
      "command": "uvx",
      "args": ["projectvault"]
    }
  }
}
```

Restart Claude Code after editing the file.

---

## Option C: Developer Install (Build from Source)

If you want to modify ProjectVault or contribute:

```bash
git clone https://github.com/labyrinth-analytics/projectvault.git
cd projectvault
uv venv
uv pip install -e .
```

Then add to Claude Code using the venv Python:

```bash
claude mcp add projectvault -- /path/to/projectvault/.venv/bin/python -m projectvault.server
```

Or in `~/.claude/settings.json`:

```json
{
  "mcpServers": {
    "projectvault": {
      "command": "/path/to/projectvault/.venv/bin/python",
      "args": ["-m", "projectvault.server"]
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

ProjectVault stores everything locally on your computer at:

```
~/.projectvault/
    projectvault.db         (search index and metadata)
    vaults/
        {vault-id}/
            docs/
                {doc-id}/
                    current.md          (your document)
                    extracted.txt       (text extracted for search)
                    metadata.json       (tags, category, notes)
                    history/            (previous versions)
```

Your documents are plain files on disk. You can back them up with any backup tool, version control them with git, open and edit them with any text editor, or copy the entire `~/.projectvault/` folder to another computer.

---

## Troubleshooting

### "uvx: command not found"

uv isn't installed or isn't in your PATH. Re-run the installer:
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```
Then restart your terminal.

### "No matching distribution found for projectvault"

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

Delete the ProjectVault data directory:
```bash
rm -rf ~/.projectvault
```
The next time you use ProjectVault, it will create a new empty database.

---

## Uninstalling

**If installed via uvx:** No uninstall needed -- uvx runs tools ephemerally.

**If installed via pip:**
```bash
pip uninstall projectvault
```

**Remove from Claude Code:**
```bash
claude mcp remove projectvault
```

**Optionally, delete your data:**
```bash
rm -rf ~/.projectvault
```

---

## MCP Tools Reference (32 total)

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
| **Claude Code** | Full | All 32 MCP tools available |
| **Cowork** | Full | Use vault_inject_summary at session start for automatic context |
| **Chat (web)** | Partial | Use vault_export_manifest and paste output into Chat |

---

## Companion Product

**[ConvoVault](https://github.com/labyrinth-analytics/convovault)** -- Cross-surface persistent memory for Claude sessions. Where ProjectVault stores *documents*, ConvoVault remembers *conversations* -- decisions made, artifacts created, questions left open. They complement each other well.
