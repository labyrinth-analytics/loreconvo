# LoreConvo Changelog

## v0.8.2 (2026-07-11)

### Fixed: Concurrent MCP clients no longer crash the server

Removed the single-instance PID lock (introduced incidentally in v0.8.0).
MCP clients that open more than one connection to the same server (some agent
frontends race parallel discovery threads at startup) previously hit a
RuntimeError crash-loop when the second connection arrived. LoreConvo now
relies on the same WAL + busy_timeout=10000ms concurrent-access protection
LoreDocs uses, so multiple simultaneous connections work. Covered by the new
`test_concurrent_instances.py`.

Also fixed pragma ordering in `_open_conn`: `busy_timeout` is now set before
the `journal_mode=WAL` switch, so the timeout covers the mode-switch pragma
under concurrent startup.

### Security: sessions.db file permissions hardened (SH-12873)

`sessions.db` is now chmod'd to owner-only permissions (0600) on every
connection open in `_open_conn`, so a database created or touched by an
earlier version (or a permissive umask) is corrected automatically.

### Fixed: idle watchdog survives a broken stderr (SH-12881)

The 5-minute idle watchdog no longer dies if its stderr pipe is closed when
it fires (e.g. the parent client already disconnected). The shutdown itself
proceeds normally.

### Removed

`scripts/rollback_anti_pattern_v080.py` -- the one-time rollback safety net
for the v0.8.0 anti-pattern tables. Those tables are a permanent feature as
of v0.8.1; the script was inert and nothing referenced it.

## v0.8.1 (2026-07-08)

### New: User-Controlled Session Durability (keep_forever)

Adds explicit session pinning so users can exclude sessions from automated
cleanup, closing the parity gap with Recall's "Durable Memory" tier (SH-11449).

**New MCP tool:** `pin_session(session_id, keep_forever=True)`
  - Pin a session to exclude it from automated cleanup.
  - Accepts bool, int (0/1), or string ("true"/"false"/"1"/"0") for keep_forever.
  - Returns `{"ok": True, "session_id": "...", "keep_forever": bool}`.
  - Returns `{"ok": False, "code": "feature_disabled", ...}` when pinning is
    disabled via LORECONVO_DISABLE_PINNING or config.json.

**New CLI command:** `loreconvo pin <session_id> [--unpin]`
  - Pin a session: `loreconvo pin <uuid>`
  - Unpin a session: `loreconvo pin <uuid> --unpin`
  - Exit codes: 0 = success, 1 = user error, 2 = DB error.

**New CLI flag:** `loreconvo save --permanent`
  - Save and immediately pin the session in one step.

**Schema change:** `keep_forever INTEGER NOT NULL DEFAULT 0` column added to
  the `sessions` table. Migration runs automatically on first startup.
  All existing sessions read as `keep_forever=False` (DEFAULT 0).

**Enforcement:** A `sessions_prunable` view (rows where `keep_forever=0`) with
  an INSTEAD OF DELETE trigger is the primary enforcement layer. All cleanup
  paths route through this view. A BEFORE DELETE trigger on `sessions` is a
  secondary defense-in-depth for raw-SQL tooling.

**Pinning disable (three-tier rollback):**
  - Tier 1: Set `LORECONVO_DISABLE_PINNING=1` (shell users).
  - Tier 2: Write `{"pinning_enabled": false}` to `~/.loreconvo/config.json`
    (managed marketplace users without shell access).
  - Tier 3: `pip install loreconvo==0.8.0` (PyPI users only).

**Downgrade instructions:** If you downgrade to 0.8.0 and a tool issues
  bare `DELETE FROM sessions` (bypassing the view), run:
  `scripts/loreconvo_0.8.1_downgrade.sql`
  Back up `sessions.db` first. After running, keep_forever=1 sessions lose
  protection. See the script header for full details.

**inspect_sessions:** Single-session detail now includes `keep_forever` (0 or 1).

**auto_load hook:** Pinned sessions receive a +1 scoring bonus (user-curation
  signal), same weight as artifact presence.

**Architecture:** SH-11664 / SH-12733 (r6 APPROVED_WITH_OPEN_HIGHS, 4 rounds).

---

## v0.8.0 (2026-06-26)

### New: Anti-Pattern Storage

Tag past sessions as anti-patterns so you and your agents can surface known
failure modes before repeating them.

**Three new MCP tools:**

- `get_anti_patterns([topic], [limit], [project])` -- Retrieve sessions tagged
  as anti-patterns. Call this at session start or before a tricky task to see
  what has failed before. Filter by keyword (`topic`) or project slug.
  Returns session ID, title, date, summary, decisions, and open questions for
  each match. Tagging is sparse by design, so FTS5 results may be slightly
  under-complete when `topic` is supplied -- the `truncated` field signals this.

- `tag_as_anti_pattern(session_id, source, reason)` -- Mark a session as an
  anti-pattern. Idempotent: tagging an already-tagged session is safe.
  Rate-limited to 20 calls per window to prevent bulk misuse.

- `untag_anti_pattern(session_id, source, reason)` -- Remove an anti-pattern
  tag. Idempotent. Both tag and untag record an audit entry so you can see the
  full tagging history for any session.

**Database changes:** Three new tables added automatically on first startup
after upgrade -- no manual migration needed:
- `anti_pattern_sessions` -- which sessions are tagged and when
- `anti_pattern_audit_log` -- full audit trail of every tag/untag operation
- `anti_pattern_rate_state` -- rate-limit state per caller

**Schema validation at startup:** LoreConvo now validates the anti-pattern
table schema on startup and exits immediately if a mismatch is detected
(protects against partial upgrades). Use the `--dry-run-validate` flag to run
just this check without starting the server: exit 0 = schema OK, exit 1 = mismatch.

**Duplicate server prevention:** A PID lockfile (`~/.loreconvo/server.pid`)
prevents two server instances from sharing the same database simultaneously.
If you launch a second server against the same database, it exits with an error
pointing to the running process ID. The lockfile is cleaned up automatically on
exit.

**Rollback:** `rollback_anti_pattern_v080.py` drops the three anti-pattern
tables and reverts to v0.7.5 schema. Back up `sessions.db` first; rolling back
discards all anti-pattern tags permanently.

32 MCP tools, 8 CLI commands.

---

(Earlier changelog entries not included; see git log for full history.)
