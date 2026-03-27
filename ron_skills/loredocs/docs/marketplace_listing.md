# LoreDocs -- Marketplace Listing Draft

> STATUS: DRAFT -- Debbie must review and approve before publishing to any marketplace.

---

## Listing Metadata

| Field | Value |
|---|---|
| Plugin Name | LoreDocs |
| Tagline | Your AI project's second brain. Search, organize, and inject knowledge -- in any Claude session. |
| Category | Knowledge Management / Productivity |
| Version | 0.1.0 |
| Author | Labyrinth Analytics Consulting |
| Support email | info@labyrinthanalyticsconsulting.com |
| License | MIT (core plugin) / Pro features require subscription |
| Platforms | Claude Code, Cowork |

---

## Short Description (150 chars max)

A searchable, versioned knowledge base for your AI projects. Organize docs, tag them, and inject them into any Claude session on demand.

---

## Long Description

### Your Project Knowledge Is a Mess. LoreDocs Fixes That.

You've got specs in one folder, reference docs in another, config files scattered everywhere, and half your project's decisions living only in your head (or buried in old chat logs). Every new Claude session starts from scratch -- you re-paste the same documents, re-explain the same constraints, re-orient Claude to your project all over again.

**LoreDocs is a structured knowledge base designed for AI projects.** It's the missing file manager for Claude -- create named vaults, add and tag your documents, search across everything, and inject exactly the right context into any Claude session with a single command.

---

### How It Works

1. **Organize** -- Create a vault for each project. Add your docs, specs, configs, and reference files. Tag them, categorize them, mark the authoritative ones.
2. **Search** -- Full-text search across all your vaults in under a second. Find the depreciation schedule. Find the API spec. Find that decision you made six months ago.
3. **Inject** -- Tell Claude which vault (or which tags) to load, and your documents land directly in the conversation context. No copy-paste. No re-upload.
4. **Version** -- Every update auto-saves the previous version. Restore any prior version instantly. Never lose a document again.

---

### Key Features

**Named vaults**
Organize knowledge by project, client, or domain. Each vault is independent -- its own search index, its own tags, its own document set. Vault for tax prep, vault for rental properties, vault for consulting engagements.

**Full-text search**
SQLite FTS5 powers sub-second search across all document contents. Not just filenames -- actual text. Find the right document even when you've forgotten what it's called.

**Rich metadata**
Tag documents, assign categories (reference, config, report, template, archive), and set priority levels (authoritative, normal, draft, outdated). Add contextual notes: "Use this for 2025 tax prep only" or "Superseded by the March 2026 revision."

**Version history**
Every `vault_update_doc` call auto-saves the previous version. View the full history, compare versions, and restore any prior state. Up to 5 versions in Free tier, unlimited in Pro.

**Context injection**
The `vault_inject` and `vault_inject_by_tag` tools load document contents directly into your Claude conversation. Ask Claude to inject everything tagged "tax-2025" and it arrives in seconds, ready for use.

**Proactive suggestions**
The `vault_suggest` tool analyzes the current conversation and recommends vault documents that are likely relevant -- without you needing to know what to ask for.

**Bulk import**
Point `vault_import_dir` at a folder and it imports everything -- PDFs, Word docs, Excel files, markdown, plain text. Text is extracted automatically for search.

**Cross-vault search**
`vault_search_all` searches across every vault at once. Find any document you've ever stored, regardless of which project it belongs to.

**Document relationships**
Link related documents with `vault_find_related`. Useful for understanding what else is affected when you update a key reference file.

**Local-first, zero cloud cost**
All data lives on your machine in a SQLite database and plain files. Nothing is sent to a server. Works fully offline. Easy to back up, version-control, or move to another machine.

---

## MCP Tools (34 total)

### Vault Management (5 tools)

| Tool | Description |
|---|---|
| `vault_create` | Create a new knowledge vault |
| `vault_list` | List all vaults with summary stats |
| `vault_info` | Detailed vault info with document manifest |
| `vault_archive` | Soft-delete a vault (hidden, recoverable) |
| `vault_delete` | Permanently delete a vault and all its documents |

### Document Management (8 tools)

| Tool | Description |
|---|---|
| `vault_add_doc` | Add a document with tags, category, and notes |
| `vault_update_doc` | Update a document (auto-versions previous content) |
| `vault_remove_doc` | Soft-delete a document |
| `vault_get_doc` | Read a document and its metadata |
| `vault_list_docs` | List documents with sort and filter |
| `vault_copy_doc` | Copy a document to another vault |
| `vault_move_doc` | Move a document to another vault |
| `vault_doc_history` | View version history for a document |

### Search & Discovery (4 tools)

| Tool | Description |
|---|---|
| `vault_search` | Full-text search within a vault |
| `vault_search_all` | Full-text search across ALL vaults |
| `vault_search_by_tag` | Find documents by tag across vaults |
| `vault_find_related` | Find documents related to a given document |

### Organization & Metadata (6 tools)

| Tool | Description |
|---|---|
| `vault_tag_doc` | Add or remove tags on a document |
| `vault_bulk_tag` | Tag multiple documents at once |
| `vault_categorize` | Set a document's category |
| `vault_set_priority` | Mark as authoritative / draft / outdated |
| `vault_add_note` | Attach a contextual note to a document |
| `vault_doc_restore` | Restore a previous version |

### Context Injection (4 tools)

| Tool | Description |
|---|---|
| `vault_inject` | Load specific documents into conversation |
| `vault_inject_by_tag` | Load all documents matching a tag |
| `vault_inject_summary` | Inject a vault overview for orientation |
| `vault_suggest` | Get proactive document suggestions for the current topic |

