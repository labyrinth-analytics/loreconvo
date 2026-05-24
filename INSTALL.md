# LoreConvo Installation Guide

**LoreConvo** gives Claude persistent memory across sessions. When you finish a session,
LoreConvo saves a summary. When you start a new session, it loads the most relevant
context automatically. Works with Claude Code and Cowork.

---

## Prerequisites

- **Python 3.10 or newer** (macOS/Linux)
- Claude Code or Cowork installed

Check your Python version:

```bash
python3 --version
```

If you see 3.10 or higher, you are good to go.

---

## Option A: Install as a Cowork Plugin (Recommended)

The LoreConvo plugin is ready to install locally. First register the local marketplace,
then install from it -- this is the same flow as the eventual public marketplace install:

```
/plugin marketplace add ~/projects/side_hustle/marketplace/claude-plugins
/plugin install loreconvo@labyrinth-analytics-claude-plugins
```

Then restart Cowork. LoreConvo MCP tools will be available in your next session.

> **Anthropic marketplace:** Once the plugin is listed on the Anthropic marketplace,
> the `/plugin marketplace add` step will not be needed -- install directly with the
> second command.

---

## Option B: Developer Install

Clone the repo and run the one-command installer:

```bash
git clone https://github.com/labyrinth-analytics/loreconvo.git
cd loreconvo
bash install.sh
```

The installer will:
1. Create a Python virtual environment at `.venv/`
2. Install the LoreConvo package and all dependencies
3. Set the correct execute permissions on the hook scripts
4. Verify the entry point binary was created
5. Create the database directory at `~/.loreconvo/`

You should see output ending with `Installation complete!`.

### Manual install (if you prefer):

```bash
python3 -m venv .venv
.venv/bin/pip install .
```

---

## Connecting to Claude Code

After installation, register LoreConvo with Claude Code using the `claude mcp add` command:

```bash
claude mcp add --scope user \
  "--env=LORECONVO_PRO=<your-license-key>" \
  loreconvo -- \
  /path/to/loreconvo/.venv/bin/python \
  /path/to/loreconvo/src/server.py
```

Replace `/path/to/loreconvo` with the actual path to your LoreConvo installation. To find it, run `pwd` from inside the loreconvo directory.

The `--env=LORECONVO_PRO=<your-license-key>` flag is optional -- omit it if you are using the free tier. The `--scope user` flag registers LoreConvo for all Claude Code sessions (not just the current project).

