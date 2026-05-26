# LoreConvo MCP Tool Catalog

LoreConvo provides 26 MCP tools that Claude calls during your sessions. You do not need to call these directly -- Claude uses them automatically when you ask it to save, search, or recall session context. Detailed entries below cover the core tools; the Quick Reference table at the bottom lists all 26.

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
| `summarize` | boolean | no | Pass `true` to compress the summary via the Claude Haiku API before saving. Requires `ANTHROPIC_API_KEY` and `pip install loreconvo[bridge]`. Defaults to `false`. Falls back to saving the raw summary if the API call fails. |
| `reasoning_notes` | text | no | Optional free-form text capturing the reasoning chain behind key decisions in this session -- why you made a particular choice, what alternatives were considered, or what constraints shaped the outcome. Stored separately from the summary. Not indexed for search. |

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

**Returns:** Complete session data including summary, decisions, artifacts, open questions, tags, skills, and `previous_summary` (the summary text from the prior save of the same session, or null if the session has never been updated). Use `previous_summary` to audit how a session summary evolved over time -- for example, to see what context was captured before a `/compact` mid-session save replaced it.

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

## Licensing

### `get_tier`

Check your current LoreConvo license tier and status. Returns whether Pro is active, the license mode, and key details.

**When Claude uses it:** When you ask "am I on the free tier?" or "check my LoreConvo license."

**Parameters:** None.

**Returns:** A dict with keys: `is_pro` (true/false), `mode` ("licensed", "dev_bypass", "free", or "invalid_key"), `product`, `exp` (expiry date), `email` (if present), and `error` (if invalid key).

---

### `vault_set_tier`

Activate a tier (free or pro) for LoreConvo. Pro tier removes the free-tier session limit (default: 50 sessions).

**When Claude uses it:** After you purchase a Pro license and set the `LORECONVO_PRO` environment variable.

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `tier` | text | yes | Tier to activate: `free` or `pro` |

**Returns:** A confirmation message with your tier status.

