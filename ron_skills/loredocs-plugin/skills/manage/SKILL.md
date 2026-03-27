---
name: manage
description: >
  Manage project knowledge vaults -- create vaults, add and update documents, tag and categorize content, search across vaults, and organize knowledge for AI projects.
  Use when the user says "create a vault", "add this to my vault", "store this document", "save this to ProjectVault", "tag this document", "search my vault for", "show my vaults", "list my documents", "update the document", "archive this vault", "import files into", "move this doc to", or any request to store, organize, or retrieve project knowledge.
---

# ProjectVault: Knowledge Management

ProjectVault stores documents in named vaults. Each vault is a collection of related documents with tags, categories, version history, and full-text search.

## Core Concepts

- **Vault** -- a named collection of documents for a project or topic (e.g., "Tax Reference 2025", "Client Onboarding Docs")
- **Document** -- a text or imported file stored in a vault, with a name, content, tags, category, and priority
- **Tag** -- a keyword label on a document (e.g., "schedule-e", "client-name", "draft")
- **Category** -- a document type: general, reference, config, report, template, archive, imported
- **Priority** -- a document's authority level: authoritative, normal, draft, outdated

## Workflow: Creating and Populating a Vault

When the user asks to create a vault and add content to it:

1. Call `vault_create` with a descriptive name and optional tags
2. Call `vault_add_doc` for each document, supplying name, content, tags, category as appropriate
3. Confirm what was created: vault name, document count, any tags applied

```
vault_create(name="Tax Reference 2025", tags=["tax", "2025"])
vault_add_doc(vault_id=..., name="Depreciation Schedule", content="...", tags=["schedule-e"], category="reference")
```

## Workflow: Adding a Single Document

When the user says "save this to my [vault name] vault" or "add this document to ProjectVault":

1. Call `vault_list` to find the target vault by name (match case-insensitively)
2. If no match, ask the user which vault or offer to create one
3. Call `vault_add_doc` with the content

## Workflow: Searching

When the user asks to find something across their vaults:

1. Call `vault_search(query="...", limit=10)` for full-text search across all vaults
2. Or call `vault_search_by_tag(tag="...")` to find by tag
3. Present results as a list: document name, vault name, a short excerpt
4. Offer to load a specific document with `vault_get_doc`

## Workflow: Updating a Document

When the user wants to update existing content:

1. Find the document: `vault_search` or `vault_list_docs(vault_id=...)`
2. Call `vault_update_doc(doc_id=..., content="...")` -- this auto-saves the previous version
3. Confirm the update; mention that history is preserved

## Workflow: Organizing with Tags and Categories

When the user asks to tag, categorize, or prioritize documents:

- Add/remove tags: `vault_tag_doc(doc_id=..., add_tags=[...], remove_tags=[...])`
- Bulk tag: `vault_bulk_tag(doc_ids=[...], add_tags=[...])`
- Set category: `vault_categorize(doc_id=..., category="reference")`
- Set priority: `vault_set_priority(doc_id=..., priority="authoritative")`

## Workflow: Importing Files from Disk

When the user says "import files from [folder]":

1. Call `vault_import_dir(vault_id=..., directory_path="...", recursive=False)`
2. Report how many files were imported and any that were skipped

## Workflow: Showing Vault Contents

When the user asks "what's in my vault" or "show my vaults":

- List all vaults: `vault_list(include_archived=False)`
- Show vault details: `vault_info(vault_id=...)`
- List documents: `vault_list_docs(vault_id=..., sort_by="updated_at", order="desc")`

## Tier Awareness

ProjectVault has free and Pro tiers:

- Free tier: up to 3 vaults, 25 documents per vault
- Pro tier: unlimited vaults and documents

Check tier status: `vault_tier_status()`

If the user hits a limit, explain that upgrading to Pro unlocks unlimited vaults and documents.

## Error Handling

- If a vault or document is not found, use `vault_list` or `vault_search` to help locate it
- If a tier limit error occurs, report the limit and explain Pro tier
- If an import fails for a file, report the filename and reason; continue with other files
