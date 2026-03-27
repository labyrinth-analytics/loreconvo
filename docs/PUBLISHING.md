# LoreConvo Plugin Publishing Guide

How to publish LoreConvo to the Claude plugin marketplace.

## Current Status

Plugin packaging is done (ron_skills/loreconvo-plugin/ and loreconvo-v0.3.0.plugin).
This document covers what is needed to go from "packaged" to "publicly installable."

---

## CRITICAL FINDING: "knowledge-work-plugins" Is Reserved

The name `knowledge-work-plugins` is reserved by Anthropic for official use and cannot
be used as a marketplace name. Reserved names include:
  claude-code-marketplace, claude-code-plugins, claude-plugins-official,
  anthropic-marketplace, anthropic-plugins, agent-skills, knowledge-work-plugins,
  life-sciences

This means LoreConvo cannot be submitted *to* `knowledge-work-plugins` -- it is an
Anthropic-internal marketplace, not a third-party one. The options are:

  Option A: Submit to the official Anthropic marketplace (claude-plugins-official)
  Option B: Create a Labyrinth Analytics self-hosted marketplace on GitHub

See "Submission Options" below.

---

## CRITICAL BUG: MCP Server Paths Are Hardcoded

The current loreconvo-plugin/.mcp.json contains:

  "command": "${HOME}/projects/side_hustle/ron_skills/loreconvo/.venv/bin/python3"
  "args":    ["${HOME}/projects/side_hustle/ron_skills/loreconvo/src/server.py"]

These paths only work on Debbie's Mac. No other user can install this plugin
without manually editing paths.

For distribution, the plugin must bundle its Python server and use ${CLAUDE_PLUGIN_ROOT}
to reference files. See "Pre-Submission Work Required" below.

---

## Submission Options

### Option A: Official Anthropic Marketplace (claude-plugins-official)

This is the highest-visibility path. Plugins appear in the built-in Discover tab and
can be installed with `/plugin install loreconvo@claude-plugins-official`.

Submission forms:
  - Claude.ai:  https://claude.ai/settings/plugins/submit
  - Console:    https://platform.claude.com/plugins/submit
  - Direct:     https://clau.de/plugin-directory-submission

Review process:
  - Anthropic reviews for quality and security before approval
  - No guaranteed timeline or public SLA
  - "Anthropic Verified" badge if it passes additional review

Requirements (inferred from docs and structure):
  - .claude-plugin/plugin.json with name, version, description, author
  - README.md with clear documentation
  - plugin name must be kebab-case (loreconvo = [OK])
  - No hardcoded paths; MCP server must be self-contained

### Option B: Self-Hosted GitHub Marketplace

Create a GitHub repo (e.g., labyrinth-analytics/claude-plugins) with a
.claude-plugin/marketplace.json listing LoreConvo and LoreDocs.

Users add it once:
  /plugin marketplace add labyrinth-analytics/claude-plugins

Then install:
  /plugin install loreconvo@labyrinth-analytics-claude-plugins

This path is:
  - Self-controlled (publish on your own timeline)
  - Lower bar for approval (no Anthropic review)
  - Less visible (users must know the GitHub repo name)
  - Good for early adopters / word-of-mouth launch

Marketplace file format (.claude-plugin/marketplace.json):

  {
    "name": "labyrinth-analytics-claude-plugins",
    "owner": {
      "name": "Labyrinth Analytics Consulting",
      "email": "debbie.wonderkitty@gmail.com"
    },
    "metadata": {
      "description": "Claude plugins from Labyrinth Analytics Consulting"
    },
    "plugins": [
      {
        "name": "loreconvo",
        "source": {
          "source": "github",
          "repo": "labyrinth-analytics/loreconvo",
          "ref": "v0.3.0"
        },
        "description": "Cross-surface persistent memory for Claude sessions.",
        "version": "0.3.0",
        "author": { "name": "Labyrinth Analytics Consulting" },
        "homepage": "https://github.com/labyrinth-analytics/loreconvo",
        "license": "MIT",
        "keywords": ["memory", "sessions", "context", "recall"]
      }
    ]
  }

Recommendation: Do Option B first (faster to ship, test in the real world), then
pursue Option A once the product is polished and has some user feedback.

---

## Pre-Submission Work Required

### 1. Fix MCP Server Bundling (BLOCKER)

The Python server must be distributable without a pre-existing venv at a specific path.

