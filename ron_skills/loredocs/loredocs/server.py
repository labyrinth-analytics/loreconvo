#!/usr/bin/env python3
"""
ProjectVault MCP Server

Knowledge management for AI projects -- search, tag, version, and organize
your project knowledge across Claude Code and Cowork.

Usage:
    python -m projectvault.server          # stdio transport (default)
    projectvault                           # via installed entry point
"""

import json
import os
import sys
from contextlib import asynccontextmanager
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from mcp.server.fastmcp import FastMCP, Context
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .storage import VaultStorage
from .tiers import TierLimitError, get_tier, set_tier, TIER_LIMITS


# ---------------------------------------------------------------------------
# Lifespan -- initialize storage once, share across all tools
# ---------------------------------------------------------------------------

@asynccontextmanager
async def app_lifespan(app):
    """Initialize the VaultStorage instance for the server lifetime."""
    root_override = os.environ.get("PROJECTVAULT_ROOT")
    root = Path(root_override) if root_override else None
    storage = VaultStorage(root=root)
    yield {"storage": storage}


mcp = FastMCP("projectvault_mcp", lifespan=app_lifespan)


def _get_storage(ctx: Context) -> VaultStorage:
    """Helper to get storage from lifespan context."""
    return ctx.request_context.lifespan_context["storage"]


# ---------------------------------------------------------------------------
# Enums and shared models
# ---------------------------------------------------------------------------

class ResponseFormat(str, Enum):
    MARKDOWN = "markdown"
    JSON = "json"


class SortOrder(str, Enum):
    ASC = "asc"
    DESC = "desc"


class DocSortField(str, Enum):
    NAME = "name"
    UPDATED = "updated_at"
    CREATED = "created_at"
    SIZE = "file_size_bytes"
    CATEGORY = "category"


class DocCategory(str, Enum):
    GENERAL = "general"
    REFERENCE = "reference"
    CONFIG = "config"
    REPORT = "report"
    TEMPLATE = "template"
    ARCHIVE = "archive"
    IMPORTED = "imported"


class DocPriority(str, Enum):
    AUTHORITATIVE = "authoritative"
    NORMAL = "normal"
    DRAFT = "draft"
    OUTDATED = "outdated"


# ---------------------------------------------------------------------------
# Helper: format file sizes
# ---------------------------------------------------------------------------

def _fmt_size(b: int) -> str:
    """Format bytes as human-readable size."""
    if b < 1024:
        return f"{b} B"
    elif b < 1024 * 1024:
        return f"{b / 1024:.1f} KB"
    elif b < 1024 * 1024 * 1024:
        return f"{b / (1024 * 1024):.1f} MB"
    return f"{b / (1024 * 1024 * 1024):.1f} GB"


def _resolve_vault(storage: VaultStorage, vault: str) -> Optional[Dict[str, Any]]:
    """Resolve a vault by ID or name."""
    result = storage.get_vault(vault)
    if not result:
        result = storage.find_vault_by_name(vault)
    return result


# ===================================================================
# VAULT MANAGEMENT TOOLS
# ===================================================================

class VaultCreateInput(BaseModel):
    """Input for creating a new vault."""
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(..., description="Name for the vault (e.g., 'Tax Prep 2025', 'Rental Properties')", min_length=1, max_length=100)
    description: str = Field(default="", description="Description of what this vault contains", max_length=500)
    tags: Optional[List[str]] = Field(default=None, description="Tags for the vault itself (e.g., ['finance', '2025'])")
    linked_projects: Optional[List[str]] = Field(default=None, description="Claude Project names to associate with this vault")


@mcp.tool(
    name="vault_create",
    annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": False}
)
async def vault_create(params: VaultCreateInput, ctx: Context) -> str:
    """Create a new knowledge vault for organizing project documents.

    A vault is a container for related documents -- like a project folder with
    superpowers (search, tags, versioning). You can link a vault to one or more
    Claude Projects, but vaults are independent and can serve multiple projects.

    Returns the new vault's ID and metadata.
    """
    storage = _get_storage(ctx)
    try:
        vault = storage.create_vault(
            name=params.name,
            description=params.description,
            tags=params.tags,
            linked_projects=params.linked_projects,
        )
    except TierLimitError as exc:
        return f"Error: {exc}"
    return json.dumps(vault, indent=2)


class VaultListInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    include_archived: bool = Field(default=False, description="Include archived vaults in the list")
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN, description="Output format")


@mcp.tool(
    name="vault_list",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}
)
async def vault_list(params: VaultListInput, ctx: Context) -> str:
    """List all knowledge vaults with summary stats (document count, total size, last modified).

    Use this to see what vaults exist and find the one you need.
    """
    storage = _get_storage(ctx)
    vaults = storage.list_vaults(include_archived=params.include_archived)

    if not vaults:
        return "No vaults found. Create one with vault_create."

    if params.response_format == ResponseFormat.JSON:
        return json.dumps(vaults, indent=2)

    lines = ["# Your Vaults", ""]
    for v in vaults:
        status = " [ARCHIVED]" if v["archived"] else ""
        lines.append(f"## {v['name']}{status} (`{v['id']}`)")
        if v["description"]:
            lines.append(f"  {v['description']}")
        lines.append(f"  - Documents: {v['doc_count']} | Size: {_fmt_size(v['total_size_bytes'])}")
        if v["tags"]:
            lines.append(f"  - Tags: {', '.join(v['tags'])}")
        if v["linked_projects"]:
            lines.append(f"  - Linked projects: {', '.join(v['linked_projects'])}")
        lines.append(f"  - Last updated: {v['updated_at'][:10]}")
        lines.append("")
    return "\n".join(lines)


class VaultIdInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    vault: str = Field(..., description="Vault ID or name", min_length=1)
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN, description="Output format")


