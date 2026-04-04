---
name: lore-onboard
description: >
  First-time setup wizard for LoreConvo. Verifies the MCP server is connected,
  the database is accessible, hooks are configured, and runs a test save/load
  cycle. Use when the user says "set up loreconvo", "onboard", "/lore-onboard",
  "verify loreconvo", "test loreconvo setup", or after first installing the plugin.
metadata:
  version: "0.3.0"
  author: "Labyrinth Analytics Consulting"
---

# LoreConvo Onboarding

Welcome the user and walk them through first-time LoreConvo setup verification.
Run each step below in order. Report results as you go. If any step fails,
explain what went wrong and how to fix it before continuing.

## Step 1: Verify MCP Server Connection

Call the `get_recent_sessions` MCP tool with `limit=1`.

- **PASS** if the tool returns a response (even an empty list).
- **FAIL** if the tool is not found or returns a connection error.

If FAIL: Tell the user:
> LoreConvo MCP server is not connected. Make sure the plugin is installed
> and the MCP server entry is in your Claude settings. Check that
> `~/.loreconvo/` exists and the server can be reached via stdio transport.

## Step 2: Verify Database

Call `list_projects` MCP tool.

- **PASS** if it returns a response (empty list is fine for new installs).
- **FAIL** if it errors with a database issue.

If FAIL: Tell the user:
> The LoreConvo database could not be accessed. Check that `~/.loreconvo/sessions.db`
> exists and is not locked by another process. You can reset it by deleting the file
> and restarting -- LoreConvo will recreate it automatically.

## Step 3: Test Save/Load Cycle

### 3a: Save a test session

Call `save_session` with:
```
title: "LoreConvo Onboarding Test"
surface: "code"
summary: "Automated onboarding verification. This session confirms that LoreConvo can save and retrieve sessions correctly. Safe to delete."
decisions: ["LoreConvo onboarding test completed successfully"]
tags: ["onboarding", "test"]
```

Capture the returned `session_id`.

- **PASS** if a session_id is returned.
- **FAIL** if save fails.

### 3b: Load the test session back

Call `get_session` with the session_id from step 3a.

- **PASS** if the session is returned with matching title "LoreConvo Onboarding Test".
- **FAIL** if not found or title does not match.

### 3c: Search for the test session

Call `search_sessions` with query `"onboarding test"`.

- **PASS** if at least one result contains the test session.
- **FAIL** if no results found (FTS5 index may not be working).

## Step 4: Verify Hooks Configuration

Check whether the auto-save and auto-load hooks are configured by looking for
the hook files. Use the Bash tool to check:

```bash
ls -la "${CLAUDE_PLUGIN_ROOT:-$HOME/.claude/plugins/loreconvo}/hooks/scripts/"
```

Or check the plugin.json for SessionStart and SessionEnd hooks.

- **PASS** if both `on_session_start.sh` and `on_session_end.sh` exist.
- **FAIL** if either is missing.

If FAIL: Tell the user:
> Hooks are not configured. The auto-save (SessionEnd) and auto-load
> (SessionStart) hooks make LoreConvo work automatically. Reinstall the
> plugin or check that hooks/scripts/ contains on_session_start.sh and
> on_session_end.sh.

## Step 5: CLAUDE.md Integration Check

Check if the user's project CLAUDE.md (in the current working directory) mentions
LoreConvo. Read the CLAUDE.md file if it exists.

- **PASS** if CLAUDE.md mentions "loreconvo" or "LoreConvo" or "save_session".
- **SKIP** if no CLAUDE.md exists (not required but recommended).
- **SUGGEST** if CLAUDE.md exists but does not mention LoreConvo.

If SUGGEST, offer to append this snippet:

```markdown
## LoreConvo Integration

This project uses LoreConvo for persistent session memory.
- At session start: context from recent sessions is auto-loaded via hooks
- At session end: the session is auto-saved via hooks
- Use `save_session` to manually vault important context mid-session
- Use `search_sessions` or `get_context_for` to recall prior work
- Use `vault_suggest` for proactive recommendations on what to revisit
```

Ask the user before modifying their CLAUDE.md.

## Summary

After all steps, present a summary table:

| Step | Check | Result |
|------|-------|--------|
| 1 | MCP Server Connection | PASS/FAIL |
| 2 | Database Access | PASS/FAIL |
| 3a | Save Session | PASS/FAIL |
| 3b | Load Session | PASS/FAIL |
| 3c | Search (FTS5) | PASS/FAIL |
| 4 | Hooks Configured | PASS/FAIL |
| 5 | CLAUDE.md Integration | PASS/SKIP/SUGGEST |

If all critical steps (1-4) pass, congratulate the user:
> LoreConvo is fully operational! Your sessions will be automatically saved
> and loaded. Use `/vault save` or ask me to "vault this session" anytime
> to manually capture important context.

If any critical step fails, summarize what needs fixing and offer to help.

## Cleanup

Do NOT delete the test session -- it serves as the user's first session record
and confirms the installation date. The "onboarding" tag makes it easy to find
later if the user wants to clean it up.
