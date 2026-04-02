# Pipeline Agent Guide

All agents in the Project Ron team MUST use the opportunity pipeline for their work.
The pipeline is the shared data layer that connects Scout -> Gina -> Ron and tracks
QA/security findings from Meg and Brock.

**If you are an agent reading this file, follow the instructions for YOUR role below.**

## Pipeline Setup (all agents)

```python
import sys, os
sys.path.insert(0, os.path.expanduser('~/.loreconvo'))
from pipeline_helpers import PipelineDB
db = PipelineDB()
# ... your operations ...
db.close()
```

If the native path fails (e.g., in a Cowork VM), PipelineDB auto-discovers the
database from mounted paths. You can also pass an explicit path:
```python
db = PipelineDB(db_path='/sessions/.../mnt/.loreconvo/sessions.db')
```

## Status Lifecycle

```
scouted -> approved-for-review -> architecture-proposed -> approved -> in-progress -> completed
scouted -> archived (Debbie skips it)
architecture-proposed -> rejected (disposition: rearchitect or archive)
Any status -> on-hold (with hold reason)
```

---

## Agent-Specific Instructions

### Scout (weekly-product-scout)

**MUST DO on every run:**
1. For each opportunity you discover, create a pipeline entry:
   ```python
   opp_id = db.add_opportunity(
       title='Product Name MCP',
       summary='One-paragraph description of the opportunity...',
       extra_tags=['niche:data-engineering', 'type:mcp-server']
   )
   print(f'Created {opp_id}')
   ```
2. Link yourself to the opportunity:
   ```python
   db.link_persona(opp_id, 'Scout', 'Discovered in weekly scan')
   ```
3. At the end of your run, print a summary of all OPP IDs you created so other
   agents can reference them.

**DO NOT** update status on existing items. Your job is to ADD new scouted items only.

---

### Gina (enterprise-architect-gina)

**MUST DO on every run:**
1. Query for items ready for your review:
   ```python
   items = db.get_by_status('approved-for-review')
   ```
2. For each item you review, write your architecture proposal:
   ```python
   doc_path = db.set_architecture(opp_id, architecture_text)
   db.set_effort(opp_id, 5)  # Fibonacci: 1,2,3,5,8,13
   db.set_dependencies(opp_id, 'Depends on: LoreConvo v0.3+, Python 3.10+')
   db.set_open_questions(opp_id, 'Q1: Should this use SQLite or DuckDB?')
   db.update_status(opp_id, 'architecture-proposed')
   ```
3. Link yourself:
   ```python
   db.link_persona(opp_id, 'Gina', 'Architecture review completed')
   ```

You are already doing this correctly. Keep it up.

---

### Ron (ron-daily)

**MUST DO at the START of every run (BEFORE other work):**

1. **Sync Debbie's decisions to the pipeline database.** Read DEBBIE_DASHBOARD.md
   and CLAUDE.md for any approval/rejection/hold decisions Debbie has made. Then
   apply them:
   ```python
   # Example: Debbie approved OPP-007 for architectural review at P2
   db.update_status('OPP-007', 'approved-for-review')
   db.set_priority('OPP-007', 'P2')

   # Example: Debbie put OPP-006 on hold
   db.set_hold_reason('OPP-006', 'No local SQL Server installation')

   # Example: Debbie approved Gina's architecture for OPP-002
   db.update_status('OPP-002', 'approved')
   ```
2. Only sync decisions that have NOT already been applied. Check current status
   first:
   ```python
   item = db.get_opportunity('OPP-007')
   if item and item['_status'] != 'approved-for-review':
       db.update_status('OPP-007', 'approved-for-review')
   ```

**MUST DO when starting build work on an approved item:**
```python
db.update_status(opp_id, 'in-progress')
db.link_persona(opp_id, 'Ron', 'Starting build')
```

**MUST DO when completing an item:**
```python
db.update_status(opp_id, 'completed')
```

---

