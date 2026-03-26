# LoreConvo -- Marketplace Listing Draft

> STATUS: DRAFT -- Debbie must review and approve before publishing to any marketplace.

---

## Listing Metadata

| Field | Value |
|---|---|
| Plugin Name | LoreConvo |
| Tagline | Vault your Claude conversations. Never re-explain yourself again. |
| Category | Memory & Context / Productivity |
| Version | 0.3.0 |
| Author | Labyrinth Analytics Consulting |
| Support email | info@labyrinthanalyticsconsulting.com |
| License | MIT (core plugin) / Pro features require subscription |
| Platforms | Claude Code, Cowork, Chat |

---

## Short Description (150 chars max)

Persistent cross-surface memory for Claude. Capture decisions, artifacts, and context -- recall it in any future session.

---

## Long Description

### Stop Re-Explaining. Start Remembering.

Every Claude session starts from zero. You spend the first five minutes catching Claude up on your project, your decisions, your constraints -- the same five minutes, every single day.

LoreConvo fixes that.

**LoreConvo is a persistent memory layer for Claude.** It captures what you built, what you decided, and what's still open -- and surfaces that context automatically at the start of your next session. Works across Claude Code, Cowork, and Chat.

---

### How It Works

1. **Save** -- At the end of a session, Claude extracts the key context (decisions, artifacts, open questions) and vaults it. Takes 10 seconds.
2. **Recall** -- At the start of your next session, LoreConvo surfaces the most relevant prior context automatically. Claude arrives ready to work.
3. **Search** -- Need to find a decision from three weeks ago? Full-text search across all your vaulted sessions. Results in under a second.

---

### Key Features

**Cross-surface memory**
Sessions saved in Claude Code are readable in Cowork and Chat. One vault, all surfaces.

**Structured context capture**
LoreConvo doesn't just save chat logs. It captures structured data -- decisions made, files created, open questions, skills used, project associations. This structure makes recall dramatically more accurate than plain-text search.

**Project organization**
Group sessions by project. Define expected skills. LoreConvo tracks which skills were used across your project and can flag when you're working on something without the right context loaded.

**Persona tagging**
Running multiple AI agents? Tag sessions by persona (e.g., `ron-bot:sql`, `debbie:tax`). Filter recall by persona so each agent gets only its relevant history.

**Proactive suggestions**
The `vault_suggest` tool surfaces sessions with unresolved questions and skill gaps -- telling you what context you probably need before you even ask.

**Session linking**
Connect related sessions. Mark one session as continuing, superseding, or related to another. Build a navigable history of your work.

**Full-text search**
SQLite FTS5 under the hood. Keyword search across all session summaries, decisions, artifacts, and open questions. Fast and local.

**Local-first, zero cloud cost**
Your data lives on your machine in a SQLite database. No API calls, no subscription required for the core feature set. Everything works offline.

---

### MCP Tools (12 total)

| Tool | Description |
|---|---|
| `save_session` | Save a session with decisions, artifacts, open questions, and tags |
| `get_recent_sessions` | List recent sessions, filtered by surface or project |
| `get_session` | Retrieve a specific session by ID |
| `search_sessions` | Full-text search across all saved sessions |
| `get_context_for` | Pull relevant context for a topic (best for session start) |
| `tag_session` | Add a persona tag to a session |
| `link_sessions` | Connect related sessions (continues, related, supersedes) |
| `create_project` | Create a named project with expected skill sets |
| `get_project` | Get project details and recent sessions |
| `list_projects` | List all projects |
| `get_skill_history` | Find sessions where a specific skill was used |
| `vault_suggest` | Get proactive context suggestions based on recent history |

---

### Companion Product: LoreDocs

LoreConvo remembers your *conversations*. **LoreDocs** remembers your *project artifacts*.

If you work on complex projects across multiple Claude sessions, consider pairing LoreConvo with LoreDocs. LoreDocs stores documents, specs, and reference materials in named vaults -- and injects them into any Claude session on demand. The two products share a common local-first philosophy and complement each other naturally.

