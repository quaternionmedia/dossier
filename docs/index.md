# Dossier Documentation

> A documentation standardization tool that auto-parses project docs and provides queryable, structured access at multiple detail levels.

## Quick Links

| Document | Description |
|----------|-------------|
| [Quickstart](quickstart.md) | Get running in 5 minutes |
| [Overview](overview.md) | Features and concepts |
| [Architecture](architecture.md) | System design and internals |
| [Roadmap](roadmap.md) | Future features and vision |
| [Contributing](contributing.md) | Development guide |

## What is Dossier?

Dossier aggregates documentation from your projects (especially GitHub repositories) and provides:

- **Multi-level queries** - Summary, overview, detailed, or technical views
- **TUI Dashboard** - Interactive terminal interface for browsing projects
- **GitHub Integration** - Bulk sync users, orgs, or individual repos
- **REST API** - Programmatic access for integrations
- **CLI** - Scriptable command-line interface

## Technology Stack

| Layer | Technology |
|-------|------------|
| Package Manager | [uv](https://github.com/astral-sh/uv) |
| CLI Framework | [Click](https://click.palletsprojects.com/) |
| TUI Dashboard | [Textual](https://textual.textualize.io/) |
| Command Explorer | [Trogon](https://github.com/Textualize/trogon) |
| API Framework | [FastAPI](https://fastapi.tiangolo.com/) |
| ORM | [SQLModel](https://sqlmodel.tiangolo.com/) |
| Database | SQLite |
| HTTP Client | [httpx](https://www.python-httpx.org/) |
| Testing | pytest, respx |

## Key Features

### 🖥️ TUI Dashboard
Full-featured terminal UI with project browser, 10 detail tabs, documentation viewer, filtering, and sync status.

```bash
uv run dossier dashboard
```

### 🔗 GitHub Integration
Sync repositories with intelligent batching, rate limit handling, and incremental updates.

```bash
uv run dossier github sync-user username
uv run dossier github sync-org orgname
```

### 📊 Documentation Queries
Query parsed documentation at different detail levels with filtering.

```bash
uv run dossier query project-name --level summary
```

### 🏗️ Project Components
Model parent-child relationships between projects for hierarchical documentation.

```bash
uv run dossier components add parent child
```

## Getting Started

### 1. Install

```bash
git clone https://github.com/your-org/dossier.git
cd dossier
uv sync
```

### 2. Set up GitHub Token (recommended)

```bash
export GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxx
```

Without a token: 60 requests/hour. With token: 5000 requests/hour.

See [Quickstart - GitHub Authentication](quickstart.md#github-authentication-setup) for detailed setup.

### 3. Sync some projects

```bash
uv run dossier github sync-user your-username
```

### 4. Launch the dashboard

```bash
uv run dossier dashboard
```

## Interfaces

| Interface | Command | Description |
|-----------|---------|-------------|
| Dashboard | `uv run dossier dashboard` | Interactive TUI with project browser |
| Explorer | `uv run dossier tui` | Interactive command explorer |
| CLI | `uv run dossier --help` | Traditional command line |
| API | `uv run dossier serve` | REST API server |

## Project Structure

```
dossier/
├── src/dossier/
│   ├── cli.py           # Click commands
│   ├── api/main.py      # FastAPI application
│   ├── models/schemas.py # SQLModel data models
│   ├── parsers/         # Documentation parsers
│   │   ├── base.py      # Base parser
│   │   └── github.py    # GitHub API client
│   └── tui/app.py       # Textual dashboard
├── tests/               # pytest test suite
├── docs/                # This documentation
└── pyproject.toml       # Project configuration
```

## Development

```bash
# Run tests
uv run pytest

# Run with coverage
uv run pytest --cov

# Start dev server
uv run dossier serve --reload

# Check database status
uv run dossier dev status
```

## License

MIT License - See LICENSE file for details.