> **Why `claude mcp add` instead of editing settings.json?** Claude Code reads
> user-level MCP servers from `~/.claude.json`, managed by `claude mcp add --scope user`.
> Adding `mcpServers` entries to `~/.claude/settings.json` is silently ignored --
> the server will not load. (GitHub issue #4976.)

### Environment variables

| Variable | What it is for | How to set it |
|----------|---------------|--------------|
| `LORECONVO_PRO` | Your Pro license key (optional) | `--env=LORECONVO_PRO=<key>` in the `claude mcp add` command |
| `LORECONVO_DB_PATH` | Path to your session memory database (optional) | `--env=LORECONVO_DB_PATH=/path/to/sessions.db` in the command |
| `LORECONVO_PROJECT_PATH` | Directory to scan for MEMORY.md at session start (optional) | `--env=LORECONVO_PROJECT_PATH=/path/to/project` in the command |
| `LORECONVO_DREAM_INJECT` | Controls whether the memory digest is injected at session start (optional) | Set to `false` to disable digest injection globally: `--env=LORECONVO_DREAM_INJECT=false` |
| `HF_HUB_OFFLINE` | Blocks HuggingFace Hub network calls after the initial model download (Pro tier only, optional) | Set to `1` to prevent all post-download hub requests: `--env=HF_HUB_OFFLINE=1` |

If `LORECONVO_DB_PATH` is not set, LoreConvo defaults to `~/.loreconvo/sessions.db`.
If `LORECONVO_PRO` is not set, LoreConvo runs on the free tier (up to 50 sessions).
If `LORECONVO_PROJECT_PATH` is not set, LoreConvo scans the current working directory for a MEMORY.md file.

### Verify the connection

After running `claude mcp add`, restart Claude Code. Run the `/mcp` command in Claude
to verify LoreConvo is connected. You should see `loreconvo` listed with a green status.

---

## Connecting to Cowork

Install via the `.plugin` file in the cloned directory:

1. Open Cowork settings
2. Click "Add plugin from file"
3. Select `loreconvo-dev.plugin` from the cloned repo
4. Restart Cowork

---

## Connecting to Cursor IDE

Cursor uses the same MCP protocol as Claude Code. Configure it by creating a `.cursor/mcp.json` file in your project root:

```json
{
  "mcpServers": {
    "loreconvo": {
      "command": "/path/to/loreconvo/.venv/bin/python",
      "args": ["/path/to/loreconvo/src/server.py"],
      "env": {
        "LORECONVO_PRO": "your-license-key"
      }
    }
  }
}
```

Or copy `.mcp.json` as `.cursor/mcp.json` if you already have a working Claude Code setup.

Restart Cursor after adding the configuration. LoreConvo MCP tools will be available in the next Cursor session.

---

## Setting Up Auto-Save and Auto-Load

Install these hooks once and every session is captured automatically -- no `save_session`
call needed. When you finish a session, the SessionEnd hook saves a structured summary
(decisions, artifacts, open questions) to your local database. When you start a new
session, the SessionStart hook loads the most relevant recent context back in.

This uses Claude Code hooks.

After running `install.sh`, add the hooks to `~/.claude/settings.json`:

```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "/Users/YOUR_USERNAME/projects/loreconvo/hooks/on_session_start.sh"
          }
        ]
      }
    ],
    "SessionEnd": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "/Users/YOUR_USERNAME/projects/loreconvo/hooks/on_session_end.sh"
          }
        ]
      }
    ]
  }
}
```

Replace `YOUR_USERNAME` with your actual Mac username.

> **If hooks were silently not running:** This was a known issue fixed in the 2026-04-06
> release. The install script now sets the correct execute permissions. If you installed
> before that fix, run `bash install.sh` again from your loreconvo directory to fix it.

### MEMORY.md Auto-Indexing

If your project has a `MEMORY.md` file, the SessionStart hook automatically indexes it into LoreConvo at the start of each session. No extra setup is required -- it happens as part of the hook you already configured above.

The MEMORY.md content is stored as a searchable entry tagged `memory_md`. Claude can find it alongside regular session history when you ask it to recall project conventions or decisions.

**To point LoreConvo at a specific project directory** (instead of the current working directory), add `LORECONVO_PROJECT_PATH` as an env flag in your `claude mcp add` command:

```bash
claude mcp add --scope user \
  "--env=LORECONVO_PRO=<your-license-key>" \
  "--env=LORECONVO_PROJECT_PATH=/Users/YOUR_USERNAME/projects/my_project" \
  loreconvo -- \
  /path/to/loreconvo/.venv/bin/python \
  /path/to/loreconvo/src/server.py
```

Replace `YOUR_USERNAME` and `my_project` with your actual values. Use the full absolute path -- do not use `~` or `$HOME`.

If you have multiple projects, leave `LORECONVO_PROJECT_PATH` unset. The hook will use wherever Claude Code is opened as the project directory, which is correct for most setups.

---

### PreCompact Hook (Recommended)

LoreConvo can also save your session before Claude Code compresses the context window.
This fires both when you manually run `/compact` and when Claude Code automatically
compresses because the context limit was reached. No session context is lost.

Add the PreCompact hook to your `~/.claude/settings.json` alongside the SessionStart
and SessionEnd hooks above:

```json
{
  "hooks": {
    "PreCompact": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "/Users/YOUR_USERNAME/projects/loreconvo/hooks/scripts/on_pre_compact.sh",
            "timeout": 30
          }
        ]
      }
    ]
  }
}
```

Replace `YOUR_USERNAME` with your actual Mac username.

After adding this hook, restart Claude Code. You can verify it is working by running
`/compact` and then checking `~/.loreconvo/hook.log` for a line like:

```
[Mon Apr 21 10:00:00 PDT 2026] pre-compact (manual): <session-id>
```

If you see that line, the hook is saving your session before compaction.

---

## Memory Recall (Dreaming)

Starting with v0.6.0, LoreConvo can consolidate your session history into a persistent memory digest. After you have saved 10 or more sessions, run the consolidation tool once to give Claude a compact summary of your project's standing decisions, open questions, and tech stack facts. The digest is automatically injected at session start from then on.

### How to run consolidation

Ask Claude:

> "Run consolidate_memories for the side_hustle project."

Claude calls `consolidate_memories` with your project name. The tool analyzes your recent sessions and writes a digest. You will see a summary of decisions extracted, open questions found, and a formatted markdown brief.

**Free tier:** up to 3 on-demand consolidations per day. Pro users have unlimited runs.

### After a consolidation run

The digest is injected into every future session start automatically. If you want to read it without running a new consolidation, ask:

> "Show me the current memory digest for side_hustle."

Claude calls `get_memory_digest` and returns the stored digest.

To see a log of all consolidation runs, ask:

> "Show me the consolidation log for side_hustle."

Claude calls `get_dream_log` and returns timestamps, session counts, and trigger information for recent runs.

### Disabling digest injection

If you want to suppress digest injection for a project without deleting the digest, set the environment variable:

```
LORECONVO_DREAM_INJECT=false
```

Add it via `--env=LORECONVO_DREAM_INJECT=false` in your `claude mcp add` command. This disables injection globally across all projects. To disable injection for one project only, ask Claude to call `get_memory_digest` with `disable=true`.

### Known limitations (v0.6.0)

- **no-llm tag:** If you tag a session with `no-llm`, it is excluded from future LLM-mode consolidation (v0.6.1). In v0.6.0 heuristic mode, all sessions are processed regardless of this tag.
- **Bulk imports leave the digest stale.** If you import a batch of sessions, the digest is not updated until you run `consolidate_memories` again. LoreConvo uses the `updated_at` timestamp on the digest to determine freshness -- importing sessions does not update that timestamp.
- **Project or surface renames strand the digest.** Digests are keyed by project name and surface. If you rename a project in `--project` tags, the old digest is no longer linked. Run `consolidate_memories` again after renaming.
- **Free-tier rate limit is enforced in the MCP layer.** The 3/day limit applies to calls through the MCP tool. The Python consolidation library does not enforce this limit if called directly.

### Setting session expiry (TTL)

You can mark any session to expire on a specific date. After the date passes, the session is hidden from search results and the auto-load hook -- but it is not deleted and can be recovered manually.

Ask Claude:

> "Set the debugging notes session to expire on June 1st, 2027."

Claude calls `set_session_expiry` with the session UUID and the ISO 8601 expiry date. To clear an expiry you previously set, ask Claude to call `set_session_expiry` with `expires_at=null`.

---

## Verifying the Installation

After connecting LoreConvo to Claude Code or Cowork, verify it is working:

**In Claude Code**, run:

```
/mcp
```

You should see `loreconvo` listed. Then ask Claude:

```
Call the get_recent_sessions tool with limit 5
```

If LoreConvo is working, Claude will respond with a list of your recent sessions
(or an empty list if this is your first time). If you see an error, check the
Troubleshooting section below.

---

## Troubleshooting

**"Module not found" or "command not found" error**

This means the install did not complete correctly. Delete the `.venv/` folder and
reinstall:

```bash
cd /path/to/loreconvo
rm -rf .venv
bash install.sh
```

**Hooks are not running (no auto-save/load)**

Check that the hook scripts have execute permission:

```bash
ls -la /path/to/loreconvo/hooks/
```

You should see `-rwxr-xr-x` for the `.sh` files. If you see `-rw-r--r--` (no `x`), run:

```bash
chmod +x /path/to/loreconvo/hooks/on_session_start.sh
chmod +x /path/to/loreconvo/hooks/on_session_end.sh
chmod +x /path/to/loreconvo/hooks/scripts/on_pre_compact.sh
```

Or simply re-run `bash install.sh` -- it sets the permissions automatically.

**`$HOME` or `~` not expanding in settings.json**

Claude Code does not expand shell variables in `settings.json`. Replace any `~` or
`$HOME` with the full absolute path to your home directory
(e.g., `/Users/debbie` instead of `~`).

**Free tier limit reached**

The free tier supports up to 50 sessions. When you reach the limit, `save_session`
returns a message explaining how to upgrade. Contact Labyrinth Analytics for a Pro
license key, then re-run `claude mcp add --scope user` with `--env=LORECONVO_PRO=<your-key>` included.

---

## Upgrading

To upgrade LoreConvo to the latest version:

```bash
cd /path/to/loreconvo
git pull
bash install.sh
```

The installer detects the existing venv and updates it in place. Your session data
at `~/.loreconvo/sessions.db` is preserved.

---

## Data Storage

All session memory is stored locally at `~/.loreconvo/sessions.db`. Nothing is sent
to any cloud service. You own your data.

---

## Privacy Note: summarize=True

By default, LoreConvo stores session data locally with no external network calls.
If you pass `summarize=True` to `save_session`, LoreConvo sends the session summary
to the Anthropic API (using your `ANTHROPIC_API_KEY`) to produce a compressed version
before saving locally. This is opt-in and disabled by default.

When `summarize=True`:
- Your session summary is transmitted to Anthropic and is subject to Anthropic's
  [Privacy Policy](https://www.anthropic.com/legal/privacy).
- If `ANTHROPIC_API_KEY` is not set, or the API call fails for any reason, LoreConvo
  falls back to saving the raw summary. Session saves never fail due to this feature.
- The `anthropic` package must be installed: `pip install loreconvo[bridge]`

---

## Security note for Pro users

When you enable the Pro tier and build the semantic index, LoreConvo creates a
`sessions.lance/` directory under your data root (default: `~/.loreconvo/`). This
directory stores vector representations (embeddings) of your session titles and
summaries. The directory is protected with mode 700 (owner-only access on POSIX
systems).

If you back up your data root, include this directory in your backup -- and treat
the backup with the same sensitivity as the source data, since the vectors encode
the semantic content of your session history.

### HuggingFace Hub network calls (Pro tier)

The Pro tier loads the BGE-small-en-v1.5 embedding model (~130 MB) from HuggingFace
on first use. This is a one-time download. After the download, inference runs entirely
locally -- no session data is transmitted to HuggingFace.

However, the `huggingface-hub` library (a dependency of `sentence-transformers`) may
make occasional metadata checks to the HuggingFace API after the initial download --
for example, to verify model card updates. No session content is included in these
requests, but they are outbound network calls.

If you want to ensure LoreConvo makes no network calls after the initial model
download, set this environment variable:

```
HF_HUB_OFFLINE=1
```

Add it to your `claude mcp add` command:

```bash
claude mcp add --scope user \
  "--env=LORECONVO_PRO=<your-license-key>" \
  "--env=HF_HUB_OFFLINE=1" \
  loreconvo -- \
  /path/to/loreconvo/.venv/bin/python \
  /path/to/loreconvo/src/server.py
```

With `HF_HUB_OFFLINE=1`, the model loads from the local cache and all HuggingFace
API requests are blocked. Make sure the model has been downloaded at least once before
setting this flag, or semantic search initialization will fail.

---

## How LoreConvo Accesses Your Data

LoreConvo provides three ways to read and write your session memory:

**MCP tools** are the primary method. Claude uses these automatically during sessions -- tools
like `save_session`, `get_recent_sessions`, and `search_sessions` connect through the MCP server.

**CLI commands** let you manage sessions from your terminal independent of any Claude session.
After installation, run `loreconvo-cli --help` to see available commands.

**Bundled scripts** are the automatic fallback. If the MCP server is unavailable (for example,
after a startup timeout or a rejected tool call), LoreConvo switches to these scripts silently.
The plugin skill handles this; no action is needed on your part.

All three methods read and write the same database at `~/.loreconvo/sessions.db`. Switching
between them never causes data loss.

---

## More Documentation

- [Quickstart Guide](docs/quickstart.md) -- get up and running in 5 minutes
- [CLI Reference](docs/cli_reference.md) -- manage sessions from the terminal
- [MCP Tool Catalog](docs/mcp_tool_catalog.md) -- all 26 tools explained in plain English
- [Changelog](docs/CHANGELOG.md) -- what changed in each release
