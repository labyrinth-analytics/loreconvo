# Repository Strategy and Release Workflow

This document describes how ConvoVault and ProjectVault are developed, released,
and distributed as public Claude plugins.

---

## Repository Map

### Private (dev monorepo)
  labyrinth-analytics/side-hustle (PRIVATE -- this repo)

  Contains everything: source code, tests, docs, business notes, CLAUDE.md,
  revenue projections, skills, scripts. Never made public.

  ron_skills/
  |-- convovault/          Source code (Python package + CLI)
  |-- convovault-plugin/   Distributable plugin files (plugin.json, .mcp.json, skills/)
  |-- projectvault/        Source code (Python package)
  |-- projectvault-plugin/ Distributable plugin files
  |-- sql_query_optimizer/ Coming soon

### Public (distribution)
  labyrinth-analytics/convovault    (PUBLIC -- plugin + installable package)
  labyrinth-analytics/projectvault  (PUBLIC -- plugin + installable package)
  labyrinth-analytics/claude-plugins (PUBLIC -- marketplace catalog)

The public repos contain only what users need to install and use the products.
No business notes, no revenue docs, no internal TODOs.

---

## Three-Tier Distribution

Tier 1: Direct MCP (power users)
  User edits .claude/settings.json manually to add the uvx command.
  Requires: uv installed, familiarity with JSON config.
  Install command: add to settings.json (see each product's README)

Tier 2: Self-hosted marketplace (primary public launch)
  User runs: /plugin marketplace add labyrinth-analytics/claude-plugins
  Then:      /plugin install convovault@labyrinth-analytics-claude-plugins
  Requires:  Claude Code or Cowork with plugin support.
  This is the target for Phase 1.

Tier 3: Official Anthropic marketplace (future)
  Submit via https://clau.de/plugin-directory-submission
  After approval, install with: /plugin install convovault@claude-plugins-official
  This is the target for Phase 2 (post-feedback).

---

## One-Time GitHub Setup (Debbie does this manually)

### 1. Create the GitHub Organization (optional but recommended)

Go to github.com -> Settings -> Organizations -> New organization
  Name: labyrinth-analytics
  Plan: Free

Or use your personal account (github.com/debbie-wonderkitty) -- just replace
"labyrinth-analytics" with your GitHub username throughout.

### 2. Create the Public Repos

Create three new repositories (public, no auto-generated README):

  github.com/labyrinth-analytics/convovault
    Description:  Cross-surface persistent memory for Claude sessions
    Topics:       mcp, claude, claude-plugin, memory, ai-tools, mcp-server
    Website:      https://labyrinthanalyticsconsulting.com

  github.com/labyrinth-analytics/projectvault
    Description:  Searchable knowledge base for your AI projects
    Topics:       mcp, claude, claude-plugin, knowledge-management, ai-tools
    Website:      https://labyrinthanalyticsconsulting.com

  github.com/labyrinth-analytics/claude-plugins
    Description:  Claude plugin marketplace for Labyrinth Analytics tools
    Topics:       claude, claude-plugin, mcp, marketplace

### 3. Create the Marketplace Catalog Repo

In labyrinth-analytics/claude-plugins, create the file:
  .claude-plugin/marketplace.json

Content:
  {
    "name": "labyrinth-analytics-claude-plugins",
    "owner": {
      "name": "Labyrinth Analytics Consulting",
      "email": "debbie.wonderkitty@gmail.com"
    },
    "metadata": {
      "description": "Claude plugins from Labyrinth Analytics Consulting -- ConvoVault, ProjectVault, and more."
    },
    "plugins": [
      {
        "name": "convovault",
        "source": {
          "source": "github",
          "repo": "labyrinth-analytics/convovault",
          "ref": "v0.3.0"
        },
        "description": "Cross-surface persistent memory for Claude sessions.",
        "version": "0.3.0",
        "author": { "name": "Labyrinth Analytics Consulting" },
        "homepage": "https://github.com/labyrinth-analytics/convovault",
        "license": "MIT",
        "category": "productivity",
        "keywords": ["memory", "sessions", "context", "recall", "cross-surface"]
      },
      {
        "name": "projectvault",
        "source": {
          "source": "github",
          "repo": "labyrinth-analytics/projectvault",
          "ref": "v0.1.0"
        },
        "description": "Searchable knowledge base for your AI projects.",
        "version": "0.1.0",
        "author": { "name": "Labyrinth Analytics Consulting" },
        "homepage": "https://github.com/labyrinth-analytics/projectvault",
        "license": "MIT",
        "category": "productivity",
        "keywords": ["knowledge-management", "documents", "search", "ai-projects"]
      }
    ]
  }

### 4. Create a PyPI Account

Go to pypi.org -> Register
  Username: labyrinth-analytics (or your preferred name)
  Email:    debbie.wonderkitty@gmail.com

Generate an API token:
  pypi.org -> Account Settings -> API Tokens -> Add API token
  Scope: Entire account (for first upload) -- then switch to per-project tokens

Save the token in ~/.pypirc:
  [distutils]
    index-servers = pypi

  [pypi]
    repository = https://upload.pypi.org/legacy/
    username = __token__
    password = pypi-xxxxxxxxxxxxxxxxxxxx

### 5. Install Release Tools

pip install build twine

---

## Development Workflow (everyday)

1. Do all development in the private monorepo (this repo)
2. Run tests locally:
     cd ron_skills/convovault && python -m pytest tests/
     cd ron_skills/projectvault && python -m pytest tests/
3. Commit to private monorepo as usual
4. When ready to release, run the release script (see below)

---

## Release Workflow (when shipping a new version)

Step 1: Decide the version number
  Follow semantic versioning (semver.org):
    Patch (0.3.0 -> 0.3.1): bug fix, no new features
    Minor (0.3.0 -> 0.4.0): new feature, backward compatible
    Major (0.3.0 -> 1.0.0): breaking change or major milestone

Step 2: Make sure all tests pass
  cd ron_skills/convovault && python -m pytest tests/ -v
  cd ron_skills/projectvault && python -m pytest tests/ -v

Step 3: Run the release script
  cd ~/projects/side_hustle
  ./scripts/release.sh convovault 0.3.1

  The script will:
    a. Run tests
    b. Update version in plugin.json and pyproject.toml
    c. Commit the version bump to the private repo
    d. Push the plugin files to the public GitHub repo (labyrinth-analytics/convovault)
    e. Create a git tag v0.3.1 in the public repo
    f. Build the Python package
    g. Upload to PyPI (you will enter your token)

Step 4: Update the marketplace catalog
  Edit labyrinth-analytics/claude-plugins/.claude-plugin/marketplace.json
  Change "ref": "v0.3.1" for the convovault entry
  Commit and push to the catalog repo

Step 5: Test the install from scratch
  uvx convovault@0.3.1     (tests PyPI install)
  /plugin install convovault@labyrinth-analytics-claude-plugins  (tests marketplace)

Step 6: Announce (when you're ready)
  -- Update labyrinthanalyticsconsulting.com
  -- Post on LinkedIn / social
  -- Email early adopters

---

## GitHub Repo Settings (recommended)

For both labyrinth-analytics/convovault and labyrinth-analytics/projectvault:

  Settings -> General:
    - Enable Issues: YES (for user bug reports)
    - Enable Discussions: YES (for community Q&A)
    - Enable Sponsorships: YES (free money)
    - Delete branch on merge: YES

  Settings -> Branches:
    - Branch protection on "main":
      - Require status checks to pass (if you add CI later)
      - Do not allow force pushes

  Settings -> Security:
    - Enable Dependabot alerts: YES
    - Enable secret scanning: YES

  Releases tab:
    - Use GitHub Releases for each version (the release script creates tags;
      you can add release notes on GitHub.com)

---

## What the Public Repos Contain

Each public repo (convovault, projectvault) will have:

  .claude-plugin/
  |-- plugin.json          (plugin metadata -- name, version, description)
  .mcp.json                (MCP server config -- uses uvx)
  skills/                  (skill SKILL.md files)
  src/                     (Python package source -- same as the private monorepo's src/)
  pyproject.toml           (package definition for PyPI)
  README.md                (the polished user-facing README)
  CHANGELOG.md             (version history)
  LICENSE                  (MIT)

The public repos do NOT contain:
  - Tests (kept in private monorepo for now)
  - docs/PUBLISHING.md (internal)
  - docs/marketplace_listing.md (internal)
  - Revenue projections
  - CLAUDE.md instructions

---

## Notes for Ron (autonomous agent)

- NEVER run the release script -- releases require Debbie's review and PyPI credentials.
- DO update CHANGELOG.md as features are completed.
- DO keep pyproject.toml version in sync with plugin.json version.
- Tests live in the private monorepo (ron_skills/convovault/tests/ etc.) and stay there.
