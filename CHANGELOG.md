# LoreConvo Changelog

## v0.8.7 (2026-07-26)

### Installs and updates now work the way you would expect

LoreConvo used to run from a Python virtual environment created in the source
tree, or from `uvx loreconvo@latest`. Both had the same problem: what actually
ran was not pinned. `@latest` resolves against a cache that can be stale, so a
server could keep running an old version indefinitely, and "did the update take
effect?" had no reliable answer. The venv had a sharper edge: its interpreter is
a symlink to a system Python, so upgrading or removing that Python broke the
server outright.

The plugin now ships a configuration pinned to an exact version, and the server
runs through `uvx` with its own managed Python. Installing or updating the
plugin is what changes your version, and nothing else does. There is no virtual
environment to create, break, or repair.

If you installed a previous version, leftover packages from the old pip install
are harmless; you can ignore them. Nothing needs to be uninstalled.

### Fixed: "database disk image is malformed" during search, and stale search results

A defect in the search index could corrupt it while saving a session, producing
"database disk image is malformed" errors on subsequent searches. A related
defect meant deleted sessions could leave fragments behind, so search sometimes
matched text that no longer existed in any session.

Both are fixed, and the fix is retroactive: upgrading repairs an index that has
already been damaged. Your sessions are not affected either way, since the
underlying data was never at risk, only the search index built over it. The
repair runs automatically on first start after the upgrade and needs nothing
from you. On a large history it may add a few seconds to that one startup.

### Fixed: diagnostics no longer hide the reason for a failure

`get_server_info` and the `loreconvo-compat-check` command reported that
something was wrong without saying what: the underlying error text was being
discarded. It is now included in the output. A missing `packaging` dependency
was also causing the compatibility check to disable itself silently; that
dependency is now declared, so the check runs and reports a real version.

### One install, every tier: semantic search now works out of the box

Semantic search used to be a separate install step. It needed the `[pro]`
extra, which pulled in PyTorch: a large download, a second environment to keep
up to date, and a common source of "why isn't semantic search working?"

Semantic search now ships in the standard install. The same embedding model as
before (BAAI/bge-small-en-v1.5) runs on ONNX Runtime instead of PyTorch, which
is roughly a third of the download size. There is one install path and one
environment for everyone. Pro is now purely a license flag: nothing extra to
install to unlock it.

`pip install loreconvo[pro]` still works and is now equivalent to a plain
install, so existing scripts do not break.

**Recommended one-time step:** run `rebuild_index` after upgrading. The new
runtime produces very slightly different vectors than the old one, so an index
built before this release will gradually drift out of step with new entries.
Rebuilding brings everything back onto the same footing. Keyword search is
unaffected and needs nothing.

The first semantic search after upgrading downloads the model (about 90MB) and
may take a minute. After that it is cached.

### Updated: MCP SDK

The bundled MCP SDK moves to 1.28.1, which carries fixes for three advisories in
the versions LoreConvo previously pinned (CVE-2026-52870, CVE-2026-52869,
CVE-2026-59950). None of them could affect LoreConvo: all three concern network
transports and a multi-client task feature that LoreConvo does not use, since it
runs over stdio as a single-client local server. The update means a security
scan of your install comes back clean.

## v0.8.6 (2026-07-24)

### Docs: corrected MCP tool count and tool references

The README and MCP tool catalog now report the accurate public tool count of 32
(previously listed as 28). Four tools that ship in the server but were missing
from the catalog are now documented: `pin_session`, `get_anti_patterns`,
`tag_as_anti_pattern`, and `untag_anti_pattern`. A reference to a nonexistent
`rebuild_semantic_index` tool was corrected to its real name, `rebuild_index`.
The `get_server_info` version-compatibility diagnostic is now excluded from the
advertised count, so "32 MCP tools" reflects user-facing tools only. This is a
documentation-only release with no code or behavior changes.

## v0.8.5 (2026-07-21)

### Security: auxiliary file and directory permissions hardened (SH-12892)

v0.8.4 hardened `sessions.db` itself; this release extends the same owner-only
treatment to everything else LoreConvo writes under `~/.loreconvo/`. The data
directory is now created with mode 0700, and `config.json` (both the tier
config in `core/config.py` and the onboarding config in `core/onboard_tool.py`)
plus the session-summarizer log file are chmod'd to 0600 on write. Files
created by an earlier version or under a permissive umask are corrected the
next time LoreConvo writes them.

### Fixed: spurious MCP compatibility warning (SH-12969)

The compatibility guard declared its tested MCP version as 1.27.2 while the
pinned dependency is 1.27.0, so the guard reported a version mismatch against
LoreConvo's own shipped pin. The constant now matches the pin and the warning
no longer fires on a correct install.

## v0.8.4 (2026-07-17)

### Added: Durable Pro license persistence

Your Pro license is now stored durably in a per-user file
(`~/.loreconvo/license.json`, owner-only permissions) instead of depending on an
environment variable being present in every shell. Once activated, Pro persists
across restarts and new sessions. The license is resolved in a stable order:
an environment variable takes precedence, then the file store, and a key
supplied via the environment is written through to the file store automatically
so it survives after the variable goes away. A short grace-period cache keeps
Pro working through brief license-validation outages.

Legacy installs that were granting Pro from an unverified local tier flag now
get a bounded 30-day grace window instead of indefinite access; after that a
verified key is required.

### Added: Automatic session capture on stop

LoreConvo now captures your session automatically when a Claude Code session is
halted mid-work, via a Stop hook, so context is saved even when you do not run a
manual save. The capture is overwritten by the normal end-of-session save when
the session closes cleanly.

## v0.8.3 (2026-07-15)

### Security: Updated click to 8.3.3 (CVE-2026-7246)

Bumped the `click` dependency from 8.3.1 to 8.3.3 to pick up the fix for
CVE-2026-7246. No functional or API changes; this is a security-only patch
release.

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
