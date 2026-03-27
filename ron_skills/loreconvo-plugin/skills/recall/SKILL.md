---
name: recall
description: >
  Recall context from past Claude sessions. Use when the user asks "what did we decide about",
  "what happened last session", "recall", "remember", "find past sessions", "session history",
  "load context for", "what did we discuss", or wants to search conversation history.
  Also triggers on "project context", "skill history", or "linked sessions".
metadata:
  version: "0.3.0"
  author: "Labyrinth Analytics Consulting"
---

# LoreConvo -- Recall Context

Search and retrieve context from past Claude sessions stored in LoreConvo.

## When to Use

- User asks about prior work, decisions, or discussions
- Starting a new session and need to load relevant context
- Searching for a specific topic across conversation history
- Loading project context or skill usage history

## Available MCP Tools for Recall

| Tool | Use When |
|------|----------|
| `get_recent_sessions` | User wants to see what was done recently |
| `get_session` | Need to retrieve a specific session by ID |
| `search_sessions` | Searching for a topic or keyword across all sessions |
| `get_context_for` | Best for "what did we decide about X" style queries |
| `get_project` | Loading context for a named project |
| `list_projects` | Seeing all tracked projects |
| `get_skill_history` | Finding sessions that used a specific skill |

## Workflow

1. Determine what the user is looking for (topic, project, time range, skill)
2. Choose the right tool:
   - Broad topic search: `get_context_for("topic")`
   - Keyword search: `search_sessions("query")`
   - Recent activity: `get_recent_sessions()`
   - Project-scoped: `get_project("project-name")`
   - Skill-scoped: `get_skill_history("skill-name")`
3. Present results with key decisions, artifacts, and open questions highlighted
4. Offer to load more detail from specific sessions if needed
