# Opportunity Pipeline Dashboard

> Auto-generated from LoreConvo on 2026-04-01 04:07
> Database: ~/.loreconvo/sessions.db (surface=pipeline)

## Active Pipeline

| ID | Name | Status | Priority | Effort | Scouted | Summary |
|---|---|---|---|---|---|---|
| 92651ff2-4e11-4ce9-b5a8-5b5c92a964e8 | Scout Run: Week of 2026-03-30 - Data Engineering Tool Gap | None | - | - | 2026-03-30T04:19:07.825096 | Weekly Scout run for March 30, 2026. Theme: the data engineering tooling gap in the MCP/Claude ecosy... |
| OPP-001 | Smart SQL Server MCP | on-hold | P1 | 3 | 2026-03-26 | Schema-aware, read-only-by-default Python MCP for SQL Server. Microsoft solution is Azure-only; comm... |
| OPP-002 | AI Cost Attribution MCP | architecture-proposed | P2 | 2 | 2026-03-26 | Per-project Claude API cost tracking. No per-project attribution exists today; enterprise tools are ... |
| OPP-003 | PromptOps Lite / LorePrompts | architecture-proposed | P3 | 3 | 2026-03-26 | Local-first prompt versioning. All enterprise tools are cloud-only and expensive. Would complete a "... |
| OPP-004 | MCP Token Profiler | architecture-proposed | P4 | 1 | 2026-03-26 | Diagnostic CLI for MCP context bloat (documented 72% context waste crisis). Best built free as a lea... |
| OPP-005 | TabularContext Library | on-hold | P5 | 1 | 2026-03-26 | Recommendation: fold into Smart SQL Server MCP as internal module, not standalone product. Fit 4/5, ... |
| OPP-006 | Security: Path traversal guard in _write_architecture_doc | completed | P2 | 1 | 2026-03-29 | pipeline_helpers.py _write_architecture_doc() builds filenames from user-controlled titles. The curr... |
| OPP-007 | Security: Restrict DB auto-discovery in find_db_path | completed | P2 | 1 | 2026-03-29 | pipeline_helpers.py find_db_path() uses broad glob patterns (/sessions/*/mnt/**/sessions.db) and con... |
| OPP-008 | Security: Sanitize log output and add rotation | completed | P2 | 1 | 2026-03-29 | on_session_end_fixed.sh logs raw stdin (including transcript paths and session IDs) to hook-debug.lo... |
| OPP-009 | Security: Enforce MAX_FILE_SIZE in VaultStorage.add_document | completed | P2 | 1 | 2026-03-29 | LoreDocs storage.py defines MAX_FILE_SIZE = 30MB but never checks it. The add_document() method writ... |
| OPP-010 | Security: Sanitize FTS5 MATCH queries | completed | P2 | 1 | 2026-03-29 | pipeline_helpers.py search() and LoreDocs vault_search pass user input directly to FTS5 MATCH. While... |
| OPP-011 | Security: Shell scripts should propagate exit codes | completed | P2 | 1 | 2026-03-29 | on_session_end_fixed.sh and on_session_end.sh unconditionally 'exit 0' even when Python auto_save.py... |
| OPP-012 | SSIS Package Analyzer MCP | on-hold | - | - | 2026-03-30 | An MCP server that parses SQL Server Integration Services (SSIS) .dtsx package files and provides AI... |
| OPP-013 | Data Pipeline Test Harness MCP | scouted | - | - | 2026-03-30 | An MCP server + Claude Code skill that generates and runs data validation tests for ETL pipelines. P... |
| OPP-014 | Schema Diff & Migration MCP | on-hold | - | - | 2026-03-30 | A lightweight MCP server that connects to SQL Server (and optionally PostgreSQL) databases to provid... |
| OPP-015 | Data Catalog Lite MCP | scouted | - | - | 2026-03-30 | A lightweight, local-first data catalog MCP server that crawls database metadata and builds a search... |
| OPP-016 | ETL Pattern Library Skill | on-hold | - | - | 2026-03-30 | A Claude Code skill + optional MCP backend that provides battle-tested ETL design patterns with read... |
| REF-SCOUT-SKILLS-001 | Scout Reference: Debbie's Builder Profile & Opportunity Fit Criteria | None | - | - | 2026-03-27 | SCOUT CONTEXT: Use this to evaluate opportunity fit. Debbie's skills are much broader than SQL Serve... |
