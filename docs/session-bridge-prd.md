# LoreConvo: Product Requirements Document
*Vault your Claude conversations. Never re-explain yourself again.*

**Author:** Debbie / Labyrinth Analytics Consulting
**Date:** March 22, 2026
**Status:** Draft v0.1

---

## Problem Statement

Claude users who work across multiple surfaces — Cowork, Code, and Chat — lose all conversational context every time they switch tools or start a new session. Key decisions, architectural choices, naming conventions, and domain knowledge discussed in one session are invisible to the next. Users compensate by manually maintaining context files (like CLAUDE.md), copy-pasting summaries, or simply re-explaining everything from scratch. This costs real time, real tokens, and real frustration — and it's a universal pain point across the Claude ecosystem.

## Goals

1. **Eliminate context re-entry**: Users should be able to start a new Claude session (in any surface) and have relevant prior decisions, summaries, and artifacts available automatically or on-demand.
2. **Capture session knowledge passively**: Session summaries should be generated with minimal user effort — ideally zero-click via hooks, or one-click via slash command.
3. **Enable cross-session search**: Users should be able to ask "What did I decide about X?" and get an answer grounded in actual session history.
4. **Support business persona workflows**: The same memory infrastructure should support persistent personas (like the Ron bot) that need stable context across interactions.
5. **Ship as a monetizable plugin**: Deliver as a Cowork/Code plugin with a clear free-to-paid upgrade path.

## Non-Goals

- **Real-time session sharing between concurrent sessions.** This is a collaboration feature, not a memory feature. Out of scope for v1.
- **Full Chat integration via API.** Claude Chat has no programmatic access to conversation history. We'll provide a paste-friendly export format, but bidirectional sync is not possible until Anthropic builds that.
- **Replacing CLAUDE.md.** LoreConvo complements manual context files — it captures what CLAUDE.md can't (the full history of decisions and artifacts across sessions).
- **Multi-user/team memory.** v1 is single-user, local-first. Team features are a v2 consideration.
- **Audio/video transcript ingestion.** Text-based session memory only for now.

---

## Competitive Landscape

The AI memory space is active but fragmented. As of March 2026, ~10+ MCP memory servers exist, but all are scoped to a single tool or surface. Nobody is building what LoreConvo targets: cross-product memory with project awareness, skill tracking, and persona support.

### Direct Competitors

**OpenMemory by Mem0** — The 800-pound gorilla. Mem0 raised $24M (backed by CEOs of Datadog and GitHub). OpenMemory is a local-first MCP server that works across Cursor, VS Code, Claude Code, and Windsurf. It stores memories as key-value pairs, supports semantic search, and runs entirely on-device. Pricing: Free (10K memories), $19/mo Starter, $249/mo Pro with graph memory and analytics.

- *Strengths:* Brand recognition, VC funding, multi-editor support, knowledge graph in pro tier.
- *Weaknesses:* No cross-product bridging (Code to Cowork to Chat). No project or persona organization. Memory is generic (key-value), not structured around decisions/artifacts/sessions. $249/mo Pro tier is expensive for individuals. No autonomous agent (Ron-type) use case support.

**ContextStream** — Cloud-based MCP server providing persistent memory and code intelligence. Indexes your codebase, tracks decisions, offers impact analysis and knowledge graphs. Works with Cursor, Claude Code, VS Code, Windsurf.

- *Strengths:* Decision history tracking, semantic code search, team collaboration features.
- *Weaknesses:* Cloud-first (privacy concerns, latency, cost). Code-focused — not designed for non-coding sessions. No pricing transparency. No persona/project tagging.

**MCP Memory Service (doobidoo)** — Open-source persistent memory for AI agent pipelines (LangGraph, CrewAI, AutoGen) and Claude. REST API + knowledge graph + autonomous consolidation.

