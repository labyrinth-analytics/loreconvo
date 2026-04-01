# LoreDocs Plugin Publishing Guide

How to publish LoreDocs to the Claude plugin marketplace.

## Current Status

Plugin packaging is done (ron_skills/loredocs-plugin/ and loredocs-v0.1.0.plugin).
This document covers what is needed to go from "packaged" to "publicly installable."

---

## CRITICAL FINDING: "knowledge-work-plugins" Is Reserved

The name `knowledge-work-plugins` is reserved by Anthropic for official use and cannot
be used as a marketplace name. Reserved names include:
  claude-code-marketplace, claude-code-plugins, claude-plugins-official,
  anthropic-marketplace, anthropic-plugins, agent-skills, knowledge-work-plugins,
  life-sciences

This means LoreDocs cannot be submitted *to* `knowledge-work-plugins` -- it is
Anthropic-internal. The options are:

  Option A: Submit to the official Anthropic marketplace (claude-plugins-official)
  Option B: Create a Labyrinth Analytics self-hosted marketplace on GitHub

See "Submission Options" below.

---

## MCP Server Path Assessment

LoreDocs's current loredocs-plugin/.mcp.json:

  "command": "python3",
  "args": ["-m", "loredocs.server"]

This is better than LoreConvo's hardcoded path, but still requires the `loredocs`
Python package to be installed in the user's system Python. A fresh plugin install will
NOT auto-install the package.

This is a distribution blocker. See "Pre-Submission Work Required" below.

---

## Submission Options

### Option A: Official Anthropic Marketplace (claude-plugins-official)

Highest-visibility path. Plugins appear in the built-in Discover tab.
Install command after approval:
  /plugin install loredocs@claude-plugins-official

Submission forms:
  - Claude.ai:  https://claude.ai/settings/plugins/submit
  - Console:    https://platform.claude.com/plugins/submit
  - Direct:     https://clau.de/plugin-directory-submission

Review process:
  - Anthropic reviews for quality and security
  - No guaranteed timeline
  - "Anthropic Verified" badge for plugins that pass additional review

### Option B: Self-Hosted GitHub Marketplace (recommended first step)

Create a shared Labyrinth Analytics marketplace repo on GitHub. LoreConvo and
LoreDocs can share the same marketplace file.

Users add it once:
  /plugin marketplace add labyrinth-analytics/claude-plugins

Then install:
  /plugin install loredocs@labyrinth-analytics-claude-plugins

This path is self-controlled with no Anthropic review required. Ideal for
early-access users and validating the product before official submission.

See the shared marketplace file format in LoreConvo's docs/PUBLISHING.md --
both plugins should be listed in the same marketplace.json.

LoreDocs entry for marketplace.json:
  {
    "name": "loredocs",
    "source": {
      "source": "github",
      "repo": "labyrinth-analytics/loredocs",
      "ref": "v0.1.0"
    },
    "description": "Searchable knowledge base for your AI projects. Store, tag, search, and inject documents into any Claude conversation.",
    "version": "0.1.0",
    "author": { "name": "Labyrinth Analytics Consulting" },
    "homepage": "https://github.com/labyrinth-analytics/loredocs",
    "license": "BSL-1.1",
    "keywords": ["knowledge-management", "documents", "search", "ai-projects"]
  }

---

## Pre-Submission Work Required

### 1. Fix MCP Server Installation (BLOCKER)

Current state: .mcp.json runs `python3 -m loredocs.server`, which requires
the loredocs package to be pip-installed in the user's Python environment.
Plugin installation does NOT run pip install automatically.

Option 1 -- npm wrapper with Python bundling (recommended):
  - Create package.json in loredocs-plugin/
  - Add postinstall script that runs: pip install loredocs
  - This is the most common pattern for Python-backed MCP plugins

Option 2 -- setup hook:
  - Add a .claude-plugin/hooks.json with a PostInstall hook
  - Hook runs: pip install --user loredocs (or installs from bundled wheel)
  - More native to the plugin system

Option 3 -- standalone binary:
  - Use PyInstaller to build a single-file executable
  - Bundle inside the plugin: ${CLAUDE_PLUGIN_ROOT}/bin/loredocs-server
  - Most portable, highest build complexity

