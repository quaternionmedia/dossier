# Architecture

[← Back to Index](index.md) | [Overview](overview.md) | [Contributing →](contributing.md)

---

## Design Principles

### 1. Cache-Merge, Not Real-Time
Dossier uses an **offline-first, cache-merge** pattern:
- Local SQLite is the source of truth for reads
- Sync operations fetch upstream and merge into local cache
- No websockets, no polling, no real-time complexity

### 2. Data-Modeled, Not Schema-Free
Every entity has a **defined SQLModel schema**:
- Core tables with typed fields and relationships
- Foreign keys enforce data integrity
- Query with SQL, not arbitrary JSON paths

### 3. Fixed Layouts, Muscle Memory
The TUI uses **consistent layouts across all projects**:
 - Main tabs and project subtabs stay in fixed positions with the same keybindings
- Learn once, navigate any project blindfolded
- No per-project customization that breaks flow

### 4. Headless-First
All functionality works **without a browser**:
- CLI for scripting and automation
- TUI for interactive exploration
- API for integrations — browser optional

## System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    Headless Interfaces                          │
├──────────────┬──────────────┬──────────────┬───────────────────┤
│  Dashboard   │   Explorer   │     CLI      │      API          │
│  (Textual)   │   (Trogon)   │   (Click)    │   (FastAPI)       │
└──────┬───────┴──────┬───────┴──────┬───────┴────────┬──────────┘
       │              │              │                │
       └──────────────┴──────┬───────┴────────────────┘
                             │
┌────────────────────────────┴────────────────────────────────────┐
│                    Cache-Merge Core                             │
├──────────────┬──────────────┬───────────────────────────────────┤
│   Parsers    │  Data Models │       Local Cache                 │
│  (GitHub+)   │  (SQLModel)  │       (SQLite)                    │
└──────────────┴──────────────┴───────────────────────────────────┘
```

## Layer Details

### Interface Layer

#### TUI Dashboard (`src/dossier/tui/app.py`)

Full-featured Textual application:

```python
class DossierApp(App):
    """Main dashboard application."""
    
    BINDINGS = [
        ("q", "quit", "Quit"),
        ("r", "refresh", "Refresh"),
        ("s", "sync", "Sync"),
        ("a", "add", "Add Project"),
        ("o", "open_github", "Open GitHub"),
        ("/", "search", "Search"),
        ("f", "cycle_filter", "Filter"),
        ("?", "help", "Help"),
        ("l", "link_selected", "Link as Project"),
        ("d", "delete", "Delete"),
    ]
```

Components:
- `ProjectDetailPanel` - Tabbed detail view
- `SyncStatusWidget` - Sync status indicator
- `StatsWidget` - Project statistics
- `ContentViewerScreen` - Modal for viewing docs/issues/PRs with prev/next navigation
- `DraggableSplitter` - Resizable panel divider

Project Tree Features:
- **Hierarchical grouping** - Projects organized by org (`🏢 owner`)
- **Inline documentation** - Docs tree under each repo (`📚 Docs`)
- **Entity categories** - Users (`👤`), Languages (`💻`), Packages (`📦`)
- **Click to navigate** - Select docs to open viewer, entities to link

**Internal Dossier Links:**

The Dossier tab supports clickable `dossier://` links for in-app navigation:

| Link Format | Action |
|-------------|--------|
| `dossier://tab/dossier` | Switch to Dossier tab |
| `dossier://tab/projects` | Switch to Projects tab |
| `dossier://tab/deltas` | Switch to Deltas tab |
| `dossier://tab/languages` | Switch to Projects > Languages |
| `dossier://lang/python` | Link to `lang/python` entity |
| `dossier://pkg/fastapi` | Link to `pkg/fastapi` entity |
| `dossier://user/username` | Show contributor info |
| `dossier://issue/123` | Open issue viewer |
| `dossier://pr/456` | Open PR viewer |
| `dossier://release/v1.0.0` | Show release info |
| `dossier://branch/main` | Show branch info |
| `dossier://doc/readme` | Open doc in viewer |

Tabs:
- **Dossier** (Main) - Formatted project overview with component tree
- **Projects** (Main) - Project detail workspace (subtabs below)
- **Deltas** (Main) - Delta list with phases, notes, and links

Project Subtabs:
- **Details** - Project info, GitHub metadata, clickable links
- **Documentation** - Tree view grouped by source file (click to preview)
- **Languages** - Language breakdown with file extensions and encoding
- **Branches** - Repository branches with default/protected status, latest commits
- **Dependencies** - Runtime/dev/optional deps (click to link entity)
- **Contributors** - Top contributors by commit count
- **Issues** - Open/closed issues (click to link entity)
- **PRs** - Pull requests with merge status (click to link entity)
- **Releases** - Version releases (click to link entity)
- **Components** - Child project relationships

