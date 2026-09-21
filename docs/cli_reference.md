# LoreConvo Bypass CLI Reference

LoreConvo ships with a bypass CLI for the MCP-unavailable case -- use it when the MCP server is not running, the MCP client is not connected, or you need to script session saves from outside Claude. This is not the separate LoreConvo CLI product (in pre-launch). If you are in a Claude session with MCP working, use the MCP tools directly; they are faster and return structured data.

---

## Getting Started

Invoke via the Python module interface from any terminal where LoreConvo is installed:

```bash
python -m loreconvo.cli [command] [options]
```

Check that it is working and see the installed version:

```
$ python -m loreconvo.cli --version
loreconvo, version 0.10.8
```

(The version you see will reflect your installed version, which may differ from the example above.)

---

## Commands

LoreConvo has 12 commands (10 top-level plus the `skills list` and `license clear` subcommands):

| Command | What it does |
|---------|-------------|
| `save` | Save a session to memory |
| `list` | List recent sessions |
| `search` | Search session memory by keyword |
| `inspect` | Inspect, filter, or delete stored sessions |
| `export` | Export a session as markdown, JSON, or a shareable team bundle (Pro) |
| `merge` | Import sessions from a shared export file (Pro) |
| `pin` | Pin a session to exclude it from automated cleanup |
| `rebuild-index` | Rebuild the LanceDB semantic search index (Pro) |
| `skill-history` | Show sessions that used a specific skill |
| `skills list` | List all skills by usage count |
| `stats` | Show memory statistics |
| `license clear` | Clear a LoreConvo Pro license |

---

## `save`

Save a session to memory. Use this after finishing a work session or from an automated script that needs to log its work.

### Syntax

```
python -m loreconvo.cli save -t "TITLE" -s SURFACE -m "SUMMARY" [options]
```

### Options

| Flag | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| `-t`, `--title` | text | yes | -- | Short name for the session |
| `-s`, `--surface` | choice | yes | -- | Where the session happened: `cowork`, `code`, or `chat` |
| `-m`, `--summary` | text | yes | -- | What happened in the session |
| `-p`, `--project` | text | no | none | Associate with a project |
| `-d`, `--decisions` | text | no | none | Key decisions (use multiple times for multiple decisions) |
| `--skills` | text | no | none | Skills used (use multiple times) |
| `--tags` | text | no | none | Tags for categorization (use multiple times) |
| `--reasoning-notes` | text | no | none | Optional reasoning chain text: why a decision was made, what alternatives were considered |
| `--external-tool` | flag | no | off | Mark as an external tool session; excluded from auto-load and search by default |
| `--permanent` | flag | no | off | Pin this session immediately so it is never auto-pruned |

### Example

```
$ python -m loreconvo.cli save -t "Fixed login bug" -s code -m "Debugged the auth timeout issue in the session middleware" --tags "bugfix" --decisions "Switch to JWT tokens"
Saved session: 922b287f-6cd6-44b0-8701-ef778199966e
  Title: Fixed login bug
  Surface: code
```

### Example with project and multiple decisions

```
$ python -m loreconvo.cli save \
    -t "Tax pipeline debugging" \
    -s code \
    -m "Fixed the K-1 parser edge case for partnership distributions" \
    -p "secret-agent-man" \
    -d "Use decimal instead of float for dollar amounts" \
    -d "Skip negative distributions" \
    --skills "us-federal-tax" \
    --tags "tax" --tags "bugfix"
Saved session: a1b2c3d4-e5f6-7890-abcd-ef1234567890
  Title: Tax pipeline debugging
  Surface: code
  Project: secret-agent-man
```

### Field length limits

`summary` is capped at 15,000 characters. Each individual `-d`/`--decisions` entry is capped at 2,000 characters. Content that exceeds the cap is stored truncated and ends with a `[TRUNCATED: <field> exceeds <cap> chars]` marker, so a cut is always visible on recall; the command output also shows `truncated: true` when any cap fires but does not say which field was cut.

Keep each decision entry to a short, self-contained claim. Use `--summary` for narrative detail.

### Common errors

**"Missing option '-t'."** -- You forgot the required `--title` flag. All three of `--title`, `--surface`, and `--summary` are required.

---

## `list`

List recent sessions, newest first. Use this to see what you have been working on.

### Syntax

```
python -m loreconvo.cli list [options]
```

### Options

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `-n`, `--limit` | integer | 10 | Maximum number of sessions to show |
| `-d`, `--days` | integer | 30 | How far back to look (in days) |
| `-p`, `--project` | text | none | Show only sessions for this project |
| `--skill` | text | none | Show only sessions that used this skill |