Correct .mcp.json after fix (Option 3 example):
  {
    "mcpServers": {
      "loredocs": {
        "command": "${CLAUDE_PLUGIN_ROOT}/bin/loredocs-server",
        "args": [],
        "env": {
          "LOREDOCS_DATA": "${HOME}/.loredocs"
        }
      }
    }
  }

### 2. Publish to PyPI (required for Option 1/2 above)

If using pip install:
  - Create pyproject.toml (or setup.py) for loredocs package
  - Register on PyPI: https://pypi.org/account/register/
  - Build: python -m build
  - Upload: python -m twine upload dist/*
  - Package name: loredocs (or labyrinth-loredocs to avoid conflicts)

### 3. Create a Public GitHub Repo for the Plugin

Current state: plugin lives inside the side_hustle monorepo.
For marketplace distribution:

Option A (standalone repo -- recommended):
  - Create github.com/labyrinth-analytics/loredocs (public)
  - Move loredocs-plugin/ contents there
  - Tag releases: git tag v0.1.0 && git push --tags

Option B (monorepo git-subdir source):
  - Make the side_hustle repo public
  - Use git-subdir source in marketplace.json

### 4. Add homepage and repository Fields to plugin.json

Current plugin.json is missing:
  "homepage": "https://github.com/labyrinth-analytics/loredocs",
  "repository": "https://github.com/labyrinth-analytics/loredocs"

Add these before submission.

### 5. Validate the Plugin

Before submission, run:
  cd ron_skills/loredocs-plugin
  claude plugin validate .

Or from within Claude Code:
  /plugin validate .

---

## Plugin Structure Checklist

  [OK] .claude-plugin/plugin.json
        - name: "loredocs" (kebab-case)
        - version: "0.1.0"
        - description: present
        - author.name: present
        - keywords: present
        - license: "BSL-1.1"
  [OK] .mcp.json (present but needs package install solution)
  [OK] skills/ directory
  [OK] README.md
  [ ]  homepage field in plugin.json
  [ ]  repository field in plugin.json
  [ ]  MCP server auto-installs on plugin install
  [ ]  PyPI package published (if using pip approach)
  [ ]  Public GitHub repo for the plugin
  [ ]  Plugin validated with: claude plugin validate .

---

## Tier/Billing Integration Notes

LoreDocs has Free/Pro/Team tier gating in tiers.py, but the billing integration
(Stripe webhooks -> vault_set_tier) is not wired up yet. Before official marketplace
submission:

  - The Free tier must work out of the box (no signup required)
  - Pro/Team upgrade path should be documented in README
  - vault_tier_status tool lets users see their current tier

For the self-hosted marketplace launch (Phase 1), Free tier only is fine.
Billing integration can be wired up for the official submission.

Key unknown (still open from CLAUDE.md):
  Does the Claude marketplace have its own billing integration, or does Labyrinth
  Analytics use Stripe independently? Research this before wiring up vault_set_tier.

---

## Recommended Launch Sequence

Phase 1 (self-hosted, no Anthropic review):
  1. Fix MCP server auto-install (pip install or binary)
  2. Create public GitHub repo: labyrinth-analytics/loredocs
  3. Create/update shared marketplace repo: labyrinth-analytics/claude-plugins
  4. Add LoreDocs to marketplace.json (alongside LoreConvo)
  5. Test: /plugin install loredocs@labyrinth-analytics-claude-plugins
  6. Share with early adopters
  7. Update marketplace_listing.md with install command

Phase 2 (official Anthropic marketplace):
  1. Collect Phase 1 feedback, polish
  2. Decide on billing approach (Free only, or Stripe integration)
  3. Submit via https://clau.de/plugin-directory-submission
  4. Wait for Anthropic review
  5. Once approved, update all install instructions

---

## Key URLs

  Submission form:     https://clau.de/plugin-directory-submission
  Claude.ai submit:    https://claude.ai/settings/plugins/submit
  Console submit:      https://platform.claude.com/plugins/submit
  Plugin docs:         https://code.claude.com/docs/en/plugins
  Marketplace docs:    https://code.claude.com/docs/en/plugin-marketplaces
  Official catalog:    https://claude.com/plugins
  Official GitHub:     https://github.com/anthropics/claude-plugins-official
  PyPI registration:   https://pypi.org/account/register/
