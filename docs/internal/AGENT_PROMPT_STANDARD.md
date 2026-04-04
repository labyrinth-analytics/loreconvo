# Agent Prompt Standard

All scheduled agent prompts MUST follow this structure. No exceptions.

---

## Mandatory Sections (every agent)

### 1. Identity and Mission (2-3 sentences)
Who you are, what you do, who you report to.

### 2. Turn Budget
Every agent MUST include:
```
## TURN BUDGET: [N] TOOL CALLS MAXIMUM
- At [N-5]: Begin wrap-up.
- At [N]: STOP. Save session. Exit.
- NEVER exceed 50 tool calls in a single session.
```
Budgets: Ron=30, Meg/Brock=25, Jacqueline/Scout/Gina/Madison/John=20.

### 3. Git Operations (MANDATORY -- identical for all agents)
```
## GIT: USE safe_git.py ONLY
python scripts/safe_git.py commit -m "message" --agent "[name]" file1 file2
python scripts/safe_git.py push
Do NOT use raw git commands. Do NOT fight lock files. 1 call for commit, 1 for push, max.
```
NO raw git add, commit, or push commands. NO lock file workarounds. NO GIT_INDEX_FILE tricks.

### 4. Session Startup (read context from Lore tools)
```
## SESSION STARTUP
1. python scripts/safe_git.py status
2. python scripts/save_to_loreconvo.py --read --limit 10
   (Read ALL agents' sessions. Search agent:debbie for decisions.)
3. python scripts/query_loredocs.py --list
4. Read CLAUDE.md (repo root) for TODOs and rules
5. Read docs/DEBBIE_DASHBOARD.md for Debbie's latest decisions
6. [agent-specific reads -- e.g., Meg reads docs/qa/, Ron reads docs/security/]
```
NO inline Python code for LoreConvo/LoreDocs access. Use the CLI scripts.

### 5. Inputs (what this agent reads)
Explicit list of files/sources this agent depends on, with paths.

### 6. Outputs (what this agent produces)
Explicit list of output files with exact paths and naming conventions.

### 7. Dependencies (upstream and downstream agents)
```
## DEPENDENCIES
Reads from: [list of agents and their output paths]
Feeds into: [list of agents that read this agent's output]
```

### 8. Session Save (MANDATORY -- identical for all agents)
```
## SESSION SAVE
python scripts/save_to_loreconvo.py \
    --title "[Agent] session YYYY-MM-DD" \
    --surface "[surface]" \
    --summary "COMPLETED: ... | BLOCKED: ... | PENDING_GIT: ... | HANDOFFS: ..." \
    --tags '["agent:[name]"]' \
    --artifacts '["path/to/output"]'
```
NO inline Python code. Use the CLI script only.

### 9. Rules (agent-specific constraints)
What this agent can and cannot do (e.g., "does NOT modify source code").

---

## BANNED from all prompts

- **No inline Python code blocks** for LoreConvo saves, git operations, or file manipulation. Reference scripts instead.
- **No raw git commands** (git add, git commit, git push, find .git -name "*.lock")
- **No hardcoded LoreConvo DB paths** (glob patterns like `/sessions/*/mnt/...`)
- **No duplicated rules** already in CLAUDE.md (just say "Read CLAUDE.md for full rules")

---

## Agent Dependency Map

```
Debbie (decisions via DEBBIE_DASHBOARD.md + LoreConvo agent:debbie)
  |
  v
Ron (builder) ---> produces code in ron_skills/, docs/COMPLETED.md
  |                 reads: competitive-intel tasks (RON: tagged items)
  v
Meg (QA) ---> reads Ron's code, produces docs/qa/qa_report_YYYY_MM_DD.md
  |
Brock (security) ---> reads Ron's code, produces docs/security/security_report_YYYY_MM_DD.md
  |                    cross-refs with Gina (BROCK-REVIEW: / GINA-REVIEW: tags)
  |                    reads: competitive-intel security notes (BROCK-REVIEW: tags)
  v
Gina (architecture) ---> reads pipeline + Ron's code, produces docs/architecture/
  |                       cross-refs with Brock
  |                       reads: competitive-intel architecture items (GINA-REVIEW: tags)
  v
Scout (research) ---> reads market, produces Opportunities/ reports
  |
Competitive Intel ---> reads market + products, produces docs/competitive/
  |                    feeds into: Ron (tasks), Madison (messaging), Gina (arch),
  |                    Brock (security), Jacqueline (dashboard)
  v
Jacqueline (PM) ---> reads ALL of the above, produces:
  |                   - docs/pm/executive_dashboard_YYYY_MM_DD.html (daily)
  |                   - docs/pm/labyrinth_product_roadmap_YYYY_MM_DD.html (weekly)
  |                   - docs/DEBBIE_DASHBOARD.md (updates daily)
  v
Madison (marketing) ---> reads product status + competitive intel messaging angles
  |                       (MADISON: tagged notes on PROD items)
  |                       produces docs/marketing/blog_drafts/
  |
John (tech docs) ---> reads Meg-verified code, produces ron_skills/*/docs/
  |
  v
Debbie (reviews dashboards, makes decisions, cycle repeats)
```

