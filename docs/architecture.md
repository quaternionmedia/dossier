# Architecture

[← Back to Index](index.md) | [Overview](overview.md) | [Contributing →](contributing.md)

---

## System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         Interfaces                               │
├──────────────┬──────────────┬──────────────┬───────────────────┤
│  Dashboard   │   Explorer   │     CLI      │      API          │
│  (Textual)   │   (Trogon)   │   (Click)    │   (FastAPI)       │
└──────┬───────┴──────┬───────┴──────┬───────┴────────┬──────────┘
       │              │              │                │
       └──────────────┴──────┬───────┴────────────────┘
                             │
┌────────────────────────────┴────────────────────────────────────┐
│                       Core Layer                                 │
├──────────────┬──────────────┬───────────────────────────────────┤
│   Parsers    │    Models    │          Database                 │
│  (GitHub)    │  (SQLModel)  │          (SQLite)                 │
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
        ("s", "sync_project", "Sync"),
        ("a", "add_project", "Add"),
        ("d", "delete_project", "Delete"),
        ("slash", "focus_search", "Search"),
        ("question_mark", "show_help", "Help"),
    ]
```

Components:
- `ProjectListItem` - Individual project in list view
- `ProjectDetailPanel` - Tabbed detail view
- `SyncStatusWidget` - Sync status indicator
- `StatsWidget` - Project statistics

Tabs (8 total):
- **Details** - Project info, GitHub metadata, clickable links
- **Documentation** - Parsed doc sections table
- **Languages** - Language breakdown with file extensions and encoding
- **Branches** - Repository branches with default/protected status, latest commits
- **Dependencies** - Runtime/dev/optional deps from manifest files
- **Contributors** - Top contributors by commit count
- **Issues** - Open/closed issues with labels
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

#### Models (`src/dossier/models/schemas.py`)

SQLModel definitions:

```python
class Project(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True, unique=True)
    description: str = ""
    version: str = "0.0.0"
    github_url: str | None = None
    github_stars: int = 0
    last_synced: datetime | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

class DocumentationSection(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="project.id")
    section_type: str
    title: str
    content: str
    summary: str = ""
    detail_level: str = "overview"

class ProjectComponent(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    parent_id: int = Field(foreign_key="project.id")
    child_id: int = Field(foreign_key="project.id")
    component_type: str = "component"

class ProjectLanguage(SQLModel, table=True):
    project_id: int
    language: str
    bytes_count: int
    percentage: float

class ProjectDependency(SQLModel, table=True):
    project_id: int
    name: str
    version_spec: str | None
    dep_type: str  # runtime, dev, optional, peer
    source: str    # pyproject.toml, package.json, requirements.txt

class ProjectContributor(SQLModel, table=True):
    project_id: int
    username: str
    contributions: int
    avatar_url: str | None
    profile_url: str | None

class ProjectIssue(SQLModel, table=True):
    project_id: int
    issue_number: int
    title: str
    state: str  # open, closed
    author: str | None
    labels: str | None

class ProjectBranch(SQLModel, table=True):
    project_id: int
    name: str
    is_default: bool
    is_protected: bool
    commit_sha: str | None
    commit_message: str | None
    commit_author: str | None
    commit_date: datetime | None
```

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

For bulk operations (sync-user, sync-org):

```python
@dataclass
class BatchResult:
    total: int
    synced: int
    skipped: int
    failed: int
    errors: list[str]
```

Configuration:
- `--batch-size` - Repos per batch (default: 5)
- `--batch-delay` - Seconds between batches (default: 2)
- `--force` - Ignore "recently synced" check

```python
async def _sync_repos_batch(repos, batch_size, batch_delay, force):
    """Process repos in batches with rate limit respect."""
    for i in range(0, len(repos), batch_size):
        batch = repos[i:i+batch_size]
        for repo in batch:
            if not force and recently_synced(repo):
                result.skipped += 1
                continue
            sync_repo(repo)
            result.synced += 1
        time.sleep(batch_delay)
```

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

### Planned: Config File

Future support for `~/.dossier/config.toml`:

```toml
[github]
token = "ghp_xxx"
default_batch_size = 5
default_batch_delay = 2

[database]
path = "~/.dossier/dossier.db"

[tui]
theme = "dark"
```

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
