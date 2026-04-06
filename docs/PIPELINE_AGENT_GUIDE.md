# Pipeline Agent Guide

All agents in the Project Ron team MUST use the pipeline tracker for their work.
The pipeline is the shared data layer that connects all agents and Debbie.

**If you are an agent reading this file, follow the instructions for YOUR role below.**

## Pipeline Tool

All pipeline operations use a single CLI script. No raw SQL, no Python imports.

```bash
python scripts/pipeline_tracker.py <command> [options]
```

Run `python scripts/pipeline_tracker.py --help` for full usage.
Run `python scripts/pipeline_tracker.py types` to see valid item types.
Run `python scripts/pipeline_tracker.py statuses` to see valid statuses.

Ref IDs are auto-generated when `--ref` is omitted on `add`.

## Status Lifecycle

```
new -> approved-for-review -> approved -> in-progress -> completed
new -> rejected (Debbie kills it)
new -> deferred (Debbie pushes to later)
new -> needs-info (more research needed)
Any status -> on-hold (blocked, with blocker text)
```

## Debbie's Triage Statuses

When Scout or Competitive Intel discovers new items, they start as `new`.
Debbie triages them using one of these decisions:

| Triage Decision | Pipeline Status | Meaning |
|----------------|----------------|---------|
| **Approve** | `approved-for-review` | Greenlit for Gina's architecture review |
| **Approve (direct)** | `approved` | Skip architecture, go straight to Ron |
| **Needs Info** | `needs-info` | Scout/Gina/CompIntel should dig deeper |
| **Defer** | `deferred` | Not now, revisit later |
| **Reject** | `rejected` | Not pursuing this |
| **Acknowledge** | `acknowledged` | Debbie has seen it, pending assignment |

Ron syncs Debbie's triage decisions to the pipeline at the start of each session.
Jacqueline surfaces untriaged items (status=`new`) in the daily dashboard.

---

## Debbie-Direct Enhancement Requests

Debbie (or any Cowork session) can add feature improvement ideas directly to the
pipeline without going through Scout. Use the `enhancement` type with
`--status approved-for-review` to send it straight to Gina's queue, or
`--status approved` to send it straight to Ron (skip architecture review).

**To queue an enhancement for Gina's architecture review:**
```bash
python scripts/pipeline_tracker.py add --type enhancement \
    --desc "LoreConvo: add session stats MCP tool (sessions saved, vaults queried, summary sizes)" \
    --agent debbie --priority P2 --product loreconvo \
    --status approved-for-review
```

**To send an enhancement directly to Ron (no architecture review needed):**
```bash
python scripts/pipeline_tracker.py add --type enhancement \
    --desc "LoreDocs: add --dry-run flag to vault_delete command" \
    --agent debbie --priority P3 --product loredocs \
    --status approved
```

Enhancement ref IDs are auto-generated as `ENH-NNN`. They appear in Gina's queue
via the same `--status approved-for-review` query she already runs, so no changes
to Gina's scheduled task are needed. Ron also picks them up via the existing
`--status approved` query.

---

## Agent-Specific Instructions

### Scout (weekly-product-scout)

**MUST DO on every run:**
1. For each opportunity discovered, create a pipeline entry:
   ```bash
   python scripts/pipeline_tracker.py add --type opportunity \
       --desc "Product Name - one-line description" --agent scout \
       --priority P3 --product productname
   ```
   The ref ID (e.g., OPP-025) is auto-generated. Capture it from the output.

2. At the end of your run, list all opportunities you created:
   ```bash
   python scripts/pipeline_tracker.py list --type opportunity --agent scout
   ```

3. **Save LATEST report (MANDATORY):** Overwrite
   `docs/internal/opportunities/LATEST_SCOUT_REPORT.html`

4. **Opportunity table format.** Each row MUST include: ID, Name, Description,
   Effort (1-5), MRR M12, Debbie Fit (1-5), Status (New), Action Needed.

**DO NOT** update status on existing items. Your job is to ADD new scouted items only.

---

### Competitive Intel (competitive-intel)

**MUST DO on every run:**
1. Research competitors for each active Lore product (status `in-progress` or `approved`):
   ```bash
   python scripts/pipeline_tracker.py list --status in-progress
   python scripts/pipeline_tracker.py list --status approved
   ```