- *Strengths:* Open-source, supports multiple agent frameworks, knowledge graph with consolidation.
- *Weaknesses:* Infrastructure-heavy (requires vector store setup). Developer-focused, not end-user friendly. No plugin packaging for Cowork marketplace.

**MCP Backpack** — Stores per-project memory that survives across sessions and transfers via git. Lightweight, developer-friendly.

- *Strengths:* Git-portable, project-scoped, simple mental model.
- *Weaknesses:* Code-only. No search across projects. No persona support. No structured decision/artifact capture.

**mcp-memory-keeper** — Minimal MCP server for preserving work history, decisions, and progress in Claude Code specifically.

- *Strengths:* Lightweight, Claude-Code-specific, preserves decisions.
- *Weaknesses:* Single-surface only. No Cowork or Chat support. No project/persona features.

### Indirect Competitors

**Claude's Built-in Memory Systems** — Claude Code has auto-memory (MEMORY.md), Chat has project-level memory, Cowork resets every session. These are separate, non-communicating systems.

- *Risk level:* HIGH. Anthropic could unify these at any time. However, as of March 2026, there's an open feature request (Issue #14227) with significant community demand and no official response. Cross-product memory appears to be a known gap without a near-term fix.

**CLAUDE.md / Manual Context Files** — The DIY approach. Power users maintain hand-curated context files that persist across sessions.

- *This is what LoreConvo replaces.* Manual curation works but doesn't scale, isn't searchable, and requires discipline to maintain.

### Competitive Positioning Matrix

| Capability                        | LoreConvo | OpenMemory | ContextStream | MCP Backpack | Built-in Memory |
|-----------------------------------|:-:|:-:|:-:|:-:|:-:|
| Cross-product (Code+Cowork+Chat)  | Y | - | - | - | - |
| Structured sessions (not just KV) | Y | - | Y | - | - |
| Project organization              | Y | - | Y | Y | - |
| Persona tagging                   | Y | - | - | - | - |
| Skill tracking                    | Y | - | - | - | - |
| Autonomous agent support (Ron)    | Y | - | - | - | - |
| Local-first / SQLite              | Y | Y | - | Y | Y |
| Semantic search                   | P2 | Y | Y | - | - |
| Knowledge graph                   | - | Pro | Y | - | - |
| Team collaboration                | P2 | - | Y | - | - |
| Plugin marketplace distribution   | Y | - | - | - | N/A |
| Price (individual)                | $8/mo | $19/mo | Unknown | Free/OSS | Free (built-in) |

### Competitive Strategy

**Positioning:** LoreConvo is not "another memory MCP server." It's the first cross-surface memory layer for the Claude ecosystem, purpose-built for users who work across Code, Cowork, and Chat — and for autonomous agents that need persistent customer context.

**Differentiation levers:**
1. *Cross-product bridging* — the only tool that unifies memory across Claude Code, Cowork, and Chat. Nobody else does this.
2. *Persona-tagged memory* — designed for the emerging "AI business agent" use case (Ron, customer-facing bots). No competitor supports this.
3. *Skill and project tracking* — sessions organized by what tools were used, not just keywords. Unique to LoreConvo.
4. *Price advantage* — $8/mo vs Mem0's $19/mo Starter or $249/mo Pro. Undercut the funded competitor on the features that matter most to Claude users.

**Anthropic risk mitigation:** If Anthropic builds native cross-product memory, LoreConvo's persona/project/skill features become the moat. Anthropic will build generic memory; we build memory organized around your business.

---

## User Stories

### Power User (Debbie-type: Claude Code + Cowork daily)

- As a power user, I want my new Cowork session to know what I decided in yesterday's Code session so that I don't waste 10 minutes re-explaining my project architecture.
- As a power user, I want to search across all my past sessions by topic so that I can find when and where I made a specific technical decision.
- As a power user, I want session summaries captured automatically when I end a session so that I don't have to remember to export anything.

### Business Persona Operator (Ron bot use case)

