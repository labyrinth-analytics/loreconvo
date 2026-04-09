# PKA Proposal Review - Debbie's Decisions
**Date:** 2026-04-08
**Proposal reviewed:** `docs/architecture/proposals/pka_implementation_plan_2026_04_08.md`
**Status:** P0 APPROVED with corrections listed below

---

## Corrections Required Before ADR-00009 Is Final

Gina must address these in the final ADR before Ron starts P1 implementation:

1. **Add competitive-intel to Section 5.1 per-agent cheat sheet.** It appears in the before/after mapping but is missing from the cheat sheet entirely.
   - Drops into: `raw/agents/competitive-intel/YYYY/MM/`
   - Filename pattern: `competitive_report_YYYY-MM-DD.md`
   - Tags: `triage:new` for new finds, `gina-review` for items needing architectural assessment

2. **Address Claude Code vs Cowork split explicitly.** The proposal assumes hooks and file-system triggers that only work in Claude Code. Specifically:
   - The "post-promotion hook" (Section 6.3) that rewrites CLAUDE.md and DEBBIE_DASHBOARD.md cannot be a file hook in Cowork.
   - The promote CLI must be run from Debbie's Terminal (Mac), not from a Cowork session.
   - The archive -> CLAUDE.md sync must be a manually-triggered script with diff preview, not an automatic hook (aligns with Q8 answer below).
   - Agent file writes to raw/ via Bash tool work in both environments.
   - The ADR must clearly indicate which operations require Terminal, which work in Cowork, and which require Code.

3. **Add "Needs More Info" as an explicit workflow path.** Currently the pipeline only documents approve/decline/hold. The missing path is: Debbie has a question before she can decide.
   - Resolution: Cowork conversation with an agent -> decision doc created and captured -> promoted to archive.
   - This path should appear in the PKA workflow diagram and the daily review loop description.

4. **Update numbering to 5 digits.** Use `DEC-00042`, `SPEC-00013`, `ADR-00009` (not 4-digit).

5. **Debbie intake path needs documentation.** Section 5 describes what agents write to raw/ but says nothing about Debbie dropping her own ideas in. Document clearly:
   - Debbie drops markdown files in `knowledge/raw/inbox/`
   - No agent needs to be specified; Jacqueline routes based on content
   - Add `agent: gina` (or other) as a tag if you want explicit routing
   - P3 should include an intake script alongside the promote CLI: `python scripts/intake.py --title "My idea"` opens a template

---

## Section 9 Open Questions - Debbie's Answers

| # | Question | Answer |
|---|----------|--------|
| 1 | Root directory name | `knowledge/` at repo root (matches Gina's vote) |
| 2 | Living docs inside or outside PKA | Outside, in `docs/living/` (matches Gina's vote) |
| 3 | Raw/ pruning aggressiveness | 90 days to start; review after Phase 7 |
| 4 | LoreConvo sessions auto-export to raw/ | Start with dual-write, BUT automate the LoreConvo->raw export to run **twice daily** (not per-agent-session and not 24hr lag). Removes lag without complicating agent prompts. |
| 5 | Who owns gina-review / brock-review handoffs | Cross-agent handoffs (gina-review/brock-review) are already being picked up per CLAUDE.md — no permission change needed there. **Agents that need Debbie's input write a question file to their own `raw/agents/<name>/` folder tagged `review:debbie`.** Jacqueline reads all of raw/, sees the tag, surfaces it in the dashboard. Debbie answers via normal review loop (drop response in `raw/inbox/` or Cowork session). No agent is ever granted write access to `processing/` — questions route back through raw/ just like everything else. |
| 6 | Numbering scheme | Global, **5 digits**: `DEC-00042` |
| 7 | Promote CLI needed for Phase 1 | Gina's phasing is fine - git mv + manual frontmatter first, CLI in P3. Need simple format reference for manual promotion (see below). |
| 8 | Archive -> CLAUDE.md sync: auto or manual | **Manual with diff-preview for P1-P2**, flip to auto after 2 weeks of clean runs |
| 9 | Public repo exposure for archive | Public option is fine, but **later phase** - not P1 |
| 10 | Does this replace PipelineDB | No. PipelineDB stays as the structured opportunity lifecycle store. PKA stores prose artifacts. They cross-link by ID. PipelineDB as fallback approved. |

---

## Section 10 Phase Approvals

- **P0:** APPROVED (this document)
- **P1 through P7:** APPROVED as outlined, subject to corrections above and pending resolution of the stability mandate (P4 remains blocked on LoreConvo/LoreDocs install fix per existing mandate)

---

## New Pipeline Item - PARA Tagging Feature

**Add to pipeline as a new opportunity/feature spec:**

Debbie uses the PARA method (Projects / Areas / Resources / Archives) for personal knowledge organization. The PKA model uses `type:` (decision/spec/adr) to describe document type, but PARA describes knowledge domain. They are complementary.

**Proposed implementation:**
- Add a `para_type: project | area | resource | archive` field to the base frontmatter schema for PKA units
- In LoreDocs: expose `para_type` as a first-class document or vault attribute for filtering
- In LoreConvo: allow sessions to carry a `para_type` tag for domain-scoped search (e.g., "show all Finances area sessions")
- Example: Labyrinth Analytics Consulting = `project`, Finances = `area`, Tax Reference Docs = `resource`

This is a differentiating product feature - Gina should add to pipeline as a SPEC item.

---

## Manual Promotion Format Reference (for use before P3 CLI exists)

When manually promoting a file from raw to processing or archive:

```
git mv knowledge/raw/agents/gina/2026/04/my_report.md \
       knowledge/processing/decisions/DEC-00001_decision_title.md
```

Then edit the frontmatter to add:
```yaml
---
id: DEC-00001
type: decision
title: "Short descriptive title"
status: processing        # change to archive when conclusion is stable
created: 2026-04-08
promoted_to_processing: 2026-04-08
author: debbie
tags: [relevant, tags]
supersedes: []
related: []
source: knowledge/raw/agents/gina/2026/04/my_report.md
context: "why this came up"
options_considered: ["A", "B"]
decision: "picked A"
rationale: "one-paragraph why"
consequences: "what this commits us to"
---
```

For archive promotion from processing:
```
git mv knowledge/processing/decisions/DEC-00001_decision_title.md \
       knowledge/archive/decisions/DEC-00001_decision_title.md
```
Update `status: archive` and add `promoted_to_archive: YYYY-MM-DD`.

---

## Action Items

| Owner | Action |
|-------|--------|
| **Gina** | Revise proposal into final ADR-00009 incorporating all corrections above |
| **Gina** | Add competitive-intel agent to Section 5.1 |
| **Gina** | Address Code vs Cowork distinction explicitly |
| **Gina** | Add "Needs More Info" workflow path |
| **Gina** | Add PARA tagging as new pipeline SPEC item |
| **Ron** | Pick up P1 after stability mandate resolved and final ADR-00009 is filed |
| **Jacqueline** | Add "PKA Adoption" row to exec dashboard once P1 begins |
| **Ron (P3)** | Add `scripts/intake.py` alongside `scripts/promote.py` |

*Captured by Debbie via Cowork session 2026-04-08.*