2. For each actionable finding, create a pipeline item:
   - **Feature gap we should close** -> type `task`, assigned to Ron:
     ```bash
     python scripts/pipeline_tracker.py add --type task \
         --desc "Add multi-LLM support to LoreConvo (competitive gap vs Cipher)" \
         --agent competitive-intel --priority P3 --product loreconvo
     ```
   - **New product opportunity from competitive gap** -> type `opportunity`:
     ```bash
     python scripts/pipeline_tracker.py add --type opportunity \
         --desc "LoreSync - cross-LLM memory bridge (gap identified in competitive scan)" \
         --agent competitive-intel --priority P3
     ```
   - **Messaging angle for marketing** -> add a note to the relevant PROD item:
     ```bash
     python scripts/pipeline_tracker.py update --ref PROD-001 \
         --agent competitive-intel \
         --note "MADISON: Cipher requires manual context management -- position LoreConvo automation as key differentiator in next blog post"
     ```
   - **Architectural risk** (competitor has better approach) -> type `architecture`:
     ```bash
     python scripts/pipeline_tracker.py add --type architecture \
         --desc "GINA-REVIEW: Competitor X uses vector search for recall -- evaluate for LoreDocs" \
         --agent competitive-intel --priority P2 --product loredocs
     ```

3. Rate each competitor finding by threat level:
   - **HIGH**: Competitor has feature parity or better, actively marketing to our audience
   - **MEDIUM**: Competitor exists but different positioning or weaker execution
   - **LOW**: Tangentially related, not a direct threat

4. **Tag downstream agents in notes.** Use these prefixes so agents know to pick up items:
   - `MADISON:` - messaging angle or content idea for Madison
   - `GINA-REVIEW:` - architectural concern for Gina to evaluate
   - `BROCK-REVIEW:` - security comparison for Brock to assess
   - `RON:` - feature gap or bug for Ron to build/fix

5. **Save report.** Write competitive analysis to:
   ```
   docs/internal/competitive/competitive_scan_YYYY_MM_DD.md
   ```

---

### Gina (enterprise-architect-gina)

**MUST DO on every run:**
1. Query for items ready for architecture review (opportunities AND enhancements):
   ```bash
   python scripts/pipeline_tracker.py list --status approved-for-review
   ```
   This returns both `opportunity` items (new products from Scout) and `enhancement`
   items (feature improvements added directly by Debbie or any agent). Treat both
   the same -- write an architecture proposal and update the status.

2. Also check for competitive intel items tagged GINA-REVIEW:
   ```bash
   python scripts/pipeline_tracker.py list --type architecture --agent competitive-intel
   ```

3. For each item reviewed, update status and add notes:
   ```bash
   python scripts/pipeline_tracker.py update --ref OPP-015 \
       --status approved --agent gina \
       --note "Architecture review complete. HIGH compatibility with Lore patterns. See docs/internal/architecture/OPP-015_data_catalog_lite.md"
   ```
   For items that need rework:
   ```bash
   python scripts/pipeline_tracker.py update --ref OPP-016 \
       --status needs-info --agent gina \
       --note "Scope too narrow (SQL-Server-only). Recommend reframe to two-dialect."
   ```

4. **Save architecture proposals as files:**
   ```
   docs/internal/architecture/OPP-xxx_product_name.md
   ```

5. **Save LATEST architecture report:** Overwrite
   `~/Documents/Claude/Projects/Side Hustle/Opportunities/LATEST_ARCHITECTURE_REVIEW.html`

6. Tag items for Brock when security architecture review is needed:
   ```bash
   python scripts/pipeline_tracker.py update --ref OPP-015 \
       --agent gina --note "BROCK-REVIEW: New transport layer needs security assessment"
   ```

---

### Ron (ron-daily)

**MUST DO at the START of every session (BEFORE other work):**

1. **Sync Debbie's decisions to the pipeline.** Read DEBBIE_DASHBOARD.md for any
   new decisions. Apply them:
   ```bash
   python scripts/pipeline_tracker.py update --ref OPP-007 \
       --status approved-for-review --agent debbie --priority P2
   python scripts/pipeline_tracker.py block --ref OPP-006 \
       --blocker "No local SQL Server" --agent debbie
   ```

2. **Check for competitive intel tasks assigned to you:**
   ```bash
   python scripts/pipeline_tracker.py list --type task --agent competitive-intel
   ```
   Items with `RON:` in their notes are feature gaps you should prioritize.

