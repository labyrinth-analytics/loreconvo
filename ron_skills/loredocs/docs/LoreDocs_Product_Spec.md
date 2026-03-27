# LoreDocs - Product Specification

## The Problem

Claude Projects' knowledge base is a powerful feature — upload files once, use them across all conversations in that project. But as projects grow, managing that knowledge becomes painful:

- **No search** — Can't find which file contains the depreciation schedule vs. the rental income breakdown
- **No organization** — Files are a flat list with no folders, tags, or categories
- **No versioning** — Update a file and the old version is gone forever
- **No bulk operations** — Adding 15 files means 15 individual uploads
- **No cross-project visibility** — Can't search across all your projects for "Schedule E"
- **No metadata** — No way to annotate files with context ("this is authoritative for tax prep", "outdated after March 2026")
- **No dependency tracking** — No way to know which files reference or depend on each other

The underlying API (Files API) exists for programmatic file management, but there's **no tool that provides a proper knowledge management layer** on top of it.

## The Opportunity

The "Knowledge & Memory" category is the largest MCP category with 283+ servers, but virtually all of them focus on **memory** (entity graphs, conversation history, key-value stores). Almost none address **structured document/artifact management** — the "file manager for AI projects" gap.

LoreDocs fills this gap.

## Product Vision

LoreDocs is an MCP server + Cowork plugin that gives Claude users a proper knowledge management system for their AI projects. Think of it as **"Git + file manager + search engine" for AI project knowledge**.

---

## Core Features

### 1. Vault Management
Create and manage multiple knowledge vaults (analogous to projects, but better organized).

- `vault_create` — Create a new vault with name, description, tags
- `vault_list` — List all vaults with summary stats (file count, total size, last modified)
- `vault_info` — Get detailed vault info including file manifest
- `vault_archive` / `vault_delete` — Lifecycle management

### 2. Document Management
Full CRUD for documents within a vault, with rich metadata.

- `vault_add_doc` — Add a document with metadata (tags, category, priority, notes)
- `vault_update_doc` — Update document content (auto-versions the previous copy)
- `vault_remove_doc` — Remove a document (soft delete with recovery option)
- `vault_get_doc` — Retrieve a specific document by name or ID
- `vault_list_docs` — List documents with sorting (name, date, size, category, tag) and filtering

### 3. Search & Discovery
The killer feature — find anything across all your vaults.

- `vault_search` — Full-text search across document contents within a vault
- `vault_search_all` — Search across ALL vaults
- `vault_find_related` — Find documents related to a given document (by content similarity or shared tags)
- `vault_search_by_tag` — Filter documents by tags across vaults

### 4. Organization & Metadata
Bring structure to the chaos.

- `vault_tag_doc` — Add/remove tags on documents
- `vault_categorize` — Assign categories (reference, config, report, template, etc.)
- `vault_set_priority` — Mark documents as authoritative, outdated, draft, etc.
- `vault_add_note` — Attach contextual notes to documents ("Use this for 2025 tax prep only")
- `vault_bulk_tag` — Tag multiple documents at once

### 5. Version History
Never lose a previous version of an important document.

- `vault_doc_history` — View version history for a document
- `vault_doc_diff` — Compare two versions of a document
- `vault_doc_restore` — Restore a previous version
- Auto-versioning on every update (configurable retention)

### 6. Context Injection
The bridge between vault and conversation.

- `vault_inject` — Load specific documents into the current conversation context
- `vault_inject_by_tag` — Load all documents matching a tag (e.g., "inject everything tagged 'tax-2025'")
- `vault_inject_summary` — Generate and inject a summary of vault contents for orientation
- `vault_suggest` — Based on the current conversation, suggest which vault documents might be relevant

### 7. Cross-Vault Operations
Move, copy, and share documents between vaults.

