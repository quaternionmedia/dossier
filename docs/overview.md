# Overview

[← Back to Index](index.md) | [Quickstart](quickstart.md) | [Workflows →](workflows.md)

---

## What is Dossier?

Dossier is a **decentralized project tracking system** built for modern, distributed teams:

1. **Replaces proprietary trackers** — Unified view of issues, PRs, releases, dependencies across all your projects
2. **Cache-merge architecture** — Work offline, sync incrementally, merge changes from multiple sources
3. **Data-modeled** — 12 structured SQLModel schemas (not arbitrary fields) for consistent querying
4. **Cross-domain** — Track projects across GitHub orgs, teams, repos — even non-GitHub sources
5. **Fixed-layout TUI** — Consistent interface across all projects for keyboard-driven speed

## Use Cases

### Replace Jira / Linear / Proprietary Trackers

Stop paying per-seat for bloated web UIs. Dossier gives you:
- Issues, PRs, releases, versions — all linked and navigable
- Works offline (airplane mode, VPN-free)
- Export everything to portable `.dossier` YAML files
- No vendor lock-in, no subscription

### Cross-Team / Cross-Org Visibility

Working across multiple GitHub orgs or teams? Dossier unifies:
- `org-a/frontend`, `org-b/backend`, `org-c/infra` — one dashboard
- Shared dependencies tracked automatically
- Consistent layouts so context-switching costs nothing

### Offline-First for Remote/Distributed Teams

Cache-merge architecture means:
- Full local SQLite database — query without network
- Sync on your schedule, not real-time polling
- Merge upstream changes without losing local state

## Core Concepts

### Data-Modeled Entities

Every piece of information in Dossier has a **typed schema** — not arbitrary JSON. This enables:
- SQL queries across your entire project portfolio
- Consistent exports and migrations
- Reliable integrations via API

### The 12 Data Models

| Model | Purpose | Linkable |
|-------|---------|----------|
| `Project` | Core entity — repos, orgs, collections | ✔️ |
| `ProjectVersion` | Semver-parsed releases with metadata | ✔️ |
| `DocumentSection` | Parsed docs at multiple detail levels | ✔️ |
| `ProjectLanguage` | Language breakdown with extensions | ✔️ |
| `ProjectBranch` | Branches with commit info | ✔️ |
| `ProjectDependency` | Deps from manifests (pyproject, package.json) | ✔️ |
| `ProjectContributor` | Top contributors by commit count | ✔️ |
| `ProjectIssue` | Issues with state, labels, authors | ✔️ |
| `ProjectPullRequest` | PRs with merge status, diff stats | ✔️ |
| `ProjectRelease` | Releases with tags, prerelease flags | ✔️ |
| `ProjectComponent` | Parent-child project relationships | ✔️ |

### Fixed-Layout TUI

The TUI uses **consistent layouts** regardless of which project you're viewing:

```
┌───────────────────────────────────────────────────┐
│ Tab 1: Dossier    │ Overview with component tree      │
│ Tab 2: Details    │ Metadata, links, timestamps       │
│ Tab 3: Docs       │ Parsed documentation sections     │
│ Tab 4: Languages  │ Language breakdown + extensions   │
│ Tab 5: Branches   │ Branches with commit info         │
│ Tab 6: Deps       │ Dependencies from manifests       │
│ Tab 7: People     │ Contributors by commit count      │
│ Tab 8: Issues     │ Open/closed issues with labels    │
│ Tab 9: PRs        │ Pull requests with merge status   │
│ Tab 10: Releases  │ Version releases with tags        │
│ Tab 11: Links     │ Component relationships           │
└───────────────────────────────────────────────────┘
```

**Why fixed layouts?** You learn the positions once. After a week, you navigate by muscle memory — Tab-Tab-Tab to Dependencies, every project, every time.

### Cache-Merge Sync

Dossier doesn't poll or stream. It uses a **cache-merge** pattern:

1. **Cache** — All data stored locally in SQLite
2. **Sync** — On-demand fetch from upstream (GitHub, etc.)
3. **Merge** — New data merged into local cache

This means:
- ✔️ Works offline (airplane mode, VPN-free environments)
- ✔️ Fast reads (no network round-trips)
- ✔️ You control when to sync

## Interfaces (All Headless)

Dossier is **headless-first** — every feature works without a browser.

### TUI Dashboard

The **Textual**-based dashboard is the primary interface:

```bash
uv run dossier dashboard
```