@mcp.tool(
    name="vault_info",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}
)
async def vault_info(params: VaultIdInput, ctx: Context) -> str:
    """Get detailed information about a vault, including its full document manifest.

    Accepts either a vault ID or vault name.
    """
    storage = _get_storage(ctx)
    vault = _resolve_vault(storage, params.vault)
    if not vault:
        return f"Error: Vault '{params.vault}' not found. Use vault_list to see available vaults."

    if params.response_format == ResponseFormat.JSON:
        return json.dumps(vault, indent=2)

    lines = [f"# Vault: {vault['name']} (`{vault['id']}`)", ""]
    if vault["description"]:
        lines.append(vault["description"])
        lines.append("")
    lines.append(f"- **Documents:** {vault['doc_count']}")
    lines.append(f"- **Total size:** {_fmt_size(vault['total_size_bytes'])}")
    lines.append(f"- **Created:** {vault['created_at'][:10]}")
    lines.append(f"- **Last updated:** {vault['updated_at'][:10]}")
    if vault["tags"]:
        lines.append(f"- **Tags:** {', '.join(vault['tags'])}")
    if vault["linked_projects"]:
        lines.append(f"- **Linked projects:** {', '.join(vault['linked_projects'])}")

    if vault["documents"]:
        lines.append("")
        lines.append("## Documents")
        lines.append("")
        for doc in vault["documents"]:
            tag_str = f" [{', '.join(doc['tags'])}]" if doc["tags"] else ""
            lines.append(
                f"- **{doc['name']}** (`{doc['id']}`) "
                f"| {doc['category']} | {_fmt_size(doc['file_size_bytes'])}{tag_str}"
            )

    return "\n".join(lines)


class VaultArchiveInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    vault: str = Field(..., description="Vault ID or name to archive", min_length=1)


@mcp.tool(
    name="vault_archive",
    annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}
)
async def vault_archive(params: VaultArchiveInput, ctx: Context) -> str:
    """Archive a vault (soft delete). Archived vaults are hidden from vault_list by default but can be restored."""
    storage = _get_storage(ctx)
    vault = _resolve_vault(storage, params.vault)
    if not vault:
        return f"Error: Vault '{params.vault}' not found."
    if storage.archive_vault(vault["id"]):
        return f"Vault '{vault['name']}' has been archived. Use vault_list with include_archived=true to see it."
    return "Error: Could not archive vault."


class VaultDeleteInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    vault: str = Field(..., description="Vault ID or name to permanently delete", min_length=1)
    confirm: bool = Field(default=False, description="Must be true to confirm permanent deletion")


@mcp.tool(
    name="vault_delete",
    annotations={"readOnlyHint": False, "destructiveHint": True, "idempotentHint": False, "openWorldHint": False}
)
async def vault_delete(params: VaultDeleteInput, ctx: Context) -> str:
    """Permanently delete a vault and ALL its documents. This cannot be undone.

    You must set confirm=true to proceed. Consider using vault_archive instead.
    """
    if not params.confirm:
        return "Error: Set confirm=true to permanently delete this vault. This action cannot be undone. Consider vault_archive instead."
    storage = _get_storage(ctx)
    vault = _resolve_vault(storage, params.vault)
    if not vault:
        return f"Error: Vault '{params.vault}' not found."
    name = vault["name"]
    if storage.delete_vault(vault["id"]):
        return f"Vault '{name}' and all its documents have been permanently deleted."
    return "Error: Could not delete vault."


class VaultLinkProjectInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    vault: str = Field(..., description="Vault ID or name", min_length=1)
    project_name: str = Field(..., description="Claude Project name to link", min_length=1)


@mcp.tool(
    name="vault_link_project",
    annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}
)
async def vault_link_project(params: VaultLinkProjectInput, ctx: Context) -> str:
    """Associate a Claude Project name with a vault.

    This is metadata for your organization -- it records which Claude Projects
    use knowledge from this vault. A vault can be linked to multiple projects.
    """
    storage = _get_storage(ctx)
    vault = _resolve_vault(storage, params.vault)
    if not vault:
        return f"Error: Vault '{params.vault}' not found."
    if storage.link_project(vault["id"], params.project_name):
        return f"Linked Claude Project '{params.project_name}' to vault '{vault['name']}'."
    return "Error: Could not link project."


# ===================================================================
# DOCUMENT MANAGEMENT TOOLS
# ===================================================================

class DocAddInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    vault: str = Field(..., description="Vault ID or name to add the document to", min_length=1)
    name: str = Field(..., description="Display name for the document (e.g., 'Depreciation Schedule 2025')", min_length=1, max_length=200)
    content: str = Field(..., description="The text content of the document", min_length=1)
    filename: Optional[str] = Field(default=None, description="Filename with extension (e.g., 'schedule.md'). Defaults to name.md")
    tags: Optional[List[str]] = Field(default=None, description="Tags for the document")
    category: DocCategory = Field(default=DocCategory.GENERAL, description="Document category")
    priority: DocPriority = Field(default=DocPriority.NORMAL, description="Document priority/status")
    notes: str = Field(default="", description="Notes about this document")


@mcp.tool(
    name="vault_add_doc",
    annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": False}
)
async def vault_add_doc(params: DocAddInput, ctx: Context) -> str:
    """Add a text document to a vault with metadata (tags, category, priority, notes).

    The document will be full-text indexed for search and stored with version tracking.
    For binary files (PDF, DOCX, etc.), use vault_import_dir to import from a directory.
    """
    storage = _get_storage(ctx)
    vault = _resolve_vault(storage, params.vault)
    if not vault:
        return f"Error: Vault '{params.vault}' not found. Use vault_list to see available vaults."

    try:
        result = storage.add_document_from_text(
            vault_id=vault["id"],
            name=params.name,
            text_content=params.content,
            filename=params.filename,
            tags=params.tags,
            category=params.category.value,
            priority=params.priority.value,
            notes=params.notes,
        )
    except TierLimitError as exc:
        return f"Error: {exc}"
    if result:
        return json.dumps(result, indent=2)
    return "Error: Could not add document."


class DocUpdateInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    doc_id: str = Field(..., description="Document ID to update", min_length=1)
    content: Optional[str] = Field(default=None, description="New text content (previous version will be saved automatically)")
    name: Optional[str] = Field(default=None, description="New display name", max_length=200)
    tags: Optional[List[str]] = Field(default=None, description="Replace all tags with this list")
    category: Optional[DocCategory] = Field(default=None, description="New category")
    priority: Optional[DocPriority] = Field(default=None, description="New priority/status")
    notes: Optional[str] = Field(default=None, description="New notes")


@mcp.tool(
    name="vault_update_doc",
    annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": False}
)
async def vault_update_doc(params: DocUpdateInput, ctx: Context) -> str:
    """Update a document's content or metadata.

    If content changes, the previous version is saved automatically in the
    version history. You can restore old versions with vault_doc_restore.
    """
    storage = _get_storage(ctx)
    content_bytes = params.content.encode("utf-8") if params.content else None
    result = storage.update_document(
        doc_id=params.doc_id,
        content=content_bytes,
        name=params.name,
        tags=params.tags,
        category=params.category.value if params.category else None,
        priority=params.priority.value if params.priority else None,
        notes=params.notes,
    )
    if result:
        return json.dumps(result, indent=2)
    return f"Error: Document '{params.doc_id}' not found."


class DocIdInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    doc_id: str = Field(..., description="Document ID", min_length=1)


@mcp.tool(
    name="vault_remove_doc",
    annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}
)
async def vault_remove_doc(params: DocIdInput, ctx: Context) -> str:
    """Soft-delete a document. The document is hidden but can be recovered.

    For permanent deletion, use vault_delete to remove the entire vault.
    """
    storage = _get_storage(ctx)
    if storage.remove_document(params.doc_id):
        return f"Document '{params.doc_id}' has been removed (soft-deleted)."
    return f"Error: Document '{params.doc_id}' not found."


class DocGetInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    doc_id: str = Field(..., description="Document ID", min_length=1)
    include_content: bool = Field(default=True, description="Include the document text content in the response")
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN, description="Output format")


@mcp.tool(
    name="vault_get_doc",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}
)
async def vault_get_doc(params: DocGetInput, ctx: Context) -> str:
    """Retrieve a document's metadata and optionally its text content.

    Use include_content=false to get just the metadata without loading the full text.
    """
    storage = _get_storage(ctx)
    doc = storage.get_document(params.doc_id)
    if not doc:
        return f"Error: Document '{params.doc_id}' not found."

    if params.include_content:
        doc["content"] = storage.get_document_content(params.doc_id) or ""

    if params.response_format == ResponseFormat.JSON:
        return json.dumps(doc, indent=2)

    lines = [f"# {doc['name']}", ""]
    lines.append(f"- **ID:** `{doc['id']}`")
    lines.append(f"- **Category:** {doc['category']}")
    lines.append(f"- **Priority:** {doc['priority']}")
    lines.append(f"- **Size:** {_fmt_size(doc['file_size_bytes'])}")
    lines.append(f"- **Versions:** {doc['version_count']}")
    if doc["tags"]:
        lines.append(f"- **Tags:** {', '.join(doc['tags'])}")
    if doc["notes"]:
        lines.append(f"- **Notes:** {doc['notes']}")
    lines.append(f"- **Last updated:** {doc['updated_at']}")

    if params.include_content and doc.get("content"):
        lines.append("")
        lines.append("---")
        lines.append("")
        lines.append(doc["content"])

    return "\n".join(lines)


class DocListInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    vault: str = Field(..., description="Vault ID or name", min_length=1)
    sort_by: DocSortField = Field(default=DocSortField.UPDATED, description="Sort field")
    sort_order: SortOrder = Field(default=SortOrder.DESC, description="Sort order")
    category: Optional[DocCategory] = Field(default=None, description="Filter by category")
    tag: Optional[str] = Field(default=None, description="Filter by tag")
    limit: int = Field(default=50, description="Max results", ge=1, le=200)
    offset: int = Field(default=0, description="Pagination offset", ge=0)
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN, description="Output format")


@mcp.tool(
    name="vault_list_docs",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}
)
async def vault_list_docs(params: DocListInput, ctx: Context) -> str:
    """List documents in a vault with sorting and filtering options.

    Supports sorting by name, date, size, or category.
    Filter by category or tag to narrow results.
    """
    storage = _get_storage(ctx)
    vault = _resolve_vault(storage, params.vault)
    if not vault:
        return f"Error: Vault '{params.vault}' not found."

    result = storage.list_documents(
        vault_id=vault["id"],
        sort_by=params.sort_by.value,
        sort_order=params.sort_order.value,
        category=params.category.value if params.category else None,
        tag=params.tag,
        limit=params.limit,
        offset=params.offset,
    )

    if params.response_format == ResponseFormat.JSON:
        return json.dumps(result, indent=2)

    if not result["documents"]:
        return f"No documents found in vault '{vault['name']}'."

    lines = [f"# Documents in '{vault['name']}'", ""]
    lines.append(f"Showing {result['count']} of {result['total']} documents")
    lines.append("")

    for doc in result["documents"]:
        tag_str = f" [{', '.join(doc['tags'])}]" if doc["tags"] else ""
        priority_badge = ""
        if doc["priority"] == "authoritative":
            priority_badge = " [AUTHORITATIVE]"
        elif doc["priority"] == "outdated":
            priority_badge = " [OUTDATED]"
        elif doc["priority"] == "draft":
            priority_badge = " [DRAFT]"

        lines.append(
            f"- **{doc['name']}** (`{doc['id']}`){priority_badge}"
        )
        lines.append(
            f"  {doc['category']} | {_fmt_size(doc['file_size_bytes'])} | "
            f"v{doc['version_count']} | {doc['updated_at'][:10]}{tag_str}"
        )
        if doc["notes"]:
            lines.append(f"  Note: {doc['notes']}")
        lines.append("")

    if result["has_more"]:
        lines.append(f"*{result['total'] - result['offset'] - result['count']} more documents. Use offset={result['offset'] + result['count']} to see the next page.*")

    return "\n".join(lines)