- As a persona operator, I want my business bot to have access to a persistent knowledge base built from past sessions so that it maintains consistent context about clients, proposals, and business decisions.
- As a persona operator, I want to tag certain session memories as "persona-relevant" so that only the right context loads for the right persona.

### Casual User (occasional Claude user)

- As a casual user, I want to see a list of my recent sessions with titles and dates so that I can pick up where I left off.
- As a casual user, I want to paste a session summary into Chat so that I can continue a conversation that started in Code or Cowork.

---

## Requirements

### Must-Have (P0)

**1. Session Capture**
- Automatically extract session summary when a session ends (via hook) or on-demand via slash command `/vault save`
- Capture: session title, start date, duration estimate, key decisions, artifacts created/modified, open questions, and a 2-3 paragraph narrative summary
- Store in local SQLite database at a configurable path
- Acceptance criteria:
  - [ ] Running `/vault save` in Code or Cowork produces a session record in SQLite
  - [ ] Hook-based capture fires on session end without user action
  - [ ] Summary includes decisions, artifacts, and open questions — not just a transcript dump

**2. Session Recall (MCP Tools)**
- `get_recent_sessions(limit, days_back)` — list recent sessions with titles and dates
- `get_session(session_id)` — full session detail
- `search_sessions(query, persona?, tags?)` — semantic keyword search across session summaries
- `get_context_for(topic)` — return relevant session fragments for a given topic
- Acceptance criteria:
  - [ ] LLM can call `search_sessions("K-1 parser")` and get relevant results
  - [ ] Results include session title, date, and the relevant excerpt
  - [ ] Search returns results in under 500ms for databases with 1000+ sessions

**3. Session Export (CLI)**
- `loreconvo export [session_id]` — export a session summary as markdown (paste-friendly for Chat)
- `loreconvo list` — list recent sessions in terminal
- `loreconvo search <query>` — search from command line
- Acceptance criteria:
  - [ ] `loreconvo export` produces clean markdown that can be pasted into Chat
  - [ ] Output includes a "Context for Claude" preamble that primes a new session

**4. SQLite Schema**
- Sessions table: id, title, start_date, end_date, surface (cowork/code/chat), summary_narrative, decisions_json, artifacts_json, open_questions_json, tags_json
- Persona associations table: session_id, persona_name
- Skill tracking table: session_id, skill_name, skill_source, invocation_count
- Projects table: name, description, expected_skills, default_persona
- Full-text search index on summary_narrative and decisions
- Acceptance criteria:
  - [ ] Schema supports FTS5 for fast keyword search
  - [ ] All JSON fields are queryable
  - [ ] Database file is portable (single file, no external dependencies)

**5. Skill & Project Tracking**
- Record which skills were invoked during each session (auto-detected from transcript or explicitly passed)
- Define projects with expected skill sets for auto-association
- Query sessions by skill (`get_skill_history("rental-property-accounting")`) or project (`get_project("secret-agent-man")`)
- Acceptance criteria:
  - [ ] `save_session` accepts a `skills_used` array and persists to `session_skills` table
  - [ ] `search_sessions` supports filtering by `skills` parameter
  - [ ] `get_project` returns project details with recent session list and skill usage breakdown
  - [ ] Sessions using 2+ expected skills from a project are flagged for auto-association

### Nice-to-Have (P1)

**6. Persona Context Filtering**
- Tag sessions with persona names (e.g., "ron-bot", "tax-prep", "labyrinth")
- `get_persona_context(persona_name)` returns only sessions tagged for that persona
- Enables the Ron bot to load only business-relevant memory
- Acceptance criteria:
  - [ ] Sessions can be tagged with multiple personas
  - [ ] Persona query returns only relevant sessions, ordered by recency

