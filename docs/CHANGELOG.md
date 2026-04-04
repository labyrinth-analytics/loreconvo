# LoreConvo Changelog

What changed in each release, written for users (not developers).

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
