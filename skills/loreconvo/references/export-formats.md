# Session Bridge Export Formats

## Markdown Export (for Chat paste)

The markdown format is designed to be pasted into Claude Chat to prime a new session with context from a previous Code or Cowork session.

```markdown
# Context from Previous Session

**Title:** Session Bridge PRD and Architecture
**Date:** 2026-03-22
**Surface:** cowork
**Project:** session-bridge
**Skills Used:** product-management:write-spec, mcp-builder

## Summary
[2-3 paragraph narrative]

## Key Decisions
- Session Bridge uses SQLite with FTS5 for local-first storage
- Plugin distributed via Cowork/Code marketplace
- $8/mo Pro tier, $20/mo Business tier

## Artifacts
- session-bridge-prd.md (PRD with competitive analysis)
- session_bridge_projection.xlsx (12-month financial model)

## Open Questions
- Can Cowork hooks fire on session end reliably?
- What is Anthropic's plugin marketplace revenue share?
```

## JSON Export (for programmatic use)

```json
{
  "id": "uuid-here",
  "title": "Session Bridge PRD and Architecture",
  "surface": "cowork",
  "project": "session-bridge",
  "start_date": "2026-03-22T10:00:00",
  "summary": "...",
  "decisions": ["..."],
  "artifacts": ["..."],
  "open_questions": ["..."],
  "skills_used": ["product-management:write-spec", "mcp-builder"],
  "tags": ["architecture", "planning"]
}
```