**7. Auto-Summarization via LLM**
- Use the current session's LLM to generate structured summaries (not just raw text)
- Extract decisions, artifacts, and questions into structured fields automatically
- Acceptance criteria:
  - [ ] Summaries are structured JSON, not freeform text
  - [ ] Extraction quality is validated against 10 sample sessions

**8. Session Linking**
- Link related sessions ("this session continues from session X")
- `get_session_chain(session_id)` returns the full thread of linked sessions
- Acceptance criteria:
  - [ ] Users can link sessions via `/vault link <session_id>`
  - [ ] Chain traversal returns sessions in chronological order

### Future Considerations (P2)

**9. Cloud Sync** — Sync SQLite to a cloud backend (Supabase, Turso) for cross-device access. This is the primary monetization unlock.

**10. Team Memory** — Shared session context for teams. Requires auth, access control, and conflict resolution.

**11. Smart Context Loading** — Automatically load relevant session context at session start based on the working directory, recent files, or initial prompt — without the user asking.

**12. Analytics Dashboard** — Visualize session history, topic frequency, decision patterns over time.

---

## Technical Architecture

### Plugin Structure

```
loreconvo/
  .claude-plugin/
    plugin.json
  skills/
    loreconvo/
      SKILL.md                    # Main skill: triggers, instructions
      references/
        schema.md                 # SQLite schema reference
        export-formats.md         # Export template definitions
  .mcp.json                       # MCP server config (points to Python server)
  src/
    server.py                     # FastMCP server (MCP interface)
    cli.py                        # Click CLI (human interface)
    core/
      database.py                 # SQLite operations, FTS5 search
      summarizer.py               # Session summary extraction logic
      models.py                   # Dataclasses for Session, Decision, Artifact
    config.py                     # Paths, defaults, persona config
```

### Dual Interface Design

```
                   [Human]                    [LLM]
                      |                          |
              loreconvo CLI          MCP Tools (FastMCP)
                      |                          |
                      +--- core/ library ---------+
                              |
                         SQLite (FTS5)
```

Both interfaces call the same core library. The CLI wraps it for terminal use (click). The MCP server wraps it for LLM use (FastMCP). No logic duplication.

### Skill & Project Tracking

**Why track skills?** Skills are the strongest signal of what a session was about. If a session invoked `rental-property-accounting` and `multi-property-tax-prep`, you know it was a rental tax session without reading a word of the summary. This enables:

- **Smart context loading**: "Load context for my rental work" resolves to `search_sessions(skills=["rental-property-accounting"])` — no fuzzy keyword matching needed.
- **Project auto-association**: Define a project with expected skills, and sessions automatically associate when those skills fire. A session that uses `us-federal-tax` + `retirement-planning` auto-tags to the "tax-prep" project.
- **Ron skill attribution**: When Ron's SQL Optimizer skill fires, that session auto-tags to `project:ron` + `persona:ron-bot:sql`. Customer memory is organized by product line without manual tagging.
- **Usage analytics**: Which skills get used most? Which projects are most active? This feeds into Ron's marketplace analytics — if the SQL Optimizer skill is invoked 3x more than the CSV Transformer, that's a signal about demand.

**How skills are captured:** During `save_session`, the caller passes a `skills_used` array. In Cowork/Code, this can be auto-detected from the session transcript (skills leave traces like "The skill-name skill is loading"). In Chat, the user lists them manually or they're inferred from the summary.

**Projects as session organizers:** A project is a named group with an expected skill set and optional default persona. When you create a project like:

```json
{
  "name": "secret-agent-man",
  "description": "Finance automation - tax prep, portfolio, rental accounting",
  "expected_skills": ["us-federal-tax", "rental-property-accounting", "retirement-planning",
                       "multi-property-tax-prep", "financial-data-validation"],
  "default_persona": "tax-prep"
}
```

...then any session that uses 2+ of those skills gets auto-suggested for that project. The LLM can also explicitly set `project: "secret-agent-man"` when saving.

### SQLite Schema (Draft)