# ===================================================================
# SEARCH TOOLS
# ===================================================================

class SearchInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    query: str = Field(..., description="Search query (supports FTS5 syntax: AND, OR, NOT, phrase matching with quotes)", min_length=1)
    vault: Optional[str] = Field(default=None, description="Vault ID or name to search within. Leave empty to search all vaults.")
    limit: int = Field(default=20, description="Max results", ge=1, le=100)
    offset: int = Field(default=0, description="Pagination offset", ge=0)
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN, description="Output format")


@mcp.tool(
    name="vault_search",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}
)
async def vault_search(params: SearchInput, ctx: Context) -> str:
    """Full-text search across document contents using SQLite FTS5.

    Searches within a specific vault if vault is provided, or across ALL
    vaults if omitted (cross-vault search).

    Supports FTS5 query syntax:
    - Simple words: depreciation schedule
    - Phrases: "rental income"
    - Boolean: depreciation AND schedule
    - Negation: rental NOT commercial
    - Prefix: deprec*
    """
    storage = _get_storage(ctx)
    vault_id = None
    vault_name = None
    if params.vault:
        vault = _resolve_vault(storage, params.vault)
        if not vault:
            return f"Error: Vault '{params.vault}' not found."
        vault_id = vault["id"]
        vault_name = vault["name"]

    result = storage.search(
        query=params.query,
        vault_id=vault_id,
        limit=params.limit,
        offset=params.offset,
    )

    if params.response_format == ResponseFormat.JSON:
        return json.dumps(result, indent=2)

    if not result["results"]:
        scope = f"vault '{vault_name}'" if vault_name else "all vaults"
        return f"No results found for '{params.query}' in {scope}."

    scope = f"vault '{vault_name}'" if vault_name else "all vaults"
    lines = [f"# Search Results: '{params.query}'", ""]
    lines.append(f"Found {result['count']} results in {scope}")
    lines.append("")

    for r in result["results"]:
        lines.append(f"- **{r['doc_name']}** (`{r['doc_id']}`) in *{r['vault_name']}*")
        lines.append(f"  ...{r['snippet']}...")
        lines.append("")

    return "\n".join(lines)


class SearchByTagInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    tag: str = Field(..., description="Tag to search for", min_length=1)
    vault: Optional[str] = Field(default=None, description="Vault ID or name. Leave empty to search all vaults.")
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN, description="Output format")


@mcp.tool(
    name="vault_search_by_tag",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}
)
async def vault_search_by_tag(params: SearchByTagInput, ctx: Context) -> str:
    """Find all documents with a specific tag, across one vault or all vaults."""
    storage = _get_storage(ctx)
    vault_id = None
    if params.vault:
        vault = _resolve_vault(storage, params.vault)
        if not vault:
            return f"Error: Vault '{params.vault}' not found."
        vault_id = vault["id"]

    results = storage.search_by_tag(params.tag, vault_id=vault_id)

    if params.response_format == ResponseFormat.JSON:
        return json.dumps(results, indent=2)

    if not results:
        return f"No documents found with tag '{params.tag}'."

    lines = [f"# Documents tagged '{params.tag}'", ""]
    lines.append(f"Found {len(results)} documents")
    lines.append("")
    for r in results:
        lines.append(f"- **{r['name']}** (`{r['id']}`) in *{r['vault_name']}* | {r['category']} | {_fmt_size(r['file_size_bytes'])}")
    return "\n".join(lines)


# ===================================================================
# METADATA AND TAGGING TOOLS
# ===================================================================

class TagDocInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    doc_id: str = Field(..., description="Document ID", min_length=1)
    add_tags: Optional[List[str]] = Field(default=None, description="Tags to add")
    remove_tags: Optional[List[str]] = Field(default=None, description="Tags to remove")


@mcp.tool(
    name="vault_tag_doc",
    annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}
)
async def vault_tag_doc(params: TagDocInput, ctx: Context) -> str:
    """Add or remove tags on a document.

    You can add and remove tags in a single operation.
    Tags are case-sensitive strings. Duplicates are automatically removed.
    """
    storage = _get_storage(ctx)
    result = storage.tag_document(
        params.doc_id,
        add_tags=params.add_tags,
        remove_tags=params.remove_tags,
    )
    if result is None:
        return f"Error: Document '{params.doc_id}' not found."
    return f"Tags updated. Current tags: {', '.join(result) if result else '(none)'}"


class BulkTagInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    doc_ids: List[str] = Field(..., description="List of document IDs to tag", min_length=1)
    add_tags: Optional[List[str]] = Field(default=None, description="Tags to add to all documents")
    remove_tags: Optional[List[str]] = Field(default=None, description="Tags to remove from all documents")