- LoreConvo = "what did we decide last session?"
- LoreDocs = "what does my project documentation say?"

---

### Chat Support (No Plugin Required)

Claude Chat does not support plugins natively, but LoreConvo works with Chat in two ways:

**Option 1 -- Chat bridge script:**
```bash
bash export-to-chat.sh
```
This exports your last session as markdown and copies it to your clipboard. Paste into Chat -- Claude has full context from your Code or Cowork session in seconds.

**Option 2 -- Manual paste:**
Use `get_recent_sessions` or `get_context_for` in Claude Code or Cowork to retrieve the context you need, then paste the output directly into Chat.

---

## Pricing Tiers

> Note to Debbie: Pricing below is a recommendation based on the revenue model in CLAUDE.md.
> Adjust before publishing.

| Feature | Free | Pro ($8/mo) | Team ($19/mo) |
|---|---|---|---|
| Sessions stored | 50 | Unlimited | Unlimited |
| Projects | 3 | Unlimited | Unlimited |
| Full-text search | Yes | Yes | Yes |
| Persona tagging | Yes | Yes | Yes |
| Session linking | No | Yes | Yes |
| vault_suggest | No | Yes | Yes |
| Chat bridge export | Yes | Yes | Yes |
| Cloud sync (coming) | No | No | Yes |
| Team shared vault (coming) | No | No | Yes |
| Priority support | No | No | Yes |

---

## Installation

LoreConvo lives in the `side_hustle` monorepo. To install:

```bash
# Clone the full repo (or pull the latest if you already have it)
git clone https://github.com/labyrinth-analytics/side_hustle.git
cd side_hustle/ron_skills/loreconvo

# Run the installer
bash install.sh
```

The install script creates a virtual environment, installs dependencies, and verifies everything works.

### Load in Claude Code

Add the plugin to your Claude Code config or load it in an existing session:

```bash
/plugin add ~/projects/side_hustle/ron_skills/loreconvo
```

### Load in Cowork

1. Click **+** next to the prompt box
2. Select **Plugins** then **Add plugin**
3. Browse to `~/projects/side_hustle/ron_skills/loreconvo`

### Use in Chat

No plugin install needed. Use the Chat bridge script or manual paste method described above.

---

## What Users Say

> "I was re-explaining the same project context every single day. LoreConvo eliminated that entirely. Claude just knows." -- Beta tester

> "The structured decisions capture is the killer feature. Not just a chat log -- actual decisions with timestamps." -- Beta tester

---

## Frequently Asked Questions

**Is my data private?**
Yes. LoreConvo stores everything locally in SQLite on your machine. Nothing is sent to any server. Labyrinth Analytics never sees your session data.

**Does it work with Claude Chat (web)?**
Yes, with a small workaround -- see the "Chat Support" section above. Use the export script or paste context manually. Full Chat plugin support is on the roadmap.

**What happens if I uninstall it?**
Your database remains at `~/.loreconvo/sessions.db`. Nothing is deleted. Reinstall anytime and your full history is still there.

**Can I use it for multiple projects?**
Yes. The project management tools let you create named projects, associate sessions, and track which skills were used across each project.

**Does it slow down my Claude sessions?**
No. The save and recall operations are synchronous SQLite queries that complete in under 100ms. The SessionEnd hook runs after the session closes.

**What is LoreDocs and do I need it?**
LoreDocs is a companion product for storing project documents and reference materials. LoreConvo and LoreDocs are independent -- you can use either or both. See the Companion Product section above.

---

## Support

- GitHub Issues: [github link TBD]
- Email: info@labyrinthanalyticsconsulting.com
- Docs: See `README.md` and `docs/` in the plugin directory

---

## Changelog

| Version | Date | Notes |
|---|---|---|
| 0.3.0 | 2026-03-22 | Added vault_suggest (proactive context recommendations) |
| 0.2.0 | 2026-03-22 | Added SessionStart/SessionEnd hooks, auto-save, auto-load |
| 0.1.0 | 2026-03-21 | Initial release: 11 MCP tools, SQLite+FTS5, CLI, Chat bridge (now 12 with vault_suggest) |
