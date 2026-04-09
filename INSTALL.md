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

## Option A: Install as a Cowork Plugin (Coming Soon)

> **Note:** The Cowork plugin marketplace is not yet live. This option will be
> available when the marketplace launches. Use Option B (developer install) in the meantime.

Once the marketplace is live, install with:

```
/plugin install loreconvo@labyrinth-analytics-claude-plugins
```

---

## Option B: Developer Install (Recommended for Now)

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

After installation, add LoreConvo to your `~/.claude/settings.json`:

```json
{
  "mcpServers": {
    "loreconvo": {
      "command": "/Users/YOUR_USERNAME/projects/loreconvo/.venv/bin/loreconvo",
      "env": {
        "LORECONVO_DB_PATH": "/Users/YOUR_USERNAME/.loreconvo/sessions.db"
      }
    }
  }
}
```

Replace `YOUR_USERNAME` with your Mac username. To find it, open a terminal and run:

```bash
whoami
```

> **Important:** Do not use `$HOME` or `~` in `settings.json`. Claude Code does not
> expand shell variables in this file. Use the full absolute path with your actual
> username instead.

### Environment variables

| Variable | What it is for | Where to find the value |
|----------|---------------|------------------------|
| `LORECONVO_DB_PATH` | Path to your session memory database | Always `~/.loreconvo/sessions.db` -- substitute your actual home path |
| `LORECONVO_PRO` | Your Pro license key (optional) | Provided when you purchase a license |

If `LORECONVO_DB_PATH` is not set, LoreConvo defaults to `~/.loreconvo/sessions.db`.
If `LORECONVO_PRO` is not set, LoreConvo runs on the free tier (up to 50 sessions).

### Restart Claude Code

After editing `settings.json`, restart Claude Code. Run the `/mcp` command in Claude
to verify LoreConvo is connected. You should see `loreconvo` listed with a green status.

---

## Connecting to Cowork

Install via the `.plugin` file in the cloned directory:

1. Open Cowork settings
2. Click "Add plugin from file"
3. Select `loreconvo-dev.plugin` from the cloned repo
4. Restart Cowork

---

## Setting Up Auto-Save and Auto-Load

LoreConvo can automatically save sessions when you close Claude Code and load relevant
context when you start a new session. This uses Claude Code hooks.

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

You should see `-rwxr-xr-x` for `on_session_start.sh` and `on_session_end.sh`. If you see
`-rw-r--r--` (no `x`), run:

```bash
chmod +x /path/to/loreconvo/hooks/on_session_start.sh
chmod +x /path/to/loreconvo/hooks/on_session_end.sh
```

Or simply re-run `bash install.sh` -- it sets the permissions automatically.

**`$HOME` or `~` not expanding in settings.json**

Claude Code does not expand shell variables in `settings.json`. Replace any `~` or
`$HOME` with the full absolute path to your home directory
(e.g., `/Users/debbie` instead of `~`).

**Free tier limit reached**

The free tier supports up to 50 sessions. When you reach the limit, `save_session`
returns a message explaining how to upgrade. Contact Labyrinth Analytics for a Pro
license key, then set it as `LORECONVO_PRO` in your `settings.json` env block.

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

## More Documentation

- [Quickstart Guide](docs/quickstart.md) -- get up and running in 5 minutes
- [CLI Reference](docs/cli_reference.md) -- manage sessions from the terminal
- [MCP Tool Catalog](docs/mcp_tool_catalog.md) -- all 13 tools explained in plain English
- [Changelog](docs/CHANGELOG.md) -- what changed in each release
