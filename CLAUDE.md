# LoreConvo (v0.3.0) - PRODUCTION

Cross-surface persistent memory for Claude sessions.
Formerly "ConvoVault" -- renamed 2026-03-25.

## Architecture
- Stack: FastMCP, SQLite+FTS5, Click CLI
- Transport: stdio (Code + Cowork compatible)
- Data: `~/.loreconvo/sessions.db`
- MCP tools: 12 | CLI commands: 6
- Hooks: SessionEnd (auto-save) + SessionStart (auto-load context)
- Module layout: `src/server.py` (relative imports from src/ -- must set PYTHONPATH or use full path)

## Key Files
- `src/server.py` -- MCP server entry point (12 `@mcp.tool()` decorators)
- `src/cli.py` -- Click CLI (6 commands)
- `src/core/` -- storage, search, session logic
- `hooks/scripts/auto_load.py` -- SessionStart hook (scores sessions by signal: open questions +3, decisions +2, artifacts +1, recency +1/+2; caps output at 4000 chars)
- `hooks/scripts/auto_save.py` -- SessionEnd hook
- `hooks/scripts/on_session_start.sh`, `on_session_end.sh` -- shell wrappers
- `skills/SKILL.md` -- OpenClaw skill definition
- `docs/marketplace_listing.md` -- marketplace listing (APPROVED)
- `docs/LoreConvo_Revenue_Projection.xlsx` -- revenue projection (APPROVED, updated 2026-03-27)
- `docs/PUBLISHING.md` -- marketplace publishing research

## Design Decisions
- Local-first: all data on user's machine, no cloud dependency
- SQLite+FTS5 for search (no vector embeddings in v1)
- Session scoring for auto-load: prioritizes sessions with open questions and recent decisions over noise
- Free/Pro tier model: free tier limited sessions, Pro unlocks unlimited via Stripe ($8/mo target)

## Revenue Target
- $3,268 MRR by month 12

## Known Issues
- Uses relative imports from src/ -- must set PYTHONPATH or use full path to server.py
- Real Claude Code transcripts wrap messages: `{"type":"user","message":{"role":"user",...}}`
- Never use `2>/dev/null` in hook scripts -- redirect to a log file instead

## Product TODOs
(none -- all LoreConvo feature work complete. Blocked on marketplace publishing.)