- `vault_copy_doc` — Copy a document from one vault to another (with metadata)
- `vault_move_doc` — Move a document between vaults (removes from source)
- `vault_link_doc` — Create a reference/symlink so the same doc appears in multiple vaults without duplication
- `vault_unlink_doc` — Remove a cross-vault reference
- `vault_link_project` — Associate a vault with one or more Claude Project names (optional metadata for organization)

### 8. Import/Export
Get data in and out easily.

- `vault_import_dir` — Bulk import from a local directory
- `vault_export` — Export vault contents to a local directory
- `vault_export_manifest` — Export a JSON manifest of vault structure and metadata

---

## Architecture

### Storage Layer
```
~/.loredocs/
    config.json              # Global config (default vault, preferences)
    loredocs.db          # SQLite database (FTS5 index, metadata, links)
    vaults/
        {vault-id}/
            manifest.json    # Vault metadata, linked_projects[], document index
            docs/
                {doc-id}/
                    current.md       # Current version
                    metadata.json    # Tags, category, notes, priority, linked_projects
                    history/
                        v1.md
                        v2.md
                        ...
            links/
                {link-id}.json   # Cross-vault document references (symlinks)
```

### Vault-Project Relationship
Vaults are **independent of Claude Projects** by design. A vault can be linked to zero, one, or many Claude Projects via an optional `linked_projects` field. This means:
- A "Tax Reference 2025" vault can serve both your "Tax Prep" and "Property Accounting" Claude Projects
- A "Rental Properties" vault can be injected into any conversation regardless of project
- Users can organize by domain (tax, rental, consulting) rather than by Claude Project boundaries
- If Anthropic later exposes a Projects API, syncing becomes a natural Pro feature

### Technology Stack
- **Language:** Python (FastMCP) — aligns with Debbie's stack and Cowork plugin compatibility
- **Storage:** Local filesystem + SQLite for search indexing (FTS5)
- **Transport:** stdio (works in both Claude Code and Cowork)
- **Search:** SQLite FTS5 for full-text search, plus tag/metadata filtering
- **Versioning:** File-based version history with configurable retention

### Why This Stack
- **SQLite FTS5** — Zero-dependency full-text search that's fast, reliable, and requires no external services
- **Filesystem storage** — Documents are plain files you can inspect, back up, and version control with git
- **Python/FastMCP** — Fastest path to both MCP server and Cowork plugin
- **stdio transport** — Works everywhere, no server to run

---

## Differentiation from Existing Tools

| Feature | Claude Projects | Memory MCP Servers | LoreDocs |
|---|---|---|---|
| Document storage | Yes (cloud) | No (entity graphs) | Yes (local) |
| Full-text search | No | No | Yes (FTS5) |
| Tags & categories | No | No | Yes |
| Version history | No | No | Yes |
| Cross-project search | No | N/A | Yes |
| Bulk operations | No | No | Yes |
| Metadata/annotations | No | Limited | Rich |
| Context injection | Automatic | N/A | On-demand + smart suggestions |
| Works offline | No | Varies | Yes |
| User owns data | No (cloud) | Varies | Yes (local files) |

---

## Monetization Strategy

### Free Tier
- 3 vaults, 50 documents per vault, 500MB total storage
- Full-text search within single vault
- Basic tagging and categories
- Version history (last 5 versions)
- All file formats supported (PDF, DOCX, XLSX, CSV, TXT, MD, HTML, PPTX, images, audio)

### Pro Tier — $9/month (via Salable)
- Unlimited vaults and documents, 10GB total storage
- Cross-vault search (FTS5 + semantic search in Year 2)
- Unlimited version history
- Smart suggestions (vault_suggest)
- Claude Projects sync (when API available)
- Export/import tools
- Priority support

### Team Tier — $19/month per seat
- Everything in Pro, 25GB per seat
- Shared vaults via git (team knowledge bases)
- Access controls per vault
- Audit log of changes (git history)

### 2-Year Revenue Projection (Project Ron context)

