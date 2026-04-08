# Architecture Proposal: `get_context_for_agent()` — Lore Bridge Tool

**Author:** Gina (Enterprise Architect)
**Date:** 2026-04-08
**Status:** DRAFT — pending Debbie review
**Products affected:** LoreConvo, LoreDocs, (new) Lore Bridge
**Strategic context:** Competitive intel (Perplexity, Apr 2026) flagged unified episodic+semantic memory as the Lore family's strongest potential moat. No known competitor bridges conversational history and document vaults in a single call.

---

## 1. Problem Statement

Today, an agent (Ron, Meg, Brock, Jacqueline, Scout, Gina, Madison, John) that needs full working context at session start has to make at least two separate, uncoordinated calls:

1. `get_recent_sessions()` against LoreConvo to recover what happened in prior sessions (decisions, blockers, handoffs, artifacts).
2. `vault_list()` + `vault_inject_summary()` against LoreDocs to recover the relevant durable knowledge (specs, architecture, reference docs).

Pain points with the current state:

- **Two round trips, two mental models.** Each agent has to remember the right call order, the right vault names, and the right search terms for both stores.
- **No cross-ranking.** A session from yesterday and a spec from last quarter compete for token budget, but each store ranks independently. The agent has no way to ask "give me the *most relevant* N tokens about topic X" — it has to over-fetch from both and trim.
- **Token budget blowouts.** Agents routinely waste 3–6 tool calls assembling context, then more on trimming. Several scheduled tasks now spend >20% of their turn budget on context loading alone.
- **Cross-agent handoffs are fragile.** A "GINA-REVIEW:" tag from Brock lives in LoreConvo, but the architecture spec it refers to lives in LoreDocs. Today, only a human reliably joins those.
- **Surface inconsistency.** Cowork, Code, and Chat each have slightly different MCP availability. An agent that depends on two servers fails twice as often as one that depends on one.

The bridge tool collapses this into a single call: *"Give me everything an agent persona needs to start work on topic X within a token budget."*

---

## 2. API Design

### Signature

```python
@mcp.tool()
def get_context_for_agent(
    agent_id: str,                       # e.g. "ron", "meg", "gina", "brock"
    topic: str | None = None,            # free-text focus, e.g. "loreconvo install flow"
    persona_hint: str | None = None,     # optional role override, e.g. "security-reviewer"
    token_budget: int = 6000,            # hard cap on returned context
    session_lookback_days: int = 14,     # episodic recency window
    vault_filters: list[str] | None = None,   # restrict to specific vaults
    include_open_questions: bool = True,
    include_handoffs: bool = True,
    format: Literal["structured", "markdown"] = "structured",
) -> dict
```

### Return shape (structured)

```jsonc
{
  "agent_id": "ron",
  "topic": "loreconvo install flow",
  "generated_at": "2026-04-08T14:32:00Z",
  "token_budget": 6000,
  "tokens_used": 5421,
  "episodic": [
    {
      "session_id": "uuid",
      "title": "Ron session 2026-04-05",
      "surface": "cowork",
      "agent": "ron",
      "summary": "...",
      "tags": ["agent:ron", "loreconvo", "install"],
      "artifacts": ["ron_skills/loreconvo/install.sh"],
      "score": 0.92,
      "score_breakdown": {"recency": 0.85, "topic": 0.95, "agent_match": 1.0}
    }
  ],
  "semantic": [
    {
      "vault": "loreconvo",
      "doc_name": "INSTALL.md",
      "version": 4,
      "priority": "high",
      "snippet": "...",
      "tags": ["install", "user-docs"],
      "score": 0.88,
      "score_breakdown": {"priority": 0.9, "topic": 0.87, "freshness": 0.8}
    }
  ],
  "open_questions": [
    {"source": "loreconvo", "session_id": "uuid", "question": "..."}
  ],
  "handoffs": [
    {"from_agent": "brock", "to_agent": "gina", "tag": "GINA-REVIEW:", "context": "..."}
  ],
  "warnings": [
    "Trimmed 3 episodic results to fit token budget",
    "LoreDocs vault 'sql_optimizer' not found"
  ]
}
```

`format="markdown"` returns the same data flattened to a single agent-readable string — useful for surfaces (Chat) where structured returns are awkward.

---

## 3. Retrieval Strategy

