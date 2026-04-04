# LoreConvo MCP Tool Catalog

LoreConvo provides 12 MCP tools that Claude calls during your sessions. You do not need to call these directly -- Claude uses them automatically when you ask it to save, search, or recall session context.

This catalog explains what each tool does, when Claude uses it, and what parameters it accepts.

---

## Session Memory

### `save_session`

Save a session summary to persistent memory. Claude calls this at the end of a session (or when you ask it to save).

**When Claude uses it:** After a work session, when you say "save this session" or when the auto-save hook fires at session end.

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `title` | text | yes | Short descriptive title for the session |
| `surface` | text | yes | Where this session ran: `cowork`, `code`, or `chat` |
| `summary` | text | yes | 2-3 paragraph narrative of what happened |
| `decisions` | list of text | no | Key decisions made during the session |
| `artifacts` | list of text | no | Files created or modified |
| `open_questions` | list of text | no | Unresolved questions to carry forward |
| `tags` | list of text | no | Freeform tags for categorization |
| `skills_used` | list of text | no | Skills invoked during the session |
| `project` | text | no | Project name to associate with |
| `start_date` | text | no | ISO 8601 start time (defaults to now) |
| `end_date` | text | no | ISO 8601 end time |

**Returns:** The new session ID and a confirmation.

**Example conversation:**
> You: "Save this session to LoreConvo. We worked on the K-1 parser and decided to use decimal types."
> Claude: *calls save_session with title, summary, decisions, and tags*

**Free tier note:** Free accounts are limited to 50 saved sessions. After that, you will see a "limit_reached" message with a link to upgrade.

---

### `get_recent_sessions`

Get a list of recent session summaries. Claude calls this at the start of a session to see what you have been working on.

**When Claude uses it:** At session start (via the auto-load hook or CLAUDE.md instructions), or when you ask "what was I working on?"

**Parameters:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| `limit` | integer | no | 10 | Maximum sessions to return |
| `days_back` | integer | no | 30 | How far back to look |
| `project` | text | no | none | Filter to sessions in this project |
| `skill` | text | no | none | Filter to sessions that used this skill |

**Returns:** A list of sessions with ID, title, surface, date, summary preview (first 200 characters), decision count, and skills used.

**Example conversation:**
> You: "Check LoreConvo for my recent sessions about the rental property."
> Claude: *calls get_recent_sessions with project filter or follows up with search_sessions*

---

### `get_session`

Get the full details of a specific session, including the complete summary, all decisions, artifacts, and open questions.

**When Claude uses it:** When you ask for details about a specific session, or when Claude needs to drill into a session found via search.

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `session_id` | text | yes | The UUID of the session to retrieve |

**Returns:** Complete session data including summary, decisions, artifacts, open questions, tags, and skills.

---

### `search_sessions`

Search session memory by keyword, with optional filters. Matches against titles, summaries, and decisions.

**When Claude uses it:** When you ask "find the session where we discussed X" or "search LoreConvo for Y."

**Parameters:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| `query` | text | yes | -- | Search keywords |
| `persona` | text | no | none | Filter to sessions tagged with this persona (supports prefix matching) |
| `tags` | list of text | no | none | Filter to sessions with any of these tags |
| `skills` | list of text | no | none | Filter to sessions that used any of these skills |
| `project` | text | no | none | Filter to sessions in this project |
| `limit` | integer | no | 10 | Maximum results |

**Returns:** Matching sessions ranked by relevance score, with summary preview and decisions.

**Example conversation:**
> You: "Search LoreConvo for sessions about depreciation schedules."
> Claude: *calls search_sessions with query "depreciation schedules"*

---

### `get_context_for`

Get relevant session context for a topic. This is the best tool for "recall" -- it finds and returns the most useful session excerpts for a given subject.

**When Claude uses it:** At session start to load prior decisions and context, or when you ask Claude to "recall what we discussed about X."

**Parameters:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| `topic` | text | yes | -- | The topic to find context for |
| `max_results` | integer | no | 5 | Maximum excerpts to return |

**Returns:** Session titles, dates, summaries, decisions, and open questions for the most relevant sessions.

---

## Organization

### `tag_session`

Tag a session with a persona for filtered recall. Supports hierarchical personas -- tagging with `ron-bot:sql` will match queries for `ron-bot`.

**When Claude uses it:** When you want to mark a session as relevant to a specific agent or role.

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `session_id` | text | yes | The session to tag |
| `persona_name` | text | yes | Persona identifier (e.g., `ron-bot`, `tax-prep`) |
| `relevance_note` | text | no | Why this session matters for the persona |

---

### `link_sessions`

Connect two related sessions with a relationship type. Use this to create a chain of sessions that build on each other.

**When Claude uses it:** When you say "this session continues from my last one" or when Claude detects related work.

**Parameters:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| `from_id` | text | yes | -- | Source session ID |
| `to_id` | text | yes | -- | Target session ID |
| `link_type` | text | no | `continues` | Relationship: `continues`, `related`, or `supersedes` |

---

## Projects

### `create_project`

Create or update a project definition. Projects group related sessions and can auto-associate based on skill usage.

**When Claude uses it:** When you ask to "create a project for X" or when setting up a new workstream.

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `name` | text | yes | Project identifier (e.g., `secret-agent-man`) |
| `description` | text | no | What this project is about |
| `expected_skills` | list of text | no | Skills typically used in this project |
| `default_persona` | text | no | Auto-tag new sessions with this persona |

---

### `get_project`

Get project details including recent sessions and skill usage statistics.

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `project_name` | text | yes | The project identifier |

---

### `list_projects`

List all defined projects with session counts. No parameters required.

---

## Discovery

### `get_skill_history`

See all sessions that used a specific skill. Useful for understanding how often a skill is used and in what contexts.

**Parameters:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| `skill_name` | text | yes | -- | The skill to look up |
| `days_back` | integer | no | 90 | How far back to search |

---

### `vault_suggest`

Get proactive context suggestions based on your session history. This tool analyzes recent sessions and surfaces:

- Sessions with unresolved open questions that need follow-up
- Sessions with key decisions worth reviewing before starting new work
- Skill gaps: skills expected by a project but not used recently

**When Claude uses it:** At the start of a session when you ask "what should I work on?" or "what context should I load?"

**Parameters:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| `project` | text | no | none | Filter suggestions to this project |
| `persona` | text | no | none | Filter to sessions tagged with this persona |
| `days_back` | integer | no | 14 | How far back to look |
| `limit` | integer | no | 5 | Maximum suggestions |

**Example conversation:**
> You: "What unresolved questions do I have from recent sessions?"
> Claude: *calls vault_suggest and presents open questions from recent sessions*

---

## Quick Reference

| Tool | One-line summary |
|------|-----------------|
| `save_session` | Save a session with decisions, artifacts, and tags |
| `get_recent_sessions` | List recent sessions (optionally filtered) |
| `get_session` | Get full details of one session by ID |
| `search_sessions` | Full-text keyword search across sessions |
| `get_context_for` | Load relevant context for a topic |
| `tag_session` | Tag a session with a persona |
| `link_sessions` | Connect two related sessions |
| `create_project` | Create or update a project definition |
| `get_project` | Get project details and session stats |
| `list_projects` | List all projects with session counts |
| `get_skill_history` | See sessions that used a specific skill |
| `vault_suggest` | Proactive suggestions for what context to load |
