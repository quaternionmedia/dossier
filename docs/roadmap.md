# Roadmap

[← Back to Index](index.md) | [Contributing →](contributing.md)

---

## Current State (v0.1.x)

Dossier currently provides:

- ✅ 10-tab TUI dashboard with comprehensive project views
- ✅ GitHub sync for repos, users, and organizations
- ✅ 11 data models (projects, docs, languages, branches, deps, contributors, issues, PRs, releases, components)
- ✅ Advanced filtering (sync status, stars sorting, full-text search)
- ✅ CLI, TUI command explorer, and REST API interfaces

---

## Phase 1: Project Abstraction & Linking

**Goal**: Enable meaningful connections between projects for portfolio analysis and dependency mapping.

### 1.1 Smart Project Linking

- **Dependency Graph** - Automatically link projects when one depends on another
  - Parse `pyproject.toml`, `package.json`, `requirements.txt`
  - Create `ProjectComponent` links for detected dependencies
  - Visualize dependency tree in TUI

- **Cross-Reference Detection** - Find related projects
  - Shared contributors across projects
  - Similar topics/languages
  - Common dependency patterns

- **Organization Grouping** - Auto-group by GitHub owner
  - Create parent "organization" projects automatically
  - Aggregate statistics (total stars, languages, activity)

### 1.2 Project Collections

- **Collections Model** - Group projects by custom criteria
  - "My Frontend Projects"
  - "Active Maintenance"
  - "Archived/Legacy"
  - "Learning/Experiments"

- **Smart Collections** - Auto-updating filters
  - "Stale Projects" (no commits in 6 months)
  - "Popular" (stars > threshold)
  - "Needs Attention" (open issues/PRs)

### 1.3 Activity Timeline

- **Unified Activity Feed** - Aggregate events across projects
  - Commits, PRs, releases, issues
  - Filter by project, time range, event type
  - TUI tab for activity timeline

---

## Phase 2: Analysis & Insights

**Goal**: Extract actionable intelligence from project data.

### 2.1 Portfolio Analytics

- **Technology Radar** - Language/framework usage over time
- **Contribution Patterns** - When/where you're most active
- **Project Health Scores** - Combined metrics (activity, issues, docs quality)
- **Growth Tracking** - Stars, forks, contributors over time

### 2.2 Documentation Quality

- **Coverage Analysis** - Detect missing docs (no README, no CONTRIBUTING, no API docs)
- **Freshness Scoring** - Flag outdated documentation
- **Consistency Checker** - Compare docs structure across projects
- **Template Suggestions** - Recommend doc templates based on project type

### 2.3 Maintenance Insights

- **Stale Dependency Detection** - Flag outdated dependencies
- **Security Alerts** - Integrate with GitHub security advisories
- **Issue Triage** - Categorize and prioritize open issues
- **PR Review Queue** - Aggregate pending reviews

---

## Phase 3: Enhanced Integration

**Goal**: Deeper GitHub integration and external platform support.

### 3.1 GitHub Enhancements

- **Webhooks Support** - Real-time sync on push/release/issue
- **GitHub Actions Status** - Track CI/CD pipeline health
- **Discussions** - Sync GitHub Discussions
- **Wiki Pages** - Parse and index wiki content
- **Code Search** - Index code for full-text search

### 3.2 Multi-Platform Support

- **GitLab** - Full GitLab API integration
- **Bitbucket** - Bitbucket API support
- **Local Git** - Parse local `.git` repos directly
- **Package Registries** - Pull metadata from PyPI, npm, crates.io

### 3.3 Export & Reports

- **Portfolio Report** - Generate PDF/HTML portfolio summary
- **Project Cards** - Generate shareable project summaries
- **Badge Generation** - Custom badges for README files
- **Changelog Generation** - Auto-generate changelogs from commits

---

## Phase 4: Collaboration & Sharing

**Goal**: Enable team usage and knowledge sharing.

### 4.1 Multi-User Support

- **User Accounts** - Optional authentication
- **Shared Databases** - PostgreSQL backend option
- **Team Collections** - Shared project groupings

### 4.2 Knowledge Base

- **Notes & Annotations** - Add notes to projects/sections
- **Tags & Labels** - Custom taxonomy
- **Search Everything** - Full-text search across all content
- **Bookmarks** - Quick access to important sections

### 4.3 Integration Ecosystem

- **VS Code Extension** - Quick project lookup
- **Alfred/Raycast** - Launcher integration
- **Slack/Discord Bot** - Project info in chat
- **Obsidian Plugin** - Link Dossier data to notes

---

## Contributing to the Roadmap

We welcome contributions to any roadmap item! See [contributing.md](contributing.md) for:

- How to propose new features
- Implementation guidelines
- Testing requirements
- Documentation standards

### Priority Markers

| Priority | Meaning |
|----------|---------|
| 🔴 High | Core functionality, blocking issues |
| 🟡 Medium | Important enhancements |
| 🟢 Low | Nice-to-have improvements |
| ⚪ Future | Long-term vision items |

### Current Priorities

1. 🔴 **Dependency Graph** - Auto-link projects from manifest files
2. 🔴 **Organization Grouping** - Auto-create parent projects for owners
3. 🟡 **Collections** - Custom project groupings
4. 🟡 **Activity Timeline** - Unified event feed
5. 🟢 **Portfolio Analytics** - Health scores and metrics

---

## Version Timeline

| Version | Target | Focus |
|---------|--------|-------|
| v0.1.x | Current | Core TUI, GitHub sync, 10 tabs |
| v0.2.0 | Q2 2025 | Project linking, collections |
| v0.3.0 | Q3 2025 | Analytics, documentation quality |
| v0.4.0 | Q4 2025 | Multi-platform, exports |
| v1.0.0 | 2026 | Stable API, collaboration features |