Two stores, one ranked result set, one budget. The bridge runs four phases.

**Phase 1 — Candidate generation (parallel).**
- LoreConvo: pull sessions from last `session_lookback_days`, plus any sessions tagged `agent:{agent_id}` or matching `persona_hint`. FTS5 match on `topic` if provided.
- LoreDocs: pull docs from `vault_filters` (or all vaults the agent has access to), FTS5 match on `topic`, weighted by `priority` field.

Each candidate gets a raw score based on its native store signals.

**Phase 2 — Cross-store normalization.**
Scores from each store are min-max normalized to [0, 1] *within their store*, then combined with a tunable weight:

```
final_score = w_episodic * normalized_episodic_score
            + w_semantic * normalized_semantic_score
            + w_agent_affinity * (1.0 if agent_match else 0.3)
            + w_handoff * (1.0 if handoff_to_this_agent else 0.0)
```

Default weights (configurable in `lore_bridge.toml`):
- `w_episodic = 0.35` (recency-weighted, exponential decay over 14 days)
- `w_semantic = 0.40` (priority-weighted: high=1.0, medium=0.7, low=0.4)
- `w_agent_affinity = 0.15`
- `w_handoff = 0.10`

**Phase 3 — Token-budget packing.**
Greedy fill: sort by `final_score` descending, add items until `token_budget` is reached. Reserve 15% of budget for `open_questions` and `handoffs` (these are cheap and high-signal). Use `tiktoken` for token counts; fall back to char/4 estimate if unavailable.

**Phase 4 — Diversity guardrail.**
Cap any single source at 40% of returned items so one chatty session can't crowd out everything else. Also cap per-vault to prevent a single doc set from dominating.

---

## 4. Architectural Options

### Option A — New MCP server ("Lore Bridge") that calls LoreConvo and LoreDocs as clients

A standalone FastMCP server. At startup it spawns or connects to the LoreConvo and LoreDocs MCP servers via stdio and acts as a client to both. Exposes one tool: `get_context_for_agent`.

**Pros**
- True separation of concerns. LoreConvo and LoreDocs stay independent and unmodified.
- The bridge can ship and version on its own cadence, including its own .plugin file.
- Failures are isolated: if LoreDocs is unavailable, the bridge degrades gracefully and returns episodic-only.
- Easiest path to add more sources later (e.g. a future LorePrompts).

**Cons**
- Three MCP servers to install, configure, and authenticate. Adds friction to the install flow that is already a stability blocker.
- Two layers of stdio = noticeably higher latency (likely 200–500ms overhead per call).
- Stdio-over-stdio is fragile in Cowork — each restart compounds the existing plugin install fragility.
- Yet another product to document, test, and support.

---

### Option B — New tool added to LoreConvo that reads the LoreDocs SQLite file directly

`get_context_for_agent` becomes a 13th tool in the LoreConvo MCP server. It opens the LoreDocs SQLite database read-only by file path (configured in `lore_bridge.toml` or auto-discovered at `~/.loredocs/loredocs.db`).

**Pros**
- One server, one install, one set of credentials. Lowest friction for users.
- No stdio-over-stdio. Direct SQLite reads are sub-millisecond.
- Ships fastest — no new package, no new repo, no new plugin.
- Reuses LoreConvo's existing FTS5 patterns and token-budgeting code.

**Cons**
- **Tight coupling.** LoreConvo now has a hard dependency on the LoreDocs schema. Any LoreDocs schema change risks breaking the bridge silently.
- **Asymmetry.** Users who installed only LoreDocs cannot use the bridge. The bridge becomes a LoreConvo-only feature, which complicates marketing ("buy LoreConvo to get the bridge that needs LoreDocs").
- Read-only access only — bridge cannot ever write back to LoreDocs (which we may want for "mark this doc as relevant to agent X").
- Conceptually muddy: LoreConvo is "memory of conversations," but it now also reaches into a different product's data.

---

### Option C — Shared `lore_bridge` library imported by both servers (RECOMMENDED, see §5)

Extract a small Python package, `lore_bridge`, that:
- Defines the canonical `Candidate` and `ContextBundle` dataclasses.
- Implements the ranking, normalization, and token-budgeting algorithms.
- Defines a `Source` protocol that any backing store implements (`fetch_candidates(topic, agent_id, ...) -> list[Candidate]`).
- Provides two concrete sources: `LoreConvoSource` (reads LoreConvo SQLite) and `LoreDocsSource` (reads LoreDocs SQLite).

