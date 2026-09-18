# LoreConvo Fallback Contract

`scripts/save_to_loreconvo.py` is a direct-SQLite fallback for when the
LoreConvo MCP server is unreachable (e.g. scheduled tasks, batch scripts, an
MCP client outage). This document is the canonical, per-product statement of
what the fallback guarantees relative to the MCP server -- read it before
relying on the fallback in place of the MCP tools.

## Tier-(a) operations (the "emergency read path")

These fallback flags cover the read path an agent needs to keep working
while the MCP server is down:

| MCP tool | Fallback | Notes |
|---|---|---|
| `get_recent_sessions` | `--read` | Lists recent sessions. |
| `get_session` | `--read-id SESSION_ID` | One session's full metadata + content. |
| `search_sessions` (keyword) | `--search QUERY` | FTS5, same as MCP. |
| `search_sessions` (semantic) | `--search QUERY --semantic` | Pro tier only. |
| `get_skill_history` | `--skill-history --skill-name NAME` | Sessions that used a skill. |
| `inspect_sessions` | `--inspect [--search|--tag-filter|--surface|--since] [--show-stats]` | Stored-session listing with filters. |
| `get_stats` | `--stats` | Usage dashboard incl. hook_saves_failing. |
| `graph_session_map` | `--graph --graph-session-id ID \| --graph-project NAME` | Mermaid graph; mermaid on stdout, errors on stderr. |
| `get_dream_log` | `--dream-log [--project P] [--surface S]` | Consolidation log entries + digest status. |
| `get_related_sessions` | `--related --related-session-id ID` | Pro only; free tier exits 1 with an upgrade message. |
| `get_memory_digest` | `--digest --project P [--surface S]` | Prints the digest markdown; no_digest exits 1. |
| `get_context_for` | `--context-for --context-topic TOPIC` | Trust-framed excerpts (SH-13436 boundary), same as MCP. |

Keyword search and `--read-id` predate this contract; `--semantic` and the
`LORECONVO_DB` env-var precedence fix are what this contract adds. The
observability read ops (SH-101927) and the Pro-search / digest / context
read ops (SH-101929/101930) extend it. Every op delegates to the
same `SessionDatabase` methods the MCP server uses -- the fallback is a
second caller of that logic, never a second implementation of it.

## Write-side operations (out of the emergency read path)

The export/import ops (SH-101928) are second callers of the shared-core
`SessionDatabase` payload methods, not part of the tier-(a) read path:

| MCP tool | Fallback | Notes |
|---|---|---|
| `export_sessions` | `--export [--format json\|jsonl] [--output FILE]` | Writes a file or prints the payload. |
| `import_sessions` | `--import-file FILE [--on-conflict skip\|replace] [--dry-run]` | DB write; error summary on stderr. |
| `export_for_anthropic` | `--anthropic-export [--output FILE]` | Pro only; free tier exits 1 with an upgrade message. |
| `consolidate_memories` | `--consolidate --project P [--surface S]` | DB write; result JSON on stdout. |

## Guaranteed invariants

1. **A set-but-unresolvable `LORECONVO_DB` is a hard error, never a silent
   fall-through.** If `LORECONVO_DB` is set but the path does not resolve to
   an existing database, every operation exits `1` with an error on stderr
   and **no rows on stdout** -- it will not silently answer from another
   corpus (auto-discovery of a Cowork mount or `~/.loreconvo/`). Fix the
   path, unset the variable, or pass `--db-path` explicitly.
2. **`--semantic` degrades, it never crashes.** Without Pro extras (or off
   the Pro tier), `--semantic` prints an upgrade tip to stderr and falls
   through to an ordinary keyword search on stdout. Tip and results are
   never interleaved on the same stream.
3. **DB discovery precedence:** `--db-path` (explicit) > `LORECONVO_DB` (env
   override) > Cowork VM mount > `~/.loreconvo/sessions.db`. This matches
   the MCP server's own resolution.

## Drift guard

`tests/test_fallback_mcp_parity.py` asserts the fallback and the MCP server
agree on every tier-(a) operation against the same corpus, plus both
invariants above. Run per-product:

```
.venv/bin/python -m pytest ron_skills/loreconvo/tests/test_fallback_mcp_parity.py
```

## Out of scope

Session-save (`save_to_loreconvo.py` with no mode flag) and the write-side
ops named in the section above are not part of this contract's parity
guard -- they predate it or landed as write-side extensions and are not
covered by the tier-(a) drift guard. The tier-(a) observability read ops
added by SH-101927 ARE covered: test_fallback_mcp_parity.py exercises them
against the same corpus the MCP server writes.