### Example

```
$ python -m loreconvo.cli list -n 3
  2026-04-04  code    Fixed login bug
           id: 922b287f-6cd6-44b0-8701-ef778199966e

1 session(s)
```

Each line shows the date, surface, project (if set), title, and skills used. The session ID is printed below each entry for use with other commands.

---

## `search`

Search session memory by keyword. Matches against session titles, summaries, and decisions. Use this when you know roughly what you are looking for but not the exact session.

### Syntax

```
python -m loreconvo.cli search QUERY [options]
```

### Options

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--persona` | text | none | Filter to sessions tagged with this persona |
| `-p`, `--project` | text | none | Filter to sessions in this project |
| `--skill` | text | none | Filter to sessions that used this skill |
| `-n`, `--limit` | integer | 10 | Maximum results to return |
| `--semantic` | flag | off | Use LanceDB hybrid (vector + BM25) search. Pro tier only. Requires `rebuild-index` to have been run at least once. |

### Example

```
$ python -m loreconvo.cli search "login"
  [0.0] 2026-04-04  Fixed login bug
         [decision] Switch to JWT tokens
         id: 922b287f-6cd6-44b0-8701-ef778199966e

1 result(s)
```

Results are ranked by relevance score (shown in brackets). Decisions from matching sessions are shown inline so you can quickly see what was decided.

---

## `export`

Export a session for pasting into Claude Chat or sharing with others. Outputs a clean markdown summary, raw JSON, a shareable team bundle, or an Anthropic managed-agents bundle.

### Syntax

```
python -m loreconvo.cli export [SESSION_ID] [options]
```

### Options

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--last` | flag | off | Export the most recent session (instead of specifying an ID) |
| `--format` | choice | markdown | Output format: `markdown`, `json`, `shared` (Pro), or `anthropic-v1` (Pro) |
| `-p`, `--project` | text | none | Filter by project (`shared` and `anthropic-v1` formats only) |
| `--session-ids` | text | none | Comma-separated list of session IDs to include (`shared` and `anthropic-v1` formats only) |
| `--all` | flag | off | Export all sessions (`shared` and `anthropic-v1` formats; use with care) |
| `--out` | text | none | Output file path (`shared` and `anthropic-v1` formats) |
| `--days-back` | integer | none | Limit to sessions from the last N days (`anthropic-v1` only) |

You must provide either a session ID or the `--last` flag for single-session exports. For multi-session formats (`shared`, `anthropic-v1`) use `--session-ids`, `--project`, or `--all`.

#### Format guide

| Format | Use when |
|--------|----------|
| `markdown` | Pasting context into Claude Chat or sharing with a colleague |
| `json` | Scripts and automation that process session data programmatically |
| `shared` | Sharing a session bundle with a teammate who will import it via `merge` (Pro) |
| `anthropic-v1` | Exporting to Anthropic managed-agents memory format (Pro) |

### Example (markdown)

```
$ python -m loreconvo.cli export --last
# Context from Previous Session

**Title:** Fixed login bug
**Date:** 2026-04-04
**Surface:** code

## Summary
Debugged the auth timeout issue in the session middleware

## Key Decisions
- Switch to JWT tokens
```

### Example (JSON)

```
$ python -m loreconvo.cli export --last --format json
{
  "id": "922b287f-6cd6-44b0-8701-ef778199966e",
  "title": "Fixed login bug",
  "surface": "code",
  "project": null,
  "start_date": "2026-04-04T04:28:09.097387",
  "summary": "Debugged the auth timeout issue in the session middleware",
  "decisions": [
    "Switch to JWT tokens"
  ],
  "artifacts": [],
  "open_questions": [],
  "skills_used": [],
  "tags": [
    "bugfix"
  ]
}
```

---

## `inspect`

Inspect stored sessions: list them, filter by tag or surface, view full detail for one session, or delete a session.

### Syntax

```
python -m loreconvo.cli inspect [SESSION_ID] [options]
```

Without arguments, lists recent sessions. Provide a SESSION_ID to view full detail for that session.

### Options

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--search` | text | none | Full-text search query |
| `--tag` | text | none | Filter by tag substring (e.g. `agent:ron`) |
| `--surface` | text | none | Filter by surface: `code`, `cowork`, or `chat` |
| `--since` | text | none | Show sessions since a date in `YYYY-MM-DD` format |
| `-n`, `--limit` | integer | 20 | Maximum sessions to show |
| `--show-stats` | flag | off | Add aggregate counts to the listing |
| `--delete` | text | none | Delete the session with this ID (prompts for confirmation) |

### Example

```
$ python -m loreconvo.cli inspect --tag "agent:ron" --since 2026-09-01 -n 5
  2026-09-14  code    ron-builder session 2026-09-14
           id: 8b3e5a12-1234-5678-abcd-ef0987654321