### Meg (meg-qa-daily)

**MUST DO on every run:**
1. After writing your QA report, log each finding to the pipeline if it relates
   to a specific product/opportunity:
   ```python
   # Find related pipeline items
   items = db.search('LoreConvo')
   for item in items:
       # Append QA finding to open_questions
       existing = item.get('open_questions', '') or ''
       new_note = f'\n\nMEG-031 (MEDIUM, {datetime.now().strftime("%Y-%m-%d")}): Version mismatch in CLAUDE.md vs SKILL.md'
       db.set_open_questions(item['id'], existing + new_note)
   ```
2. For findings that affect the overall pipeline health, print a summary:
   ```python
   print('QA Pipeline Impact: 1 MEDIUM finding on OPP-003 (LorePrompts)')
   ```

---

### Brock (brock-security-daily)

**MUST DO on every run:**
1. After writing your security report, log each finding to the pipeline if it
   relates to a specific product/opportunity:
   ```python
   items = db.search('SQL Optimizer')
   for item in items:
       existing = item.get('open_questions', '') or ''
       new_note = f'\n\nSEC-011 (MEDIUM, {datetime.now().strftime("%Y-%m-%d")}): TOCTOU race in file export'
       db.set_open_questions(item['id'], existing + new_note)
   ```
2. For CRITICAL/HIGH findings, also update the item status if appropriate:
   ```python
   # If a CRITICAL security finding blocks a product launch:
   db.set_hold_reason(opp_id, 'CRITICAL security finding SEC-XXX must be resolved first')
   ```

---

### Jacqueline (pm-jacqueline-daily)

**MUST DO on every run:**
1. Read the full pipeline state as your primary data source:
   ```python
   all_items = db.get_all_pipeline()
   for item in all_items:
       print(f"{item['id']}: {item['title']} -- {item['_status']} (P{item['_priority'] or '?'})")
   ```
2. Cross-reference pipeline state with agent reports (Meg, Brock, Ron) to validate
   that what agents reported matches the DB state.
3. Include the pipeline dashboard table in your HTML executive dashboard.
4. Flag any items where status seems stale (e.g., 'in-progress' for more than 7 days).

You can also generate a markdown dashboard:
```python
dashboard_md = db.generate_markdown_dashboard()
print(dashboard_md)
```

---

### Madison (madison-marketing-agent)

**MUST DO on every run:**
1. Check pipeline for product status before writing about any product:
   ```python
   all_items = db.get_all_pipeline()
   ```
2. Only write about products that are in 'approved', 'in-progress', or 'completed' status.
3. Reference pipeline OPP IDs when linking content to specific products.

---

## Pipeline Methods Quick Reference

| Method | Used By | Purpose |
|--------|---------|---------|
| `add_opportunity(title, summary, tags)` | Scout | Create new scouted item |
| `get_by_status(status)` | Gina, Jacqueline | Query items by status |
| `get_all_pipeline()` | Jacqueline, Madison | Full pipeline view |
| `get_opportunity(opp_id)` | All | Get single item |
| `search(query)` | Meg, Brock | Find related items |
| `update_status(opp_id, status)` | Ron, Gina | Change item status |
| `set_priority(opp_id, 'P1')` | Ron | Set priority from Debbie's decisions |
| `set_effort(opp_id, 5)` | Gina | Fibonacci effort estimate |
| `set_architecture(opp_id, text)` | Gina | Write architecture proposal |
| `set_dependencies(opp_id, text)` | Gina | Note dependencies |
| `set_open_questions(opp_id, text)` | Gina, Meg, Brock | Add questions/findings |
| `set_hold_reason(opp_id, reason)` | Ron, Brock | Put item on hold |
| `reject(opp_id, reason, disposition)` | Ron | Reject with reason |
| `link_persona(opp_id, name, note)` | All | Link agent to item |
| `generate_markdown_dashboard()` | Jacqueline | Generate dashboard table |
