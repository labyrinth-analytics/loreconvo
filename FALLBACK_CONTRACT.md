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

Keyword search and `--read-id` predate this contract; `--semantic` and the
`LORECONVO_DB` env-var precedence fix are what this contract adds. Both
delegate to the same `SessionDatabase.search_sessions()` call the MCP server
uses -- the fallback is a second caller of that logic, never a second
implementation of it.

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

Session-save (`save_to_loreconvo.py` with no `--read`/`--read-id`/`--search`
flag) and all write-side flags are not part of this contract -- they predate
it and are not covered by the parity guard.
