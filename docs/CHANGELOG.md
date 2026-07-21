# LoreConvo Changelog

What changed in each release, written for users (not developers).

---

## v0.8.5 (2026-07-21)

### Security: file and folder permissions hardened

v0.8.4 locked down the session database itself. This release extends the same
owner-only protection to everything else LoreConvo keeps in `~/.loreconvo/`:
the folder is now created private to you, and your config files and the
session-summarizer log are set to owner-only permissions whenever they are
written. Files left readable by an earlier version, or by a permissive system
setting, are corrected automatically the next time LoreConvo writes them. No
action needed on your part.

### Fixed: spurious compatibility warning on startup

Some installs showed an MCP version-mismatch warning even though the shipped
version was correct: the compatibility check was comparing against the wrong
reference version. The warning no longer appears on a correct install.

---

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

---

## v0.8.2 (2026-07-11)

### Fixed: Concurrent MCP clients no longer crash the server

Removed the single-instance PID lock. MCP clients that open more than one
connection to the same server (some agent frontends race parallel discovery
threads at startup) previously hit a RuntimeError crash-loop when the second
connection arrived. LoreConvo now relies on the same WAL + busy_timeout
concurrent-access protection LoreDocs uses, so multiple simultaneous
connections work.

Also fixed pragma ordering in the database layer: `busy_timeout` is now set
before the WAL journal-mode switch, so the timeout protects the mode switch
itself under concurrent startup.

### Security: sessions.db file permissions hardened

`sessions.db` is now set to owner-only permissions (0600) every time a
connection opens, so a database created or touched by an earlier version (or
a permissive umask) is corrected automatically.

### Fixed: idle watchdog survives a broken stderr

The 5-minute idle watchdog no longer dies if its stderr pipe is closed when
it fires (e.g. the parent client already disconnected). The shutdown itself
proceeds normally.

### Removed

`scripts/rollback_anti_pattern_v080.py` -- the one-time rollback safety net
for the v0.8.0 anti-pattern tables. Those tables are a permanent feature as
of v0.8.1; the script was inert.

---

## v0.8.1 (2026-07-08)

### New: User-Controlled Session Durability (keep_forever)

Adds explicit session pinning so users can exclude sessions from automated
cleanup, closing the parity gap with Recall's "Durable Memory" tier.

**New MCP tool:** `pin_session(session_id, keep_forever=True)`
  - Pin a session to exclude it from automated cleanup.
  - Accepts bool, int (0/1), or string ("true"/"false"/"1"/"0") for keep_forever.
  - Returns `{"ok": True, "session_id": "...", "keep_forever": bool}`.
  - Returns `{"ok": False, "code": "feature_disabled", ...}` when pinning is
    disabled via LORECONVO_DISABLE_PINNING or config.json.

**New CLI command:** `loreconvo pin <session_id> [--unpin]`
  - Pin a session: `loreconvo pin <uuid>`
  - Unpin a session: `loreconvo pin <uuid> --unpin`

**New CLI flag:** `loreconvo save --permanent`
  - Save and immediately pin the session in one step.

**Schema change:** `keep_forever INTEGER NOT NULL DEFAULT 0` column added to
  the `sessions` table. Migration runs automatically on first startup.
  All existing sessions read as `keep_forever=False` (DEFAULT 0).

**Enforcement:** A `sessions_prunable` view (rows where `keep_forever=0`) with
  an INSTEAD OF DELETE trigger is the primary enforcement layer. A BEFORE
  DELETE trigger on `sessions` is a secondary defense-in-depth for raw-SQL tooling.

**auto_load hook:** Pinned sessions receive a +1 scoring bonus (user-curation
  signal), same weight as artifact presence.

---

## v0.8.0 (2026-06-26)

### New: Anti-Pattern Storage

Tag past sessions as anti-patterns so you and your agents can surface known
failure modes before repeating them.

**Three new MCP tools:**

- `get_anti_patterns([topic], [limit], [project])` -- Retrieve sessions tagged
  as anti-patterns. Call this at session start or before a tricky task to see
  what has failed before. Filter by keyword (`topic`) or project slug.

