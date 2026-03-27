# Product Comparison Brief: Obsidian vs ConvoVault vs ProjectVault
**Date:** March 25, 2026
**Purpose:** Reference document for Labyrinth Analytics Consulting website content
**Context:** Debbie asked about how Obsidian Vaults compare to ConvoVault and ProjectVault. This brief captures the findings for use in website copy, blog posts, or product pages.

---

## Key Insight

Obsidian, ConvoVault, and ProjectVault solve the same fundamental problem -- preventing knowledge loss -- but for different audiences and time horizons:

| Tool | Audience | Time Horizon | Data Model | Interface |
|------|----------|-------------|------------|-----------|
| Obsidian | Humans | Everything (notes, ideas, journals) | Linked markdown files on disk | GUI editor + graph view |
| ConvoVault | AI agents | Session memory (what happened) | SQLite + FTS5, structured metadata | MCP tools (12) + CLI (6) |
| ProjectVault | AI agents | Project knowledge (what we know) | SQLite + FTS5, versioned docs | MCP tools (34) |

## Where They Overlap

**Obsidian + ConvoVault:** Both capture timestamped, searchable entries with tags. Both are local-first. The difference is audience -- Obsidian daily notes are for you to read, ConvoVault session records are for Claude to read.

**Obsidian + ProjectVault:** The biggest overlap. Both organize knowledge by project/topic with document linking. Both use plain-text-friendly storage. Obsidian is a human wiki; ProjectVault is an AI wiki.

**ConvoVault + ProjectVault:** Designed as companions. Same tech stack (SQLite + FTS5), same architecture (local-first, MCP-native, stdio transport). ConvoVault = "what did we discuss" (session memory). ProjectVault = "what do we know" (project knowledge). Together they give AI agents both working memory and long-term reference.

**All three:** Local-first storage, full-text search, knowledge persistence, tagging/categorization, and the core goal of remembering so you (or your AI) don't have to.

## Token Savings Argument (for website copy)

Without persistent memory, every Claude session starts from zero. Users burn 3,000-8,000 tokens per session re-explaining context, re-asking resolved questions, and redoing discovery.

With ConvoVault + ProjectVault:
- ConvoVault auto-loads top-scored recent sessions (~800 tokens, pre-filtered by signal)
- ProjectVault injects compact project summaries (~500 tokens)
- Prior decisions, open questions, and artifacts are already in context
- Estimated savings: ~2,000-6,000 tokens per session

Back-of-napkin math for a power user: ~4,000 tokens/session x 5 sessions/day x 22 working days = 440K tokens/month saved. At API pricing (~$3/M input tokens for Sonnet), that's ~$1.30/month direct savings. But the real value is fewer wasted turns, faster ramp-up, and more context window for actual work.

## Real Scenarios (for case studies / website examples)

1. **Ron's daily session:** Without ConvoVault, Ron needs the full CLAUDE.md re-read plus a manual summary of yesterday's work. With it, auto_load.py scores and injects the most relevant sessions in zero human effort.

2. **LiteLLM security audit (March 25, 2026):** Three separate sessions across two projects needed to know the audit result. ConvoVault lets each session find "litellm audit clean" via search instead of re-explaining the outcome each time.

3. **Tax pipeline context:** ProjectVault stores SAM's architecture docs, pipeline state, and form mappings. Instead of Claude re-discovering which nodes exist every session, vault_inject_summary provides the full map in ~500 tokens.

4. **Multi-surface continuity:** Start work in Claude Code on a Mac, continue in Cowork on a different machine. ConvoVault persists across all three surfaces (Code, Cowork, Chat).

## Future Integration Opportunity

An Obsidian MCP server could bridge all three tools:
- Let Claude read personal Obsidian notes for richer project context
- Write ConvoVault session summaries back as Obsidian pages for human browsing
- Sync ProjectVault docs to Obsidian for a unified knowledge graph

This is a Phase 2+ idea, not a Phase 1 priority.

## Available Visual Assets

All in `side_hustle/docs/`:

| File | Description | Use Case |
|------|-------------|----------|
| `knowledge_tools_venn_diagram.html` | Interactive 3-circle Venn diagram with click-to-explore zones + token savings section | Product comparison page, blog post |
| `convovault_projectvault_diagram.html` | Marketing-style product architecture diagram | Product landing pages, how-it-works section |
| `convovault_projectvault_sketch.html` | Hand-drawn sketch style diagram | Blog posts, social media, informal presentations |

## Messaging Angles for Website

1. **"Memory for your AI"** -- Obsidian is your second brain. ConvoVault + ProjectVault are your AI's second brain.
2. **"Stop re-explaining"** -- Focus on the pain of context loss between sessions.
3. **"Local-first, no cloud required"** -- Privacy and control, same philosophy as Obsidian.
4. **"Works across surfaces"** -- Code, Cowork, Chat. One memory layer for all three.
5. **"Designed as companions"** -- ConvoVault for conversations, ProjectVault for knowledge. Together they're the complete AI memory stack.
