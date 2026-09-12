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

LoreConvo has 7 commands (including the `skills` subgroup):

| Command | What it does |
|---------|-------------|
| `save` | Save a session to memory |
| `list` | List recent sessions |
| `search` | Search session memory by keyword |
| `export` | Export a session as markdown or JSON |
| `skill-history` | Show sessions that used a specific skill |
| `skills list` | List all skills by usage count |
| `stats` | Show memory statistics |

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

`summary` is capped at 8,000 characters. Each individual `-d`/`--decisions` entry is capped at 500 characters. Content that exceeds the cap is stored truncated without an ellipsis; the command output shows `truncated: true` when any cap fires but does not say which field was cut.

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

Export a session for pasting into Claude Chat or sharing with others. Outputs either a clean markdown summary or raw JSON.

### Syntax

```
python -m loreconvo.cli export [SESSION_ID] [options]
```

### Options

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--last` | flag | off | Export the most recent session (instead of specifying an ID) |
| `--format` | choice | markdown | Output format: `markdown` or `json` |

You must provide either a session ID or the `--last` flag.

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

### When to use each format

**Markdown** is best for pasting into Claude Chat or sharing with a colleague. It is human-readable and includes all the important context.

**JSON** is best for scripts and automation. Use it when you need to process session data programmatically.

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