### Bulk Operations (2 tools)

| Tool | Description |
|---|---|
| `vault_import_dir` | Bulk import files from a folder (PDF, DOCX, XLSX, PPTX, TXT, MD) |
| `vault_export` | Export vault files to a local folder |

### Vault Links & Tier Management (3 tools)

| Tool | Description |
|---|---|
| `vault_link_project` | Associate a vault with a Claude Project name |
| `vault_tier_status` | Check current tier and usage vs. limits |
| `vault_set_tier` | Activate Pro tier with your license key |

---

## Pricing Tiers

> Note to Debbie: Pricing below matches the revenue model in CLAUDE.md.
> Adjust before publishing.

| Feature | Free | Pro ($9/mo) | Team ($20/mo) |
|---|---|---|---|
| Vaults | 3 | Unlimited | Unlimited |
| Documents per vault | 50 | Unlimited | Unlimited |
| Total storage | 500 MB | Unlimited | Unlimited |
| Version history per doc | 5 versions | Unlimited | Unlimited |
| Full-text search | Yes | Yes | Yes |
| Tags, categories, notes | Yes | Yes | Yes |
| Context injection | Yes | Yes | Yes |
| vault_suggest | Yes | Yes | Yes |
| Bulk import (PDF, DOCX, etc.) | Yes | Yes | Yes |
| Cross-vault search | Yes | Yes | Yes |
| vault_find_related | Yes | Yes | Yes |
| Cloud sync (coming) | No | No | Yes |
| Shared team vaults (coming) | No | No | Yes |
| Priority support | No | No | Yes |

---

## Installation

### Prerequisites

Python 3.10 or higher. Check with:
```bash
python3 --version
```

### Install

```bash
git clone https://github.com/labyrinth-analytics/side_hustle.git
cd side_hustle/ron_skills/loredocs
pip install -e .
```

### Add to Claude Code

```bash
claude mcp add loredocs -- python -m loredocs.server
```

### Add to Cowork

Add to `~/.claude/settings.json`:

```json
{
  "mcpServers": {
    "loredocs": {
      "command": "python",
      "args": ["-m", "loredocs.server"]
    }
  }
}
```

Restart Cowork. Full installation walkthrough is in `INSTALL.md`.

---

## Quick Start

Once connected, try these in a Claude conversation:

**Create a vault and add a doc:**
> "Create a vault called 'Tax Reference 2025' and add a document called 'Depreciation Schedule' with these contents: [paste text]"

**Search your knowledge:**
> "Search my Tax Reference 2025 vault for 'straight-line depreciation'"

**Inject context at session start:**
> "Inject everything tagged 'tax-2025' from my vault into our conversation"

**Get proactive suggestions:**
> "Which vault documents are relevant to what we're working on right now?"

---

## Where Is My Data?

Everything is stored locally at:

```
~/.loredocs/
    loredocs.db          (search index and metadata)
    config.json              (tier setting)
    vaults/
        {vault-id}/
            docs/
                {doc-id}/
                    current.md       (document content)
                    extracted.txt    (text extracted for search)
                    metadata.json    (tags, category, notes)
                    history/         (previous versions)
```

Your documents are plain files. Back them up with any tool. Version-control them with git. Move the entire `~/.loredocs/` folder to another computer and everything works.

---

## Companion Product: LoreConvo

LoreDocs remembers your *project documents*. **LoreConvo** remembers your *conversations*.

If you work on ongoing projects across multiple Claude sessions, consider pairing LoreDocs with LoreConvo. LoreConvo captures decisions, artifacts, and open questions from each session and surfaces them automatically at the start of the next one. The two products share a local-first philosophy and complement each other naturally.

- LoreDocs = "what does my project documentation say?"
- LoreConvo = "what did we decide last session?"

---

## Frequently Asked Questions

**Is my data private?**
Yes. LoreDocs stores everything locally in SQLite and plain files on your machine. Nothing is ever sent to any server. Labyrinth Analytics never sees your documents.

**What file types can I import?**
PDF, DOCX (Word), XLSX (Excel), PPTX (PowerPoint), TXT, and Markdown. Text is extracted automatically for full-text search. Image-only (scanned) PDFs are stored but not searchable.

**How is this different from Claude Projects' built-in knowledge base?**
Claude Projects lets you upload files, but there's no search, no tagging, no version history, no bulk operations, and no cross-project visibility. LoreDocs adds all of that, and works across Code and Cowork -- not just in a single Project.

**Does it work with Claude Chat (web)?**
Not yet -- Chat does not support plugins. Claude Code and Cowork are the primary platforms. Chat support is on the roadmap.

**What happens if I uninstall it?**
Your database and files stay at `~/.loredocs/`. Reinstall anytime and your full history is there.

**Can I have separate vaults for separate clients or projects?**
Yes. Each vault is independent. Create as many as you like (up to 3 on Free, unlimited on Pro).

**What is LoreConvo and do I need it?**
LoreConvo is a companion product for persistent conversation memory. It's independent -- use either or both. See the Companion Product section above.

---

## Support

- GitHub Issues: [github link TBD]
- Email: info@labyrinthanalyticsconsulting.com
- Installation guide: `INSTALL.md` in the plugin directory
- Product spec: `docs/LoreDocs_Product_Spec.md`

---

## Changelog

| Version | Date | Notes |
|---|---|---|
| 0.1.0 | 2026-03-22 | Initial release: 34 MCP tools, SQLite+FTS5, tier gating, Cowork plugin packaging |
