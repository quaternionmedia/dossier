# Dossier Project Instructions

## Project Overview
Dossier is a documentation standardization tool that auto-parses project documentation and provides different levels of information through consistent, data-modeled queries.

## Tech Stack
- **Package Manager**: uv
- **API Framework**: FastAPI
- **CLI Framework**: Click + Trogon (TUI command explorer)
- **TUI Dashboard**: Textual
- **ORM/Models**: SQLModel
- **HTTP Client**: httpx (with retry/rate limit handling)
- **Testing**: pytest, pytest-asyncio, respx

## Project Structure
```
dossier/
├── src/
│   └── dossier/
│       ├── __init__.py
│       ├── cli.py          # Click CLI commands
│       ├── api/
│       │   ├── __init__.py
│       │   └── main.py     # FastAPI application
│       ├── models/
│       │   ├── __init__.py
│       │   └── schemas.py  # SQLModel data models
│       ├── parsers/
│       │   ├── __init__.py
│       │   ├── base.py     # Documentation parsers
│       │   ├── github.py   # GitHub API client
│       │   └── autolinker.py # Entity graph builder
│       └── tui/
│           ├── __init__.py
│           └── app.py      # Textual TUI dashboard
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_cli.py
│   ├── test_api.py
│   ├── test_github.py
│   ├── test_models.py
│   ├── test_parsers.py
│   └── test_tui.py
├── docs/
│   ├── index.md
│   ├── overview.md
│   ├── quickstart.md
│   ├── dashboard.md    # TUI dashboard guide
│   ├── workflows.md
│   ├── architecture.md
│   ├── extending.md
│   ├── contributing.md
│   └── roadmap.md
├── pyproject.toml
└── README.md
```

## Data Models

### Core Models (in schemas.py)
- **Project** - Main project entity with GitHub metadata and URL helper methods
- **ProjectVersion** - Semver-parsed releases with metadata
- **DocumentSection** - Parsed documentation content with levels
- **ProjectComponent** - Parent-child project relationships
- **ProjectLanguage** - Language breakdown with file_extensions and encoding
- **ProjectBranch** - Repository branches with commit info
- **ProjectDependency** - Dependencies from pyproject.toml, package.json, etc.
- **ProjectContributor** - Top contributors with commit counts
- **ProjectIssue** - Issues with state, labels, and authors
- **ProjectPullRequest** - PRs with merge status, branches, and diff stats
- **ProjectRelease** - Version releases with tags and prerelease status
- **Entity** - Named entities for graph linking
- **Link** - Relationships between entities

## Development Commands
- `uv run dossier` - Run CLI
- `uv run dossier dashboard` - Launch Textual TUI dashboard
- `uv run dossier tui` - Launch Trogon command explorer
- `uv run dossier serve --reload` - Run API server
- `uv run dossier dev status` - Show database stats
- `uv run dossier dev reset -y` - Reset database (recreates schema)
- `uv run dossier dev purge -p "test" -y` - Purge test projects from database
- `uv run pytest` - Run tests

## Testing Guidelines
- Tests use in-memory SQLite databases to avoid file creep
- Test fixtures are in `tests/conftest.py`
- After running tests, use `uv run dossier dev purge -p "test" -y` to clean up any test data
- The `pytest_configure` and `pytest_unconfigure` hooks automatically run dev purge
- **Name test projects with "test" in the name so they can be easily purged**
- Generate screenshots: `uv run pytest tests/test_tui.py --screenshots`

## GitHub Commands
- `uv run dossier github sync owner/repo` - Sync single repo
- `uv run dossier github sync-user username` - Sync all user repos
- `uv run dossier github sync-org orgname` - Sync all org repos
- `uv run dossier github search "query"` - Search repositories

## Export Commands
- `uv run dossier export dossier owner/repo` - Export .dossier file
- `uv run dossier export show owner/repo` - Preview dossier (no save)
- `uv run dossier export all -d ./exports` - Export all projects
- `uv run dossier init projectname` - Create template .dossier file

## Graph Commands (Entity Linking)
- `uv run dossier graph build owner/repo` - Build entity graph for one project
- `uv run dossier graph build-all` - Build graphs for all synced projects
- `uv run dossier graph stats` - Show graph statistics

### Entity Scoping Patterns
Entities are namespaced for disambiguation:
- **Global**: `lang/{language}`, `pkg/{package}` (same everywhere)
- **App-scoped**: `github/user/{username}` (same user across all repos)
- **Repo-scoped**: `{owner}/{repo}/branch/{name}`, `{owner}/{repo}/issue/{number}`, `{owner}/{repo}/pr/{number}`, `{owner}/{repo}/ver/v{version}`, `{owner}/{repo}/doc/{slug}`

## Database Migration Commands
- `uv run dossier db upgrade` - Apply pending migrations
- `uv run dossier db downgrade` - Rollback one migration
- `uv run dossier db current` - Show current revision
- `uv run dossier db history` - Show migration history
- `uv run dossier db revision "message"` - Create new migration
- `uv run dossier db stamp head` - Mark as current version

## Coding Conventions
- Use type hints for all function signatures
- Follow PEP 8 style guidelines
- Use SQLModel for all data models
- Implement CLI commands as Click groups/commands
- Use FastAPI dependency injection for database sessions
- Use httpx for HTTP requests with proper error handling