- `tag_as_anti_pattern(session_id, source, reason)` -- Mark a session as an
  anti-pattern. Idempotent. Rate-limited to 20 calls per window.

- `untag_anti_pattern(session_id, source, reason)` -- Remove an anti-pattern
  tag. Idempotent. Both tag and untag record audit entries.

**Database changes:** Three new tables added automatically on first startup
after upgrade -- no manual migration needed.

**Duplicate server prevention:** A PID lockfile (`~/.loreconvo/server.pid`)
prevents two server instances from sharing the same database simultaneously.

**Startup validation:** `--dry-run-validate` flag checks schema and exits
without starting the server (exit 0 = OK, exit 1 = mismatch).

**Rollback:** `rollback_anti_pattern_v080.py` removes the anti-pattern tables.
Back up `sessions.db` before running.

32 MCP tools, 8 CLI commands.

---

## v0.7.5

### Security

- **Dependency security updates.** `pydantic-settings` is upgraded from 2.13.1 to
  2.14.2, clearing a moderate-severity advisory (GHSA-4xgf-cpjx-pc3j). `idna` is
  upgraded from 3.11 to 3.15, clearing PYSEC-2026-215. All runtime dependencies
  remain exact-pinned.

### Docs

- Removed a deprecated Cowork-surface restore guide that leaked an internal
  filesystem path. The install-hook guide now uses a generic install-directory
  placeholder and correctly names the session database file (`sessions.db`).
  The schema diagram's version header and internal role names are updated to
  match the current release.

---

## v0.7.4

### Security

- **Dependency security updates.** `cryptography` is upgraded from 46.0.7 to 49.0.0,
  clearing an OpenSSL advisory (GHSA-537c-gmf6-5ccf). `starlette` is now pinned to
  1.3.1, which clears five advisories. All runtime dependencies are exact-pinned.
- **Transcript path validation.** The auto-save hook now verifies that the session
  transcript path resolves inside `~/.claude` before reading it, so a crafted path
  cannot point the reader somewhere else.

### Reliability

- **WAL journal-mode guardrail.** LoreConvo now detects and refuses to mix SQLite
  journal modes on the same database, avoiding a class of "database is locked" and
  integrity errors that could occur when a WAL-mode database was opened on an older
  code path. In-memory databases (which cannot use WAL) are exempt.

### Packaging

- License metadata migrated to SPDX form (`BUSL-1.1`); the build now requires
  setuptools >= 77.

### Docs

- The install guide adds Codex and Hermes MCP setup sections. The README adds a
  Free-vs-Pro plan comparison and removes stale team-tier wording.

---

## v0.7.3

Internal packaging release: prepared plugin metadata for the MCP plugin registry
submission. No user-facing functional changes.

---

## v0.7.2

### Fixes

- **No more "database is locked" errors from leaked server processes.** Some MCP
  clients keep a stdio server parked open instead of closing it, leaving a process
  that held the SQLite write lock. The idle-exit watchdog now defaults to 5 minutes
  (override with `LORECONVO_IDLE_TIMEOUT`) and connections wait briefly on contention
  instead of failing instantly, so transient locks resolve on their own.
- **Fixed a startup crash** caused by an internal journal-mode validation call that no
  longer existed.
- **Mid-session (PreCompact) saves are now correctly filed.** Sessions captured by the
  PreCompact hook are now namespaced to the right project and tagged with the agent
  name, instead of occasionally being saved un-namespaced.

### Improvements

- **Auto-save now captures open questions.** When a session is saved automatically, any
  unresolved questions are extracted heuristically so they surface in your next session.
- **Safer exports.** Export paths are validated to prevent writing outside the intended
  directory.
- **More predictable installs.** The Anthropic SDK is pinned (`anthropic==0.87.0`) and
  LoreConvo is verified against MCP Python SDK 1.27.2.
- **Better crash diagnostics.** Auto-save crash-recovery stubs are now tagged with the
  agent and run that produced them.

### Project

- **GitHub issue templates added.** Bug-report and feature-request forms (with a privacy
  reminder not to paste keys or private session contents) make reporting issues clearer.