@mcp.tool(
    name="vault_bulk_tag",
    annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}
)
async def vault_bulk_tag(params: BulkTagInput, ctx: Context) -> str:
    """Apply tag changes to multiple documents at once.

    Useful for organizing a batch of documents after import or reclassification.
    """
    storage = _get_storage(ctx)
    count = storage.bulk_tag(
        params.doc_ids,
        add_tags=params.add_tags,
        remove_tags=params.remove_tags,
    )
    return f"Updated tags on {count} of {len(params.doc_ids)} documents."


class CategorizeInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    doc_id: str = Field(..., description="Document ID", min_length=1)
    category: DocCategory = Field(..., description="New category")


@mcp.tool(
    name="vault_categorize",
    annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}
)
async def vault_categorize(params: CategorizeInput, ctx: Context) -> str:
    """Set a document's category (general, reference, config, report, template, archive, imported)."""
    storage = _get_storage(ctx)
    result = storage.update_document(params.doc_id, category=params.category.value)
    if result:
        return f"Document '{result['name']}' category set to '{params.category.value}'."
    return f"Error: Document '{params.doc_id}' not found."


class SetPriorityInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    doc_id: str = Field(..., description="Document ID", min_length=1)
    priority: DocPriority = Field(..., description="New priority/status")


@mcp.tool(
    name="vault_set_priority",
    annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}
)
async def vault_set_priority(params: SetPriorityInput, ctx: Context) -> str:
    """Mark a document's priority/status: authoritative, normal, draft, or outdated.

    'authoritative' means this document is the source of truth.
    'outdated' flags the document as no longer current.
    """
    storage = _get_storage(ctx)
    result = storage.update_document(params.doc_id, priority=params.priority.value)
    if result:
        return f"Document '{result['name']}' priority set to '{params.priority.value}'."
    return f"Error: Document '{params.doc_id}' not found."


class AddNoteInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    doc_id: str = Field(..., description="Document ID", min_length=1)
    notes: str = Field(..., description="Note to attach (e.g., 'Use this for 2025 tax prep only')", max_length=1000)


@mcp.tool(
    name="vault_add_note",
    annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}
)
async def vault_add_note(params: AddNoteInput, ctx: Context) -> str:
    """Attach a contextual note to a document.

    Notes help you and your AI assistant understand when/how to use this document.
    """
    storage = _get_storage(ctx)
    result = storage.update_document(params.doc_id, notes=params.notes)
    if result:
        return f"Note added to '{result['name']}'."
    return f"Error: Document '{params.doc_id}' not found."


# ===================================================================
# VERSION HISTORY TOOLS
# ===================================================================

@mcp.tool(
    name="vault_doc_history",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}
)
async def vault_doc_history(params: DocIdInput, ctx: Context) -> str:
    """View the version history for a document.

    Every time a document's content is updated, the previous version is saved
    automatically. Use vault_doc_restore to revert to an earlier version.
    """
    storage = _get_storage(ctx)
    doc = storage.get_document(params.doc_id)
    if not doc:
        return f"Error: Document '{params.doc_id}' not found."

    history = storage.get_doc_history(params.doc_id)
    if not history:
        return f"No version history for document '{params.doc_id}'."

    lines = [f"# Version History: {doc['name']}", ""]
    for v in history:
        current = " (current)" if v.get("current") else ""
        lines.append(f"- **v{v['version']}**{current} | {v['modified_at'][:10]} | {_fmt_size(v['file_size_bytes'])}")
    return "\n".join(lines)


class DocRestoreInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    doc_id: str = Field(..., description="Document ID", min_length=1)
    version: int = Field(..., description="Version number to restore", ge=1)


@mcp.tool(
    name="vault_doc_restore",
    annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": False}
)
async def vault_doc_restore(params: DocRestoreInput, ctx: Context) -> str:
    """Restore a document to a previous version.

    The current version is saved to history first, then the specified version
    becomes the new current version.
    """
    storage = _get_storage(ctx)
    doc = storage.get_document(params.doc_id)
    if not doc:
        return f"Error: Document '{params.doc_id}' not found."

    vault_id = doc["vault_id"]
    ext = doc["file_extension"]
    doc_dir = storage.vaults_dir / vault_id / "docs" / params.doc_id
    version_file = doc_dir / "history" / f"v{params.version}{ext}"

    if not version_file.exists():
        return f"Error: Version {params.version} not found for document '{params.doc_id}'."

    content = version_file.read_bytes()
    result = storage.update_document(
        params.doc_id,
        content=content,
        filename=doc["original_filename"],
    )
    if result:
        return f"Document '{doc['name']}' restored to version {params.version}. Previous content saved as v{doc['version_count']}."
    return "Error: Could not restore version."


# ===================================================================
# CROSS-VAULT OPERATIONS
# ===================================================================

class CopyDocInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    doc_id: str = Field(..., description="Document ID to copy", min_length=1)
    target_vault: str = Field(..., description="Target vault ID or name", min_length=1)


@mcp.tool(
    name="vault_copy_doc",
    annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": False}
)
async def vault_copy_doc(params: CopyDocInput, ctx: Context) -> str:
    """Copy a document from one vault to another, including all metadata."""
    storage = _get_storage(ctx)
    target = _resolve_vault(storage, params.target_vault)
    if not target:
        return f"Error: Target vault '{params.target_vault}' not found."

    result = storage.copy_document(params.doc_id, target["id"])
    if result:
        return f"Document copied to vault '{target['name']}'. New ID: {result['id']}"
    return f"Error: Could not copy document '{params.doc_id}'. Check that it exists."


class MoveDocInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    doc_id: str = Field(..., description="Document ID to move", min_length=1)
    target_vault: str = Field(..., description="Target vault ID or name", min_length=1)


