# Agent Migration: Cowork -> Claude Code Local Scheduler

**Date:** 2026-04-08
**Author:** Ron (via Debbie request)

---

## What Was Moved and Why

Six scheduled agents were migrated from the Cowork plugin system to local macOS cron
jobs running via Claude Code CLI (`claude -p`). The Cowork versions are disabled but
their SKILL.md files remain intact for rollback.

**Why not Claude Code's cloud CCR scheduler?**
CCR (Claude Code Remote) runs in Anthropic's cloud -- it cannot access the local
SQLite databases that power LoreConvo (`~/.loreconvo/sessions.db`), LoreDocs
(`~/.loredocs/loredocs.db`), the pipeline DB, or local Ollama. The entire agent
communication backbone would break.

**Why local cron + `claude -p`?**
- Full access to LoreConvo and LoreDocs MCP tools (configured in settings.json)
- Full access to the local filesystem and git credentials
- Ollama preprocessing steps (Meg, Brock) actually work now (would fail in CCR)
- Real git push credentials -- no VM lock file workarounds needed
- Same Claude model and knowledge base as interactive sessions

---

## Agents Migrated

| Agent | Task ID | Cron (Pacific) | First next run |
|-------|---------|----------------|----------------|
| Ron | ron-daily | `5 17 * * *` | Today 5:05 PM |
| Meg | meg-qa-daily | `33 18 * * *` | Today 6:33 PM |
| Brock | brock-security-daily | `38 23 * * *` | Tonight 11:38 PM |
| Gina (architect) | enterprise-architect-gina | `0 4 * * 3,6` | Next Wed or Sat 4:00 AM |
| Gina (product review) | gina-product-review | `0 4 * * 1,3,5` | Next Mon/Wed/Fri 4:00 AM |
| John | john-tech-docs | `38 3 * * 2,6` | Next Tue or Sat 3:38 AM |

Note: Gina runs two tasks simultaneously on Wednesdays (architect + product review
both fire at 4:00 AM Wed). This matches the prior Cowork behavior -- intentional.

---

## Where Things Live

### Wrapper script
```
/Users/debbieshapiro/projects/side_hustle/scripts/run_agent_code.sh
```
Single script handles all six agents. Pass the agent name as argument:
```
./scripts/run_agent_code.sh ron-daily
```

### SKILL.md source files (Cowork versions -- read-only, do not modify)
```
/Users/debbieshapiro/Documents/Claude/Scheduled/<agent-name>/SKILL.md
```
The wrapper reads these verbatim at runtime. If a SKILL.md is updated, the next
scheduled run picks it up automatically -- no crontab changes needed.

### Logs
```
/Users/debbieshapiro/projects/side_hustle/logs/<agent>_YYYYMMDD_HHMMSS.log
```
Log files are gitignored (*.log in .gitignore). Logs older than 14 days are
auto-purged by the wrapper script at each run.

### Crontab
View with: `crontab -l`
Edit with: `crontab -e`

---

## Crontab Entries Installed

```cron
SHELL=/bin/bash
MAILTO=""

# Labyrinth Analytics scheduled agents -- all times America/Los_Angeles
# Wrapper: /Users/debbieshapiro/projects/side_hustle/scripts/run_agent_code.sh
# Logs:    /Users/debbieshapiro/projects/side_hustle/logs/

# Ron -- daily builder (5:05 PM)
5 17 * * * /Users/debbieshapiro/projects/side_hustle/scripts/run_agent_code.sh ron-daily

# Meg -- daily QA (6:33 PM, after Ron)
33 18 * * * /Users/debbieshapiro/projects/side_hustle/scripts/run_agent_code.sh meg-qa-daily

# Brock -- daily security (11:38 PM, after Meg)
38 23 * * * /Users/debbieshapiro/projects/side_hustle/scripts/run_agent_code.sh brock-security-daily

# Gina -- enterprise architect (Wed/Sat 4:00 AM)
0 4 * * 3,6 /Users/debbieshapiro/projects/side_hustle/scripts/run_agent_code.sh enterprise-architect-gina

# Gina -- product review (Mon/Wed/Fri 4:00 AM)
0 4 * * 1,3,5 /Users/debbieshapiro/projects/side_hustle/scripts/run_agent_code.sh gina-product-review

# John -- tech docs (Tue/Sat 3:38 AM)
38 3 * * 2,6 /Users/debbieshapiro/projects/side_hustle/scripts/run_agent_code.sh john-tech-docs
```

---

## How to Re-Enable Cowork Versions

The Cowork SKILL.md files are untouched in:
```
/Users/debbieshapiro/Documents/Claude/Scheduled/<agent-name>/SKILL.md
```
To re-activate in Cowork: re-enable the scheduled task in the Cowork plugin UI.
The SKILL.md content is unchanged and will work as-is.

To run BOTH (Cowork + local cron) simultaneously: not recommended -- they'd both
write to LoreConvo and the same git branch, causing conflicts.

---

## Rollback Steps

1. Disable local cron entries:
   ```
   crontab -e
   # Comment out or delete the 6 agent lines
   ```
2. Re-enable the Cowork scheduled tasks in the Cowork plugin UI.
3. No file changes needed -- the wrapper script and logs/ dir can stay.

---

## Monitoring

Check agent logs:
```bash
# Most recent ron-daily log
ls -t /Users/debbieshapiro/projects/side_hustle/logs/ron-daily_*.log | head -1 | xargs tail -50

# All logs from today
ls /Users/debbieshapiro/projects/side_hustle/logs/*_$(date +%Y%m%d)_*.log

# Watch a running session live
tail -f /Users/debbieshapiro/projects/side_hustle/logs/ron-daily_*.log
```

---

## Notes on Local LLM (Ollama) Integration

Meg and Brock's SKILL.md already include an optional preprocessing step using Ollama
(`qwen3.5:9b`). In CCR this would always fail (no local Ollama). Running locally,
this step will work whenever Ollama is running on your machine.

The main agent sessions still use Claude (claude-sonnet-4-6) because MCP tool use
(LoreConvo, LoreDocs, filesystem, Bash) requires Claude's tool-calling capabilities.
Local LLMs do not support MCP tool calls in this setup.
