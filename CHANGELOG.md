# LoreConvo Changelog

## v0.10.3 (2026-08-11)

### Added: Opt-in semantic dedup pass in `consolidate_memories`

Consolidation can now collapse near-duplicate sessions before extracting
signals, so a project where the same decision was restated across several
sessions no longer produces a digest that repeats it. The pass compares the
LanceDB embeddings already held for the candidate sessions and drops a session
when its cosine similarity to a newer kept session exceeds the mode threshold.

The `dedup` argument accepts three values:

- `off` -- the pass does not run and consolidation behaves exactly as before.
  This is the default.
- `conservative` -- collapses near-verbatim restatements (cosine > 0.97).
- `balanced` -- collapses paraphrases (cosine > 0.95).

It can also be set with the `LORECONVO_CONSOLIDATION_DEDUP` environment
variable; an explicit argument always wins over the env var. Matching is
case-sensitive against those three lowercase literals, and an unrecognised
value resolves to `off` with a logged warning rather than failing the call.

The result dict gains `sessions_considered`, `sessions_collapsed`,
`sessions_consolidated`, `dedup`, and `collapsed` -- the last being a list of
`{session_id, similar_to, similarity}` records, so every collapse is
attributable rather than silent. A session with no vector in the index is
never collapsed, and the LanceDB read is scoped by project and surface, so a
session outside the consolidation scope cannot be compared against. If
LanceDB is unavailable the pass degrades to a pass-through.

### Fixed: A failing hook could surface as a session error

`on_session_end.sh` and `on_pre_compact.sh` propagated the Python exit code to
the caller. Both hooks invoke LoreConvo through `uvx`, which is
network-capable -- a first-run package download or an unreachable PyPI made
the hook fail, and that failure reached the user as an error in a session that
was otherwise fine. Both now log the failure to the hook log and exit 0
unconditionally. A hook that cannot save is a lost save, not a broken session.

### Fixed: Post-turn capture worker reprocessed entries it had already handled

`capture_worker.py` read the capture queue looking only for `queued` entries
and ignored the `processed` markers written beside them, so every drain
re-summarized everything still in the queue file -- burning API calls against
the daily ceiling and producing duplicate captures. The worker now reads the
`processed` markers first and skips any `queued` entry whose timestamp and
session ID have already been handled.

### Fixed: Fallback save script bypassed the Free-tier session limit

`scripts/save_to_loreconvo.py` -- the script path used when the MCP server is
unavailable -- inserted new sessions without checking the 50-session Free
limit that the MCP server's `save_session` enforces. Saving through the
fallback therefore had no cap. The script now performs the same check before
inserting a new session, and reports the limit with the upgrade link when it
is reached. Updates to existing sessions are unaffected, since they do not add
to the count.

## v0.10.2 (2026-08-09)

### Fixed: Commands named in errors and docs that could not run

The `loreconvo` console script is the MCP server entry point
(`loreconvo.server:main`). Several places named `loreconvo <command>` as if it
were the CLI, so following them started a stdio server that waits on stdin
instead of running the command. The bundled fallback CLI has no console script
of its own; it is invoked `python -m loreconvo.cli <command>`.

Corrected in four places:

- `anthropic_bridge.py` -- the `ToolError` raised when memory deletion is
  attempted through the Anthropic memory-tool bridge told the caller to run
  `loreconvo inspect --delete <id>`. This is the only one reachable at
  runtime rather than in documentation.
- `cli.py` -- `export --help` described importing the bundle via
  `loreconvo merge`.
- `INSTALL.md` -- the Team memory (Pro) bullet, same command.
- `skills/loreconvo/SKILL.md` -- the Chat-export section gave
  `loreconvo export --last --format markdown`. This file ships in the
  marketplace bundle, so the wrong form was also being read by Claude.

Flags and command names were correct throughout; only the invocation prefix
was wrong. A `cli-invocation` rule in `scripts/check_doc_sync.py` now derives
the real command set from the Click/Typer app and fails the build on any
shipped file naming a form that cannot work.

### Fixed: `graph_session_map` missing from the MCP tool catalog