- Documentation updates to the install guide, MCP tool catalog, and schema-migration notes.

---

## v0.7.1

### New Features

- **Cross-product session linking with LoreDocs (Pro).** LoreConvo Pro can now discover and display the LoreDocs documents most relevant to any session, and vice versa. When you save a session, LoreConvo automatically identifies the most semantically similar vault documents and links them. Two new MCP tools expose this: `get_docs_for_session` (see which LoreDocs documents relate to a session) and `session_link_doc` (manually create a session-to-document link). Cross-product linking requires both LoreConvo Pro and LoreDocs Pro to be installed, and can be disabled per-session via opt-out.

---

## v0.7.0

### New Features

- **LLM async session summarization (Pro).** LoreConvo now automatically upgrades
  auto-saved sessions from heuristic summaries to LLM-quality summaries in the
  background, using Claude Haiku. Set `LORECONVO_ANTHROPIC_API_KEY` to opt in.
  Summarization happens after your session ends, without blocking the hook.
  A daily cap (configurable via `LORECONVO_SUMMARIZER_DAILY_CAP`, default 100)
  prevents runaway API spend. Each session tracks its summary quality via a new
  `summary_source` field: `heuristic`, `summary_pending`, `claude_async`, or
  `permanently_heuristic` (after 5 failed retries). Pro tier only.

### Migrations

- No action required. LoreConvo migrates your database automatically the next time
  it starts after you upgrade. The v0.7.0 upgrade adds the `summary_source`,
  `summary_retry_count`, and `fallback_reason` columns to sessions and creates the
  `cap_state` and `schema_migration_log` tables that async summarization needs. The
  migration is idempotent and preserves all existing sessions.

---

## v0.6.1

### New Features

- **Embedding-based related session discovery (Pro).** `get_related_sessions` now
  returns a v2 response envelope (`{"version": 2, "sessions": [...]}`) where each
  session includes `link_type` and `shared_term_count` fields. Pro users get automatic
  embedding-based links using BGE-small-en-v1.5 (cosine >= 0.75, up to 10 bidirectional
  pairs per save, same-project scoped, circuit-breaker protected). Free tier: keyword
  co-occurrence links only. Deduplication: if the same session pair is linked by both
  co-occurrence and embedding, co-occurrence wins. To disable embedding links, set
  `LORECONVO_EMBEDDING_LINKS=0`.

- **Session version history (previous_summary).** Each time you update a saved session,
  LoreConvo now captures the prior summary before overwriting it. The previous summary is
  stored in a new `previous_summary` field on the session and returned by the `get_session`
  MCP tool. This is an audit field -- it is not indexed for search. Use it to see what
  context was captured before a mid-session save (for example, from the PreCompact hook)
  replaced the original summary.

- **reasoning_notes parameter for save_session.** You can now pass an optional
  `reasoning_notes` text field when saving a session. Use this to record the reasoning
  chain behind a decision -- why you made a particular choice, what alternatives were
  considered, or what constraints shaped the outcome. Reasoning notes are stored separately
  from the session summary and are not indexed for search.

---

## 2026-05-19 -- v0.6.0

### New Features

- **Memory Recall: LoreConvo now consolidates your sessions into a living memory digest.** When you call `consolidate_memories`, LoreConvo reads your recent sessions and synthesizes a compact digest of standing facts, open questions, and recurring themes -- so you can ask "what have I been working on?" and get a coherent answer instead of a wall of raw session text. The digest is automatically injected into your next Claude session via the SessionStart hook, so you pick up context without hunting through history.

- **Session expiry (TTL).** You can now set an expiration date on any session using `set_session_expiry`. Once expired, the session is excluded from search results, the recent sessions list, and auto-load context. This lets you mark short-lived context (like one-off debugging notes) as temporary without deleting it. Expired sessions remain in the database and can be queried explicitly if you need them.

- **Get Memory Digest and Get Dream Log tools.** Two new read tools complement `consolidate_memories`: `get_memory_digest` returns your current consolidated digest, and `get_dream_log` shows the consolidation log -- what was processed, when, and which sessions contributed. Useful for understanding what LoreConvo knows and when it last updated its summary.

