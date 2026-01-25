# Roadmap

[← Back to Index](index.md) | [Contributing →](contributing.md)

---

## Vision

Dossier aims to be the **decentralized alternative to Jira** — a data-modeled, offline-first project tracker that works across repos, teams, and organizations without vendor lock-in.

## Current State (v0.1.x)

Dossier currently provides:

- ? **Core data models** ? Projects, Versions, Docs, Languages, Branches, Dependencies, Contributors, Issues, PRs, Releases, Components, Deltas, Entities, Links
- ✅ **Cache-merge sync** — GitHub repos, users, and organizations with offline-first SQLite
- ✅ **Fixed-layout TUI** — Main tabs + project subtabs with consistent navigation across all projects
- ✅ **Linkable entities** — Every data model element navigable in the component tree
- ✅ **Content viewer** — Click tree items to preview docs, issues, and PRs inline
- ✅ **Entity graphs** — Auto-build scoped entity graphs with disambiguation
- ✅ **Vim-style commands** — `:q`, `:r`, `:s`, `:filter`, `:sort`, `:clear` in command bar
- ✅ **Headless interfaces** — CLI, TUI dashboard, REST API
- ✅ **Portable exports** — `.dossier` YAML files for sharing
- ✅ **Database migrations** — Alembic-managed schema evolution
- ✅ **Settings overlay** — Press `` ` `` to configure theme, default tab, sync preferences
- ✅ **Persistent config** — Auto-save settings to `~/.dossier/config.json`

---

## Phase 1: Cross-Domain Unification

**Goal**: First-class support for tracking projects across multiple orgs, teams, and sources.

### 1.1 Multi-Source Sync

- **Unified Project Registry** - Single view across:
  - Multiple GitHub orgs (`org-a/*`, `org-b/*`, `org-c/*`)
  - Personal repos mixed with work repos
  - Non-GitHub sources (GitLab, local git, manual)

- **Smart Deduplication** - Handle forks and mirrors:
  - Detect upstream/fork relationships
  - Merge metadata intelligently
  - Track divergence

### 1.2 Team Workspaces

- **Workspace Model** - Logical groupings:
  - "Platform Team" → repos across 3 orgs
  - "Q1 Initiative" → cross-team project set
  - "Personal" → side projects and experiments

- **Workspace Sync** - Batch operations per workspace

### 1.3 Dependency Graph

- ✅ **Auto-Link Dependencies** - Parse manifests:
  - `pyproject.toml`, `package.json`, `Cargo.toml`
  - Create `ProjectComponent` links automatically
  - Visualize in TUI component tree

---

## Phase 2: Foundation & Delta Management

**Goal**: Eliminate technical debt and complete the delta feature as the core local tracking mechanism.

### 2.1 Centralize Database Configuration

- [ ] Create single `src/dossier/database.py` module with unified engine/session factory
- [ ] Update CLI, API, and TUI to use centralized module
- [ ] Support `DOSSIER_DB_PATH` environment variable override
- [ ] Fix hardcoded `sqlite:///dossier.db` to match documented `~/.dossier/dossier.db`

### 2.2 Unify Configuration

- [ ] Add `github_token` to DossierConfig (with `GITHUB_TOKEN` env var fallback)
- [ ] Add `database_path` to DossierConfig
- [ ] Document all configuration options in one place
- [ ] Create settings migration for old configs

### 2.3 Complete Delta CLI & API

- **CLI Commands**:
  - `dossier deltas list [project]`
  - `dossier deltas create <project> <name> --title "Title"`
  - `dossier deltas advance <project> <name> [--note "Note"]`
  - `dossier deltas link <project> <name> --issue 123`
  - `dossier deltas show <project> <name>`

- **API Endpoints**:
  - `GET /projects/{name}/deltas`
  - `POST /projects/{name}/deltas`
  - `PUT /projects/{name}/deltas/{delta_name}/advance`
  - `POST /projects/{name}/deltas/{delta_name}/links`

### 2.4 Entity System Consolidation

- [ ] Integrate DeltaLink with Entity/Link system (create both when linking)
- [ ] Add delta entity type to autolinker
- [ ] Create unified "get all links for X" query helper
- [ ] Resolve Project-Delta identity: Deltas are NOT separate Projects
- [ ] Document all entity name patterns in one reference
- [ ] Create helper functions for parsing entity names

---

## Phase 3: Interface Parity & Jira Features

**Goal**: CLI, API, and TUI have matching capabilities; add board views for project tracking.

### 3.1 Interface Parity

- **API Expansion**:
  - Add `sync-user` and `sync-org` endpoints
  - Add entity graph endpoints
  - Add batch operations endpoint

- **CLI Enhancement**:
  - Add entity query commands
  - Add workspace/filter commands

- **TUI Refinement**:
  - Complete delta detail view
  - Add delta creation modal
  - Implement delta-to-entity navigation

### 3.2 Board Views (TUI)

- **Kanban Tab** - Card-based view:
  - Columns: Backlog → In Progress → Review → Done
  - Drag-and-drop with keyboard
  - Swimlanes by project/assignee

- **Sprint Planning** - Time-boxed iterations:
  - Sprint backlog management
  - Velocity tracking
  - Burndown in ASCII

### 3.3 Issue Management

- **Local Issue Creation** - Create issues without GitHub:
  - Track tasks in non-GitHub projects
  - Offline issue creation, sync later
  - Custom fields per workspace

- **Cross-Project Issues** - Issues spanning multiple repos:
  - "Epic" style groupings
  - Dependencies between issues
  - Unified backlog view

### 3.4 Reporting

- **Activity Dashboard** - Cross-project metrics:
  - Open issues/PRs trend
  - Release cadence
  - Contributor activity

- **Export Reports** - Generate summaries:
  - Weekly digest (Markdown/HTML)
  - Sprint retrospective data
  - Stakeholder updates

---

## Phase 4: Multi-Platform & Extensibility

**Goal**: Beyond GitHub — support other forges and custom sources.

### 4.1 Additional Sources

- **GitLab** - Full GitLab API integration
- **Bitbucket** - Bitbucket Cloud/Server
- **Gitea/Forgejo** - Self-hosted forges
- **Local Git** - Parse `.git` directly (no remote needed)

### 4.2 Plugin Architecture

- **Custom Parsers** - Add your own sources:
  - Jira import (read-only migration)
  - Notion databases
  - Linear export

- **Custom Exporters** - Output formats:
  - Obsidian-compatible Markdown
  - CSV for spreadsheet fans
  - JSON-LD for linked data

### 4.3 Sync Backends

- **PostgreSQL** - Shared team cache
- **SQLite over Syncthing** - Peer-to-peer sync
- **Git-based sync** - Commit cache to repo

### 4.4 Workspace Model

- Add Workspace table for logical project groupings
- Project-Workspace relationships (many-to-many)
- Workspace-scoped views and filters
- Cross-project deltas spanning multiple repositories

---

## Phase 5: Team Collaboration

**Goal**: Optional multi-user features for teams (still works fully offline for individuals).

### 5.1 Shared Workspaces

- **Team Cache** - Optional shared PostgreSQL backend
- **Conflict Resolution** - Merge strategies for concurrent edits
- **Audit Log** - Who changed what, when

### 5.2 Integrations

- **VS Code Extension** - Quick project lookup from editor
- **Alfred/Raycast** - Launcher integration for macOS
- **Slack/Discord Bot** - Query projects from chat
- **CLI Completion** - Fish/Zsh/Bash completions

### 5.3 Knowledge Base

- **Notes & Annotations** - Add notes to any entity
- **Tags & Labels** - Custom taxonomy beyond GitHub labels
- **Full-Text Search** - Search across all cached content
- **Bookmarks** - Quick access to important items

---

## Contributing to the Roadmap

We welcome contributions! See [contributing.md](contributing.md) for guidelines.

### Priority Markers

| Priority | Meaning |
|----------|---------|
| 🔴 High | Core functionality, blocking issues |
| 🟡 Medium | Important enhancements |
| 🟢 Low | Nice-to-have improvements |
| ⚪ Future | Long-term vision items |

### Current Priorities

1. 🔴 **Centralize Database Config** - Eliminate hardcoded paths and duplicate initialization
2. 🔴 **Delta CLI/API Commands** - Complete the delta feature with full interface support
3. 🟡 **Entity System Consolidation** - Unify DeltaLink with Entity/Link system
4. 🟡 **Interface Parity** - Match capabilities across CLI, API, and TUI
5. ✅ **Dependency Graph** - Auto-link from manifests (implemented)
6. ✅ **Entity Graphs** - Full entity linking with disambiguation (implemented)
7. 🟡 **Kanban Board Tab** - Card-based issue view in TUI
8. 🟢 **GitLab Support** - Second forge integration