The tool shipped in v0.10.0 but never reached
`docs/mcp_tool_catalog.md`, and the catalog's stated tool count still read 38.
Both corrected (39). The catalog had a drift test that could never run -- it
pointed at the monorepo `docs/` rather than the product's, and its body opened
with an unconditional skip -- so nothing caught the omission. The test now
delegates to `check_doc_sync.py`, which fails when any user-facing tool is
absent from the catalog or the stated count is stale.

## v0.10.1 (2026-08-09)

### Fixed: Documentation error in the v0.10.0 release notes

The v0.10.0 notes and README gave the new license command as
`loreconvo license clear`. That does not work: the `loreconvo` console script
is the MCP server entry point, so the command starts a stdio server instead.
The correct invocation is `python -m loreconvo.cli license clear`. Corrected
in both the changelog and the README; no code changed.

## v0.10.0 (2026-08-09)

### Added: Knowledge-graph Mermaid export (`graph_session_map`)

A new MCP tool renders the session graph -- sessions plus the `link_sessions`
relationships between them -- as a Mermaid diagram that can be pasted into any
Markdown renderer that supports Mermaid. Scope is controlled by project, a
root session ID, and a neighborhood depth. This brings the user-facing tool
count to 39.

### Added: Post-turn capture hook (opt-in)

A two-stage PostToolUse capture path. Stage 1 (`post_turn_capture.py`) is a
fast enqueue that writes a work item to `~/.loreconvo/capture_queue/` every N
tool calls; Stage 2 (`capture_worker.py`) drains the queue out of band and
summarizes. This keeps per-turn hook latency off the critical path.

Off by default. Enable with `LORECONVO_POST_TURN_CAPTURE=1`. Tunable with
`LORECONVO_TURN_CAPTURE_INTERVAL` (default 10 tool calls) and
`LORECONVO_TURN_CAPTURE_MAX_CALLS_PER_DAY`. Queue items older than 7 days are
discarded.

### Added: `license clear` command on the bundled fallback CLI

`python -m loreconvo.cli license clear` clears the stored Pro license key.
Pass `--suite` to also clear the suite-wide key held by the sibling product.
Warnings raised by the underlying `license_store.clear_key()` are now surfaced
in CLI output instead of being discarded.

Note the invocation: the `loreconvo` console script is the MCP server entry
point (`loreconvo.server:main`), so `loreconvo license clear` starts a stdio
server rather than running this command. The bundled CLI at `src/cli.py` is a
fallback surface for when MCP is unavailable and has no console script of its
own. The separate `loreconvo-cli` package is a different product (PROD-00910)
and does not carry this command.

### Changed: Database initialization deferred to first tool call

The MCP server previously constructed `SessionDatabase` at module import. It
now initializes lazily on first use, which removes database setup from server
startup. Note for anyone patching internals in tests: the module-level `db`
global is gone, replaced by `_db` behind a `_get_db()` accessor.

### Changed: Hook database write paths consolidated

`auto_save.py`, `periodic_save.py`, and `pre_compact_save.py` now route all
writes through a shared `core/storage_core.py` rather than each opening and
configuring their own connection. Connection setup (WAL mode, busy timeout,
row factory) has a single definition, and a guard test enforces that the
schema DDL is not duplicated across modules. No behavior change intended.

### Fixed: Spurious "install is degraded" warning on source installs

The hook bootstrap resolves `storage_core` from the installed `loreconvo`
package when one is present, and otherwise falls back to a bounded upward
search for a local `src/core/storage_core.py`. It misclassified "no package
installed" as "package installed but broken", because
`importlib.util.find_spec("loreconvo.core")` raises `ModuleNotFoundError` when
the parent package is absent rather than returning `None`, and a catch-all
`except Exception` recorded that as a broken-package error.

The effect was that every hook run on a source install (`install.sh`, no
`pip install loreconvo`) printed `WARNING: loreconvo package is installed but
broken (No module named 'loreconvo') ... The install is degraded; reinstall
loreconvo`. Saves succeeded normally throughout -- the warning was false, but
it advised a pointless reinstall. Only a genuinely broken package (parent
importable, `core.storage_core` failing) now triggers degraded mode.