@mcp.tool(
    name="vault_move_doc",
    annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": False}
)
async def vault_move_doc(params: MoveDocInput, ctx: Context) -> str:
    """Move a document to a different vault. Removes it from the source vault."""
    storage = _get_storage(ctx)
    target = _resolve_vault(storage, params.target_vault)
    if not target:
        return f"Error: Target vault '{params.target_vault}' not found."

    result = storage.move_document(params.doc_id, target["id"])
    if result:
        return f"Document moved to vault '{target['name']}'. New ID: {result['id']}"
    return f"Error: Could not move document '{params.doc_id}'. Check that it exists."


# ===================================================================
# CONTEXT INJECTION TOOLS
# ===================================================================

class InjectInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    doc_ids: List[str] = Field(..., description="Document IDs to inject into conversation", min_length=1)


@mcp.tool(
    name="vault_inject",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}
)
async def vault_inject(params: InjectInput, ctx: Context) -> str:
    """Load specific documents into the current conversation context.

    Returns the full text content of each document, formatted for easy reading.
    Use this to bring vault knowledge into the current conversation.
    """
    storage = _get_storage(ctx)
    parts = []
    for doc_id in params.doc_ids:
        doc = storage.get_document(doc_id)
        if not doc:
            parts.append(f"[Document '{doc_id}' not found]")
            continue
        content = storage.get_document_content(doc_id) or "(empty)"
        parts.append(f"=== {doc['name']} ({doc['id']}) ===")
        parts.append(f"Category: {doc['category']} | Priority: {doc['priority']}")
        if doc["tags"]:
            parts.append(f"Tags: {', '.join(doc['tags'])}")
        if doc["notes"]:
            parts.append(f"Note: {doc['notes']}")
        parts.append("")
        parts.append(content)
        parts.append("")
        parts.append("=" * 60)
        parts.append("")

    return "\n".join(parts)


class InjectByTagInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    tag: str = Field(..., description="Tag to match (e.g., 'tax-2025')", min_length=1)
    vault: Optional[str] = Field(default=None, description="Vault ID or name. Leave empty for all vaults.")


@mcp.tool(
    name="vault_inject_by_tag",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}
)
async def vault_inject_by_tag(params: InjectByTagInput, ctx: Context) -> str:
    """Load all documents matching a tag into the current conversation context.

    Useful for bringing in all documents related to a topic, e.g.,
    'inject everything tagged tax-2025'.
    """
    storage = _get_storage(ctx)
    vault_id = None
    if params.vault:
        vault = _resolve_vault(storage, params.vault)
        if vault:
            vault_id = vault["id"]

    docs = storage.search_by_tag(params.tag, vault_id=vault_id)
    if not docs:
        return f"No documents found with tag '{params.tag}'."

    doc_ids = [d["id"] for d in docs]
    inject_params = InjectInput(doc_ids=doc_ids)
    return await vault_inject(inject_params, ctx)


class InjectSummaryInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    vault: str = Field(..., description="Vault ID or name", min_length=1)


@mcp.tool(
    name="vault_inject_summary",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}
)
async def vault_inject_summary(params: InjectSummaryInput, ctx: Context) -> str:
    """Generate a summary overview of a vault's contents for conversation orientation.

    Lists all documents with their categories, tags, priorities, and notes.
    Useful at the start of a conversation to understand what knowledge is available.
    """
    storage = _get_storage(ctx)
    vault = _resolve_vault(storage, params.vault)
    if not vault:
        return f"Error: Vault '{params.vault}' not found."

    # This is essentially vault_info in markdown format
    return await vault_info(VaultIdInput(vault=vault["id"]), ctx)


# ===================================================================
# IMPORT / EXPORT TOOLS
# ===================================================================

class ImportDirInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    vault: str = Field(..., description="Vault ID or name to import into", min_length=1)
    directory: str = Field(..., description="Absolute path to directory containing files to import")
    tags: Optional[List[str]] = Field(default=None, description="Tags to apply to all imported documents")
    category: DocCategory = Field(default=DocCategory.IMPORTED, description="Category for imported documents")


@mcp.tool(
    name="vault_import_dir",
    annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": False}
)
async def vault_import_dir(params: ImportDirInput, ctx: Context) -> str:
    """Bulk import all supported files from a directory into a vault.

    Imports text files, PDFs, Word docs, Excel files, PowerPoints, and more.
    Each file becomes a separate document with text extracted for search indexing.
    Files over 30MB are skipped. Hidden files (starting with .) are skipped.
    """
    storage = _get_storage(ctx)
    vault = _resolve_vault(storage, params.vault)
    if not vault:
        return f"Error: Vault '{params.vault}' not found."

    dir_path = Path(params.directory)
    if not dir_path.is_dir():
        return f"Error: Directory '{params.directory}' not found or is not a directory."

    results = storage.import_directory(
        vault_id=vault["id"],
        dir_path=dir_path,
        tags=params.tags,
        category=params.category.value,
    )

    if not results:
        return f"No files imported from '{params.directory}'. Check that the directory contains supported files under 30MB."

    lines = [f"Imported {len(results)} files into vault '{vault['name']}':", ""]
    for r in results:
        lines.append(f"- {r['name']} ({r['original_filename']}) - {_fmt_size(r['file_size_bytes'])}")

    return "\n".join(lines)


class ExportInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    vault: str = Field(..., description="Vault ID or name to export", min_length=1)
    directory: str = Field(..., description="Absolute path to output directory")


@mcp.tool(
    name="vault_export",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}
)
async def vault_export(params: ExportInput, ctx: Context) -> str:
    """Export all documents from a vault to a local directory.

    Copies the original files (not extracted text) to the specified directory.
    Useful for backing up or sharing vault contents.
    """
    storage = _get_storage(ctx)
    vault = _resolve_vault(storage, params.vault)
    if not vault:
        return f"Error: Vault '{params.vault}' not found."

    output_dir = Path(params.directory)
    count = storage.export_vault(vault["id"], output_dir)

    if count == 0:
        return f"No documents to export from vault '{vault['name']}'."
    return f"Exported {count} documents from vault '{vault['name']}' to {params.directory}"


