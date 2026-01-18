# Extending Dossier

[← Back to Workflows](workflows.md) | [Architecture](architecture.md) | [Contributing →](contributing.md)

---

Dossier is designed to be extended for personal or team needs. This guide covers customization, adding new parsers, data models, and building on top of Dossier.

## Quick Customization

### Custom Database Location

```bash
# Default: ~/.dossier/dossier.db
# Override with environment variable:
export DOSSIER_DB_PATH=/path/to/custom/dossier.db

# Or per-command:
DOSSIER_DB_PATH=./project.db uv run dossier dashboard
```

### Team-Shared Database

For a team cache, point everyone to a shared path:

```bash
# On shared drive (NFS, SMB, etc.)
export DOSSIER_DB_PATH=/shared/team/dossier.db

# Caution: SQLite doesn't handle concurrent writes well
# Use for read-heavy workloads or consider future PostgreSQL support
```

---

## Adding Custom Parsers

Want to sync from GitLab, Bitbucket, or a custom source? Create a parser.

### Parser Structure

```python
# src/dossier/parsers/gitlab.py
from dossier.models import Project, DocumentSection
from dossier.parsers.base import BaseParser

class GitLabParser(BaseParser):
    """Parser for GitLab repositories."""
    
    def __init__(self, token: str | None = None):
        self.token = token or os.environ.get("GITLAB_TOKEN")
        self.base_url = "https://gitlab.com/api/v4"
    
    def parse_repo(self, project_path: str) -> Project:
        """Fetch and parse a GitLab project.
        
        Args:
            project_path: GitLab project path (e.g., "group/project")
            
        Returns:
            Project instance with populated fields.
        """
        # Fetch from GitLab API
        response = httpx.get(
            f"{self.base_url}/projects/{project_path.replace('/', '%2F')}",
            headers={"PRIVATE-TOKEN": self.token} if self.token else {},
        )
        data = response.json()
        
        return Project(
            name=data["path_with_namespace"],
            description=data.get("description", ""),
            repository_url=data["web_url"],
            # Map GitLab fields to Dossier schema
        )
    
    def get_readme(self, project_path: str) -> str | None:
        """Fetch README content."""
        # Implementation
        pass
```

### Register the Parser

```python
# src/dossier/parsers/__init__.py
from .base import BaseParser
from .github import GitHubParser
from .gitlab import GitLabParser  # Add this

__all__ = ["BaseParser", "GitHubParser", "GitLabParser"]
```

### Add CLI Command

```python
# In src/dossier/cli.py, add to the gitlab group:

@cli.group()
def gitlab():
    """GitLab integration commands."""
    pass

@gitlab.command("sync")
@click.argument("project_path")
@click.option("--token", envvar="GITLAB_TOKEN", help="GitLab token")
def gitlab_sync(project_path: str, token: str | None):
    """Sync a GitLab project."""
    from dossier.parsers.gitlab import GitLabParser
    
    parser = GitLabParser(token=token)
    project = parser.parse_repo(project_path)
    
    with get_session() as session:
        # Save to database
        session.add(project)
        session.commit()
    
    click.echo(f"✓ Synced {project.name}")
```

### Test Your Parser

```python
# tests/test_gitlab.py
import pytest
from dossier.parsers.gitlab import GitLabParser

def test_gitlab_parse_repo():
    """Test GitLab repo parsing."""
    parser = GitLabParser()
    
    # Use respx to mock GitLab API
    with respx.mock:
        respx.get("https://gitlab.com/api/v4/projects/test%2Frepo").mock(
            return_value=httpx.Response(200, json={
                "path_with_namespace": "test/repo",
                "description": "Test project",
                "web_url": "https://gitlab.com/test/repo",
            })
        )
        
        project = parser.parse_repo("test/repo")
        
    assert project.name == "test/repo"
    assert project.description == "Test project"
```

---

## Adding Data Models

