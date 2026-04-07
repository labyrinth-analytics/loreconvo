# Agent Skill: Git Operations

All agents MUST use safe_git.py for every git operation. Never use raw git commands.

## Commands

```
python scripts/safe_git.py commit -m "message" --agent "{YOUR_AGENT_NAME}" file1 file2
python scripts/safe_git.py push
python scripts/safe_git.py status
```

Replace `{YOUR_AGENT_NAME}` with your agent name (ron, meg, brock, gina, scout, competitive-intel,
madison, john, jacqueline).

## Rules

- 1 tool call for commit, 1 tool call for push -- MAX. Never retry.
- Cowork VM git lock files are immutable. safe_git.py handles them automatically via pending_commits.json.
- NEVER manually manipulate .git/index, rename lock files, or use GIT_INDEX_FILE.
- If safe_git.py falls through to pending_commits.json, that counts as done. Move on.
- push will fail from Cowork VM (no GitHub credentials) -- this is EXPECTED. Debbie pushes from her Mac.
- Do NOT spend more than 2 tool calls total on git in any session.
