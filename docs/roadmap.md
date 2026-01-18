# Roadmap

[← Back to Index](index.md) | [Contributing →](contributing.md)

---

## Vision

Dossier aims to be the **decentralized alternative to Jira** — a data-modeled, offline-first project tracker that works across repos, teams, and organizations without vendor lock-in.

## Current State (v0.1.x)

Dossier currently provides:

- ✅ **13 data models** — Projects, Versions, Docs, Languages, Branches, Dependencies, Contributors, Issues, PRs, Releases, Components, Entities, Links
- ✅ **Cache-merge sync** — GitHub repos, users, and organizations with offline-first SQLite
- ✅ **Fixed-layout TUI** — 11 tabs with consistent navigation across all projects
- ✅ **Linkable entities** — Every data model element navigable in the component tree
- ✅ **Content viewer** — Click tree items to preview docs, issues, and PRs inline
- ✅ **Entity graphs** — Auto-build scoped entity graphs with disambiguation
- ✅ **Vim-style commands** — `:q`, `:r`, `:s`, `:filter`, `:sort`, `:clear` in command bar
- ✅ **Headless interfaces** — CLI, TUI dashboard, REST API
- ✅ **Portable exports** — `.dossier` YAML files for sharing
- ✅ **Database migrations** — Alembic-managed schema evolution

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

## Phase 2: Jira Replacement Features

**Goal**: Full-featured issue/project tracking to replace proprietary tools.

### 2.1 Issue Management

- **Local Issue Creation** - Create issues without GitHub:
  - Track tasks in non-GitHub projects
  - Offline issue creation, sync later
  - Custom fields per workspace

- **Cross-Project Issues** - Issues spanning multiple repos:
  - "Epic" style groupings
  - Dependencies between issues
  - Unified backlog view

### 2.2 Board Views (TUI)

- **Kanban Tab** - Card-based view:
  - Columns: Backlog → In Progress → Review → Done
  - Drag-and-drop with keyboard
  - Swimlanes by project/assignee

- **Sprint Planning** - Time-boxed iterations:
  - Sprint backlog management
  - Velocity tracking
  - Burndown in ASCII

### 2.3 Reporting

- **Activity Dashboard** - Cross-project metrics:
  - Open issues/PRs trend
  - Release cadence
  - Contributor activity

- **Export Reports** - Generate summaries:
  - Weekly digest (Markdown/HTML)
  - Sprint retrospective data
  - Stakeholder updates

---

## Phase 3: Multi-Platform & Extensibility

**Goal**: Beyond GitHub — support other forges and custom sources.

### 3.1 Additional Sources

- **GitLab** - Full GitLab API integration
- **Bitbucket** - Bitbucket Cloud/Server
- **Gitea/Forgejo** - Self-hosted forges
- **Local Git** - Parse `.git` directly (no remote needed)

### 3.2 Plugin Architecture

- **Custom Parsers** - Add your own sources:
  - Jira import (read-only migration)
  - Notion databases
  - Linear export

- **Custom Exporters** - Output formats:
  - Obsidian-compatible Markdown
  - CSV for spreadsheet fans
  - JSON-LD for linked data

### 3.3 Sync Backends

- **PostgreSQL** - Shared team cache
- **SQLite over Syncthing** - Peer-to-peer sync
- **Git-based sync** - Commit cache to repo

---

## Phase 4: Team Collaboration

**Goal**: Optional multi-user features for teams (still works fully offline for individuals).

### 4.1 Shared Workspaces

- **Team Cache** - Optional shared PostgreSQL backend
- **Conflict Resolution** - Merge strategies for concurrent edits
- **Audit Log** - Who changed what, when

### 4.2 Integrations

- **VS Code Extension** - Quick project lookup from editor
- **Alfred/Raycast** - Launcher integration for macOS
- **Slack/Discord Bot** - Query projects from chat
- **CLI Completion** - Fish/Zsh/Bash completions

### 4.3 Knowledge Base

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

1. � **Multi-Org Workspaces** - Track projects across GitHub orgs
2. ✅ **Dependency Graph** - Auto-link from manifests (implemented)
3. 🟡 **Kanban Board Tab** - Card-based issue view in TUI
4. 🟡 **GitLab Support** - Second forge integration
5. 🟢 **Sprint Planning** - Time-boxed iteration support

