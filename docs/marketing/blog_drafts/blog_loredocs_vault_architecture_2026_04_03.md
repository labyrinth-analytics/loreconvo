---
title: "Building a Reference Library for AI Projects: How LoreDocs Vault Architecture Works"
date: 2026-04-03
author: Labyrinth Analytics
summary: "Your AI project knowledge should be organized and retrievable. LoreDocs uses semantic vaults instead of folders -- here is why that matters."
keywords: [LoreDocs, knowledge management, AI projects, semantic search, Claude, MCP server, data engineering]
products: [LoreDocs]
status: draft
---

# Building a Reference Library for AI Projects: How LoreDocs Vault Architecture Works

You have been working on a data pipeline for six months. In that time you have created:

- Schema design documents (three versions, only the latest is current)
- A runbook for deployment (updated twice)
- Architecture decision records for partitioning strategy, watermark approach, and CDC logic
- SQL performance tuning notes that contradict something from a meeting last month
- A design doc that was rejected but contains useful reasoning about why that approach will not work

All of this knowledge lives somewhere. Some is in Confluence, some in git README files, some in Notion, some in Slack threads you pinned three months ago. When you need to answer a question -- "did we decide on event sourcing or CDC?" -- you have to remember which document to search, hope it is in the right tool, and dig through multiple versions.

That is the reference knowledge problem. It is different from the session memory problem (which LoreConvo solves). It is more about organized, discoverable, canonical knowledge that you want to retrieve by topic rather than by time.

## The Difference: Episodes vs. Reference Knowledge

This distinction matters.

LoreConvo is *episodic*. It captures the timeline of what happened in your sessions. "On Tuesday we decided on watermark architecture" is an episode. Sessions are timestamped. They answer the question: what happened when?

LoreDocs is *semantic*. It is the reference library. "The canonical architecture for our incremental load is watermark-based" is reference knowledge. It is not timestamped in the same way -- the knowledge is current until you update it. Vaults answer the question: what is true now?

If you are working on a project and need to know "what did we decide last week about the partitioning strategy," you ask LoreConvo. If you need to know "what is the standard partitioning strategy we use," you ask LoreDocs.

Both matter. Most knowledge management tools try to be both and end up being good at neither.

## How Vaults Work

A LoreDocs vault is a semantic namespace. It is not a folder. It is a collection of documents organized around a topic, with automatic indexing, cross-linking, and version tracking.

Here is what a typical LoreDocs vault looks like for a data engineering project:

```
[Architecture Vault]
  - Partition Strategy (current version: v2, Feb 2026)
  - Incremental Load Patterns (current: v1)
  - Date Handling Standards (current: v3, overwrites v1 from Jan)
  - Schema Evolution Policy (current: v2)
  - Rate Limiting & Retry Logic (current: v1)

[Operations Vault]
  - Deployment Runbook (v3, latest tested)
  - Troubleshooting Guide (v2)
  - Monitoring & Alerting Setup (v2)

[SQL Patterns Vault]
  - Window Function Patterns (v4, most recent)
  - Partition Pruning Examples (v2)
  - Type Casting Gotchas (v1, flagged for review)
```

Each vault is independent. Architecture decisions live in the Architecture vault. Operational procedures live in Operations. SQL patterns live in the SQL Patterns vault. When you search or retrieve, you search within the vault and get current documents without wading through deprecated versions.

## The Semantic Search Layer

LoreDocs uses semantic search instead of full-text keyword matching. That sounds like a technical detail, but it changes how you interact with your own knowledge.

With keyword search, you need to remember the exact term the document used. "If the doc calls it 'watermark pattern' vs. 'timestamp tracking,' will I find it?" With semantic search, you ask in your own words and LoreDocs finds the relevant document regardless of terminology.

Example: you ask "how do we handle slowly changing dimensions?" The semantic search layer understands that your question is about dimension management, even though the canonical document calls it "Schema Evolution Policy." It returns the right document.

The search also works backwards. When you retrieve an architecture document, LoreDocs can automatically link related documents from other vaults. You pull up the Partition Strategy, and it shows "also relevant: Rate Limiting & Retry Logic" because those decisions are linked in the knowledge graph.

## Version Control Built In

Every document has an implicit version history. When you update a doc in a vault, you do not overwrite it -- you create a new version with a timestamp. LoreDocs tracks the lineage.

This means you can answer questions like:
- "What was our partition strategy in January?" (retrieve v1)
- "What changed between the partition strategy v1 and v2?" (compare)
- "Why did we change from event sourcing to CDC?" (the decision record explains it)