Need to track additional data? Add a new SQLModel schema.

### Define the Model

```python
# src/dossier/models/schemas.py

class ProjectTag(SQLModel, table=True):
    """Custom tags for projects."""
    
    __tablename__ = "project_tag"
    
    id: int | None = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="project.id", index=True)
    tag: str = Field(index=True)
    color: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
```

### Create Migration

```bash
# Generate migration
uv run dossier db revision "add project_tag table"

# Edit the generated file in alembic/versions/
# Then apply:
uv run dossier db upgrade
```

### Export the Model

```python
# src/dossier/models/__init__.py
from .schemas import (
    Project,
    ProjectTag,  # Add this
    # ...
)

__all__ = [
    "Project",
    "ProjectTag",  # Add this
    # ...
]
```

### Add CLI Commands

```python
# src/dossier/cli.py

@cli.group()
def tags():
    """Manage project tags."""
    pass

@tags.command("add")
@click.argument("project_name")
@click.argument("tag")
@click.option("--color", default=None)
def tags_add(project_name: str, tag: str, color: str | None):
    """Add a tag to a project."""
    with get_session() as session:
        project = session.exec(
            select(Project).where(Project.name == project_name)
        ).first()
        
        if not project:
            raise click.ClickException(f"Project not found: {project_name}")
        
        project_tag = ProjectTag(
            project_id=project.id,
            tag=tag,
            color=color,
        )
        session.add(project_tag)
        session.commit()
        
    click.echo(f"✓ Added tag '{tag}' to {project_name}")

@tags.command("list")
@click.argument("project_name")
def tags_list(project_name: str):
    """List tags for a project."""
    with get_session() as session:
        project = session.exec(
            select(Project).where(Project.name == project_name)
        ).first()
        
        if not project:
            raise click.ClickException(f"Project not found: {project_name}")
        
        tags = session.exec(
            select(ProjectTag).where(ProjectTag.project_id == project.id)
        ).all()
        
        for t in tags:
            color_str = f" ({t.color})" if t.color else ""
            click.echo(f"  • {t.tag}{color_str}")
```

---

## Adding TUI Components

Extend the dashboard with new tabs or widgets.

### Add a New Tab

```python
# src/dossier/tui/app.py

# In the DossierApp class, add to compose():
def compose(self) -> ComposeResult:
    # ... existing code ...
    
    with TabbedContent(id="detail-tabs"):
        # ... existing tabs ...
        with TabPane("Tags", id="tags-tab"):
            yield DataTable(id="tags-table")

# Add handler to populate the tab:
def _load_tags_tab(self, project: Project) -> None:
    """Load tags for the selected project."""
    table = self.query_one("#tags-table", DataTable)
    table.clear(columns=True)
    table.add_columns("Tag", "Color", "Created")
    
    with get_session() as session:
        tags = session.exec(
            select(ProjectTag).where(ProjectTag.project_id == project.id)
        ).all()
        
        for tag in tags:
            table.add_row(
                tag.tag,
                tag.color or "-",
                tag.created_at.strftime("%Y-%m-%d"),
            )
```

### Add Keyboard Binding

```python
# In DossierApp class:
BINDINGS = [
    # ... existing bindings ...
    ("t", "add_tag", "Add Tag"),
]

def action_add_tag(self) -> None:
    """Open dialog to add tag to selected project."""
    # Implementation
    pass
```

---

## Adding API Endpoints

Extend the REST API for integrations.

### Add Endpoint