The library is then imported by both LoreConvo and LoreDocs servers. Each server exposes the same `get_context_for_agent` MCP tool, configured to know about whichever stores are available locally.

**Pros**
- **Symmetric.** Whichever product the user installs, the bridge tool is available. If both are installed, the tool sees both stores.
- **Schema is owned by the library, not the consumer.** Each `Source` adapter is the only thing that touches a foreign schema, so drift is contained.
- **Testable in isolation.** The ranking algorithm has no MCP dependency and can be unit tested with synthetic candidates.
- **Future-proof.** Adding LorePrompts or LoreScope is "write a new Source adapter," not "spin up a new server."
- No new server = no new install friction.

**Cons**
- Both products now have a runtime dependency on `lore_bridge`. Version pinning matters (use `lore_bridge==0.x.y` exact pins).
- Some duplication: the same MCP tool is registered in two places. Solvable with a shared decorator or a tiny tool-registration helper.
- Slightly more upfront design work than Option B.

---

## 5. Recommendation

**Adopt Option C — shared `lore_bridge` library.**

Reasoning:
1. **Symmetry beats convenience.** Option B ships fastest but creates a long-term marketing and support headache (one product reaches into another's database). Option C makes the bridge a first-class shared capability.
2. **The stability mandate cares about install friction.** Option A adds a third server right when we are still fixing the install flow for two. Option C adds zero new install steps.
3. **Schema drift is the #1 risk.** Encapsulating each store behind a `Source` adapter is the cleanest defense. Adapters become the contract; schema changes only break the adapter, not the consumer.
4. **Algorithm reuse.** Ranking and token-packing logic should be unit-tested without any MCP plumbing. A library is the natural home.
5. **Cross-sell story improves.** "Install either Lore product and get bridge tooling. Install both and the bridge sees everything." That is a much stronger pitch than "Pro tier of LoreConvo unlocks LoreDocs reads."

Build Option C in stages so we can ship value early:

- **Stage 1 (MVP):** `lore_bridge` library + `LoreConvoSource` + `LoreDocsSource` + tool registered in LoreConvo only. Ship inside LoreConvo's next minor release. Validates the algorithm with real users.
- **Stage 2:** Register the same tool in LoreDocs. Now both products expose `get_context_for_agent`.
- **Stage 3:** Extend with `LorePromptsSource` and `LoreScopeSource` when those products land.

---

## 6. Effort Estimate

**T-shirt size: M (medium).** Estimate 4–6 focused Ron sessions for Stage 1, 1–2 sessions for Stage 2.

Specific tasks:

Stage 1 (MVP):
1. Create `ron_skills/lore_bridge/` package skeleton with `pyproject.toml`, exact version pin pattern, and ASCII-only source.
2. Define `Candidate`, `ContextBundle`, `Source` protocol dataclasses.
3. Implement `RankingEngine` with normalization, weighted scoring, diversity guardrail, and token-budget packer. Pure functions, no I/O.
4. Implement `LoreConvoSource` adapter — reads sessions table via FTS5, applies recency decay, returns Candidates.
5. Implement `LoreDocsSource` adapter — reads vault docs via FTS5, applies priority weighting, returns Candidates.
6. Unit tests for ranking, packing, and each adapter against fixture SQLite databases.
7. Register `get_context_for_agent` MCP tool in LoreConvo's `server.py`. Wire to `lore_bridge`.
8. Update LoreConvo INSTALL.md, README.md, SKILL.md, and docs site (John's responsibility) with the new tool.
9. Doc-sync checklist: tool count goes from 12 to 13 across all locations.
10. Meg writes integration tests, Brock reviews trust boundary (cross-product file access).

Stage 2:
11. Register the same tool in LoreDocs `server.py`.
12. Add config flag for which sources to enable.
13. Update LoreDocs docs.

---

## 7. Open Questions for Debbie

1. **Naming.** `get_context_for_agent` is descriptive but long. Alternatives: `recall_for_agent`, `lore_context`, `agent_briefing`, `prep_agent`. Preference?
2. **Default token budget.** 6000 tokens is my guess based on current agent turn budgets. Should it be smaller (4000) for Chat surface and larger (8000) for Code/Cowork?
3. **Persona vs agent_id.** Do we want a `persona` concept distinct from `agent_id`? E.g. Brock can request context "as a security reviewer" even though his agent_id is "brock." Adds flexibility, adds complexity.
4. **Vault access control.** Should the bridge respect any LoreDocs vault privacy/tier flags, or just assume the caller has full access?
5. **Tier gating.** Is the bridge a free-tier feature or Pro-tier? It is arguably the strongest cross-sell hook in the suite — putting it behind Pro might monetize, but might also kneecap the very moat we are building.
6. **Stage 1 host.** Confirm Stage 1 ships inside LoreConvo (my recommendation) rather than LoreDocs. LoreConvo has more install momentum and a more mature MCP surface.
7. **Schema drift contract.** Should `lore_bridge` declare a minimum compatible LoreConvo and LoreDocs schema version and refuse to start otherwise? (I think yes, but it adds release coordination.)

---

## 8. Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| **Schema drift** between LoreConvo/LoreDocs and the bridge silently returns empty results | Medium | High | Bridge declares minimum schema version per source. Each adapter has a `validate_schema()` method called at startup. Failing validation logs a clear error and disables that source rather than crashing. |
| **Token budget blowouts** when a long session or doc is included whole | Medium | Medium | Greedy packer counts tokens per item before adding. Items larger than 25% of budget are auto-truncated with a `[truncated]` marker. Hard cap on returned items (default 30). |
| **Stale joins** (referenced session points at a deleted artifact, or doc references an obsolete spec) | Medium | Low | Bridge does not resolve cross-references — it returns what each store has. Stale data is a store-level problem, not a bridge problem. Document this clearly. |
| **Performance** — full FTS5 sweep across two large stores per call | Low (today) | Medium (later) | Both stores already use FTS5 indexes. Add a 30-day default lookback window for episodic. Cache results for 60 seconds keyed by (agent_id, topic, budget). Add timing instrumentation from day one. |
| **Cross-product file access trust boundary** (LoreConvo opens a file owned by LoreDocs) | Medium | Medium | Brock review required. Open LoreDocs SQLite read-only with `mode=ro`. Validate path resolves under `~/.loredocs/`. Never write. Document in security report. |
| **Asymmetric installs** — user has only one product, bridge silently returns half the picture | High | Low | When a source is missing, surface it in `warnings[]` field in the response. Document the cross-sell explicitly. |
| **Ranking weights are wrong** for real workloads | High | Medium | Weights live in `lore_bridge.toml`, not code. Ship with conservative defaults, measure (see §9), and tune. |
| **Tool count drift** in docs (we just added the doc-sync checklist for a reason) | Medium | Low | Add to John's checklist. Run doc-sync after Stage 1 and Stage 2 each. |

---

## 9. Success Metrics

We will know `get_context_for_agent` is working if:

1. **Adoption.** Within 30 days of Stage 1 shipping, at least 5 of the 8 scheduled agents are calling `get_context_for_agent` at session start instead of the legacy two-call pattern. Measured by LoreConvo session logs (we can grep for tool calls).
2. **Tool-call efficiency.** Average tool calls per agent session for context loading drops from current ~4-6 to ≤2. Measured by Jacqueline's daily dashboard (add a "context loading cost" panel).
3. **Token efficiency.** Returned context fits within budget on >95% of calls (no overruns), and `tokens_used / token_budget` ratio is ≥0.7 (proves we are not under-utilizing the budget).
4. **Coverage.** When an agent receives a handoff (e.g. "GINA-REVIEW:") from another agent, the relevant handoff appears in the bridge response on >90% of calls. Measured by handoff resolution audits in Jacqueline's weekly roadmap.
5. **Failure rate.** Bridge tool errors out on <1% of calls. Measured by error-surface LoreConvo logs.
6. **Subjective quality.** Spot-check 10 bridge responses per week against what a human would have selected. Target ≥80% overlap on the top-5 results.
7. **Cross-sell signal (Stage 2+).** Conversion lift on LoreConvo->LoreDocs and LoreDocs->LoreConvo upsells after the bridge is live in both. Measured by install telemetry once we have it.

---

**End of proposal.** Awaiting Debbie's review on §7 open questions before any implementation work begins. This proposal does not authorize Ron to start building — it is for architectural review only, per the active product stability mandate.