```sql
CREATE TABLE sessions (
    id              TEXT PRIMARY KEY,   -- UUID
    title           TEXT NOT NULL,
    surface         TEXT NOT NULL,       -- 'cowork', 'code', 'chat'
    project         TEXT,                -- project name if part of a defined project
    start_date      TEXT NOT NULL,       -- ISO 8601
    end_date        TEXT,
    summary         TEXT,                -- narrative summary
    decisions       TEXT,                -- JSON array
    artifacts       TEXT,                -- JSON array
    open_questions  TEXT,                -- JSON array
    tags            TEXT,                -- JSON array
    created_at      TEXT DEFAULT (datetime('now'))
);

CREATE VIRTUAL TABLE sessions_fts USING fts5(
    title, summary, decisions, content=sessions, content_rowid=rowid
);

-- Skills used during this session (auto-detected or manually tagged)
CREATE TABLE session_skills (
    session_id      TEXT NOT NULL REFERENCES sessions(id),
    skill_name      TEXT NOT NULL,       -- e.g. 'rental-property-accounting', 'us-federal-tax'
    skill_source    TEXT,                -- 'local', 'plugin:engineering', 'plugin:data', etc.
    invocation_count INTEGER DEFAULT 1,  -- how many times it was called
    PRIMARY KEY (session_id, skill_name)
);

-- Projects group related sessions and define expected skill sets
CREATE TABLE projects (
    name            TEXT PRIMARY KEY,    -- e.g. 'secret-agent-man', 'project-ron', 'labyrinth'
    description     TEXT,
    expected_skills TEXT,                -- JSON array of skill names typically used
    default_persona TEXT,                -- auto-tag sessions with this persona
    created_at      TEXT DEFAULT (datetime('now'))
);

CREATE TABLE persona_sessions (
    persona_name    TEXT NOT NULL,
    session_id      TEXT NOT NULL REFERENCES sessions(id),
    relevance_note  TEXT,
    PRIMARY KEY (persona_name, session_id)
);

CREATE TABLE session_links (
    from_session_id TEXT NOT NULL REFERENCES sessions(id),
    to_session_id   TEXT NOT NULL REFERENCES sessions(id),
    link_type       TEXT DEFAULT 'continues',  -- 'continues', 'related', 'supersedes'
    PRIMARY KEY (from_session_id, to_session_id)
);
```

### MCP Tool Definitions

| Tool                  | Parameters                                  | Returns                          |
|-----------------------|---------------------------------------------|----------------------------------|
| `save_session`        | title, surface, summary, decisions, skills_used, project?, etc. | session_id              |
| `get_recent_sessions` | limit (default 10), days_back (default 30), project?, skill? | List of session summaries |
| `get_session`         | session_id                                  | Full session record + skills used |
| `search_sessions`     | query, persona?, tags?, skills?, project?, limit? | Ranked list of matching sessions |
| `get_context_for`     | topic, max_results?                         | Relevant excerpts across sessions|
| `tag_session`         | session_id, persona_name, relevance_note?   | Confirmation                     |
| `link_sessions`       | from_id, to_id, link_type?                  | Confirmation                     |
| `get_project`         | project_name                                | Project details + recent sessions + skill usage stats |
| `list_projects`       | (none)                                      | All projects with session counts  |
| `create_project`      | name, description, expected_skills?, default_persona? | Confirmation             |
| `get_skill_history`   | skill_name, days_back?                      | All sessions that used this skill |

---

## Ron Bot Integration Points

LoreConvo isn't just a standalone product — it's a critical piece of infrastructure for Project Ron (the autonomous AI agent business targeting $8K/month). Here's how they fit together:

### LoreConvo as Ron's Memory Layer

Ron's biggest limitation as an autonomous agent is context loss between sessions. Whether Ron is handling customer support for ClawHub skills, generating financial reports, or processing CSV transformations, he needs to remember what happened in previous interactions. LoreConvo gives Ron a persistent memory without requiring a custom database for each skill.