**Assumptions:**
- Claude ecosystem has 10,000+ MCP servers and growing rapidly
- Plugin marketplace is young — early movers have advantage
- Salable handles billing (they take ~2-3% transaction fee)
- Marketing via Claude community forums, Reddit, X, and plugin marketplace listings
- Solo developer (Debbie) — no employee costs
- Hosting costs near zero (local-first architecture, no cloud infrastructure for core product)

#### Year 1 — Build & Launch

| Quarter | Phase | Free Users | Pro ($9) | Team ($19) | MRR | Cumulative Revenue |
|---|---|---|---|---|---|---|
| Q1 (Mo 1-3) | Build + free launch | 150 | 0 | 0 | $0 | $0 |
| Q2 (Mo 4-6) | Pro tier launch | 400 | 35 | 0 | $315 | $945 |
| Q3 (Mo 7-9) | Growth + Team tier | 800 | 80 | 5 | $815 | $3,390 |
| Q4 (Mo 10-12) | Optimization | 1,200 | 150 | 15 | $1,635 | $8,295 |

**Year 1 Total: ~$8,300**
**Year 1 Exit MRR: ~$1,635/month**

#### Year 2 — Scale & Expand

| Quarter | Phase | Free Users | Pro ($9) | Team ($19) | MRR | Cumulative Revenue |
|---|---|---|---|---|---|---|
| Q5 (Mo 13-15) | Semantic search launch | 2,000 | 250 | 30 | $2,820 | $16,755 |
| Q6 (Mo 16-18) | Cloud sync (Pro feature) | 3,000 | 400 | 50 | $4,550 | $30,405 |
| Q7 (Mo 19-21) | Enterprise pilot | 4,500 | 550 | 80 | $6,470 | $49,815 |
| Q8 (Mo 22-24) | Maturity | 6,000 | 700 | 120 | $8,580 | $75,555 |

**Year 2 Total: ~$67,250**
**Year 2 Exit MRR: ~$8,580/month**

#### Scenario Analysis

| Scenario | Year 1 Revenue | Year 2 Revenue | Month 24 MRR |
|---|---|---|---|
| Conservative (50% of above) | $4,150 | $33,600 | $4,290 |
| **Moderate (baseline)** | **$8,300** | **$67,250** | **$8,580** |
| Optimistic (2x) | $16,600 | $134,500 | $17,160 |

#### Key Growth Levers (Year 2)
1. **Semantic search (embeddings)** — Major Pro tier differentiator, drives upgrades from free
2. **Cloud sync / Claude Projects API** — If Anthropic exposes a Projects API, first-mover advantage is massive
3. **Team tier adoption** — Small consulting firms, dev teams, data teams managing shared knowledge
4. **Cross-platform expansion** — Adapt for Cursor, Windsurf, VS Code Copilot (same MCP, different clients)
5. **Content marketing** — "How I organize 50+ knowledge files across 12 Claude projects" blog posts

#### Cost Structure (Year 2)
- Salable transaction fees (~3%): ~$170/month at $5,700 MRR
- Domain + hosting for marketing site: ~$20/month
- Cloud sync infrastructure (if launched): ~$50-200/month depending on usage
- Total costs: ~$250-400/month
- **Margin: 93-96%**

#### Contribution to Project Ron
At moderate scenario, LoreDocs contributes ~$8,580/month to the $8K/month Project Ron target by month 24. Combined with LoreConvo ($3.2K target) and other portfolio products, this gives comfortable headroom even if individual products underperform.

---

## MCP Tool Manifest (Draft)

### Tool Summary

