# LoreConvo Quickstart

Get LoreConvo running in under 5 minutes. By the end, you will have persistent session memory working across your Claude sessions.

---

## Prerequisites

- Python 3.10 or newer
- macOS or Linux
- Claude Code or Cowork installed

Check your Python version:

```
$ python3 --version
Python 3.10.12
```

If you see 3.10 or higher, you are good to go.

---

## Step 1: Get the Source

Clone or download LoreConvo:

```bash
git clone https://github.com/labyrinth-analytics/loreconvo.git
cd loreconvo
```

---

## Step 2: Install

Run the install script:

```bash
bash install.sh
```

This creates a virtual environment, installs all dependencies, and verifies that everything works. You should see output ending with a success message.

If you prefer to install manually:

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
```

---

## Step 3: Connect to Claude

**Claude Code (terminal):**

```bash
claude --plugin-dir /path/to/loreconvo
```

Or load it inside an existing session:

```
/plugin add /path/to/loreconvo
```

**Cowork (desktop app):**

1. Click the **+** button next to the prompt box
2. Select **Plugins**
3. Select **Add plugin**
4. Browse to the `loreconvo` source folder

---

## Step 4: Verify It Works

Ask Claude:

> "Run get_recent_sessions and show me the results."

You should see either a list of sessions (if you have used LoreConvo before) or an empty list. Either result means LoreConvo is connected and working.

For a more thorough check, use the onboarding skill:

> "Run /lore-onboard"

This checks your database, MCP tools, hooks, and plugin structure.

---

## Step 5: Save Your First Session

At the end of your next work session, tell Claude:

> "Save this session to LoreConvo with a summary of what we did."

Claude will call `save_session` and store the session context. The next time you start a session, Claude will automatically recall this context.

---

## Step 6: Build a Memory Digest (Recommended After 10+ Sessions)

Once you have saved 10 or more sessions, LoreConvo can consolidate them into a compact memory digest -- a structured summary of your project's key decisions, open questions, and tech stack facts. Claude injects this digest automatically at each session start from then on.

Ask Claude:

> "Run consolidate_memories for the side_hustle project."

Replace `side_hustle` with your own project name. You will see a brief summary of what was extracted. After that, every new session starts with an up-to-date project brief already loaded.

**Free tier:** up to 3 consolidation runs per day. **Pro:** unlimited.

---

## What Happens Next

- **Claude Code:** The SessionStart and SessionEnd hooks run automatically. Context loads at the start of each session and saves at the end. You do not need to do anything.

- **Cowork:** Hooks do not run automatically yet. Add LoreConvo instructions to your project CLAUDE.md so Claude checks for context at session start. See [COWORK_RESTORE.md](COWORK_RESTORE.md) for the recommended setup.

- **Claude Chat:** Use the `export` command to copy session context to your clipboard, then paste it into Chat. See the [CLI Reference](cli_reference.md) for details.

---

## Troubleshooting

**"No module named 'mcp'" error?**
The virtual environment may not have installed correctly. Re-run `bash install.sh`.

**MCP tools not showing up?**
Make sure you loaded the plugin correctly. In Claude Code, run `/plugin add /path/to/loreconvo` and check for errors.

**Cowork cannot see sessions from Code?**
Ask Claude to "mount my ~/.loreconvo folder" so Cowork can access the shared database.

---

## Next Steps

- Read the [CLI Reference](cli_reference.md) to use LoreConvo from the command line
- Read the [MCP Tool Catalog](mcp_tool_catalog.md) for a full list of what Claude can do with LoreConvo
- Read [COWORK_RESTORE.md](COWORK_RESTORE.md) for Cowork-specific setup

**Optional: Compact summaries via Claude API**

If you want LoreConvo to compress long session summaries before saving them, install the bridge extra and set your API key:

```bash
pip install loreconvo[bridge]
```

Then ask Claude to save with summarization:

> "Save this session to LoreConvo with summarize=true."

This sends the session summary to Claude Haiku for compression. If the API call fails for any reason, LoreConvo saves the original summary instead. See [INSTALL.md](../INSTALL.md) for the full privacy note.
