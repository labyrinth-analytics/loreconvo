# Agent Skill: Error Logging

When to log: tool failure, package/import error, crash, or blocked on a critical issue mid-session.
Log IMMEDIATELY -- do NOT wait until session end.
Do NOT log non-critical issues (minor warnings, skipped optional steps).

## Command

```
python ron_skills/loreconvo/scripts/save_to_loreconvo.py \
    --title "agent:{NAME} error YYYY-MM-DD" \
    --surface "error" \
    --summary "ERROR: <what failed> | IMPACT: <what could not be completed> | CONTEXT: <relevant state>" \
    --tags '["agent:{NAME}", "error"]' \
    --project "side_hustle"
```

Replace `{NAME}` with your agent tag from the table below.

## Agent Name Reference

| Agent              | {NAME} value       |
|--------------------|--------------------|
| Ron                | ron                |
| Meg                | meg                |
| Brock              | brock              |
| Gina               | gina               |
| Scout              | scout              |
| Competitive Intel  | competitive-intel  |
| Madison            | madison            |
| John               | john               |
| Jacqueline         | jacqueline         |

## Why This Matters

Jacqueline reads surface:error sessions to build the Agent Health section of the daily executive dashboard.
If your session crashes before the normal end-of-session save, this mid-session error log is your only record.
If you skip this, Jacqueline flags you as SILENT (no session found) instead of YELLOW (errored but ran).