| Tool Name | Description | Read-Only | Destructive |
|---|---|---|---|
| `vault_create` | Create a new knowledge vault | No | No |
| `vault_list` | List all vaults with stats | Yes | No |
| `vault_info` | Get detailed vault information | Yes | No |
| `vault_archive` | Archive a vault | No | No |
| `vault_delete` | Permanently delete a vault | No | Yes |
| `vault_add_doc` | Add document to vault | No | No |
| `vault_update_doc` | Update document (auto-versions) | No | No |
| `vault_remove_doc` | Soft-delete a document | No | No |
| `vault_get_doc` | Retrieve document content | Yes | No |
| `vault_list_docs` | List docs with sort/filter | Yes | No |
| `vault_search` | Full-text search within vault | Yes | No |
| `vault_search_all` | Search across all vaults | Yes | No |
| `vault_find_related` | Find related documents | Yes | No |
| `vault_tag_doc` | Add/remove tags | No | No |
| `vault_categorize` | Set document category | No | No |
| `vault_set_priority` | Set document priority/status | No | No |
| `vault_add_note` | Attach note to document | No | No |
| `vault_bulk_tag` | Tag multiple documents | No | No |
| `vault_doc_history` | View version history | Yes | No |
| `vault_doc_diff` | Compare two versions | Yes | No |
| `vault_doc_restore` | Restore previous version | No | No |
| `vault_inject` | Load docs into conversation | Yes | No |
| `vault_inject_by_tag` | Load docs by tag filter | Yes | No |
| `vault_inject_summary` | Generate vault overview | Yes | No |
| `vault_suggest` | Suggest relevant docs | Yes | No |
| `vault_copy_doc` | Copy document between vaults | No | No |
| `vault_move_doc` | Move document between vaults | No | No |
| `vault_link_doc` | Create cross-vault reference | No | No |
| `vault_unlink_doc` | Remove cross-vault reference | No | No |
| `vault_link_project` | Associate vault with Claude Project names | No | No |
| `vault_import_dir` | Bulk import from directory | No | No |
| `vault_export` | Export vault to directory | Yes | No |

---

## Implementation Phases

### Phase 1: Core (Week 1-2)
- Vault CRUD (create, list, info, delete)
- Document CRUD (add, update, remove, get, list)
- Basic metadata (tags, categories)
- Local filesystem storage
- SQLite FTS5 search index
- stdio transport

### Phase 2: Search & Organization (Week 3)
- Full-text search (single vault + cross-vault)
- Tag-based filtering and search
- Sort by name, date, size, category
- Bulk tagging operations
- Version history (auto-version on update, diff, restore)

### Phase 3: Smart Features (Week 4)
- Context injection tools (inject, inject_by_tag, inject_summary)
- Smart suggestions (vault_suggest based on conversation context)
- Import/export (directory import, vault export, manifest export)
- Find related documents

### Phase 4: Polish & Ship (Week 5)
- Cowork plugin packaging (.plugin format)
- Claude Code MCP configuration
- Documentation and README
- Free/Pro tier gating logic
- Error handling and edge cases
- Testing suite

---

## Key Design Decisions

1. **Local-first storage** — Users own their data. No cloud dependency. Can back up with git.
2. **SQLite FTS5 over vector embeddings** — Simpler, faster, zero dependencies. Good enough for document search. Can add embeddings later if needed.
3. **Auto-versioning** — Every `vault_update_doc` saves the previous version automatically. Users never lose work.
4. **Soft deletes** — `vault_remove_doc` marks as deleted but retains for recovery. Hard delete requires explicit confirmation.
5. **stdio transport** — Maximum compatibility across Claude Code and Cowork. No server process to manage.
6. **Plain files on disk** — Documents stored as actual files, not blobs in a database. Easy to inspect, edit externally, and back up.

---

## Resolved Design Decisions (March 22, 2026)

### 1. Claude Projects Sync — YES, plan for it
When/if Anthropic exposes a Projects API, LoreDocs will offer bidirectional sync as a Pro feature. For now, the `vault_link_project` tool records the association as metadata so the sync mapping is ready when the API becomes available. This is a potential first-mover advantage — being ready to integrate before competitors.

