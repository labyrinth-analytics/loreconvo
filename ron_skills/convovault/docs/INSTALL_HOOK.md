# ConvoVault SessionEnd Hook - Installation

This hook automatically saves every Claude Code session to ConvoVault when the session ends. No manual `/vault save` needed.

## What it does

When a Claude Code session ends (for any reason except "resume"), the hook:

1. Reads the transcript JSONL file
2. Extracts user messages, assistant messages, tools used, and files modified
3. Generates a summary of the session
4. Saves everything to ConvoVault's SQLite database at `~/.convovault/convovault.db`
5. Logs activity to `~/.convovault/hook.log`

The heavy parsing runs in the background so it never slows down session exit.

## Installation

### Step 1: Copy the hook scripts

Copy both files into your ConvoVault installation:

```bash
cp hooks/scripts/session-end-save.sh ~/projects/side_hustle/ron_skills/convovault/hooks/scripts/
cp hooks/scripts/parse_transcript.py ~/projects/side_hustle/ron_skills/convovault/hooks/scripts/
chmod +x ~/projects/side_hustle/ron_skills/convovault/hooks/scripts/session-end-save.sh
```

### Step 2: Register the hook globally

Add the SessionEnd hook to your global Claude Code settings. Edit `~/.claude/settings.json`:

```json
{
  "hooks": {
    "SessionEnd": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "$HOME/projects/side_hustle/ron_skills/convovault/hooks/scripts/session-end-save.sh"
          }
        ]
      }
    ]
  }
}
```

If you already have other hooks in settings.json, just add the SessionEnd entry alongside them.

### Step 3: Verify

Start and end a Claude Code session, then check:

```bash
# Check the hook log
cat ~/.convovault/hook.log

# Query saved sessions
sqlite3 ~/.convovault/convovault.db "SELECT session_id, project, user_message_count, ended_at FROM sessions ORDER BY ended_at DESC LIMIT 5;"
```

## Configuration

**Custom ConvoVault location:** If ConvoVault is not at `~/projects/side_hustle/ron_skills/convovault/`, set the environment variable:

```bash
export CONVOVAULT_DIR="/your/custom/path"
```

**Increase hook timeout:** If you have very large transcripts (1000+ messages), increase the SessionEnd timeout:

```bash
export CLAUDE_CODE_SESSIONEND_HOOKS_TIMEOUT_MS=5000
```

(The default 1.5s timeout only applies to the bash launcher; the Python parser runs in the background regardless.)

## Skip conditions

The hook automatically skips saving when:

- `reason` is `resume` (session is being resumed, not ended)
- Transcript file is missing or empty
- ConvoVault venv is not found
- `session_id` or `transcript_path` is missing from the hook input

## Database schema

The hook writes to the `sessions` table with these fields:

| Field | Type | Description |
|-------|------|-------------|
| session_id | TEXT | Claude Code's session UUID |
| surface | TEXT | Always "code" for this hook |
| project | TEXT | Inferred from cwd directory name |
| cwd | TEXT | Working directory at session end |
| ended_at | TEXT | ISO 8601 timestamp |
| end_reason | TEXT | clear, logout, prompt_input_exit, other |
| summary | TEXT | Auto-generated session summary |
| tools_used | TEXT | JSON array of tool names used |
| files_modified | TEXT | JSON array of file paths touched |
| user_message_count | INT | Number of user messages |
| assistant_message_count | INT | Number of assistant responses |
| transcript_path | TEXT | Original JSONL file location |

If a session_id already exists (resumed session), the record is updated rather than duplicated.