#### Command Explorer (`trogon` integration)

Auto-generated from Click commands:

```python
@cli.command()
@trogon.tui()
def tui():
    """Open interactive command explorer."""
    pass
```

#### CLI (`src/dossier/cli.py`)

Click command groups:

```
dossier
├── projects        # Project management
│   ├── list
│   ├── add
│   ├── show
│   ├── rename
│   └── remove
├── github          # GitHub sync
│   ├── sync
│   ├── download     # user or org, worked out rather than asked
│   ├── sync-user
│   ├── sync-org
│   ├── info
│   └── search
├── query           # Documentation queries
├── components      # Project relationships
│   ├── add
│   ├── list
│   └── remove
├── dev             # Development utilities
│   ├── status
│   ├── reset
│   ├── clear
│   ├── seed
│   ├── vacuum
│   └── dump
├── graph           # Entity graph building
│   ├── build       # Build graph for one project
│   ├── build-all   # Build graphs for all projects
│   └── stats       # Show graph statistics
├── serve           # API server
├── dashboard       # TUI dashboard
└── tui             # Command explorer
```

#### REST API (`src/dossier/api/main.py`)

FastAPI with lifespan pattern:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database on startup."""
    init_db()
    yield

app = FastAPI(
    title="Dossier API",
    lifespan=lifespan,
)
```

Endpoints:
- `GET /` - API information
- `GET /health` - Health check
- `GET /projects` - List projects
- `POST /projects` - Create project
- `GET /projects/{name}` - Get project details
- `GET /docs/{name}` - Query documentation

### Core Layer

#### Data Models (`src/dossier/models/schemas.py`)

Dossier uses **typed SQLModel schemas** — not arbitrary JSON. This enables SQL queries, consistent exports, and reliable API contracts.

```python
# Core entity
class Project(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True, unique=True)  # "owner/repo" or custom
    full_name: str | None = Field(default=None, index=True)  # Computed from various sources
    description: str = ""
    github_stars: int = 0
    last_synced: datetime | None = None

# Semver-parsed versions
class ProjectVersion(SQLModel, table=True):
    project_id: int = Field(foreign_key="project.id")
    version: str           # "1.2.3-beta+build"
    major: int | None      # 1
    minor: int | None      # 2  
    patch: int | None      # 3
    prerelease: str | None # "beta"
    build_metadata: str | None  # "build"
    source: str = "release"    # release, pyproject, package_json, manual
    is_latest: bool = False

# Documentation at multiple detail levels
class DocumentSection(SQLModel, table=True):
    project_id: int = Field(foreign_key="project.id")
    title: str
    content: str
    detail_level: str  # summary, overview, detailed, technical

# GitHub-synced metadata
class ProjectLanguage(SQLModel, table=True):    # Language breakdown
class ProjectBranch(SQLModel, table=True):      # Branches + commits
class ProjectDependency(SQLModel, table=True):  # From manifests
class ProjectContributor(SQLModel, table=True): # By commit count
class ProjectIssue(SQLModel, table=True):       # Issues + labels
class ProjectPullRequest(SQLModel, table=True): # PRs + diff stats
class ProjectRelease(SQLModel, table=True):     # Releases + tags
class ProjectComponent(SQLModel, table=True):   # Parent-child links

# Entity graph models
class Entity(SQLModel, table=True):             # Named entities for linking
class Link(SQLModel, table=True):               # Entity relationships
```

**Why typed schemas?**
- Query across your portfolio: `SELECT * FROM project_issue WHERE state = 'open'`
- Consistent exports: Every `.dossier` file has the same structure
- API contracts: Clients know exactly what to expect

#### Entity Scoping & Disambiguation

Every linkable entity gets a unique, namespaced project identifier:

| Scope | Pattern | Example | Rationale |
|-------|---------|---------|----------|
| **Global** | `lang/{language}` | `lang/python` | Same language everywhere |
| **Global** | `pkg/{package}` | `pkg/fastapi` | Same package everywhere |
| **App-scoped** | `github/user/{username}` | `github/user/astral-sh` | Same user across all GitHub repos |
| **Repo-scoped** | `{owner}/{repo}/branch/{name}` | `astral-sh/ruff/branch/main` | Branches are per-repo |
| **Repo-scoped** | `{owner}/{repo}/issue/{number}` | `astral-sh/ruff/issue/123` | Issues are per-repo |
| **Repo-scoped** | `{owner}/{repo}/pr/{number}` | `astral-sh/ruff/pr/456` | PRs are per-repo |
| **Repo-scoped** | `{owner}/{repo}/ver/v{version}` | `astral-sh/ruff/ver/v0.1.0` | Versions are per-repo |
| **Repo-scoped** | `{owner}/{repo}/doc/{slug}` | `astral-sh/ruff/doc/readme` | Docs are per-repo |

**Why scoping matters:**
- `issue/123` could be from any repo — ambiguous
- `astral-sh/ruff/issue/123` is unambiguous and navigable
- Contributors are app-scoped because the same GitHub user contributes to multiple repos

#### Parsers

**Base Parser** (`src/dossier/parsers/base.py`):

```python
class BaseParser:
    """Parse local documentation files."""
    
    def parse(self, path: str) -> Project:
        """Extract project info from local files."""
        pass
```

**GitHub Parser** (`src/dossier/parsers/github.py`):

```python
class GitHubParser:
    """GitHub API integration with rate limit handling."""
    
    def __init__(self, token: str | None = None):
        self.token = token or os.environ.get("GITHUB_TOKEN")
        self.client = httpx.Client(...)
        self.rate_limit = RateLimitInfo(...)
    
    def parse_repo(self, url: str) -> Project:
        """Fetch and parse a GitHub repository."""
        pass
    
    def get_user_repos(self, username: str) -> list[dict]:
        """List all repositories for a user."""
        pass
    
    def get_org_repos(self, org: str) -> list[dict]:
        """List all repositories for an organization."""
        pass
```

Rate limit handling:

```python
@dataclass
class RateLimitInfo:
    limit: int = 60
    remaining: int = 60
    reset_time: datetime | None = None
    
    def update_from_response(self, response: httpx.Response):
        """Update limits from X-RateLimit headers."""
        pass
    
    @property
    def is_limited(self) -> bool:
        return self.remaining <= 0
```

**AutoLinker** (`src/dossier/parsers/autolinker.py`):

Automatically builds entity graphs from synced project data:

```python
class AutoLinker:
    """Automatically builds entity/link graphs from project data."""
    
    def build_graph(self, project: Project, **options) -> LinkStats:
        """Build entity graph for a single project."""
        pass
    
    def build_all_graphs(self, **options) -> LinkStats:
        """Build graphs for all synced projects."""
        pass
```

Entity linking follows the scoping patterns above — contributors become `github/user/{username}`, languages become `lang/{language}`, and repo-specific entities get the full `{owner}/{repo}/{type}/{id}` path.

#### Database

SQLite with SQLModel:

```python
DATABASE_PATH = Path.home() / ".dossier" / "dossier.db"

engine = create_engine(f"sqlite:///{DATABASE_PATH}")

def init_db():
    """Create tables if they don't exist."""
    SQLModel.metadata.create_all(engine)

