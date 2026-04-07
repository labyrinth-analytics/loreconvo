# Agent Skill: Session Save

At the end of EVERY session, save to BOTH LoreDocs and LoreConvo. This is mandatory.
LoreConvo is how agents communicate. LoreDocs archives outputs for cross-agent search.

## Step 1: LoreDocs (archive your primary output file)

```
python ron_skills/loredocs/scripts/query_loredocs.py --add-doc \
    --vault "{VAULT}" \
    --name "{DOC_NAME}" \
    --file {FILE_PATH} \
    --tags '["{AGENT_TAG}", "{CATEGORY_TAG}", "YYYY-MM-DD"]' \
    --category "{CATEGORY}"
```

## Step 2: LoreConvo (log session for agent communication)

```
python ron_skills/loreconvo/scripts/save_to_loreconvo.py \
    --title "{TITLE} YYYY-MM-DD" \
    --surface "{SURFACE}" \
    --summary "COMPLETED: ... | BLOCKED: ... | PENDING_GIT: ... | HANDOFFS: ..." \
    --tags '["{AGENT_TAG}"]' \
    --artifacts '["path/to/primary/output/file"]' \
    --project "side_hustle"
```

## Per-Agent Values

| Agent             | LoreDocs Vault               | Category              | Surface    | Agent Tag             | Title Prefix                  |
|-------------------|------------------------------|-----------------------|------------|-----------------------|-------------------------------|
| Ron               | Project Ron - Deliverables   | deliverable           | cowork     | agent:ron             | Ron session                   |
| Meg               | QA Reports                   | qa-report             | qa         | agent:meg             | Meg QA Report                 |
| Brock             | Security Reports             | security-report       | security   | agent:brock           | Brock Security Report         |
| Gina (pipeline)   | Pipeline Architecture Reviews| architecture-proposal | cowork     | agent:gina            | Gina architecture session     |
| Gina (product)    | Pipeline Architecture Reviews| architecture-review   | cowork     | agent:gina            | Gina product review           |
| Scout             | Pipeline Architecture Reviews| scout-report          | pipeline   | agent:scout           | Scout research                |
| Competitive Intel | Competitive Intelligence     | competitive-scan      | pipeline   | agent:competitive-intel| Competitive intel scan       |
| Madison           | Marketing Content            | blog-draft            | marketing  | agent:madison         | Madison marketing session     |
| John              | Project Ron - Deliverables   | documentation         | cowork     | agent:john            | John tech docs                |
| Jacqueline (daily)| PM Dashboards                | executive-dashboard   | pm         | agent:jacqueline      | Jacqueline PM session         |
| Jacqueline (roadmap)| PM Dashboards              | product-roadmap       | pm         | agent:jacqueline      | Jacqueline roadmap            |

Note for Jacqueline roadmap: add "roadmap" to tags array.

## Summary Format

The `--summary` field MUST include these four structured fields:
- COMPLETED: what was finished this session
- BLOCKED: what could not be completed and why
- PENDING_GIT: files that need committing if git was blocked
- HANDOFFS: questions or items for other specific agents

Other agents read these fields to coordinate. Skipping any field leaves gaps in the handoff chain.
