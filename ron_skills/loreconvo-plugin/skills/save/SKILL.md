---
name: save
description: >
  Save the current session to LoreConvo. Use when the user asks to "save this session",
  "vault this", "remember this session", "/vault save", or when a significant decision was made
  and the session is ending. Also triggers on "tag as persona", "link sessions", or when the
  user switches topics and the current context should be preserved.
metadata:
  version: "0.3.0"
  author: "Labyrinth Analytics Consulting"
---

# LoreConvo -- Save Session

Capture session context (decisions, artifacts, open questions) into LoreConvo for future recall.

## When to Save

- User explicitly requests it ("vault this", "save this session")
- A significant decision was made during the session
- Session is ending and contains valuable context
- User switches topics or projects

## How to Save

Call the `save_session` MCP tool with structured data extracted from the conversation:

1. **Title**: Short, descriptive (e.g., "LoreConvo plugin packaging")
2. **Surface**: Where this ran -- `cowork`, `code`, or `chat`
3. **Summary**: 2-3 paragraphs covering what was done, why, and what matters for future sessions
4. **Decisions**: List every decision made, even small ones. These are the most searchable items.
5. **Artifacts**: Files created or modified, with paths
6. **Open questions**: Unresolved items to carry forward
7. **Skills used**: List all skills invoked during this session
8. **Project**: Associate with a defined project if applicable
9. **Tags**: Freeform tags for additional categorization

## Post-Save Tools

| Tool | Use When |
|------|----------|
| `tag_session` | Adding persona tags (e.g., "ron-bot:sql") after saving |
| `link_sessions` | Connecting this session to a related prior session |
| `create_project` | Creating a new project to group sessions |

## Session Linking

After saving, link related sessions:
- `link_sessions(from_id, to_id, "continues")` -- This session continues another
- `link_sessions(from_id, to_id, "related")` -- These sessions are related
- `link_sessions(from_id, to_id, "supersedes")` -- This session replaces another