### Bug Fixes

- **Expired sessions no longer surface in search or auto-load.** Previously, setting an expiry on a session had no effect on what appeared in search results or the auto-load context injected at session start. All three paths (search, `get_recent_sessions`, auto-load) now filter out expired sessions automatically.

---

## 2026-05-17 -- v0.5.1

### New Features

- **Opt-in session summarization via Claude API.** When saving a session with `save_session`, you can now pass `summarize=True` to have LoreConvo automatically compress your summary using Claude Haiku before storing it. Long session summaries that would otherwise bloat your context window are condensed to the key facts. This requires an `ANTHROPIC_API_KEY` in your environment; if the key is absent or the API call fails for any reason, the original summary is saved as-is. The feature is strictly opt-in -- nothing changes if you do not pass `summarize=True`.

---

## 2026-05-14 -- v0.5.0

### New Features

- **Semantic search for Pro users.** LoreConvo Pro now supports hybrid semantic search: your sessions are indexed with BGE-small embeddings and searched using a combination of vector similarity, BM25 full-text, and a recency decay reranker. In practice this means queries like "the auth bug we fixed last sprint" find the right session even if those exact words don't appear in the summary. If the semantic index isn't available, search falls back silently to FTS5. Install with `pip install loreconvo[pro]` to enable this feature.

- **Related session discovery (Pro).** LoreConvo now automatically detects sessions that are topically related by analyzing which keywords co-occur across your session history. The new `get_related_sessions` tool surfaces sessions you might want to pull in as context when starting a new conversation on a familiar topic. This runs without any external API calls -- it's purely local analysis of your existing session data.

- **Anthropic Managed Agents export (Pro).** A new `export_for_anthropic` tool exports your sessions in the format required by Anthropic's managed-agents memory API (`memory_20250818`). This makes LoreConvo usable as a drop-in memory backend for agents built on the Anthropic SDK. The export includes a `--days-back` option on the CLI (`loreconvo export anthropic-v1`) to control how far back the export reaches.

---

## 2026-04-18

### Bug Fixes

- **Search now returns accurate results for more query terms.** The fallback search script (`save_to_loreconvo.py --search`) was using slow keyword matching for all queries. It now uses LoreConvo's full-text search engine first, which is faster and understands word boundaries correctly. If your search term contains special characters that the full-text engine cannot parse (such as hyphenated words like "build-time"), the script automatically retries with keyword matching instead. You do not need to do anything differently -- searches just work better now.

### Improvements

- **Session timestamps are now stored in a consistent UTC format.** LoreConvo now saves all session timestamps as UTC ISO 8601 strings (for example: `2026-04-18T14:30:00Z`). This aligns with the format LoreDocs uses and prepares both products for future cross-product time comparisons and cloud sync. Existing sessions are not affected -- they were already recorded in UTC, just without the explicit timezone marker.

---

## 2026-04-13

### Improvements

- **Multi-word search now finds more results.** When you searched for two-word phrases like "stripe billing," LoreConvo was treating them as an exact phrase match -- so a session that mentioned "stripe" and "billing" in separate sentences would not show up. LoreConvo now treats each word as an independent search term and returns sessions that contain all the words anywhere in the text. This significantly improves recall for multi-word queries.

- **Faster database queries.** Three new indexes were added to the session database to speed up lookups by date, project, and persona. The query that lists all projects was also rewritten to use a single database call instead of one per project. No visible changes -- queries simply complete faster as your session count grows.

---

## 2026-04-08

### Bug Fixes

- **Sessions now save reliably in Cowork.** Previously, when running inside a Cowork VM, the fallback save script (`save_to_loreconvo.py`) could write sessions to a temporary directory that disappears when the VM ends -- meaning any session saved there was silently lost. The script now checks your persistent mounted data path first and only falls back to the local VM directory if no persistent path is found. If you have been running agents in Cowork and noticed sessions not appearing, update to this version and your sessions will persist correctly going forward.

---