1 session(s)
```

---

## `merge`

Import sessions from a shared export file produced by `export --format shared`. LoreConvo Pro required. Duplicate sessions (by UUID or content hash) are skipped automatically.

### Syntax

```
python -m loreconvo.cli merge FILE
```

`FILE` must be a JSON bundle created by `python -m loreconvo.cli export --format shared`.

### Example

```
$ python -m loreconvo.cli merge teammate_sessions.json
Imported 3 new session(s), skipped 1 duplicate(s).
```

---

## `pin`

Pin a session to exclude it from automated cleanup. Any existing expiry date is cleared when pinning. Use `--unpin` to remove the exclusion.

### Syntax

```
python -m loreconvo.cli pin SESSION_ID [--unpin]
```

### Options

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--unpin` | flag | off | Remove the automated-cleanup exclusion instead of setting it |

### Example

```
$ python -m loreconvo.cli pin 922b287f-6cd6-44b0-8701-ef778199966e
Session pinned: 922b287f-6cd6-44b0-8701-ef778199966e

$ python -m loreconvo.cli pin 922b287f-6cd6-44b0-8701-ef778199966e --unpin
Session unpinned: 922b287f-6cd6-44b0-8701-ef778199966e
```

Exit codes: 0 = success, 1 = user error (bad ID or session not found), 2 = DB/system error.

---

## `rebuild-index`

Rebuild the LanceDB semantic search index used by `search --semantic`. Pro tier required. Downloads the BGE-small-en-v1.5 embedding model (~130MB) on first run if it is not already cached. Run once after your first Pro activation, or to recover a corrupted index.

### Syntax

```
python -m loreconvo.cli rebuild-index
```

### Example

```
$ python -m loreconvo.cli rebuild-index
Rebuilding semantic search index (may take 1-2 minutes on first run)...
[OK] Index built: 47 session(s) indexed (of 50 total in database).
```

---

## `license clear`

Clear a LoreConvo Pro license from this machine. Use `--suite` to also clear the suite-wide Pro key from the sibling product (LoreDocs).

### Syntax

```
python -m loreconvo.cli license clear [--suite]
```

### Options

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--suite` | flag | off | Also clear suite-wide Pro from the sibling LoreDocs product |

### Example

```
$ python -m loreconvo.cli license clear
LoreConvo Pro license cleared.
```

---

## `skill-history`

Show all sessions that used a specific skill. Use this to track how often and in what context a particular skill gets used.

### Syntax

```
python -m loreconvo.cli skill-history SKILL_NAME [options]
```

### Options

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `-d`, `--days` | integer | 90 | How far back to search |

### Example

```
$ python -m loreconvo.cli skill-history rental-property-accounting
  2026-04-01  cowork  Rental expense review for Q1
  2026-03-28  code    Depreciation schedule update

2 session(s) used 'rental-property-accounting'
```

---

## `skills list`

List all distinct skills that have been recorded in session memory, sorted by how often they were used. Use this to see which skills you rely on most.

### Syntax

```
python -m loreconvo.cli skills list
```

### Example

```
$ python -m loreconvo.cli skills list
     5  us-federal-tax
     3  rental-property-accounting
     2  ynab-multi-budget-management
     1  wa-bo-tax-consulting

4 distinct skill(s)
```

The number on the left is how many sessions used that skill.

---

## `stats`

Show a quick summary of your session memory: total sessions, projects, and the most recent session.

### Syntax

```
python -m loreconvo.cli stats
```

### Example

```
$ python -m loreconvo.cli stats
Total sessions: 1
Projects: 0
Most recent: Fixed login bug (2026-04-04)
```

When you have projects defined, stats shows a breakdown by project:

```
$ python -m loreconvo.cli stats
Total sessions: 47
Projects: 3
  secret-agent-man: 28 sessions
  side_hustle: 15 sessions
  labyrinth-website: 4 sessions
Most recent: Tax pipeline debugging (2026-04-04)
```

---

## Data Location

The CLI reads and writes to the same SQLite database used by the MCP server:

```
~/.loreconvo/sessions.db
```

You can override this by setting the `LORECONVO_DB` environment variable.

---

## Fallback Script

If you are running a scheduled task or automation script where the MCP server is not available, the `scripts/save_to_loreconvo.py` script provides the same save/read/search operations directly against the database. See the [README](../README.md) for usage examples.