- **Fixed tab layout** — Same positions, every project
- **Keyboard-driven** — `Tab`, `j/k`, `/search`, `s`ync, `q`uit
- **Component tree** — Navigate linked entities (docs, versions, issues, etc.)
- **Multi-select** — Batch sync/delete with `Space` or `Ctrl+A`

### CLI

Scriptable command-line for automation:

```bash
uv run dossier github sync-org myorg --limit 50
uv run dossier projects list --synced --format json
uv run dossier export all -d ./backups
```

### REST API

FastAPI server for integrations:

```bash
uv run dossier serve --reload
# Swagger UI at http://localhost:8000/docs
```

### Command Explorer

**Trogon**-based interactive discovery (if you forget CLI flags):

```bash
uv run dossier tui
```

## GitHub Integration

### Features

- **Single Repo Sync** - Sync individual repositories
- **User Sync** - Bulk sync all repos from a user
- **Org Sync** - Bulk sync all repos from an organization
- **Intelligent Batching** - Configurable batch sizes with delays
- **Rate Limit Handling** - Automatic detection and backoff
- **Incremental Sync** - Skip recently synced repos (unless forced)

### Authentication

GitHub API has strict rate limits:

| Auth Type | Rate Limit | Notes |
|-----------|------------|-------|
| No token | 60/hour | Shared across IP |
| Token | 5000/hour | Per-user |
| GitHub Actions | 1000/hour | GITHUB_TOKEN |

**Always configure a token for real usage**:

```bash
export GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxx
```

### Rate Limit Handling

Dossier tracks rate limits and provides feedback:

```
📊 Rate limit: 4832/5000 remaining (resets in 45m)
```

When limits are hit:
- Batch operations pause gracefully
- Clear messaging about when to retry
- Resume capability for partial syncs

## Data Storage (Local Cache)

### SQLite as Local Cache

All data stored locally in `~/.dossier/dossier.db`:

```
~/.dossier/
├── dossier.db          # SQLite cache (your data, your machine)
└── exports/            # Generated .dossier files
```

**Why SQLite?**
- Works offline — no network needed for reads
- Fast — indexed queries across thousands of projects
- Portable — copy the file to another machine
- No server — no Docker, no PostgreSQL, no setup

### 12 Data Tables

| Table | Purpose |
|-------|---------|
| `project` | Core project records |
| `project_version` | Semver-parsed versions |
| `documentsection` | Parsed documentation |
| `project_component` | Parent-child relationships |
| `project_language` | Language breakdown |
| `project_branch` | Branches with commits |
| `project_dependency` | Dependencies from manifests |
| `project_contributor` | Top contributors |
| `project_issue` | Issues with labels |
| `project_pull_request` | PRs with diff stats |
| `project_release` | Releases with tags |

### Management Commands

```bash
# View database stats
uv run dossier dev status

# Reset everything
uv run dossier dev reset -y

# Export data
uv run dossier dev dump -o backup.json

# Optimize storage
uv run dossier dev vacuum
```

## Parsing System

### Current Parsers

| Parser | Source | Extracts |
|--------|--------|----------|
| `GitHubParser` | GitHub API | Repo metadata, README, languages |
| `BaseParser` | Local files | README.md, docs/ folder |

### What Gets Parsed

From GitHub repositories:
- Repository metadata (name, description, stars, topics)
- README content (parsed as documentation section)
- Primary language and all language breakdown
- License information
- Recent activity timestamps

### Extensibility

Add custom parsers by implementing:

```python
class CustomParser:
    def parse(self, source: str) -> Project:
        """Parse source into a Project with DocumentationSections."""
        pass
```

## Quick Examples

### Sync and Browse

```bash
# Sync your GitHub repos
uv run dossier github sync-user YOUR_USERNAME

# Launch dashboard
uv run dossier dashboard
```

### Cross-Org Tracking

```bash
# Sync multiple orgs into one cache
uv run dossier github sync-org org-frontend
uv run dossier github sync-org org-backend
uv run dossier github sync-org org-infra

# One unified view
uv run dossier dashboard
```

### Offline Workflow

```bash
# Sync while online
uv run dossier github sync-user myusername

# Works offline (all reads from local cache)
uv run dossier dashboard
uv run dossier projects list
```

**For complete workflows with copy-paste commands, see [Workflows & Examples](workflows.md).**

## Next Steps

- [Workflows & Examples](workflows.md) — Copy-paste ready examples
- [Quickstart Guide](quickstart.md) — Installation and first steps
- [Architecture](architecture.md) — System design details
- [Extending Dossier](extending.md) — Customize for your needs
- [Contributing](contributing.md) — Development workflow
