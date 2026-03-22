# Session Bridge SQLite Schema

## Tables

### sessions
Primary table storing session summaries.

| Column | Type | Description |
|--------|------|-------------|
| id | TEXT PK | UUID |
| title | TEXT | Short session title |
| surface | TEXT | 'cowork', 'code', or 'chat' |
| project | TEXT | Project name (nullable) |
| start_date | TEXT | ISO 8601 timestamp |
| end_date | TEXT | ISO 8601 timestamp (nullable) |
| summary | TEXT | Narrative summary |
| decisions | TEXT | JSON array of decision strings |
| artifacts | TEXT | JSON array of artifact paths/descriptions |
| open_questions | TEXT | JSON array of unresolved questions |
| tags | TEXT | JSON array of freeform tags |
| created_at | TEXT | Auto-populated creation timestamp |

### session_skills
Tracks which skills were used in each session.

| Column | Type | Description |
|--------|------|-------------|
| session_id | TEXT FK | References sessions.id |
| skill_name | TEXT | Skill identifier |
| skill_source | TEXT | 'local', 'plugin:name', etc. |
| invocation_count | INTEGER | Times the skill was called |

### projects
Defines projects that group related sessions.

| Column | Type | Description |
|--------|------|-------------|
| name | TEXT PK | Project identifier |
| description | TEXT | What the project is about |
| expected_skills | TEXT | JSON array of expected skill names |
| default_persona | TEXT | Auto-tag sessions with this persona |

### persona_sessions
Links sessions to personas for filtered recall.

| Column | Type | Description |
|--------|------|-------------|
| persona_name | TEXT | Persona identifier (supports hierarchy via ':') |
| session_id | TEXT FK | References sessions.id |
| relevance_note | TEXT | Why this session matters for this persona |

### session_links
Links related sessions into chains.

| Column | Type | Description |
|--------|------|-------------|
| from_session_id | TEXT FK | Source session |
| to_session_id | TEXT FK | Target session |
| link_type | TEXT | 'continues', 'related', or 'supersedes' |

## Search

Full-text search uses SQLite FTS5 over title, summary, and decisions fields.
Triggers automatically sync the FTS index on insert, update, and delete.

## Storage Location

Default: `~/.session-bridge/sessions.db`
Override: Set `SESSION_BRIDGE_DB` environment variable.
