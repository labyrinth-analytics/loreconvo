# LoreConvo Changelog

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

Anti-pattern storage: tag sessions with observed failure modes for future
avoidance. 32 MCP tools, CLI 8 commands.

(Earlier changelog entries not included; see git log for full history.)