**Setup steps:**
1. Purchase a Pro license at [labyrinthanalyticsconsulting.com](https://labyrinthanalyticsconsulting.com)
2. Set `LORECONVO_PRO=<your-license-key>` in your environment
3. Restart the MCP server
4. Ask Claude to "activate Pro tier" -- Claude will call `vault_set_tier` with `tier='pro'`

**Note:** Reverting to `free` re-enables limits but preserves all existing sessions.

---

## Data Portability

### `export_sessions`

Export sessions to JSON or JSONL for backup or migration. Includes full session detail: decisions, artifacts, open questions, tags, and skills.

**When Claude uses it:** When you ask "export my LoreConvo sessions" or "back up my session history."

**Parameters:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| `output_path` | text | no | none | File path to write the export (e.g. `/tmp/loreconvo_export.json`). If omitted, data is returned inline. |
| `project` | text | no | none | Export only sessions from this project |
| `tags` | list of text | no | none | Export only sessions with any of these tags |
| `days_back` | integer | no | none | Limit to sessions from the last N days. Omit for all time. |
| `limit` | integer | no | 1000 | Maximum sessions to export |
| `format` | text | no | `json` | `json` (full export with metadata wrapper) or `jsonl` (one session per line) |

**Returns:** A dict with `status`, `session_count`, `format`, and either `data` (inline) or `path` (file written).

**Example conversation:**
> You: "Export all my sessions from the side_hustle project to /tmp/backup.json"
> Claude: *calls export_sessions with project="side_hustle" and output_path="/tmp/backup.json"*

---

### `import_sessions`

Import sessions from a LoreConvo export file (JSON or JSONL). Session UUIDs are preserved so re-importing the same file is safe.

**When Claude uses it:** When you ask "import sessions from a backup file" or "restore from this export."

**Parameters:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| `file_path` | text | yes | -- | Path to the export file (JSON or JSONL format) |
| `on_conflict` | text | no | `skip` | What to do if a session ID already exists: `skip` (leave existing unchanged) or `replace` (overwrite with imported version) |
| `dry_run` | boolean | no | false | If true, parse and validate the file but make no database changes |

**Returns:** A dict with `status`, `imported` count, `skipped` count, and any `errors` encountered.

**Example conversation:**
> You: "Import sessions from /tmp/loreconvo_export.json -- skip duplicates."
> Claude: *calls import_sessions with file_path and on_conflict="skip"*

---

## Memory Recall

### `consolidate_memories`

When you need a compact summary of everything that has happened in a project, this tool scans your recent sessions, extracts the key decisions, open questions, and tech stack facts, and writes a markdown digest that Claude injects automatically at the start of every new session. It runs on-demand and returns the digest alongside a status flag. If another consolidation is already running, it returns `status: lock_held` rather than competing.

**When Claude uses it:** When you ask for a project brief or when your digest is stale.

**Parameters:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| `project` | text | yes | -- | Project name matching the `--project` tag used when saving sessions |
| `surface` | text | no | none | Surface to consolidate: `code`, `cowork`, or `chat`. Omit to include all surfaces. |
| `max_sessions` | integer | no | 50 | Maximum number of recent sessions to analyze |
| `mode` | text | no | `heuristic` | Consolidation strategy. Only `heuristic` is available in v0.6.0. |

**Example conversation:**
> You: "Build a fresh memory digest for the side_hustle project."
> Claude: *calls consolidate_memories with project="side_hustle"*

**Free tier note:** Free users can run this tool up to 3 times per day. Pro users have unlimited runs.

---

### `get_memory_digest`

Returns the current consolidated memory digest without running a new consolidation. Use this when you want to read what LoreConvo already knows without triggering another analysis. If no consolidation has run yet, you get a `no_digest` status telling you to run `consolidate_memories` first. You can also use the optional `disable` flag to control whether the digest is injected automatically at session start.

**When Claude uses it:** When you ask to see the current digest or to enable or disable its automatic injection.

**Parameters:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| `project` | text | yes | -- | Project name |
| `surface` | text | no | none | Surface filter (`code`, `cowork`, `chat`). Omit for all surfaces. |
| `disable` | boolean | no | omitted | Pass `true` to suppress automatic digest injection; `false` to re-enable. Omit to read without changing the setting. |

**Returns:** Digest status, `source_count`, `updated_at`, `disabled` flag, and the full `digest_markdown`.

**Example conversation:**
> You: "Show me the current memory digest for side_hustle."
> Claude: *calls get_memory_digest with project="side_hustle"*

---

### `set_session_expiry`

Sets or clears an expiry date on a session. After the date passes, the session is hidden from search results, the recent sessions list, and the auto-load hook. The session is NOT deleted -- it stays in the database and you can recover it explicitly if needed. Pass `expires_at=null` to clear a previously set expiry. This is useful for marking temporary debugging notes or one-off context as time-limited.

**When Claude uses it:** When you ask to expire a session or remove an expiry you set earlier.

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `session_id` | text | yes | UUID of the session to update |
| `expires_at` | text | yes (nullable) | ISO 8601 timestamp (e.g. `2027-01-01T00:00:00Z`) when the session expires, or `null` to clear |

**Example conversation:**
> You: "Set the debugging session from yesterday to expire on June 1st."
> Claude: *calls set_session_expiry with the session UUID and expires_at="2026-06-01T00:00:00Z"*

---

### `get_dream_log`

Returns recent consolidation log entries so you can see exactly what LoreConvo processed during each run: timestamp, project, surface, mode, number of sessions analyzed, and what triggered the run. Use this to confirm consolidation happened, monitor free-tier usage, or diagnose why a digest might be missing or stale.

**When Claude uses it:** When you ask for a log of consolidation runs or want to check how many free-tier runs you have used.

**Parameters:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| `project` | text | no | none | Filter log entries to a specific project. Omit for all projects. |
| `surface` | text | no | none | Filter to a specific surface. Omit for all surfaces. |
| `limit` | integer | no | 10 | Maximum number of entries to return, newest first |

**Example conversation:**
> You: "Did a consolidation run for side_hustle today?"
> Claude: *calls get_dream_log with project="side_hustle" and limit=10*

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
| `get_tier` | Check current tier and license key status |
| `vault_set_tier` | Activate free or Pro tier |
| `export_sessions` | Export sessions to JSON or JSONL for backup or migration |
| `import_sessions` | Import sessions from a LoreConvo export file |
| `get_related_sessions` | Find sessions related to a given session by ID |
| `consolidate_memories` | Merge related sessions into persistent memory entries (Recall) |
| `get_memory_digest` | Inject a condensed memory digest into the current session (Recall) |
| `get_dream_log` | View the consolidation activity log |
| `set_session_expiry` | Mark a session to expire and be pruned after a given date |
| `get_stats` | Show usage statistics: session count, surface breakdown |
| `inspect_sessions` | Inspect session internals for debugging |
| `export_for_anthropic` | Export sessions in Anthropic managed-agent format (Pro) |
| `rebuild_semantic_index` | Rebuild the LanceDB semantic search index (Pro) |
| `loreconvo_onboard` | First-time setup wizard |