**Concrete integration for Ron's Phase 1 skills:**

1. **SQL Query Optimizer** — Ron tags customer sessions by company/user. When a returning customer asks "optimize this query," Ron calls `search_sessions(persona="ron-bot", tags=["sql-optimizer", "customer:acme"])` and loads prior query patterns, schema context, and optimization preferences. The customer gets personalized service without re-explaining their database.

2. **Financial Report Generator** — Ron remembers a client's chart of accounts, reporting preferences, and prior period data. Each report generation session builds on the last. This is a major differentiator over competitors whose agents start fresh every time.

3. **CSV/Excel Data Transformer** — Ron remembers column mappings, transformation rules, and data quality issues from previous uploads for each customer. "Clean this file the same way as last month" just works.

### LoreConvo as a Revenue Multiplier

LoreConvo fits into Project Ron's revenue model in two ways:

**Direct revenue (Model C — Claude Plugin):** LoreConvo itself is a sellable Claude plugin. At $8/month Pro tier, it's one of the 2-3 plugins in Ron's Phase 1 portfolio. It targets power users who already feel the cross-session pain — exactly the audience who also buys Ron's other skills.

**Indirect revenue (competitive moat):** Any Ron skill backed by LoreConvo memory has a retention advantage. Customers who've built up session history with Ron's tools have switching costs. Their context, preferences, and patterns are stored locally — they lose all of that if they switch to a competitor's agent. This is the kind of lock-in that doesn't feel exploitative because users genuinely benefit from the accumulated context.

### Architecture Alignment with Ron's Hybrid Platform Strategy

Per the Project Ron plan, the recommended architecture is Claude for quality/reliability + NemoClaw for always-on execution. LoreConvo's SQLite-first design supports this perfectly:

- **Claude sessions** write to the same SQLite DB as **NemoClaw sessions**
- Ron running locally on NemoClaw can read context from earlier Claude Code sessions
- The DB file lives on the local machine — no cloud dependency, no API costs for memory access
- If/when cloud sync is added (Business tier), it enables cross-device Ron deployment

### Persona Tagging Schema for Ron

```
Personas:
  ron-bot           → All Ron business operations
  ron-bot:support   → Customer support interactions
  ron-bot:sql       → SQL Optimizer skill sessions
  ron-bot:finance   → Financial Report Generator sessions
  ron-bot:transform → CSV/Excel Transformer sessions
  tax-prep          → Debbie's personal tax work (excluded from Ron)
  labyrinth         → Consulting business (may overlap with Ron)
```

This hierarchical tagging means Ron can load broad context (`persona:ron-bot`) or narrow context (`persona:ron-bot:sql`) depending on the task.

---

## Monetization Strategy

### Free Tier (Plugin)
- Local SQLite storage
- Manual save via `/vault save`
- Basic search (keyword)
- 100 session limit
- Single persona

### Pro Tier ($8/month)
- Unlimited sessions
- Auto-capture via hooks
- Multiple personas
- Session linking and chains
- Export to markdown/JSON
- Priority support

### Business Tier ($20/month)
- Everything in Pro
- Cloud sync (cross-device)
- Semantic search (embedding-based)
- Analytics dashboard
- API access for custom integrations
- Team memory (when available)

### Revenue Projection (Conservative)
- Target: 500 free users in first 3 months (plugin marketplace)
- 10% conversion to Pro = 50 paying users = $400/month
- 2% conversion to Business = 10 paying users = $200/month
- Month 3 run rate: ~$600/month, growing with marketplace traffic

---

## Success Metrics

### Leading (Weeks 1-4)
- Plugin installs: 200+ in first month (success), 500+ (stretch)
- `/vault save` usage: 3+ saves per active user per week
- Search queries: 5+ per active user per week
- Session recall accuracy: users find relevant context 80%+ of the time