Option 1 -- npm wrapper (recommended for plugin distribution):
  - Create package.json in loreconvo-plugin/ that installs loreconvo as an npm package
  - Change .mcp.json to use npx or a bundled node script
  - This is how most distributed MCP plugins work

Option 2 -- setup hook:
  - Add a PostInstall hook to loreconvo-plugin/hooks/ that runs pip install
  - Change .mcp.json to use: python3 -m loreconvo.server (installed globally)
  - Less reliable (depends on user's system Python)

Option 3 -- standalone binary (future):
  - Use PyInstaller to bundle Python server into a single executable
  - Reference ${CLAUDE_PLUGIN_ROOT}/bin/loreconvo-server in .mcp.json
  - Most portable, but adds build complexity

For now: write the .mcp.json as it would look after fixing, document it here,
and block the official submission until this is resolved.

Correct .mcp.json template (using CLAUDE_PLUGIN_ROOT):
  {
    "mcpServers": {
      "loreconvo": {
        "command": "${CLAUDE_PLUGIN_ROOT}/bin/loreconvo-server",
        "args": [],
        "env": {
          "LORECONVO_DB": "${HOME}/.loreconvo/sessions.db"
        }
      }
    }
  }

### 2. Create a Public GitHub Repo for the Plugin

Current state: the plugin lives inside the side_hustle monorepo.
For marketplace distribution, LoreConvo needs its own public GitHub repo, or
the monorepo needs to be public with the plugin as a git-subdir source.

Option A (standalone repo -- cleaner):
  - Create github.com/labyrinth-analytics/loreconvo (public)
  - Move loreconvo-plugin/ contents there
  - Tag releases (v0.3.0)

Option B (monorepo with git-subdir source):
  - Make side_hustle repo public
  - In marketplace.json, use source: { "source": "git-subdir", ... }
  - Simpler but exposes the whole monorepo

### 3. Add homepage and repository Fields to plugin.json

Current plugin.json is missing:
  "homepage": "https://github.com/labyrinth-analytics/loreconvo",
  "repository": "https://github.com/labyrinth-analytics/loreconvo"

These are optional but strongly recommended for marketplace credibility.

### 4. Validate the Plugin

Before submission, run:
  cd ron_skills/loreconvo-plugin
  claude plugin validate .

Or from within Claude Code:
  /plugin validate .

Fix any errors before submitting.

---

## Plugin Structure Checklist

  [OK] .claude-plugin/plugin.json
        - name: "loreconvo" (kebab-case)
        - version: "0.3.0"
        - description: present
        - author.name: present
        - keywords: present
        - license: "MIT"
  [OK] .mcp.json (present but needs path fix -- see above)
  [OK] skills/ directory (recall/, save/)
  [OK] README.md
  [ ]  homepage field in plugin.json
  [ ]  repository field in plugin.json
  [ ]  MCP server uses ${CLAUDE_PLUGIN_ROOT} (currently hardcoded ${HOME})
  [ ]  Public GitHub repo for the plugin
  [ ]  Plugin validated with: claude plugin validate .

---

## Recommended Launch Sequence

Phase 1 (self-hosted, no Anthropic review needed):
  1. Fix MCP server bundling
  2. Create public GitHub repo: labyrinth-analytics/loreconvo
  3. Create marketplace repo: labyrinth-analytics/claude-plugins
  4. Add marketplace.json listing LoreConvo (and LoreDocs when ready)
  5. Test: /plugin marketplace add labyrinth-analytics/claude-plugins
  6. Share with early adopters via GitHub README / social media
  7. Update marketplace_listing.md with the install command

Phase 2 (official Anthropic marketplace):
  1. Collect feedback from Phase 1 users
  2. Polish docs, fix any issues
  3. Submit via https://clau.de/plugin-directory-submission
  4. Wait for Anthropic review
  5. Once approved, update install instructions everywhere

---

## Key URLs

  Submission form:     https://clau.de/plugin-directory-submission
  Claude.ai submit:    https://claude.ai/settings/plugins/submit
  Console submit:      https://platform.claude.com/plugins/submit
  Plugin docs:         https://code.claude.com/docs/en/plugins
  Marketplace docs:    https://code.claude.com/docs/en/plugin-marketplaces
  Official catalog:    https://claude.com/plugins
  Official GitHub:     https://github.com/anthropics/claude-plugins-official