### 2. Embedding-Based Semantic Search — YES, Pro tier (Year 2)
FTS5 keyword search ships in Phase 1. Semantic search via embeddings launches in Year 2 as a major Pro tier differentiator. Implementation options to evaluate:
- **Local embeddings** (e.g., sentence-transformers) — zero API cost, works offline, but requires ~500MB model download
- **API-based embeddings** (e.g., Anthropic/OpenAI) — better quality, but adds cost and cloud dependency
- **Hybrid approach** — local for indexing, API for complex queries
Decision on which approach deferred to Year 2 planning. FTS5 covers 80%+ of use cases in the meantime.

### 3. Shared Vaults — Git-based for Team tier
Team tier shared vaults will use **git as the sync layer**:
- Each vault is already a directory of plain files — naturally git-compatible
- Teams push/pull vault changes through a shared git remote (GitHub, GitLab, etc.)
- Conflict resolution follows git merge semantics (last-write-wins for metadata, manual merge for doc content)
- No proprietary cloud infrastructure needed — teams bring their own git remote
- Audit log comes free via git history
This keeps the architecture local-first while enabling collaboration. Cloud sync (S3, etc.) can be evaluated later if git proves too technical for non-developer teams.

### 4. File Format Support — Match Claude Projects from Day 1
LoreDocs will support all file formats currently accepted by Claude Projects:

**Documents:** PDF, DOCX, XLSX, CSV, TXT, MD, HTML, PPTX
**Images:** JPEG, PNG, GIF, WEBP
**Audio:** MP3, WAV

Implementation approach:
- **Text-native formats** (TXT, MD, CSV, HTML): Store as-is, index directly with FTS5
- **Rich documents** (PDF, DOCX, XLSX, PPTX): Store original binary + extract text for FTS5 indexing
  - PDF: `pdfplumber` or `pymupdf` for text extraction
  - DOCX: `python-docx` for text extraction
  - XLSX: `openpyxl` for cell content extraction
  - PPTX: `python-pptx` for slide text extraction
- **Images:** Store as-is, no text extraction in v1 (OCR can be a future Pro feature)
- **Audio:** Store as-is, no transcription in v1 (whisper integration as future feature)

The key insight: we store the **original file** untouched but maintain a **text extraction** alongside it for search indexing. Users get full fidelity on retrieval, full searchability on discovery.

### 5. Vault Size Limits — Percentage of Claude Project Capacity

Claude Projects allow **30MB per file** and the total extracted text must fit within ~200K tokens (~150K words, roughly **600KB-1MB of extracted text**).

LoreDocs tier limits based on these reference points:

| Limit | Free | Pro ($9) | Team ($19) |
|---|---|---|---|
| Max file size | 30MB (match Claude) | 30MB | 30MB |
| Vaults | 3 | Unlimited | Unlimited |
| Docs per vault | 50 | Unlimited | Unlimited |
| Total storage per vault | 200MB (~33% of a typical project) | 2GB | 5GB |
| Total storage (all vaults) | 500MB | 10GB | 25GB per seat |
| Version retention | Last 5 versions | Unlimited | Unlimited |
| FTS index | Single vault only | Cross-vault | Cross-vault |
| Semantic search | No | Yes (Year 2) | Yes (Year 2) |
| Shared vaults | No | No | Yes (git-based) |
| Claude Projects sync | No | Yes (when available) | Yes (when available) |

**Rationale:** The free tier gives enough room to manage ~3 small-to-medium Claude Projects worth of knowledge (500MB total). Power users who manage 5+ projects or keep large reference documents will naturally hit the limit and upgrade. The 30MB per-file cap matches Claude's own limit, so there's no friction when moving files between LoreDocs and Claude Projects.

---

## Remaining Open Questions

1. **OCR for images?** — Should we add Tesseract/EasyOCR for image text extraction in a future release?
2. **Audio transcription?** — Whisper integration for indexing audio file contents?
3. **Plugin marketplace listing** — Which marketplace(s) to target first? Claude Plugin Marketplace? MCP Market? LobeHub?
4. **Onboarding flow** — Should `vault_import_dir` auto-detect and import existing Claude Project knowledge dumps, or keep it generic?