### Lagging (Months 2-6)
- Free-to-paid conversion: 8%+ (success), 15%+ (stretch)
- Monthly recurring revenue: $500+ by month 3
- Net promoter score: 40+ among active users
- Feature requests for team/cloud sync: signals demand for Business tier

---

## Open Questions

| Question | Owner | Blocking? |
|----------|-------|-----------|
| What is Anthropic's plugin marketplace timeline and revenue share model? | Research | Yes — affects pricing |
| Can Cowork hooks fire on session end reliably, or do we need a heartbeat approach? | Engineering | Yes — affects auto-capture |
| Should semantic search (embeddings) be in Pro or Business tier? | Product | No |
| What's the Ron bot's current architecture? Need doc upload to design integration. | Debbie | No — can build persona tagging generically |
| Is there a rate limit or cost concern with using the session LLM for summarization? | Engineering | No — can use simple extraction as fallback |
| What's the IP/licensing situation for a plugin that reads Claude session transcripts? | Legal | Yes — need to check ToS |

---

## Timeline (Aligned with Project Ron Phases)

### LoreConvo Phase 1: MVP — aligns with Ron Phase 1, Weeks 1-3
- SQLite schema + core library (Python, dataclasses)
- CLI via Click (save, list, search, export)
- MCP server via FastMCP (4 core tools: save, get_recent, search, get_context_for)
- Plugin packaging (.plugin file for Cowork/Code)
- Manual save only (no hooks yet)
- **Milestone:** Debbie uses it daily across her own Code/Cowork sessions
- **Milestone:** LoreConvo is one of Ron's first Claude plugin listings

### LoreConvo Phase 2: Personas + Auto-Capture — aligns with Ron Phase 2, Weeks 4-8
- Hook-based auto-capture on session end
- Persona tagging and filtering (ron-bot, tax-prep, labyrinth hierarchies)
- Session linking and chains
- Ron's skills (SQL Optimizer, Financial Report Gen, CSV Transformer) call LoreConvo for customer memory
- **Milestone:** Ron's skills demonstrate returning-customer memory in demos

### LoreConvo Phase 3: Monetization — aligns with Ron Phase 3, Weeks 9-16
- Feature gating (free: 100 sessions, manual save, 1 persona | pro: unlimited)
- Salable billing integration (same platform Ron uses for other skills)
- Export formats (markdown for Chat paste, JSON for programmatic use)
- LoreConvo listed on Claude Marketplace + promoted alongside Ron's skills
- **Milestone:** First paying customers on Pro tier

### LoreConvo Phase 4: Cloud + Scale — aligns with Ron Phase 4, Month 5+
- Cloud sync via Turso (SQLite-compatible, edge-distributed)
- Semantic search (embedding-based, uses local model on NemoClaw or Claude API)
- Analytics dashboard (session frequency, topic heatmap, persona usage)
- Team memory (shared session context for teams — Business tier)
- API access for custom integrations
- **Milestone:** Business tier customers, $200+/month from LoreConvo alone

---

## Appendix: Relationship to Other Debbie Projects

| Project | How LoreConvo Helps |
|---------|------------------------|
| **Project Ron** | Ron's memory layer. Every Ron skill gets persistent customer context. LoreConvo is also a sellable plugin in Ron's portfolio. |
| **Secret Agent Man (Tax Prep)** | Tax pipeline decisions, config choices, and year-over-year patterns persist across sessions. No more re-explaining depreciation schedules. |
| **Labyrinth Analytics Consulting** | Client session history, project decisions, and deliverable tracking. Could evolve into a client-facing feature. |
| **Portfolio Management** | Investment decisions, rebalance rationale, and bucket strategy changes are searchable across sessions. |
| **Rental Properties** | Property-specific decisions (insurance splits, maintenance history) accumulated across sessions. |

---

*Living document. Last updated March 22, 2026.*