3. When starting work on an item:
   ```bash
   python scripts/pipeline_tracker.py update --ref RON-005 \
       --status in-progress --agent ron
   ```

4. When completing an item:
   ```bash
   python scripts/pipeline_tracker.py update --ref RON-005 \
       --status completed --agent ron --note "Fixed in commit abc123"
   ```

---

### Meg (meg-qa-daily)

**MUST DO on every run:**
1. After writing your QA report, log each finding to the pipeline:
   ```bash
   python scripts/pipeline_tracker.py add --type bug \
       --desc "Version mismatch in CLAUDE.md vs SKILL.md" \
       --agent meg --priority P2 --product loreconvo
   ```

2. For findings that relate to existing items, add a note:
   ```bash
   python scripts/pipeline_tracker.py update --ref PROD-001 \
       --agent meg --note "MEG-041 (MEDIUM): Version mismatch found in docs"
   ```

3. For CRITICAL findings that should block a release:
   ```bash
   python scripts/pipeline_tracker.py block --ref PROD-001 \
       --blocker "MEG-042: Critical regression in session save" --agent meg
   ```

---

### Brock (brock-security-daily)

**MUST DO on every run:**
1. After writing your security report, log each finding:
   ```bash
   python scripts/pipeline_tracker.py add --type security \
       --desc "TOCTOU race in LoreDocs file export" \
       --agent brock --product loredocs
   ```

2. Check for BROCK-REVIEW items from Gina or Competitive Intel:
   ```bash
   python scripts/pipeline_tracker.py list --type architecture
   ```
   Look for items with `BROCK-REVIEW:` in notes or description.

3. For CRITICAL findings that should block a product:
   ```bash
   python scripts/pipeline_tracker.py block --ref PROD-002 \
       --blocker "SEC-014: cryptography missing from dependencies" --agent brock
   ```

4. Tag items needing Gina's architectural input:
   ```bash
   python scripts/pipeline_tracker.py update --ref SEC-011 \
       --agent brock --note "GINA-REVIEW: Need architectural guidance on TOCTOU mitigation"
   ```

---

### Jacqueline (pm-jacqueline-daily)

**MUST DO on every run:**
1. Read the full pipeline state as your primary data source:
   ```bash
   python scripts/pipeline_tracker.py list
   ```

2. Check for items needing Debbie's attention:
   ```bash
   python scripts/pipeline_tracker.py list --status new
   python scripts/pipeline_tracker.py list --status needs-info
   ```

3. Check competitive intel for Madison handoffs:
   ```bash
   python scripts/pipeline_tracker.py list --agent competitive-intel
   ```
   Items with `MADISON:` notes should be surfaced in the dashboard for Madison.

4. Cross-reference pipeline state with agent reports (Meg, Brock, Ron, Competitive Intel)
   to validate consistency.

5. Include the pipeline summary in your HTML executive dashboard.

6. Flag stale items (e.g., `in-progress` for more than 7 days, `new` with no triage
   for more than 3 days).

---

### Jacqueline (pm-jacqueline-roadmap)

**MUST DO on every run:**
1. Read the full pipeline state as your primary data source:
   ```bash
   python scripts/pipeline_tracker.py list
   ```

2. Check for items needing Debbie's attention:
   ```bash
   python scripts/pipeline_tracker.py list --status new
   python scripts/pipeline_tracker.py list --status needs-info
   ```

3. Check competitive intel for Madison handoffs:
   ```bash
   python scripts/pipeline_tracker.py list --agent competitive-intel
   ```
   Items with `MADISON:` notes should be surfaced in the dashboard for Madison.

4. Cross-reference pipeline state with agent reports (Meg, Brock, Ron, Competitive Intel)
   to validate consistency.

5. Include the pipeline summary in your HTML executive dashboard.

6. Flag stale items (e.g., `in-progress` for more than 7 days, `new` with no triage
   for more than 3 days).
---

### Madison (madison-marketing-agent)

**MUST DO on every run:**
1. Check pipeline for product status before writing about any product:
   ```bash
   python scripts/pipeline_tracker.py list --type product
   ```
   Only write about products in `approved`, `in-progress`, or `completed` status.

