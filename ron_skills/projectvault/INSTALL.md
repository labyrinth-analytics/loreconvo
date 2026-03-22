# ProjectVault Installation Guide

**ProjectVault** gives you a searchable, organized, version-tracked knowledge base for your AI projects. Works with Claude Code and Cowork.

---

## Prerequisites

You need **Python 3.10 or higher** installed on your computer.

**Check if you have Python:**
Open a terminal (or Command Prompt on Windows) and type:
```
python3 --version
```
You should see something like `Python 3.12.4`. If you get an error, install Python from [python.org/downloads](https://www.python.org/downloads/).

---

## Step 1: Download ProjectVault

**Option A: Clone from GitHub (recommended)**
```bash
git clone https://github.com/your-org/projectvault.git
cd projectvault
```

**Option B: Download the ZIP file**
Download and unzip the project, then open a terminal in that folder.

---

## Step 2: Install ProjectVault

Run this single command in the `projectvault` folder:

```bash
pip install -e .
```

> **Windows users:** If you get a permissions error, try `pip install -e . --user`
>
> **Mac/Linux users:** If you get a permissions error, try `pip install -e . --break-system-packages` or use a virtual environment (see Troubleshooting below).

This installs ProjectVault and all its dependencies (PDF reader, Word doc reader, etc.).

**Verify it installed correctly:**
```bash
projectvault --help
```
You should see output about the MCP server starting. Press Ctrl+C to stop it.

---

## Step 3: Connect to Claude Code

Add ProjectVault to your Claude Code configuration. Open your terminal and run:

```bash
claude mcp add projectvault -- python -m projectvault.server
```

That's it! ProjectVault is now available in all your Claude Code conversations.

**Verify it's connected:**
```bash
claude mcp list
```
You should see `projectvault` in the list.

---

## Step 4: Connect to Cowork (Optional)

If you use Claude's Cowork mode, add ProjectVault there too.

1. Open your Claude Code settings file. You can find it at:
   - **Mac/Linux:** `~/.claude/settings.json`
   - **Windows:** `%USERPROFILE%\.claude\settings.json`

2. Add ProjectVault to the `mcpServers` section:

```json
{
  "mcpServers": {
    "projectvault": {
      "command": "python",
      "args": ["-m", "projectvault.server"]
    }
  }
}
```

3. Restart Claude/Cowork.

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

Your documents are plain files on disk. You can:
- Back them up with any backup tool
- Version control them with git
- Open and edit them with any text editor
- Copy the entire `~/.projectvault/` folder to another computer

---

## Troubleshooting

### "command not found: projectvault"

The install didn't put the command in your PATH. Try running ProjectVault directly:
```bash
python -m projectvault.server
```

And use this longer form when adding to Claude Code:
```bash
claude mcp add projectvault -- python -m projectvault.server
```

### "Permission denied" during install

**Option 1: Use --user flag:**
```bash
pip install -e . --user
```

**Option 2: Use a virtual environment:**
```bash
python3 -m venv .venv
source .venv/bin/activate       # Mac/Linux
.venv\Scripts\activate          # Windows
pip install -e .
```

If using a virtual environment, update the Claude Code MCP command to use the venv Python:
```bash
claude mcp add projectvault -- /path/to/projectvault/.venv/bin/python -m projectvault.server
```

### "No module named pdfplumber" (or similar)

A dependency didn't install. Re-run:
```bash
pip install -e .
```

Or install the missing package directly:
```bash
pip install pdfplumber python-docx openpyxl python-pptx
```

### PDF/DOCX files aren't searchable

Make sure the extraction libraries are installed:
```bash
pip install pdfplumber python-docx openpyxl python-pptx
```

If a specific file still doesn't extract, the file may be image-only (scanned PDF) or password-protected. Text extraction works on files that contain actual text, not images of text.

### I want to start fresh

Delete the ProjectVault data directory:
```bash
rm -rf ~/.projectvault
```

The next time you use ProjectVault, it will create a new empty database.

---

## Uninstalling

```bash
pip uninstall projectvault
```

Optionally, delete your data:
```bash
rm -rf ~/.projectvault
```

And remove from Claude Code:
```bash
claude mcp remove projectvault
```

---

## Available Tools (32 total)

| Tool | What It Does |
|------|-------------|
| `vault_create` | Create a new knowledge vault |
| `vault_list` | List all your vaults |
| `vault_info` | Get details about a vault and its documents |
| `vault_archive` | Hide a vault (soft delete) |
| `vault_delete` | Permanently delete a vault |
| `vault_link_project` | Associate a vault with a Claude Project |
| `vault_add_doc` | Add a text document to a vault |
| `vault_update_doc` | Update a document (auto-saves previous version) |
| `vault_remove_doc` | Remove a document (soft delete) |
| `vault_get_doc` | Read a document's content and metadata |
| `vault_list_docs` | List documents with sort and filter |
| `vault_search` | Full-text search across documents |
| `vault_search_by_tag` | Find documents by tag |
| `vault_tag_doc` | Add/remove tags on a document |
| `vault_bulk_tag` | Tag multiple documents at once |
| `vault_categorize` | Set a document's category |
| `vault_set_priority` | Mark as authoritative/normal/draft/outdated |
| `vault_add_note` | Attach a note to a document |
| `vault_doc_history` | View version history |
| `vault_doc_restore` | Restore a previous version |
| `vault_copy_doc` | Copy a document to another vault |
| `vault_move_doc` | Move a document to another vault |
| `vault_inject` | Load documents into conversation |
| `vault_inject_by_tag` | Load all documents with a tag |
| `vault_inject_summary` | Get a vault overview |
| `vault_import_dir` | Bulk import files from a folder |
| `vault_export` | Export vault files to a folder |