Deprecated documents are not deleted. They stay in the vault but are marked as superseded. If someone new joins the project and finds the old event sourcing design, they see "superseded by CDC approach (Feb 2026)" and know to read the newer version.

## Why Not Just Use Confluence/Notion/Shared Drive?

These tools are good for general documentation. But they have a few problems for technical projects:

**Organization by hierarchy.** Folders (or pages, or nested databases) force you to make structural choices upfront. "Is this a SQL pattern or an architecture decision?" You guess wrong and it gets lost in the wrong category.

**Weak search.** Full-text search finds keywords but misses intent. You search for "incremental" and get 47 results, half of which are not relevant.

**Version chaos.** Most tools have "make a copy" culture or a "version 1, version 1 final, version 1 final REAL" naming convention. The canonical version is unclear.

**Stale documents.** The latest doc is somewhere, but you do not know if the one you found has been superseded. There is no "this doc was replaced by X" link.

**No cross-linking.** The Partition Strategy doc does not automatically know that Rate Limiting & Retry Logic are related. You have to remember to add manual links.

LoreDocs is designed specifically for this: technical knowledge that needs to be current, retrievable, and connected.

## A Concrete Example

Here is how this works in practice. You are onboarding a new engineer to a data pipeline project.

In the old way:
1. You point them to a Confluence space with 40 pages
2. They read the outdated v1 partition strategy doc (you did not realize it was stale)
3. They ask you "should we use event sourcing or CDC?" and you realize they read the wrong doc
4. You spend 30 minutes explaining what is actually current

With LoreDocs:
1. You give them access to the project vaults
2. They ask Claude (with LoreDocs enabled) "what is our partition strategy"
3. Claude retrieves the current Partition Strategy document from the Architecture vault
4. They also get "related: Rate Limiting & Retry Logic" because the docs are linked
5. They see the document version is v2 (Feb 2026) and know it is current
6. No confusion. No stale information.

The knowledge is organized semantically. It is discoverable without needing to know the project folder structure. Versions are tracked. Related docs are connected. That is the vault architecture.

## Integration with Your AI Workflow

LoreDocs is built for AI projects. It integrates as an MCP server, which means Claude can query your vaults directly.

When you work in Claude Code or Cowork:

**At session start:** Claude can query your vaults and inject relevant reference knowledge automatically. If you are working on the partition strategy, the relevant architecture doc is already in context.

**During development:** You can ask Claude questions that reference your vaults. "Is this approach consistent with our Rate Limiting & Retry Logic doc?" Claude has access to the actual doc, not your paraphrase.

**Documentation-as-you-go:** When you finish a design decision, you add it to the relevant vault immediately. No separate documentation pass later. The knowledge is captured while the decision is fresh.

**Agent workflows:** If you run autonomous agents (like we do at Labyrinth Analytics), each agent has access to the shared vault. The QA agent reads the same architecture docs as the builder. The deployment agent reads the same runbook. No version mismatch between agents.

## What LoreDocs Is (And Is Not)

LoreDocs is for reference knowledge: canonical decisions, current standards, design patterns, runbooks, architecture choices.

LoreDocs is *not* for:
- Session timelines (that is LoreConvo)
- Raw conversation history
- Project chat or comments (that stays in your normal comms tools)
- Every thought you have

The idea is that you write documents the way you would write them anyway, but instead of emailing them, you put them in a vault. LoreDocs handles the organization, versioning, search, and linking. You maintain the knowledge. LoreDocs maintains the structure.

## Current Status: Alpha

LoreDocs v0.1.0 is in alpha. It is production-ready for organizing and searching your reference knowledge, but the installation and team collaboration features are still being built out.

You can:
- Create vaults
- Add documents with semantic indexing
- Search across vaults
- Retrieve documents by topic
- Track document versions
- Access from Claude Code and Cowork via the MCP server

You cannot (yet):
- Share vaults with teams (coming soon)
- Publish vaults to a web URL
- Set document permissions
- Auto-sync from external sources (Git, Confluence, etc.)

Free tier covers a practical workload for a solo project or small team. Pro tier (coming soon) will support larger knowledge bases and team features.

## Getting Started

If you are building on a data pipeline, running an AI project, or managing any ongoing technical work, you should have a reference library. Right now most people improvise -- scattered docs in multiple tools, stale information, no way to know what is current.

LoreDocs handles the structure so you do not have to think about it.

[Get started with LoreDocs -- alpha access available](https://labyrinthanalyticsconsulting.com/tools)

---

*Labyrinth Analytics Consulting helps organizations navigate the dark corners of their data. Learn more at [labyrinthanalyticsconsulting.com](https://labyrinthanalyticsconsulting.com).*