## 2026-04-06

### Bug Fixes

- **Install script now correctly creates the `loreconvo` entry point.** If you cloned LoreConvo and ran `install.sh` on a fresh machine, the `loreconvo` command might not have been created, causing a "module not found" error. The installer now runs `pip install .` to install the full package and entry point binary. If you hit this issue before, delete your `.venv/` folder and run `bash install.sh` again.

- **Hook scripts now work after a fresh install.** The SessionStart and SessionEnd hooks (which auto-load and auto-save your Claude sessions) were silently failing if you installed by cloning the repo. This is because git does not preserve file execute permissions. The install script now explicitly sets the correct permissions. Auto-save and auto-load now work correctly after a fresh install without any manual steps.

---

## 2026-04-03

### New Features

- **License key validation for Pro tier.** Pro access now uses Ed25519-signed license keys instead of a simple environment variable. Free users are unaffected. If you have a license key, set it as your `LORECONVO_PRO` environment variable and LoreConvo validates it locally (no internet needed). Keys are product-scoped and expiry-checked.

- **Onboarding skill (`/lore-onboard`).** New built-in skill that walks you through verifying your LoreConvo installation. Run it in Claude Code or Cowork to check that the database, MCP tools, hooks, and plugin structure are all working. Useful after a fresh install or upgrade.

- **Onboard verification script.** A new `scripts/onboard_verify.py` script that checks your installation programmatically: database connectivity, tool count, hook presence, and plugin structure. Used by the onboarding skill.

### Improvements

- **Plugin defaults fixed.** The public plugin `.mcp.json` now ships with empty `LORECONVO_PRO` values (not "1"), so new users start on the free tier as intended. The internal development `.mcp.json` retains dev-mode access.

- **Session limit error message updated.** When free-tier users hit the 50-session limit, the error message now explains how to upgrade with a license key.

---

## 2026-04-01

### Improvements

- **Plugin onboarding UX.** Improved the first-run experience for new plugin installs. Clearer error messages when the database is not initialized.

- **Pipeline sync.** Internal pipeline integration improvements for the agent team (does not affect end users).

---

## 2026-03-31

### New Features

- **BSL 1.1 license.** LoreConvo is now licensed under the Business Source License 1.1. Free for personal and non-commercial use (up to 50 sessions). Converts to Apache 2.0 on 2030-03-31.

- **50-session free tier enforcement.** Free accounts can save up to 50 sessions. After that, `save_session` returns a friendly "limit_reached" message with a link to upgrade. Existing sessions are never deleted.

---

## 2026-03-29

### New Features

- **CLI entry point.** LoreConvo now has a full command-line interface with 7 commands: `save`, `list`, `search`, `export`, `skill-history`, `skills list`, and `stats`. See the [CLI Reference](cli_reference.md) for details.

- **Skills list command.** New `skills list` subcommand shows all distinct skills recorded in session memory, sorted by usage count.

### Improvements

- **Dependency pinning.** All dependencies are now pinned to exact versions in `requirements-lock.txt` for reproducible installs.

- **Security hardening.** Redacted API keys from reports, set up virtual environments for isolation, improved `.gitignore` coverage.

---

## 2026-03-25

### New Features

- **Renamed from ConvoVault to LoreConvo.** The product has a new name. All tool names, database paths, and documentation have been updated. If you were using ConvoVault, your existing data at `~/.loreconvo/sessions.db` is preserved.

### Improvements

- **Auto-load session scoring.** The SessionStart hook now scores recent sessions by signal quality: sessions with open questions (+3), key decisions (+2), and artifacts (+1) are prioritized. Low-signal sessions are filtered out. Output is capped at 4000 characters to avoid overwhelming Claude.

- **Vault suggest tool.** New `vault_suggest` MCP tool that proactively recommends which context to load based on open questions, key decisions, and skill gaps.

---

## Earlier Releases

LoreConvo v0.1.0-v0.2.0 established the core architecture: SQLite+FTS5 storage, 12 MCP tools, auto-save/auto-load hooks for Claude Code, and cross-surface support for Cowork and Chat.