### Security: cryptography 49.0.0 -> 50.0.0

Picks up the fix for CVE-2026-69247.

## v0.9.0 (2026-08-04)

### Added: Agent context injection

Two new MCP tools let agents auto-load targeted session context at session
start instead of relying on ad hoc searches: `configure_agent_context` stores
a named topic list per `(agent_name, project)`, and `inject_agent_context`
returns matching session context as markdown (stored config or call-time
topics), capped at 4000 characters. Responses use a four-state status enum
(`ok`/`warning`/`partial`/`error`) -- callers must branch on `status`
explicitly rather than treating anything other than `error` as success. See
the `using-loreconvo` skill for the caller pattern.

### Added: Structured memory items

A new `memory_items` layer stores decisions, open questions, and artifacts as
first-class structured records (separate from free-text session summaries),
with lifecycle transitions (retire/answer/wont-answer), FTS5 search, and
project scoping. New MCP tools: `save_memory_item`, `query_memory_items`,
`transition_memory_item`, `update_memory_item`.

## v0.8.10 (2026-07-31)

### Changed: Hook output format change -- recalled-content trust boundary

The auto-load SessionStart hook now wraps recalled session/digest content in
an explicit untrusted-data delimiter (`<system-reminder id="...">...</system-reminder>`)
before injecting it into Claude Code's context, with a per-session nonce, a
provenance line per session ("heuristic capture", "LLM summarized (Pro)",
etc.), and the removal of the prior free-floating instruction-like sentence
at the end of the block.

This is a framing/boundary-integrity fix (SH-13436), not a claim to solve
prompt injection. The injected-context text format has never been a
documented, stable contract for this hook; any external tooling parsing it
structurally should expect this and future format changes.

### Fixed: Auto-save length limits now match documented values

Session auto-save was still capping saved summaries and decisions at limits
left over from an earlier version of the hook (50,000 and 5,000 characters)
rather than the smaller values actually intended for this release (8,000 and
500). A separate bug in the truncation marker could also let a saved field
run slightly past its limit instead of stopping at it.

Starting in v0.8.10, saved summaries are capped at 8,000 characters and
decisions at 500, and the `[TRUNCATED: ...]` marker is reserved inside that
limit so a truncated field never exceeds it.

## v0.8.9 (2026-07-28)

### Fixed: Idle-watchdog now releases resources cleanly instead of killing the server

The idle-watchdog timeout (5 minutes with no MCP messages) would force-exit the
stdio server process when the timeout fired. Some clients (Claude Desktop, early
Claude Code versions) park stdio servers open while they're idle instead of
closing the pipe when they're done, causing the process to stay open, lock the
database, and leak system resources.

Starting in v0.8.9, the watchdog closes its database connection and drops its
cached Lance semantic-search index, then returns cleanly instead of exiting the
process. The server stays parked, but releases the resources it was holding.
Clients that do close the pipe promptly are not affected. Clients that park the
connection will now stay stable and will not block other Claude instances from
accessing the database.

If you were using the workaround environment variable `LORECONVO_IDLE_TIMEOUT=86400`
(1 day) to avoid the server exit, you can remove it — the fix handles the timeout
without needing a workaround.

## v0.8.8 (2026-07-26)

### Fixed: installing or updating LoreConvo from the marketplace

Installing or updating LoreConvo from the plugin marketplace failed with
"invalid manifest file ... Validation errors: hooks: Invalid input", and there
was no way around it from the user's side.

The plugin manifest declared its hooks in a shape the plugin loader does not
accept. Nothing about LoreConvo itself was wrong, but the marketplace validates
the manifest before it will install or update anything, so the whole plugin was
rejected at the door. Versions 0.8.3 through 0.8.7 are all affected.

This release fixes the manifest. Install and update both work again.

If you are stuck on an older version, update normally; no manual cleanup is
needed. There are no changes to the LoreConvo package itself in this release,
so nothing about your data, settings, or saved sessions changes.

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
