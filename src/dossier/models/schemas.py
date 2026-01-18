"""SQLModel schemas for Dossier documentation models."""

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from sqlmodel import Field, Relationship, SQLModel


def utcnow() -> datetime:
    """Get current UTC time."""
    return datetime.now(timezone.utc)


class DocumentationLevel(str, Enum):
    """Levels of documentation detail."""
    
    SUMMARY = "summary"  # Brief overview, 1-2 sentences
    OVERVIEW = "overview"  # High-level description with key points
    DETAILED = "detailed"  # Full documentation with examples
    TECHNICAL = "technical"  # Implementation details for developers


class ProjectComponent(SQLModel, table=True):
    """Association table for project parent-child relationships."""
    
    __tablename__ = "project_component"
    
    parent_id: int = Field(foreign_key="project.id", primary_key=True)
    child_id: int = Field(foreign_key="project.id", primary_key=True)
    relationship_type: str = Field(default="component")  # component, dependency, related
    order: int = Field(default=0)  # For ordering subcomponents
    created_at: datetime = Field(default_factory=utcnow)


class Project(SQLModel, table=True):
    """A project being documented."""
    
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True, unique=True)
    description: Optional[str] = None
    repository_url: Optional[str] = None
    documentation_path: Optional[str] = None
    
    # GitHub sync metadata
    github_owner: Optional[str] = None  # GitHub user or org
    github_repo: Optional[str] = None   # Repository name
    github_stars: Optional[int] = None
    github_language: Optional[str] = None
    last_synced_at: Optional[datetime] = None
    
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class DocumentSection(SQLModel, table=True):
    """A section of documentation for a project."""
    
    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="project.id", index=True)
    title: str
    content: str
    level: DocumentationLevel = Field(default=DocumentationLevel.DETAILED)
    section_type: str = Field(default="general")  # e.g., "readme", "api", "setup"
    source_file: Optional[str] = None
    order: int = Field(default=0)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class ProjectContributor(SQLModel, table=True):
    """A contributor to a project (from GitHub)."""
    
    __tablename__ = "project_contributor"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="project.id", index=True)
    username: str
    avatar_url: Optional[str] = None
    contributions: int = 0
    profile_url: Optional[str] = None
    created_at: datetime = Field(default_factory=utcnow)


class ProjectIssue(SQLModel, table=True):
    """An issue from a project's GitHub repository."""
    
    __tablename__ = "project_issue"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="project.id", index=True)
    issue_number: int
    title: str
    state: str = "open"  # open, closed
    author: Optional[str] = None
    labels: Optional[str] = None  # JSON string of labels
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    issue_created_at: Optional[datetime] = None
    issue_updated_at: Optional[datetime] = None


class ProjectLanguage(SQLModel, table=True):
    """Language breakdown for a project."""
    
    __tablename__ = "project_language"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="project.id", index=True)
    language: str
    bytes_count: int = 0
    percentage: float = 0.0
    file_extensions: Optional[str] = None  # Comma-separated list of extensions
    encoding: Optional[str] = None  # Common encoding for this language
    created_at: datetime = Field(default_factory=utcnow)


class ProjectBranch(SQLModel, table=True):
    """A branch of a project's repository."""
    
    __tablename__ = "project_branch"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="project.id", index=True)
    name: str
    is_default: bool = False
    is_protected: bool = False
    commit_sha: Optional[str] = None  # Latest commit SHA
    commit_message: Optional[str] = None  # Latest commit message
    commit_author: Optional[str] = None  # Latest commit author
    commit_date: Optional[datetime] = None  # Latest commit date
    created_at: datetime = Field(default_factory=utcnow)


class ProjectDependency(SQLModel, table=True):
    """A dependency of a project (from package.json, pyproject.toml, etc)."""
    
    __tablename__ = "project_dependency"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="project.id", index=True)
    name: str
    version_spec: Optional[str] = None  # e.g., "^1.0.0", ">=2.0"
    dep_type: str = "runtime"  # runtime, dev, optional, peer
    source: str = "unknown"  # pyproject.toml, package.json, requirements.txt, etc
    created_at: datetime = Field(default_factory=utcnow)


class ProjectPullRequest(SQLModel, table=True):
    """A pull request from a project's GitHub repository."""
    
    __tablename__ = "project_pull_request"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="project.id", index=True)
    pr_number: int
    title: str
    state: str = "open"  # open, closed, merged
    author: Optional[str] = None
    base_branch: Optional[str] = None  # Target branch
    head_branch: Optional[str] = None  # Source branch
    is_draft: bool = False
    is_merged: bool = False
    additions: int = 0
    deletions: int = 0
    labels: Optional[str] = None  # Comma-separated labels
    pr_created_at: Optional[datetime] = None
    pr_updated_at: Optional[datetime] = None
    pr_merged_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=utcnow)


class ProjectRelease(SQLModel, table=True):
    """A release/tag from a project's GitHub repository."""
    
    __tablename__ = "project_release"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="project.id", index=True)
    tag_name: str
    name: Optional[str] = None
    body: Optional[str] = None  # Release notes (truncated)
    is_prerelease: bool = False
    is_draft: bool = False
    author: Optional[str] = None
    target_commitish: Optional[str] = None  # Branch or commit
    release_created_at: Optional[datetime] = None
    release_published_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=utcnow)


class DocumentationQuery(SQLModel):
    """Query parameters for documentation requests."""
    
    project_name: Optional[str] = None
    level: DocumentationLevel = DocumentationLevel.OVERVIEW
    section_type: Optional[str] = None
    search_term: Optional[str] = None


class DocumentationResponse(SQLModel):
    """Response model for documentation queries."""
    
    project_name: str
    level: DocumentationLevel
    sections: list[dict] = Field(default_factory=list)
    total_sections: int = 0
    query_time_ms: float = 0.0
