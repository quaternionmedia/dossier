# Overview

[← Back to Index](index.md) | [Quickstart](quickstart.md) | [Architecture →](architecture.md)

---

## What is Dossier?

Dossier is a documentation standardization tool that:

1. **Aggregates** documentation from multiple sources (GitHub repos, local files)
2. **Parses** and structures content into queryable data models
3. **Provides** consistent access at multiple detail levels
4. **Presents** information through CLI, TUI, and API interfaces

## Core Concepts

### Projects

A **Project** is the primary unit of organization. Projects can represent:

- GitHub repositories
- Local codebases
- Documentation collections
- Organizational units (containing other projects)

```python
class Project:
    name: str              # Unique identifier (e.g., "owner/repo")
    description: str       # Brief description
    version: str           # Current version
    github_url: str        # Source repository URL
    github_stars: int      # Star count (if GitHub)
    last_synced: datetime  # Last GitHub sync timestamp
```

### Documentation Sections

**DocumentationSection** represents parsed content from a project:

```python
class DocumentationSection:
    project_id: int
    section_type: str      # readme, contributing, api, changelog, etc.
    title: str
    content: str           # Full content
    summary: str           # Brief summary
    detail_level: DetailLevel  # summary, overview, detailed, technical
```

### Detail Levels

Query documentation at the appropriate depth:

| Level | Use Case | Content |
|-------|----------|---------|
| `summary` | Quick scan | 1-2 sentence description |
| `overview` | Understanding | Key features and concepts |
| `detailed` | Learning | Full documentation with examples |
| `technical` | Implementation | API signatures, internals |

### Project Components

**ProjectComponent** models parent-child relationships:

```python
class ProjectComponent:
    parent_id: int         # Parent project
    child_id: int          # Child project
    component_type: str    # submodule, dependency, component
```

Use cases:
- Organizations containing repositories
- Monorepos with multiple packages
- Dependencies and relationships

## Interfaces

### TUI Dashboard

The **Textual**-based dashboard provides:

- **Project List** - Searchable, filterable list of all projects
- **Filter Bar** - Filter by sync status (All/Synced/Unsynced), sort by stars
- **Detail Panel** - Tabbed view with 10 information tabs:
  - Details, Documentation, Languages, Branches, Dependencies, Contributors, Issues, Pull Requests, Releases, Components
- **Languages Tab** - Language breakdown with file extensions and encoding info
- **Branches Tab** - Repository branches with default/protected status and latest commit info
- **Dependencies Tab** - Parsed from pyproject.toml, package.json, requirements.txt
- **Contributors Tab** - Top contributors ranked by commit count
- **Issues Tab** - Open/closed issues with labels and authors
- **Pull Requests Tab** - PRs with merge status, branch info, and diff stats (+/-)
- **Releases Tab** - Version releases with tags, prerelease/draft status
- **Clickable Links** - URLs throughout open in browser
- **Sync Status** - Visual indicators for GitHub sync state
- **Quick Actions** - Keyboard shortcuts (s=sync, r=refresh, f=filter, o=open GitHub, q=quit)

```bash
uv run dossier dashboard
```

### Command Explorer

The **Trogon**-based explorer provides:

- Interactive command discovery
- Parameter input forms
- Command preview and execution

```bash
uv run dossier tui
```

### CLI

Traditional command-line for scripting:

```bash
uv run dossier projects list
uv run dossier github sync owner/repo
uv run dossier query project --level overview
```

### REST API

FastAPI server for programmatic access:

```bash
uv run dossier serve --reload
# Access at http://localhost:8000/docs
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

## Data Storage

### SQLite Database

Projects are stored in `~/.dossier/dossier.db`:

```
~/.dossier/
├── dossier.db          # SQLite database
└── logs/               # Optional log files
```

### Tables

| Table | Purpose |
|-------|---------|
| `project` | Core project records |
| `documentsection` | Parsed documentation |
| `project_component` | Parent-child relationships |
| `project_language` | Language breakdown with extensions/encoding |
| `project_branch` | Repository branches with commit info |
| `project_dependency` | Project dependencies |
| `project_contributor` | Top contributors |
| `project_issue` | GitHub issues |
| `project_pull_request` | Pull requests with merge/diff stats |
| `project_release` | Version releases with tags |

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

## Workflow Examples

### Personal Portfolio

```bash
# Sync all your repos
export GITHUB_TOKEN=ghp_xxx
uv run dossier github sync-user yourusername

# Browse in dashboard
uv run dossier dashboard

# Query specific project
uv run dossier query yourusername/project --level overview
```

### Organization Audit

```bash
# Sync organization
uv run dossier github sync-org myorg --limit 100

# List by stars
uv run dossier projects list -v --sort stars

# Export for reporting
uv run dossier dev dump -o org-audit.json
```

### Documentation Aggregation

```bash
# Sync multiple sources
uv run dossier github sync pallets/flask
uv run dossier github sync pallets/click
uv run dossier github sync pallets/jinja

# Create parent project
uv run dossier projects add pallets -d "Pallets Projects"

# Add relationships
uv run dossier components add pallets pallets/flask
uv run dossier components add pallets pallets/click
uv run dossier components add pallets pallets/jinja

# View hierarchy
uv run dossier components list pallets --recursive
```

## Next Steps

- [Quickstart Guide](quickstart.md) - Installation and first steps
- [Architecture](architecture.md) - System design details
- [Contributing](contributing.md) - Development workflow
