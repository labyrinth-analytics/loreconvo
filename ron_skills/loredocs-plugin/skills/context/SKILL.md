---
name: context
description: >
  Load vault knowledge into the current Claude conversation. Injects documents, summaries, or tagged sets from LoreDocs as context so Claude can answer questions using stored knowledge.
  Use when the user says "load my vault", "inject context from", "bring in my [project] docs", "load everything tagged", "give me a summary of my vault", "use my saved knowledge about", "load context for this project", or when starting a session where relevant vault knowledge should be active.
---

# LoreDocs: Context Injection

Context injection pulls stored documents into the active conversation so Claude can reference them without the user pasting content manually.

## Workflow: Load a Full Vault

When the user asks to load all documents from a vault:

1. Find the vault: `vault_list()` then match by name
2. Call `vault_inject(vault_id=..., max_docs=20, priority_filter=None)`
3. Confirm: "Loaded N documents from [vault name] into context."

Use `priority_filter="authoritative"` if the vault is large and the user wants only the most trusted content.

## Workflow: Load a Vault Summary

When the user wants an overview without loading all content:

1. Call `vault_inject_summary(vault_id=...)` to get a structured summary: doc count, tags, categories, recent activity
2. Present the summary in a readable format
3. Offer to load specific documents or tag groups if they want to drill in

## Workflow: Load by Tag

When the user wants documents on a specific topic:

1. Call `vault_inject_by_tag(tag="...", vault_id=None)` to load all docs with that tag across all vaults (or within a specific vault)
2. Confirm how many documents were loaded and from which vaults

## Workflow: Session Start Context

When starting a work session on a project:

1. Ask the user (or check context): which vault or project is relevant?
2. Call `vault_inject_summary` first to get the overview
3. If they need specific documents, call `vault_inject` or `vault_inject_by_tag`
4. Summarize what knowledge is now active

## Workflow: Find Related Documents

When the user asks what else is related to a document:

1. Call `vault_find_related(doc_id=..., limit=5)` to surface semantically related docs
2. Present the results with names and brief descriptions
3. Offer to load any of them

## Suggested Prompts

Guide the user with these example requests once context is loaded:

- "Summarize the key points from my loaded vault"
- "Answer my question using the loaded documents"
- "Which document covers [topic]?"
- "Compare the loaded documents on [topic]"

## Tips

- For large vaults, use `vault_inject_summary` first, then load specific documents on demand
- Tag important reference documents as "authoritative" so they can be filtered to the top
- Use `vault_inject_by_tag` when working on a specific topic that spans multiple vaults
