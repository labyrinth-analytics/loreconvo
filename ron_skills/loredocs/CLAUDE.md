# LoreDocs (v0.1.0) - ALPHA

Knowledge management MCP server for AI projects.
Formerly "ProjectVault" -- renamed 2026-03-25.

## Architecture
- Stack: FastMCP, SQLite+FTS5, filesystem storage
- Transport: stdio (Code + Cowork compatible)
- Data: `~/.loredocs/loredocs.db` + `~/.loredocs/vaults/`
- MCP tools: 34
- Module layout: `loredocs/server.py` (standard `python -m loredocs.server` pattern)
- Test isolation: set `LOREDOCS_ROOT` env var to override default data path

## Key Files
- `loredocs/server.py` -- MCP server entry point (34 `@mcp.tool()` decorators)
- `loredocs/storage.py` -- SQLite+FTS5 storage layer
- `loredocs/tiers.py` -- Free/Pro/Team tier gating (TierEnforcer, vault_tier_status, vault_set_tier)
- `INSTALL.md` -- installation guide
- `docs/marketplace_listing.md` -- marketplace listing (APPROVED)
- `docs/PUBLISHING.md` -- marketplace publishing research
- `docs/ProjectVault_Product_Spec.md` -- product spec (needs rename)
- `test_mcp_tools.py` -- 43 MCP tool-layer tests
- `test_tier_integration.py` -- 29 integration tests for tier enforcement
- `test_phase2.py`, `test_storage.py`, `test_tiers.py` -- unit tests

## Design Decisions
- Local-first: all data on user's machine, no cloud dependency
- SQLite+FTS5 for search (no vector embeddings in v1)
- Plain files on disk for vault content (easy backup, git-friendly)
- Tier gating: TierEnforcer checks limits before vault/doc creation; returns error strings (not exceptions) for MCP compatibility
- Free/Pro/Team tier model: Pro $9/mo, Team $19-20/mo target

## Revenue Target
- $1,635 MRR by month 12

## Known Issues
- MCP SDK v1.26.0 renamed `lifespan_state` to `lifespan_context` (already fixed)
- Old artifact: `projectvault-v0.1.0.tar.gz` and `projectvault.egg-info` still in directory (delete these)
- `docs/ProjectVault_Product_Spec.md` needs rename to `docs/LoreDocs_Product_Spec.md`

## Product TODOs
(none -- all LoreDocs feature work complete. Blocked on marketplace publishing.)
