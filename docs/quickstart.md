# Quickstart Guide

[← Back to Index](index.md) | [Overview](overview.md) | [Architecture →](architecture.md)

---

Get Dossier up and running in under 5 minutes.

## Prerequisites

- Python 3.13 or higher
- [uv](https://github.com/astral-sh/uv) package manager

### Installing uv

```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell)
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

## Installation

### From Source

```bash
# Clone the repository
git clone https://github.com/your-org/dossier.git
cd dossier

# Install dependencies
uv sync
```

### Verify Installation

```bash
uv run dossier --version
# Output: dossier, version 0.1.0
```

## Interfaces

Dossier provides three ways to interact:

| Interface | Command | Best For |
|-----------|---------|----------|
| **TUI Dashboard** | `uv run dossier dashboard` | Interactive project tracking |
| **Command Explorer** | `uv run dossier tui` | Discovering CLI commands |
| **CLI** | `uv run dossier <command>` | Scripting and automation |

## TUI Dashboard

Launch the full-featured terminal dashboard:

```bash
uv run dossier dashboard
```

### Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `q` | Quit |
| `r` | Refresh project list |
| `s` | Sync selected project(s) |
| `a` | Add new project |
| `o` | Open GitHub in browser |
| `d` | Delete selected project(s) |
| `/` | Focus search |
| `f` | Cycle filter (All → Synced → Unsynced) |
| `?` | Show help |
| `Tab` | Navigate panels |

### Multi-Selection

| Key | Action |
|-----|--------|
| `Ctrl+Click` | Toggle select clicked project |
| `Shift+Click` | Toggle select clicked project |
| `Space` | Toggle select current project |
| `Ctrl+A` | Select all visible projects |
| `Escape` | Clear selection |

Selected projects are highlighted. Use with Sync (`s`) or Delete (`d`) for batch operations.

The dashboard shows:
- **Project List** - Searchable list with sync status (🔄/○) and star counts
- **Dossier Tab** - Formatted project overview with component tree (languages, dependencies, contributors)
- **Details Tab** - Project metadata, clickable GitHub links, timestamps
- **Documentation Tab** - Parsed documentation sections
- **Languages Tab** - Language breakdown with file extensions and encoding
- **Branches Tab** - Repository branches with default/protected status, latest commits
- **Dependencies Tab** - Clickable links to PyPI/npm packages
- **Contributors Tab** - Top contributors with clickable GitHub profile links
- **Issues Tab** - Clickable issue numbers linking to GitHub
- **Pull Requests Tab** - PRs with merge status and diff stats
- **Releases Tab** - Version releases with tags
- **Components Tab** - Child project relationships

## GitHub Authentication Setup

**Important**: Without authentication, GitHub API is limited to **60 requests/hour**. With a token, you get **5000 requests/hour**.

### Step 1: Create a Personal Access Token

1. Go to [GitHub Settings → Developer settings → Personal access tokens → Tokens (classic)](https://github.com/settings/tokens)
2. Click **"Generate new token (classic)"**
3. Add a note: "Dossier CLI"
4. Select scopes:
   - ✅ `public_repo` - Access public repositories
   - ✅ `repo` - Access private repositories (optional)
5. Click **"Generate token"**
6. **Copy the token immediately** (you won't see it again!)

### Step 2: Set Environment Variable

```bash
# Linux/macOS - add to ~/.bashrc, ~/.zshrc, or ~/.profile
export GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxx

# Windows PowerShell - add to $PROFILE
$env:GITHUB_TOKEN = "ghp_xxxxxxxxxxxxxxxxxxxx"

# Windows Command Prompt
set GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxx

# Or pass directly to commands
uv run dossier github sync-user myuser --token ghp_xxx
```

### Step 3: Verify Setup

```bash
uv run dossier github sync-user yourname --limit 1
```

Look for the rate limit indicator:
- ❌ `📊 Rate limit: 59/60 remaining` - No token (limited)
- ✅ `📊 Rate limit: 4999/5000 remaining` - Token active!

## CLI Quick Reference

### Project Management

```bash
# List all projects
uv run dossier projects list
uv run dossier projects list -v           # Verbose with details
uv run dossier projects list --synced     # Only GitHub-synced

# Add a project manually
uv run dossier projects add my-project -d "Description"

# Show project details
uv run dossier projects show owner/repo

# Rename or remove
uv run dossier projects rename old-name new-name
uv run dossier projects remove my-project -y
```

### GitHub Sync

```bash
# Sync a single repository
uv run dossier github sync https://github.com/astral-sh/uv
uv run dossier github sync astral-sh/uv                    # Short form

# Sync all repos from a user
uv run dossier github sync-user astral-sh
uv run dossier github sync-user myuser --language python   # Filter by language

# Sync all repos from an organization
uv run dossier github sync-org microsoft --limit 20
uv run dossier github sync-org myorg --batch-size 3        # Smaller batches

# Force re-sync (ignore "recently synced" check)
uv run dossier github sync-user myuser --force

# Get repo info without syncing
uv run dossier github info https://github.com/pallets/click

# Search GitHub
uv run dossier github search "fastapi"
uv run dossier github search "language:python topic:cli" --limit 10
```

### Query Documentation

```bash
# Query at different detail levels
uv run dossier query my-project --level summary
uv run dossier query my-project --level overview
uv run dossier query my-project --level detailed
uv run dossier query my-project --level technical

# Filter by section type or search
uv run dossier query my-project --section-type readme
uv run dossier query my-project --search "installation"
```

### Project Components

```bash
# Add a subcomponent relationship
uv run dossier components add parent-project child-project
uv run dossier components add myorg myorg/repo --type component

# List components
uv run dossier components list parent-project
uv run dossier components list parent-project --recursive

# Remove relationship
uv run dossier components remove parent-project child-project
```

### Development Utilities

```bash
# Database status
uv run dossier dev status

# Reset database (delete all data)
uv run dossier dev reset -y

# Clear specific data
uv run dossier dev clear --projects
uv run dossier dev clear --docs
uv run dossier dev clear --all -y

# Seed example data
uv run dossier dev seed --example

# Optimize database
uv run dossier dev vacuum

# Export data
uv run dossier dev dump --format json -o backup.json
```

### Export Dossier Files

Generate standardized `.dossier` project overview files:

```bash
# Export a project to .dossier file
uv run dossier export dossier owner/repo

# Preview dossier without saving
uv run dossier export show owner/repo

# Export all projects to a directory
uv run dossier export all -d ./exports

# Create a template .dossier file for manual editing
uv run dossier init myproject
```

### Database Migrations

Manage database schema changes with Alembic:

```bash
# Apply all pending migrations
uv run dossier db upgrade

# Show current migration revision
uv run dossier db current

# Show migration history
uv run dossier db history

# Create a new migration
uv run dossier db revision "add new feature"

# Rollback one migration
uv run dossier db downgrade

# Stamp database as current version (skip migrations)
uv run dossier db stamp head
```

## API Server

Start the REST API:

```bash
uv run dossier serve --reload
```

Access:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **Health Check**: http://localhost:8000/health

### API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | API info |
| GET | `/health` | Health check |
| GET | `/projects` | List projects |
| POST | `/projects` | Create project |
| GET | `/projects/{name}` | Get project |
| GET | `/docs/{name}?level=overview` | Query documentation |

## Example Workflow

### 1. Set up GitHub token (one-time)

```bash
export GITHUB_TOKEN=ghp_xxxxxxxxxxxx
```

### 2. Sync an organization

```bash
uv run dossier github sync-org quaternionmedia
```

### 3. Browse in the dashboard

```bash
uv run dossier dashboard
```

### 4. Query from CLI

```bash
uv run dossier projects list -v
uv run dossier query quaternionmedia/somerepo --level summary
```

## Troubleshooting

### Rate limit errors

```
⚠️  Rate limit hit. Run again to continue from where you left off.
```

**Solution**: Set `GITHUB_TOKEN` environment variable (see above).

### "Project not found"

```bash
# Check if project exists
uv run dossier projects list | grep project-name
```

### Database issues

```bash
# Check status
uv run dossier dev status

# Reset if needed
uv run dossier dev reset -y
```

### Timezone errors

If you see `TypeError: can't subtract offset-naive and offset-aware datetimes`, update to the latest version.

## Next Steps

- [Understand the Architecture](architecture.md)
- [Learn how to Contribute](contributing.md)
- [Read the full Overview](overview.md)