def get_session():
    """Get database session."""
    with Session(engine) as session:
        yield session
```

## Data Flow

### GitHub Sync Flow

```
1. User runs: dossier github sync-user username

2. CLI Layer:
   ├── Parse arguments
   ├── Initialize GitHubParser with token
   └── Call sync function

3. Parser Layer:
   ├── GET /users/{username}/repos
   ├── Update rate_limit from headers
   ├── For each repo:
   │   ├── GET /repos/{owner}/{repo}
   │   ├── GET /repos/{owner}/{repo}/readme
   │   └── Parse into Project + DocumentationSection
   └── Return batch results

4. Database Layer:
   ├── Check if project exists (by name)
   ├── Update or create Project
   ├── Create/update DocumentationSections
   └── Commit transaction

5. Response:
   └── Display results with rate limit status
```

### Query Flow

```
1. User runs: dossier query project-name --level overview

2. CLI Layer:
   └── Parse arguments, validate level

3. Database Layer:
   ├── SELECT * FROM project WHERE name = ?
   ├── SELECT * FROM documentationsection 
   │   WHERE project_id = ? AND detail_level = ?
   └── Return results

4. Response:
   └── Format and display documentation
```

## Batch Processing

### Intelligent Batching

For bulk operations (`download`, `sync-user`, `sync-org`):

```python
@dataclass
class Report:            # dossier.download
    outcomes: list[Fetched]   # one per repository, as it landed
    rate_limited: bool
