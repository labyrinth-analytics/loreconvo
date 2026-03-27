# SQL Query Optimizer (v0.1.0) - IN PROGRESS

SQL optimization tool with analysis and recommendations.

## Architecture
- Stack: FastMCP, sqlparse, Python
- Two components:
  - `src/` -- MCP server + analyzer (local, free tier)
  - `api/` -- Paid API backend (FastAPI, Docker, Railway deployment target)
- Target platform: ClawHub skill (free) + paid API backend

## Key Files
- `src/server.py` -- MCP server entry point
- `src/analyzer.py` -- SQL analysis engine
- `skill/SKILL.md` -- OpenClaw/ClawHub skill definition
- `api/main.py` -- FastAPI paid backend
- `api/optimizer.py` -- API-level optimization logic
- `api/credits.py` -- credit/billing system
- `api/Dockerfile`, `api/railway.toml` -- deployment config
- `tests/test_analyzer.py` -- 34 tests passing
- `DEPLOY_GUIDE.md`, `QUICKSTART.md` -- documentation

## Design Decisions
- Free skill on ClawHub drives traffic to paid API backend
- Credit-based billing for API usage (MeshCore billing integration)
- Docker + Railway for deployment
- sqlparse for SQL parsing (no database connection needed for analysis)

## Product TODOs
1. [ ] ClawHub skill packaging
2. [ ] Integration tests with real SQL Server queries
3. [ ] Paid API backend (deployment, auth, billing) -- blocked on marketplace/billing decisions
