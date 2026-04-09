# Competitive Intelligence Scan -- 2026-04-09

**Agent:** competitive-intel
**Scope:** LoreConvo (persistent memory), LoreDocs (knowledge management), Claude plugin ecosystem
**Research date:** 2026-04-09
**Prior scan:** competitive_scan_2026_04_06.md (3 days ago)

---

## Executive Summary

- **ALERT: Claude-Mem now at 44k+ stars** -- doubled since Apr 6 (was 21.5k). v11.0.0 shipped Apr 4 with 6 new corpus tools and Claude Code hooks (Stop + PreCompact). An OOM bug (Issue #1077: chroma-mcp processes not cleaned up) is a known weakness to monitor.
- **ALERT: MemPalace (INTAKE item) launched April 6 -- 23k+ stars in 2 days.** MIT, free, multi-platform (Claude, ChatGPT, Gemini, Cursor), ChromaDB + SQLite KG, 24 MCP tools, already has a Claude Code plugin (PR #188 April 8). Significant controversy over benchmark score claims, which were walked back from "100% perfect" to 96.6%. HIGH threat.
- **Ecosystem fragmentation accelerating** -- at least 5 new MCP memory plugins identified this scan (claude-mem, MemPalace, memory-store-plugin, claude-code-buddy, mcp-memory-keeper). The category is exploding.
- **Basic Memory upgraded to FastMCP 3.0** with hybrid vector+FTS search -- closes the biggest technical gap vs Lore.
- **Obsidian ecosystem growing as parallel track** -- multiple MCP tools bridge Obsidian vaults to Claude (mcp-obsidian: 3k stars). This is an adjacent LoreDocs threat for users already on Obsidian.

---

## Competitor Tables (Updated)

### LoreConvo Competitors (Persistent AI Memory)

| Competitor | Stars | Pricing | Threat | Change from Apr 6 | Key Differentiator |
|------------|-------|---------|--------|-------------------|-------------------|
| Claude-Mem | 44k | OSS | **HIGH** | Stars doubled (21.5k->44k); v11 with corpus tools + OOM bug | Claude Code-native, auto-capture, explosive growth |
| MemPalace | 23k | OSS (MIT) | **HIGH (NEW)** | Launched Apr 6; already has Claude Code plugin (Apr 8) | Multi-platform, palace architecture, viral (backed by celebrity brand) |
| Mem0 | ~52k | Freemium + MCP | HIGH | No change | Universal LLM support, Composio MCP integration active |
| Hindsight | 7.3k | OSS + Cloud | HIGH | No change | SOTA benchmarks, Claude Code integration (v0.4.20) |
| Basic Memory | ~3.2k | OSS + cloud sub | MEDIUM | Upgraded to FastMCP 3.0 + vector search (hybrid FTS+semantic) | MCP-native, markdown files, now with semantic search |
| memory-store-plugin | Unknown | OSS | LOW (NEW) | New entrant; julep-ai | Session lifecycle tracking (start/end/git/quality score) |
| claude-code-buddy | Unknown | OSS | LOW (NEW) | New entrant; PCIRCLE-AI | Minimal, decision/pattern memory only |
| mcp-memory-keeper | Unknown | OSS | LOW (NEW) | New entrant; mkreyman | Simple session context keeper |

### LoreDocs Competitors (AI Knowledge Management)

| Competitor | Stars | Pricing | Threat | Change from Apr 6 | Key Differentiator |
|------------|-------|---------|--------|-------------------|-------------------|
| MemPalace | 23k | OSS (MIT) | **HIGH (NEW)** | Launched Apr 6 -- knowledge graph (SQLite) stores structured relationships | Palace KG overlaps with vault use case |
| Basic Memory | ~3.2k | OSS + cloud sub | HIGH | FastMCP 3.0 + semantic vector search | Knowledge graph, markdown, now hybrid search |
| Obsidian MCPs (mcp-obsidian, mcpvault) | 3k / small | OSS | MEDIUM | Growing ecosystem; 3 ways to use Obsidian with Claude | Familiar tool for PKM users; zero-dependency options |
| ClaudeVault (Cannon07) | Unknown | OSS | LOW (NEW) | New; TypeScript MCP + Obsidian + Git sync | Cross-device sync via Git |
| NotebookLM + Claude MCP | N/A | Freemium (Google) | LOW-MEDIUM | NotebookLM added MCP support March 2026 | Research automation, multimodal, Google-backed |

### LoreScope Competitors (AI Workflow Analytics)

| Competitor | Stars | Pricing | Threat | Notes |
|------------|-------|---------|--------|-------|
| *(No direct competitor)* | -- | -- | -- | White space confirmed (unchanged) |

---

## Detailed Analysis

### MemPalace (milla-jovovich/mempalace) -- INTAKE ITEM PROCESSED

**URL:** https://github.com/milla-jovovich/mempalace
**Stars:** 23,000+ (launched April 6, 2026) | Forks: ~3,000 | License: MIT
**Site:** https://www.mempalace.tech/

**What they do:**
Local AI memory system combining ChromaDB (vector semantic search) with a SQLite temporal knowledge graph. Exposes 24 MCP tools (JSON-RPC 2.0 over stdio) to Claude, ChatGPT, Gemini, and Cursor. Organizes memory using a "palace" metaphor: Wings (projects/people) > Rooms (topics) > Tunnels (cross-references). Claims 96.6% Recall@5 on LongMemEval benchmark in "raw verbatim mode." AAAK lossy compression feature underperforms (authors publicly corrected benchmark claims downward from 100%). Can retroactively mine existing Claude/ChatGPT/Slack chat exports.

**Claude Code Plugin:** PR #188 (merged April 8) added a Claude Code plugin with hooks (Stop hook auto-saves every 15 human messages, PreCompact hook saves before context compression, 19 MCP tools pre-configured). This brings MemPalace into direct competition with LoreConvo at the plugin level, not just as an MCP server.

**Controversy:** Developers publicly questioned both the benchmark claims and the celebrity's (Milla Jovovich) genuine technical involvement. Cybernews, Hacker News, and Substack reviewers have raised credibility concerns. The score was revised from "100% perfect" to 96.6%. This is a real weakness: the brand may attract attention but also skepticism.

**Strengths vs LoreConvo:**
- Multi-platform (Claude + ChatGPT + Gemini + Cursor) vs LoreConvo's Claude-only focus
- Semantic vector search (ChromaDB) vs LoreConvo's FTS5 -- better fuzzy/conceptual recall
- Free forever (MIT) -- zero cost barrier
- Retroactive chat export mining -- can immediately onboard existing history
- 23k stars in 2 days -- extraordinary distribution/virality
- Palace metaphor is distinctive and memorable
- Knowledge graph (SQLite) gives it LoreDocs-adjacent capability

**Weaknesses vs LoreConvo:**
- Heavier install dependency (ChromaDB) vs LoreConvo's pure SQLite
- Benchmark controversy undermines trust
- No plugin packaging or official marketplace listing
- No tier gating or commercial model (pure OSS, no monetization path)
- No Cowork compatibility yet (Claude Code only via hooks)
- AAAK compression is acknowledged as underperforming
- Possible OOM/resource management issues at scale (ChromaDB is more resource-intensive)
- Celebrity-brand association may hurt credibility with technical users

**Threat level: HIGH.** Despite the controversy, MemPalace is now the second-largest threat (after Claude-Mem) purely by distribution velocity. The multi-platform story is a genuine differentiator LoreConvo does not have. The palace KG overlaps with LoreDocs use cases.

**Actions needed:**
- MADISON: Monitor controversy development -- if credibility collapse continues, publish a "Trust your memory tool" angle (accuracy and transparency over viral benchmarks). Contrarian positioning opportunity.
- MADISON: MemPalace's multi-platform story is their strongest card vs us. Respond with Cowork compatibility angle: "The only Claude memory plugin that works in BOTH Claude Code AND Claude Cowork." Multi-platform in both directions.
- GINA-REVIEW: MemPalace's retroactive chat export mining (Claude/ChatGPT/Slack) is a feature LoreConvo does not have. Evaluate import-from-export as a LoreConvo feature for user onboarding. Effort to get someone to switch: if they can bring their Claude history, they switch.
- RON: MemPalace has no Cowork support. LoreConvo Cowork compatibility is a differentiator to document and market explicitly. [FROZEN - post mandate]

---

### Claude-Mem (thedotmack/claude-mem) -- Threat Escalation

**URL:** https://github.com/thedotmack/claude-mem
**Stars:** 44,100+ (was 21,500 on Apr 6 -- nearly doubled in 3 days)
**Docs:** https://docs.claude-mem.ai

**New development since Apr 6:**
- v11.0.0 (Apr 4): 6 new corpus MCP tools (build_corpus, list_corpora, prime_corpus, query_corpus, rebuild_corpus, reprime_corpus) -- adds a structured knowledge corpus layer on top of raw session capture
- Added Ollama provider support -- no longer Claude-only for AI compression
- Added get_session MCP tool resolving memory_session_id to Claude Code session
- Listed on ClaudePluginHub (official/semi-official plugin directory)
- Dedicated docs site at docs.claude-mem.ai signals product maturity

**Known weakness confirmed:** Issue #1077: chroma-mcp processes are never cleaned up when Claude Code sessions end, causing memory leak / OOM. This is an active open issue and a real technical liability.

**Why the doubling matters:** This is not organic growth alone -- the v11 corpus tools appear to have triggered a fresh wave of discovery (Hacker News, Reddit). Claude-Mem is becoming the default "just install it" memory plugin for Claude Code developers.

**Threat level: HIGH (escalating).** The corpus tool addition means Claude-Mem is now encroaching on LoreDocs territory, not just LoreConvo. A tool that captures sessions AND organizes them into queryable corpora is a full knowledge vault competitor.

**Actions needed:**
- MADISON: "Claude-Mem has an OOM bug that eats your RAM" is a valid and accurate differentiator to publish. LoreConvo uses SQLite (zero background processes). Angle: "Lightweight memory that doesn't tax your machine."
- GINA-REVIEW: claude-mem's corpus model (build_corpus/prime_corpus) is an interesting pattern -- structured document sets queryable via vector search. Is this a design pattern LoreDocs should adopt? Evaluate overlap with vault model.
- RON: Document LoreConvo's resource profile (SQLite, no persistent background process, no ChromaDB) as a differentiation. [FROZEN - post mandate]

---

### Basic Memory -- Technical Gap Narrowed

**URL:** https://github.com/basicmachines-co/basic-memory
**Stars:** ~3,200 | Updated: April 2026

**New development since Apr 6:**
- Upgraded to FastMCP 3.0 (with tool annotations for better client integration)
- Added semantic vector search using FastEmbed (hybrid FTS + vector)
- This directly closes the "LoreConvo has FTS5, Basic Memory has neither FTS nor vectors" gap

**Why this matters for LoreDocs:** Basic Memory is now a capable hybrid-search knowledge vault. Its approach (plain Markdown files on disk, easy backup, git-friendly) directly mirrors LoreDocs' design philosophy. Users evaluating LoreDocs will also evaluate Basic Memory.

**Threat level: MEDIUM (upgraded from LOW-MEDIUM).** The FastMCP 3.0 + vector search upgrade is a meaningful technical advancement. However, Basic Memory lacks tier gating, commercial model, and multi-vault organization. LoreDocs remains differentiated on those axes.

**Actions needed:**
- GINA-REVIEW: LoreDocs needs a vector/semantic search story. Basic Memory now has hybrid FTS+vector (FastEmbed). LoreDocs has only FTS5. Is adding FastEmbed or similar a near-term technical priority? Claude-Mem and MemPalace also have semantic search. FTS5-only is becoming the minority approach.

---

### Obsidian Ecosystem -- Adjacent Threat Growing

**Relevant tools:**
- mcp-obsidian (MarkusPfundstein): 3,000 stars, requires Obsidian Local REST API plugin
- mcpvault (bitbonsai): Zero dependencies, reads raw .md files directly, BM25 search (last updated March 2026)
- ClaudeVault (Cannon07): TypeScript MCP, Obsidian + Git cross-device sync

**Why this matters:** There is a growing class of "use your Obsidian vault as LLM memory" workflows. For users already using Obsidian (a large PKM user base), these tools offer zero switching cost. LoreDocs targets users without an existing PKM workflow; Obsidian MCPs target users who already have one.

**Threat level: MEDIUM** for LoreDocs specifically. Obsidian MCPs are not Claude-native plugins; they require more setup. But their target user overlaps significantly with LoreDocs' most likely early adopters (knowledge workers, researchers, data professionals).

**Actions needed:**
- MADISON: LoreDocs vs Obsidian MCPs content angle: "If you're not already on Obsidian, don't start now just for AI memory -- LoreDocs is plugin-native and takes 30 seconds to install." Target non-Obsidian users. [Note on LoreDocs PROD item]
- GINA-REVIEW: Consider whether LoreDocs should offer an Obsidian import/bridge tool to capture users with existing vaults. Low-effort onboarding path.

---

## Product Gap Recommendations (MANDATORY)

| Product | Gap | Competitor(s) | Priority | Effort | Recommended Action |
|---------|-----|---------------|----------|--------|--------------------|
| LoreConvo | Semantic / vector search (fuzzy recall by meaning, not keyword) | MemPalace (ChromaDB), Basic Memory (FastEmbed hybrid), claude-mem (corpus tools) | P1 | Medium | GINA-REVIEW: Evaluate adding FastEmbed or sentence-transformers for hybrid FTS5 + semantic search. FTS5-only is now a minority approach in the category. |
| LoreConvo | Retroactive chat export import (mine existing Claude/ChatGPT/Slack history) | MemPalace | P2 | Medium | RON: Build import-from-export feature for Claude conversation history. Key onboarding accelerant -- users can bring their history. [FROZEN - post mandate] |
| LoreConvo | Cowork compatibility marketed explicitly as a differentiator | MemPalace (Claude Code only), claude-mem (Claude Code only), Basic Memory (no Cowork) | P1 | Low | MADISON: Add "Works in both Claude Code AND Claude Cowork" to all product copy and comparisons. This is a free win -- no code needed. |
| LoreDocs | Semantic / vector search | Basic Memory (FastEmbed hybrid), MemPalace (ChromaDB KG) | P1 | Medium | GINA-REVIEW: LoreDocs FTS5-only is behind competitors. Evaluate FastEmbed hybrid search as top technical priority post-mandate. |
| LoreDocs | Obsidian import / bridge | mcp-obsidian, mcpvault, ClaudeVault | P2 | Low | GINA-REVIEW: An Obsidian vault importer would capture a large existing user base. Evaluate effort to build a one-way import from .md files into LoreDocs vaults. |
| LoreConvo | Resource efficiency story (no background processes, SQLite only) | claude-mem (known OOM bug, chroma-mcp processes) | P1 | Low | MADISON: Publish "lightweight memory" angle. "LoreConvo runs on SQLite -- zero background processes, no RAM leaks." Directly addresses claude-mem's known OOM issue. |

**Notes on existing pipeline items:**
- Semantic search gap was tagged for GINA-REVIEW in the Apr 6 scan. This is a P1 escalation -- three competitors now have it vs LoreConvo's FTS5-only.
- Cowork compatibility marketing (P1, Low effort) is a near-term win that does not require code.

---

## INTAKE Items Processed

### MemPalace (milla-jovovich/mempalace)
- **Processed:** 2026-04-09 -- see competitive_scan_2026_04_09.md (HIGH threat, 2 pipeline items created: GINA-REVIEW retroactive import, MADISON multi-platform counter-positioning)

---

## Trend Comparison (Apr 6 vs Apr 9)

| Item | Apr 6 | Apr 9 | Direction |
|------|-------|-------|-----------|
| Claude-Mem stars | 21,500 | 44,100+ | NEGATIVE for Lore -- explosive growth |
| Claude-Mem corpus tools | No | Yes (v11.0.0) | NEGATIVE -- now encroaches LoreDocs |
| Claude-Mem OOM bug | Unknown | Confirmed (Issue #1077) | POSITIVE -- exploitable differentiator |
| MemPalace | n/a | 23k stars, Claude Code plugin | NEW HIGH THREAT |
| MemPalace benchmark controversy | n/a | Active -- score walked back | NEUTRAL/POSITIVE (trust angle) |
| Basic Memory vector search | No | Yes (FastMCP 3.0, FastEmbed) | NEGATIVE -- gap vs LoreDocs narrowed |
| Obsidian MCPs | Known | Growing ecosystem (3 tools confirmed) | NEGATIVE for LoreDocs |
| LoreScope competition | None confirmed | None confirmed | POSITIVE -- white space holds |
| Category fragmentation | Moderate | High -- 5+ new memory tools | NEGATIVE/NEUTRAL -- more noise, harder discovery |