```python
# src/dossier/api/main.py

@app.get("/projects/{name}/tags")
def get_project_tags(
    name: str,
    session: Session = Depends(get_session),
) -> list[dict]:
    """Get tags for a project."""
    project = session.exec(
        select(Project).where(Project.name == name)
    ).first()
    
    if not project:
        raise HTTPException(404, f"Project not found: {name}")
    
    tags = session.exec(
        select(ProjectTag).where(ProjectTag.project_id == project.id)
    ).all()
    
    return [{"tag": t.tag, "color": t.color} for t in tags]

@app.post("/projects/{name}/tags")
def add_project_tag(
    name: str,
    tag: str,
    color: str | None = None,
    session: Session = Depends(get_session),
) -> dict:
    """Add a tag to a project."""
    project = session.exec(
        select(Project).where(Project.name == name)
    ).first()
    
    if not project:
        raise HTTPException(404, f"Project not found: {name}")
    
    project_tag = ProjectTag(project_id=project.id, tag=tag, color=color)
    session.add(project_tag)
    session.commit()
    
    return {"status": "ok", "tag": tag}
```

### Test the Endpoint

```python
# tests/test_api.py

def test_get_project_tags(client, sample_project):
    """Test getting tags for a project."""
    response = client.get(f"/projects/{sample_project.name}/tags")
    assert response.status_code == 200
    assert isinstance(response.json(), list)

def test_add_project_tag(client, sample_project):
    """Test adding a tag to a project."""
    response = client.post(
        f"/projects/{sample_project.name}/tags",
        params={"tag": "important", "color": "red"},
    )
    assert response.status_code == 200
    assert response.json()["tag"] == "important"
```

---

## Project-Specific Configuration

### Config File Support (Planned)

Future `~/.dossier/config.toml`:

```toml
[github]
token = "ghp_xxx"
default_batch_size = 10
default_batch_delay = 1

[gitlab]
token = "glpat_xxx"
base_url = "https://gitlab.mycompany.com"

[database]
path = "~/.dossier/dossier.db"

[tui]
theme = "dark"
default_tab = "dossier"

[tags]
default_colors = ["blue", "green", "yellow", "red"]
```

### Per-Project Config (Planned)

`.dossier.toml` in repository root:

```toml
[project]
display_name = "My Awesome Project"
category = "frontend"
team = "platform"

[sync]
include_branches = ["main", "develop"]
exclude_labels = ["wontfix", "duplicate"]

[export]
include_sections = ["readme", "contributing"]
```

---

## Testing Your Extensions

### Test Structure

```
tests/
├── test_gitlab.py         # Your parser tests
├── test_tags.py           # Your model tests
├── test_api_tags.py       # Your API tests
└── conftest.py            # Shared fixtures
```

### Fixtures for Custom Models

```python
# tests/conftest.py

@pytest.fixture
def sample_project_with_tags(test_session):
    """Create a project with tags for testing."""
    project = Project(name="test/tagged-project")
    test_session.add(project)
    test_session.commit()
    test_session.refresh(project)
    
    tags = [
        ProjectTag(project_id=project.id, tag="important", color="red"),
        ProjectTag(project_id=project.id, tag="frontend", color="blue"),
    ]
    for tag in tags:
        test_session.add(tag)
    test_session.commit()
    
    return project
```

### Run Tests

```bash
# Run all tests
uv run pytest

# Run only your extension tests
uv run pytest tests/test_gitlab.py tests/test_tags.py -v

# With coverage
uv run pytest --cov=dossier --cov-report=html
```

---

## Packaging as a Plugin (Future)

Eventually, Dossier will support plugins:

```bash
# Install a community plugin
uv add dossier-gitlab

# Plugin auto-registers commands
uv run dossier gitlab sync group/project
```

Plugin structure:
```
dossier-gitlab/
├── src/dossier_gitlab/
│   ├── __init__.py
│   ├── parser.py
│   └── cli.py
├── tests/
├── pyproject.toml
└── README.md
```

---

## Getting Help

- **Questions**: Open a GitHub Discussion
- **Bugs**: Open a GitHub Issue  
- **Feature Requests**: Open an Issue with `[Feature]` prefix
- **Contributions**: See [Contributing Guide](contributing.md)

---

Next: [Contributing Guide →](contributing.md)