# ---------------------------------------------------------------------------
# Phase 2: Document linking
# ---------------------------------------------------------------------------

class LinkDocInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    source_doc: str = Field(..., description="Source document ID", min_length=1)
    target_doc: str = Field(..., description="Target document ID", min_length=1)
    label: str = Field(default="related", description="Relationship label, e.g. 'related', 'references', 'supersedes', 'part-of'")


@mcp.tool(
    name="vault_link_doc",
    annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}
)
async def vault_link_doc(params: LinkDocInput, ctx: Context) -> str:
    """Create a link between two documents across any vault.

    Links are bidirectional and labelled (e.g. 'related', 'references',
    'supersedes', 'part-of').  If the link already exists, reports it.
    Use vault_find_related to discover all docs linked to a given document.
    """
    storage = _get_storage(ctx)
    result = storage.link_doc(params.source_doc, params.target_doc, params.label)
    if result is None:
        return (
            f"Error: One or both documents not found "
            f"(source='{params.source_doc}', target='{params.target_doc}')."
        )
    if result.get("already_existed"):
        return (
            f"Link already exists between '{result['source_doc_name']}' and "
            f"'{result['target_doc_name']}' (label: {result['label']})."
        )
    return (
        f"Linked '{result['source_doc_name']}' -> '{result['target_doc_name']}' "
        f"(label: {result['label']}, link ID: {result['id']})"
    )


class UnlinkDocInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    source_doc: str = Field(..., description="Source document ID", min_length=1)
    target_doc: str = Field(..., description="Target document ID", min_length=1)


@mcp.tool(
    name="vault_unlink_doc",
    annotations={"readOnlyHint": False, "destructiveHint": True, "idempotentHint": True, "openWorldHint": False}
)
async def vault_unlink_doc(params: UnlinkDocInput, ctx: Context) -> str:
    """Remove a link between two documents (both directions).

    If no link exists between the two documents, reports that cleanly.
    """
    storage = _get_storage(ctx)
    deleted = storage.unlink_doc(params.source_doc, params.target_doc)
    if deleted == 0:
        return f"No link found between '{params.source_doc}' and '{params.target_doc}'."
    return (
        f"Removed link between '{params.source_doc}' and '{params.target_doc}' "
        f"({deleted} row(s) deleted)."
    )


class FindRelatedInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    doc_id: str = Field(..., description="Document ID to find related documents for", min_length=1)


@mcp.tool(
    name="vault_find_related",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}
)
async def vault_find_related(params: FindRelatedInput, ctx: Context) -> str:
    """Find all documents linked to a given document.

    Returns each related document with its vault, category, tags, and link label.
    Use vault_link_doc to create new links.
    """
    storage = _get_storage(ctx)
    related = storage.find_related_docs(params.doc_id)
    if not related:
        return (
            f"No related documents found for '{params.doc_id}'. "
            "Use vault_link_doc to create links."
        )

    lines = [f"Found {len(related)} related document(s):", ""]
    for r in related:
        tag_str = ", ".join(r["tags"]) if r["tags"] else "none"
        lines.append(
            f"- [{r['label']}] {r['name']} "
            f"(vault: {r['vault_name']}, category: {r['category']}, tags: {tag_str})"
        )
        lines.append(f"  ID: {r['id']}  updated: {r['updated_at'][:10]}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Phase 2: vault_suggest
# ---------------------------------------------------------------------------

class VaultSuggestInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    vault: Optional[str] = Field(
        default=None,
        description="Vault ID or name to scope suggestions to (omit for all vaults)"
    )
    limit: int = Field(default=5, ge=1, le=20, description="Max suggestions to return")


@mcp.tool(
    name="vault_suggest",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}
)
async def vault_suggest(params: VaultSuggestInput, ctx: Context) -> str:
    """Get suggestions for documents that may need attention.

    Surfaces documents that are undocumented (no notes), unorganized (no tags),
    or isolated (no links to other documents).  Use to guide housekeeping work
    or to discover documents that haven't been connected to the broader graph.

    Optionally scope to a single vault.
    """
    storage = _get_storage(ctx)
    vault_id: Optional[str] = None
    if params.vault:
        vault = _resolve_vault(storage, params.vault)
        if not vault:
            return f"Error: Vault '{params.vault}' not found."
        vault_id = vault["id"]

    suggestions = storage.get_suggestions(vault_id=vault_id, limit=params.limit)
    if not suggestions:
        return "No suggestions right now -- your vaults look well-organized!"

    lines = [f"Found {len(suggestions)} suggestion(s):", ""]
    for s in suggestions:
        lines.append(f"[{s['reason']}] {s['doc_name']} (vault: {s['vault_name']})")
        lines.append(f"  -> {s['label']}")
        lines.append(f"  doc_id: {s['doc_id']}  updated: {s['updated_at'][:10]}")
        lines.append("")
    return "\n".join(lines).rstrip()


# ---------------------------------------------------------------------------
# Phase 2: vault_export_manifest
# ---------------------------------------------------------------------------

class ExportManifestInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    vault: str = Field(..., description="Vault ID or name to export manifest for", min_length=1)
    format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Output format: markdown or json"
    )