```

(`dossier.parsers.github.BatchResult` predates this and is now referenced by
nothing but its own tests.)

Configuration:
- `--batch-size` - Repos per batch (default: 5)
- `--force` - Fetch even what was synced within the hour
- `--dry-run` - (on `download`) list what it would fetch, and stop

The engine is `dossier.download`, and it is the **only** place that writes a
fetched repository into the database. It was implemented four times before —
once on the command line and three times in the dashboard — and the three
copies in the panel disagreed with the client about four column names, so the
panel silently stored nulls for every branch commit date and every pull request
timestamp, and its batch sync failed outright on every project.

`download()` commits per repository and reports each one through a callback, so
the command line can paint a coloured line and the panel can move a progress
bar without either of them owning the write:

```python
report = download(session, parser, client, repos, on_each=render)
# -> Report(fetched=, skipped=, failed=, rate_limited=)
```

A rate limit stops the run and says so. Everything already fetched stays
committed, which is what makes "run it again to continue" true rather than a
hope.

## Error Handling

### Rate Limit Recovery

```python
if parser.rate_limit.is_limited:
    reset = parser.rate_limit.reset_time
    click.echo(f"⚠️  Rate limit hit. Resets at {reset}")
    # Graceful exit, can resume later
    return
```

### Timezone Handling

SQLite stores naive datetimes. Code handles conversion:

```python
if last_synced.tzinfo is None:
    last_synced = last_synced.replace(tzinfo=timezone.utc)
```

## Testing Architecture

### Test Structure

```
tests/
├── conftest.py       # Shared fixtures
├── test_api.py       # API endpoint tests
├── test_cli.py       # CLI command tests
├── test_github.py    # GitHub parser tests
├── test_models.py    # Model tests
├── test_parsers.py   # Parser tests
└── test_tui.py       # TUI component tests
```

### Fixtures (`conftest.py`)

```python
@pytest.fixture
def db_session():
    """Provide clean database session."""
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session

@pytest.fixture
def sample_project(db_session):
    """Create sample project for tests."""
    project = Project(name="test/repo", ...)
    db_session.add(project)
    db_session.commit()
    return project
```

### HTTP Mocking

Using `respx` for GitHub API mocks:

```python
@pytest.fixture
def mock_github():
    with respx.mock:
        respx.get("https://api.github.com/repos/owner/repo").mock(
            return_value=httpx.Response(200, json={...})
        )
        yield
```

## Configuration

### Environment Variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `GITHUB_TOKEN` | GitHub API authentication | None |
| `DOSSIER_DB_PATH` | Custom database location | `~/.dossier/dossier.db` |

### Configuration File

User preferences are stored in `~/.dossier/config.json`:

```json
{
  "theme": "textual-dark",
  "default_tab": "tab-dossier",
  "tree_density": "comfortable",
  "sync_batch_size": 10,
  "sync_delay": 1.0,
  "export_format": "yaml",
  "sidebar_width": null
}
```

Configuration is managed by `src/dossier/config.py`:

```python
from dossier.config import DossierConfig

# Load config (creates defaults if missing)
config = DossierConfig.load()

# Access settings
print(config.theme)  # "textual-dark"
print(config.sync_batch_size)  # 10

# Modify and save
config.theme = "nord"
config.save()

# Reset to defaults
config.reset()
config.save()
```

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `theme` | str | `textual-dark` | TUI color theme |
| `default_tab` | str | `tab-dossier` | Tab to open on project select |
| `tree_density` | str | `comfortable` | Tree spacing (future) |
| `sync_batch_size` | int | `10` | Repos per sync batch |
| `sync_delay` | float | `1.0` | Seconds between batches |
| `export_format` | str | `yaml` | Default export format |
| `sidebar_width` | int | `null` | Sidebar width (future) |

## Extension Points

### Adding New Parsers

1. Create parser in `src/dossier/parsers/`:

```python
class GitLabParser:
    def parse_repo(self, url: str) -> Project:
        # Implementation
        pass
```

2. Register in CLI or API

### Adding New Commands

1. Add to appropriate group in `cli.py`:

```python
@projects.command()
@click.argument("name")
def archive(name: str):
    """Archive a project."""
    pass
```

### Adding API Endpoints

1. Add route in `api/main.py`:

```python
@app.post("/projects/{name}/archive")
async def archive_project(name: str):
    """Archive a project."""
    pass
```

## Performance Considerations

### Database Indexing

Indexed fields for fast queries:
- `project.name` - Primary lookup
- `documentationsection.project_id` - Foreign key joins
- `projectcomponent.parent_id` - Hierarchy queries

### Lazy Loading

Documentation content loaded on demand:
- List views show minimal data
- Detail views fetch full content

### Connection Pooling

SQLModel session management:
- Sessions created per-request
- Connections pooled by SQLAlchemy

## Security Notes

### Token Storage

- Tokens passed via environment variable
- Never logged or stored in database
- CLI `--token` flag for one-time use

### Input Validation

- Project names sanitized
- URLs validated before fetch
- SQL injection prevented by ORM