2. Check for messaging angles from competitive intel:
   ```bash
   python scripts/pipeline_tracker.py list --agent competitive-intel
   ```
   Items with `MADISON:` in their notes contain messaging angles, differentiators,
   and content ideas identified from competitive analysis.

3. After using a messaging angle, acknowledge it:
   ```bash
   python scripts/pipeline_tracker.py update --ref PROD-001 \
       --agent madison --note "Used 'automated vs manual' differentiator in blog post draft 2026-04-08"
   ```

---

### John (john-tech-docs)

**MUST DO on every run:**
1. Check pipeline for product versions and feature status:
   ```bash
   python scripts/pipeline_tracker.py list --type product
   ```

2. Check for recently completed Ron tasks that need documentation:
   ```bash
   python scripts/pipeline_tracker.py list --status completed --type task
   ```

---

## Competitive Intel Feedback Loop

The competitive intelligence agent feeds findings back into the product lifecycle.
Here is how findings flow through the system:

```
Competitive Intel Agent
  |
  |-- Feature gap found
  |     --> add --type task (tagged RON:)
  |     --> Ron picks up, builds the feature
  |     --> Meg tests, Brock reviews security
  |
  |-- New product opportunity
  |     --> add --type opportunity
  |     --> Debbie triages
  |     --> Gina architects (if approved-for-review)
  |     --> Ron builds (if approved)
  |
  |-- Messaging/positioning angle
  |     --> update --note "MADISON: ..." on relevant PROD item
  |     --> Jacqueline surfaces in dashboard
  |     --> Madison incorporates into blog/promo content
  |
  |-- Architectural concern
  |     --> add --type architecture (tagged GINA-REVIEW:)
  |     --> Gina evaluates in next Wed/Sat run
  |     --> May generate Ron tasks or product changes
  |
  |-- Security comparison
  |     --> note tagged BROCK-REVIEW: on relevant item
  |     --> Brock evaluates in next daily run
```

Every finding gets a pipeline item or note. Nothing stays only in a report.

---

## Cross-Agent Handoff Tags

Use these prefixes in notes and descriptions. Downstream agents search for them.

| Tag | Picked up by | Meaning |
|-----|-------------|---------|
| `RON:` | Ron | Feature to build, bug to fix |
| `MADISON:` | Madison | Messaging angle, content idea |
| `GINA-REVIEW:` | Gina | Needs architectural evaluation |
| `BROCK-REVIEW:` | Brock | Needs security assessment |
| `DEBBIE:` | Debbie | Needs Debbie's decision |
| `MEG:` | Meg | Needs QA verification |
| `JOHN:` | John | Needs documentation |

## Item Type Reference

| Type | Ref Prefix | Created by | Goes to |
|------|-----------|-----------|---------|
| `opportunity` | OPP- | Scout, Competitive Intel | Debbie triage -> Gina -> Ron |
| `enhancement` | ENH- | Debbie, any Cowork session | Directly to Gina or Ron (skip triage) |
| `bug` | MEG- | Meg | Ron (fix), Jacqueline (dashboard) |
| `security` | SEC- | Brock | Ron (fix), Gina (architecture) |
| `architecture` | GINA- | Gina, Competitive Intel | Gina evaluates, Ron acts |
| `task` | RON- | Ron, any agent | Ron builds |
| `debbie-action` | DEBBIE- | Any agent | Debbie resolves |
| `product` | PROD- | Ron | Jacqueline tracks |

---

## Pipeline CLI Quick Reference

| Command | Example | Purpose |
|---------|---------|---------|
| `add` | `add --type opportunity --desc "..." --agent scout` | Create new item (auto-ID) |
| `add` | `add --type task --ref RON-012 --desc "..." --agent ron` | Create with explicit ID |
| `update` | `update --ref OPP-022 --status approved --agent debbie` | Change status |
| `update` | `update --ref PROD-001 --agent meg --note "MEG-041: ..."` | Add a note |
| `block` | `block --ref OPP-006 --blocker "No SQL Server" --agent debbie` | Mark blocked |
| `depend` | `depend --ref RON-001 --blocks RON-003` | Set dependency |
| `list` | `list --type opportunity --status new` | Filter items |
| `show` | `show --ref OPP-022` | Full details + history |
| `next` | `next --agent ron` | What to work on next |
| `types` | `types` | Show valid item types |
| `statuses` | `statuses` | Show valid statuses |