@mcp.tool(
    name="vault_export_manifest",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}
)
async def vault_export_manifest(params: ExportManifestInput, ctx: Context) -> str:
    """Export a complete manifest of a vault's contents.

    Returns vault metadata, document list with tags and categories,
    tag frequency index, category counts, and link count.
    Use the json format for machine-readable output.
    Use the markdown format for human-readable summaries.
    """
    storage = _get_storage(ctx)
    vault = _resolve_vault(storage, params.vault)
    if not vault:
        return f"Error: Vault '{params.vault}' not found."

    manifest = storage.get_vault_manifest(vault["id"])
    if not manifest:
        return f"Error: Could not generate manifest for vault '{params.vault}'."

    if params.format == ResponseFormat.JSON:
        import json as _json
        return _json.dumps(manifest, indent=2, default=str)

    # Markdown format
    v = manifest["vault"]
    lines = [
        f"# Vault Manifest: {v['name']}",
        "",
        f"**Description:** {v['description'] or '(none)'}",
        f"**Documents:** {manifest['document_count']}",
        f"**Links:** {manifest['link_count']}",
        f"**Generated:** {manifest['generated_at'][:19]}",
        "",
    ]

    if manifest["category_counts"]:
        lines.append("## By Category")
        for cat, cnt in sorted(manifest["category_counts"].items()):
            lines.append(f"- {cat}: {cnt}")
        lines.append("")

    if manifest["tag_counts"]:
        lines.append("## Tag Index")
        sorted_tags = sorted(manifest["tag_counts"].items(), key=lambda x: -x[1])
        for tag, cnt in sorted_tags:
            lines.append(f"- {tag}: {cnt}")
        lines.append("")

    if manifest["documents"]:
        lines.append("## Documents")
        for doc in manifest["documents"]:
            tag_str = ", ".join(doc["tags"]) if doc["tags"] else "untagged"
            lines.append(f"- **{doc['name']}** [{doc['category']}]  tags: {tag_str}")
            lines.append(f"  ID: {doc['id']}  updated: {doc['updated_at'][:10]}")

    return "\n".join(lines)


# ===================================================================
# TIER MANAGEMENT TOOLS
# ===================================================================

class VaultTierStatusInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Output format: 'markdown' (default) or 'json'"
    )


@mcp.tool(
    name="vault_tier_status",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}
)
async def vault_tier_status(params: VaultTierStatusInput, ctx: Context) -> str:
    """Show current tier (Free or Pro) and usage vs. limits.

    Displays how many vaults and how much storage are in use, with percentages
    against Free tier limits. Useful before hitting a limit to know how close
    you are, or to confirm Pro tier is active after upgrading.
    """
    storage = _get_storage(ctx)

    vault_count = len(storage.list_vaults(include_archived=False))
    total_bytes = storage.get_total_storage_bytes()
    status = storage.enforcer.status_dict(vault_count, total_bytes)

    if params.response_format == ResponseFormat.JSON:
        return json.dumps(status, indent=2)

    tier_label = "Pro (unlimited)" if status["is_pro"] else "Free"
    lines = [
        "# ProjectVault Tier Status",
        "",
        f"**Tier:** {tier_label}",
        "",
        "## Usage",
        "",
    ]

    # Vaults
    vault_limit_str = str(status["vault_limit"]) if status["vault_limit"] is not None else "unlimited"
    pct_str = f" ({status['vault_usage_pct']}%)" if status["vault_usage_pct"] is not None else ""
    lines.append(f"- **Vaults:** {status['vault_count']} / {vault_limit_str}{pct_str}")

    # Storage
    storage_limit_str = (
        f"{status['storage_limit_mb']} MB" if status["storage_limit_mb"] is not None else "unlimited"
    )
    storage_pct_str = (
        f" ({status['storage_usage_pct']}%)" if status["storage_usage_pct"] is not None else ""
    )
    lines.append(
        f"- **Storage:** {status['storage_used_mb']} MB / {storage_limit_str}{storage_pct_str}"
    )

    # Per-vault and per-doc limits
    doc_limit = status["docs_per_vault_limit"]
    ver_limit = status["versions_per_doc_limit"]
    lines.append(
        f"- **Docs per vault:** "
        f"{doc_limit if doc_limit is not None else 'unlimited'}"
    )
    lines.append(
        f"- **Versions per doc:** "
        f"{ver_limit if ver_limit is not None else 'unlimited'}"
    )

    if not status["is_pro"]:
        lines += [
            "",
            "## Upgrade to Pro",
            "",
            "Pro tier removes all limits. Use `vault_set_tier` with `tier='pro'` "
            "to activate your license after purchase.",
        ]

    return "\n".join(lines)


class VaultSetTierInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    tier: str = Field(
        ...,
        description="Tier to activate: 'free' or 'pro'",
        pattern="^(free|pro)$"
    )


@mcp.tool(
    name="vault_set_tier",
    annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}
)
async def vault_set_tier(params: VaultSetTierInput, ctx: Context) -> str:
    """Activate a tier (free or pro) for ProjectVault.

    Pro tier removes all vault, document, storage, and version limits.
    After purchasing a Pro license, call this tool with tier='pro' to unlock
    unlimited usage. Reverting to tier='free' re-enables limits (but does not
    delete any existing data that exceeds the limits -- it only blocks new writes).

    Note: In a future release this will verify a license key. For now it trusts
    the caller (suitable for single-user local installs).
    """
    storage = _get_storage(ctx)
    try:
        set_tier(storage.root, params.tier)
    except ValueError as exc:
        return f"Error: {exc}"

    limits = TIER_LIMITS[params.tier]
    if limits.is_unlimited():
        summary = "All limits removed. Enjoy unlimited vaults, documents, and storage."
    else:
        summary = (
            f"Free tier active. Limits: {limits.max_vaults} vaults, "
            f"{limits.max_docs_per_vault} docs/vault, "
            f"{(limits.max_storage_bytes or 0) // (1024 * 1024)} MB storage, "
            f"{limits.max_versions_per_doc} versions/doc."
        )

    return f"[OK] Tier set to '{params.tier}'. {summary}"


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    """Run the ProjectVault MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