### Execution Order (daily)

| Time | Agent | Depends on |
|------|-------|------------|
| 5:05 PM | Ron | Debbie decisions, Meg/Brock findings |
| 6:30 PM | Meg | Ron's commits |
| 11:30 PM | Brock | Ron's commits, Gina cross-refs |
| 1:30 AM (daily) | Jacqueline | Ron, Meg, Brock, Scout, Gina outputs |
| 3:00 AM (Mon) | Scout | Market research (independent) |
| 4:00 AM (Wed/Sat) | Gina | Pipeline data, Ron's code, Brock cross-refs |
| 12:30 AM (Tue/Fri) | Madison | Product status from Jacqueline |
| 3:30 AM (Tue/Sat) | John | Meg-verified code |

### Per-Agent Input/Output Reference

**Ron**
- Reads: CLAUDE.md, DEBBIE_DASHBOARD.md, docs/qa/, docs/security/, LoreConvo (all agents)
- Produces: Code in ron_skills/, docs/COMPLETED.md, LoreConvo session (surface: cowork)

**Meg**
- Reads: Ron's recent commits (git log), ron_skills/ code, previous QA reports
- Produces: docs/qa/qa_report_YYYY_MM_DD.md, test files in ron_skills/*/tests/, LoreConvo (surface: qa)

**Brock**
- Reads: Ron's recent commits, ron_skills/ code, docs/architecture/ for BROCK-REVIEW items
- Produces: docs/security/security_report_YYYY_MM_DD.md, LoreConvo (surface: security)

**Gina**
- Reads: Pipeline DB, ron_skills/ code, docs/security/ for GINA-REVIEW items
- Produces: docs/architecture/OPP-XXX_*.md, docs/architecture/product_review_YYYY_MM_DD.md, Opportunities/LATEST_ARCHITECTURE_REVIEW.html, LoreConvo (surface: cowork)

**Scout**
- Reads: Market research (web), pipeline DB for existing opportunities
- Produces: Opportunities/LATEST_SCOUT_REPORT.html, Opportunities/scout_YYYY_MM_DD.md, LoreConvo (surface: pipeline)

**Jacqueline**
- Reads: ALL agent outputs (Ron, Meg, Brock, Gina, Scout, Madison, John), CLAUDE.md, DEBBIE_DASHBOARD.md, pipeline DB, LoreConvo
- Produces: docs/pm/executive_dashboard_YYYY_MM_DD.html, docs/pm/labyrinth_product_roadmap_YYYY_MM_DD.html (Sat), docs/DEBBIE_DASHBOARD.md (updates), LoreConvo (surface: pm)

**Madison**
- Reads: Product status from Jacqueline/CLAUDE.md, blog publishing skill
- Produces: docs/marketing/blog_drafts/*.md, docs/marketing/promo/*.md, docs/marketing/content_calendar_madison.md, LoreConvo (surface: marketing)

**Competitive Intel**
- Reads: Web research, product CLAUDE.md files, previous reports in docs/competitive/, pipeline state
- Produces: docs/competitive/competitive_scan_YYYY_MM_DD.md, pipeline items (tasks for Ron, opportunities, architecture items for Gina, MADISON: notes on PROD items), LoreConvo (surface: pipeline)
- Feeds into: Ron (RON: tasks), Madison (MADISON: notes), Gina (GINA-REVIEW: arch items), Brock (BROCK-REVIEW: notes), Jacqueline (dashboard), Debbie (new opportunities to triage)

**John**
- Reads: Meg-verified code in ron_skills/, existing docs in ron_skills/*/docs/
- Produces: ron_skills/*/docs/ (cli_reference, mcp_tool_catalog, quickstart, CHANGELOG), docs/technical/tech_docs_report_YYYY_MM_DD.md, LoreConvo (surface: cowork)
