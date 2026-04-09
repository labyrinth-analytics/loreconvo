# LoreDocs

Your AI project's knowledge base. Organized, searchable, version-tracked.

LoreDocs gives Claude persistent access to your project documentation -- specs, guides, architecture decisions, reference docs -- so it never loses context between sessions. Works with Claude Code and Cowork.

## Quick Start

**Prerequisites:** [uv](https://docs.astral.sh/uv/getting-started/installation/) (fast Python package manager).

```bash
# Install uv (one time)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone and install
cd /path/to/loredocs
uv sync
```

For detailed installation instructions (including Cowork plugin setup), see [INSTALL.md](INSTALL.md).

## Using LoreDocs

### Claude Code (Terminal)

```bash
claude --plugin-dir /path/to/loredocs
```

Or inside an existing session:

```
/plugin add /path/to/loredocs
```

Once loaded, Claude has access to all 35 LoreDocs MCP tools automatically. Ask Claude to "create a vault for this project" or "find the architecture doc" and it uses the tools on its own.

### Cowork (Desktop App)

1. Click **+** next to the prompt box
2. Select **Plugins** > **Add plugin**
3. Browse to the `loredocs` source folder

**Shared Database Access:** Cowork runs in a sandboxed VM. To access docs saved from Claude Code, ask Claude:

> "Mount my ~/.loredocs folder"

## How It Works

LoreDocs organizes knowledge into **vaults** -- named containers for related documents. Each vault can hold specs, guides, decisions, checklists, or any text you want Claude to remember.

```
~/.loredocs/loredocs.db          <-- SQLite database (metadata, search index)
~/.loredocs/vaults/<vault-id>/   <-- Document files on disk
```

**Key concepts:**

- **Vaults** group related docs by project or topic
- **Documents** are text files with metadata (tags, categories, priority, notes)
- **Version history** tracks every change to every document
- **Full-text search** via SQLite FTS5 finds anything instantly
- **Injection** loads vault content into Claude's context on demand

## Verify Installation

After installing, verify LoreDocs is working by asking Claude:

> "Run `vault_list` and show me the results."

If you see a list of vaults (or an empty list if this is your first time), LoreDocs is connected. If you get an error about missing tools, re-run `uv sync` and reload the plugin.

## Recommended CLAUDE.md Setup

For the best experience, add the following snippet to your `~/.claude/CLAUDE.md` (global) or your project's `CLAUDE.md`. This tells Claude how to use LoreDocs consistently across sessions.

```markdown
## LoreDocs (persistent project knowledge)

At session start:
1. Call `vault_list` to see available knowledge vaults.
2. Call `vault_inject_summary` for any vaults relevant to the current project.
3. Use this context to understand project architecture, decisions, and reference docs.

During the session:
- If you create significant documentation, add it to LoreDocs with `vault_add_doc`.
- Tag documents for easy cross-vault discovery with `vault_tag_doc`.

At session end:
- If new docs were created or updated, ensure they are stored in LoreDocs for future sessions.
```

**For Cowork users:** Cowork does not run hooks automatically. Add instructions to call `vault_list` and `vault_inject_summary` at session start in your project CLAUDE.md.

## Features

- **Vault organization**: Group docs by project with linked project metadata
- **Document versioning**: Full history with rollback to any prior version
- **Tagging and categorization**: Tag docs for cross-vault discovery
- **Priority levels**: Mark docs as critical, high, normal, or low priority
- **Full-text search**: Fast keyword search across all vaults and documents
- **Context injection**: Load specific docs, tags, or vault summaries into Claude's context
- **Bulk operations**: Import directories, bulk-tag, export manifests
- **Document linking**: Connect related docs across vaults
- **Tier management**: Free/Pro/Team tiers with configurable limits
- **Local-first**: SQLite database, no cloud dependency, zero API costs

## MCP Tools

LoreDocs provides 35 MCP tools organized by function:

### Vault Management (6 tools)
| Tool | What it does |
|------|-------------|
| `vault_create` | Create a new vault with name and description |
| `vault_list` | List all vaults with doc counts and sizes |
| `vault_info` | Get detailed vault information |
| `vault_archive` | Archive a vault (preserves data, hides from listing) |
| `vault_delete` | Permanently delete a vault and all its documents |
| `vault_link_project` | Link a vault to a project directory |

### Document Operations (9 tools)
| Tool | What it does |
|------|-------------|
| `vault_add_doc` | Add a new document to a vault |
| `vault_update_doc` | Update document content (creates version history) |
| `vault_remove_doc` | Remove a document from a vault |
| `vault_get_doc` | Retrieve a document with full content |
| `vault_list_docs` | List documents in a vault with filtering and sorting |
| `vault_copy_doc` | Copy a document to another vault |
| `vault_move_doc` | Move a document to another vault |
| `vault_doc_history` | View version history of a document |
| `vault_doc_restore` | Restore a document to a previous version |

### Search and Discovery (4 tools)
| Tool | What it does |
|------|-------------|
| `vault_search` | Full-text search across all vaults |
| `vault_search_by_tag` | Find documents by tag across all vaults |
| `vault_find_related` | Discover documents related to a given doc |
| `vault_suggest` | Proactive suggestions for relevant docs to load |

### Organization (5 tools)
| Tool | What it does |
|------|-------------|
| `vault_tag_doc` | Add tags to a document |
| `vault_bulk_tag` | Tag multiple documents at once |
| `vault_categorize` | Set document category (spec, guide, decision, etc.) |
| `vault_set_priority` | Set document priority level |
| `vault_add_note` | Add a note or annotation to a document |

### Context Injection (3 tools)
| Tool | What it does |
|------|-------------|
| `vault_inject` | Load specific documents into Claude's context |
| `vault_inject_by_tag` | Load all documents matching a tag |
| `vault_inject_summary` | Load a vault summary with doc titles and descriptions |

### Import/Export (3 tools)
| Tool | What it does |
|------|-------------|
| `vault_import_dir` | Import a directory of files into a vault |
| `vault_export` | Export a document to a file on disk |
| `vault_export_manifest` | Export vault metadata as a JSON manifest |

### Document Links (2 tools)
| Tool | What it does |
|------|-------------|
| `vault_link_doc` | Create a link between two documents |
| `vault_unlink_doc` | Remove a link between documents |

### Administration (3 tools)
| Tool | What it does |
|------|-------------|
| `vault_tier_status` | Check current tier limits and usage |
| `vault_set_tier` | Set the active tier (free, pro, team) |
| `get_license_tier` | Check current tier and license key status |

## Works With LoreConvo

LoreDocs is the knowledge base; [LoreConvo](https://github.com/labyrinth-analytics/loreconvo) is the session memory. Together they give Claude both long-term documentation and conversation history:

- **LoreConvo** remembers what you discussed, decided, and left open
- **LoreDocs** stores the reference docs, specs, and guides Claude needs

Both use local SQLite databases and work across Claude Code and Cowork.

## Requirements

- Python 3.10+
- macOS or Linux
- [uv](https://docs.astral.sh/uv/getting-started/installation/) package manager
- `mcp` and `pydantic` (auto-installed by `uv sync`)

## Data Storage

Documents and metadata are stored locally in SQLite at `~/.loredocs/loredocs.db`. Document files live in `~/.loredocs/vaults/`. Override the database path with the `LOREDOCS_DB` environment variable.

## Troubleshooting

**MCP tools not showing up in Claude Code?**
Make sure you ran `uv sync` first. The virtual environment must exist with dependencies installed.

**"No module named 'mcp'" error?**
The `.mcp.json` points to the virtual environment's Python. If you moved the folder, re-run `uv sync`.

**Cowork can't see docs saved in Code?**
Ask Claude to "mount my ~/.loredocs folder" so Cowork can access the shared database.

## Fallback Script (Direct DB Access)

If the MCP server is unreachable (e.g., in scheduled tasks or automation scripts), `scripts/query_loredocs.py` provides the same core operations directly against the SQLite database.

```bash
# List all vaults
python scripts/query_loredocs.py --list

# Show vault details and document manifest
python scripts/query_loredocs.py --info "My Project Docs"

# Search documents across all vaults
python scripts/query_loredocs.py --search "architecture"

# Add a document to a vault
python scripts/query_loredocs.py --add-doc \
    --vault "My Project Docs" \
    --name "Architecture Overview" \
    --file docs/architecture.md \
    --tags '["architecture", "design"]'

# Add a document from stdin
echo "# Quick Note" | python scripts/query_loredocs.py --add-doc \
    --vault "My Project Docs" \
    --name "Quick Note" \
    --stdin
```

The script auto-discovers the database at `~/.loredocs/loredocs.db` (or pass `--db-path` explicitly). It writes the same schema as the MCP tools, including FTS indexing and on-disk file storage.

## License

Business Source License 1.1 (BSL 1.1) - Labyrinth Analytics Consulting

Free for personal/non-commercial use (up to 3 vaults). Commercial use requires
a paid license. Converts to Apache 2.0 on 2030-03-31. See [LICENSE](LICENSE) for details.
