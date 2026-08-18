"""SQLModel schemas for Dossier documentation models."""

from datetime import datetime, timezone
from enum import Enum
from typing import ClassVar, Optional

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


class DeltaPhase(str, Enum):
    """Phases of a delta's lifecycle."""

    BRAINSTORM = "brainstorm"  # Initial ideation phase
    PLANNING = "planning"  # Design and planning phase
    IMPLEMENTATION = "implementation"  # Active development
    REVIEW = "review"  # Code review / QA phase
    DOCUMENTATION = "documentation"  # Documentation phase
    COMPLETE = "complete"  # Delta is finished
    ABANDONED = "abandoned"  # Delta was abandoned


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
    name: str = Field(index=True, unique=True)  # Short name or owner/repo
    full_name: Optional[str] = Field(default=None, index=True)  # owner/repo format
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
    
    def get_full_name(self) -> str:
        """Get owner/repo format name, computing it if not stored."""
        if self.full_name:
            return self.full_name
        if self.github_owner and self.github_repo:
            return f"{self.github_owner}/{self.github_repo}"
        # Try to extract from repository_url
        if self.repository_url:
            url = self.repository_url.rstrip("/")
            if "github.com" in url:
                parts = url.split("github.com/")[-1].split("/")
                if len(parts) >= 2:
                    return f"{parts[0]}/{parts[1]}"
        # Try to extract from name if it has / format
        if "/" in self.name:
            return self.name
        return self.name
    
    @property
    def github_url(self) -> Optional[str]:
        """Get the GitHub repository URL, constructing it if necessary."""
        if self.repository_url:
            return self.repository_url
        if self.github_owner and self.github_repo:
            return f"https://github.com/{self.github_owner}/{self.github_repo}"
        # Try from full_name
        if self.full_name and "/" in self.full_name:
            return f"https://github.com/{self.full_name}"
        # Try to construct from name if it looks like owner/repo
        if "/" in self.name:
            return f"https://github.com/{self.name}"
        return None
    
    @property
    def github_owner_url(self) -> Optional[str]:
        """Get the GitHub owner (user/org) URL."""
        owner = self._get_owner()
        if owner:
            return f"https://github.com/{owner}"
        return None
    
    def _get_owner(self) -> Optional[str]:
        """Extract owner from various sources."""
        if self.github_owner:
            return self.github_owner
        if self.full_name and "/" in self.full_name:
            return self.full_name.split("/")[0]
        if self.repository_url:
            url = self.repository_url.rstrip("/")
            if "github.com" in url:
                parts = url.split("github.com/")[-1].split("/")
                if parts:
                    return parts[0]
        if "/" in self.name:
            return self.name.split("/")[0]
        return None
    
    def _get_repo(self) -> Optional[str]:
        """Extract repo name from various sources."""
        if self.github_repo:
            return self.github_repo
        if self.full_name and "/" in self.full_name:
            return self.full_name.split("/")[-1]
        if self.repository_url:
            url = self.repository_url.rstrip("/")
            if "github.com" in url:
                parts = url.split("github.com/")[-1].split("/")
                if len(parts) >= 2:
                    return parts[1]
        if "/" in self.name:
            return self.name.split("/")[-1]
        return self.name
    
    def github_issues_url(self, issue_number: Optional[int] = None) -> Optional[str]:
        """Get URL for issues or a specific issue."""
        base = self.github_url
        if not base:
            return None
        if issue_number:
            return f"{base}/issues/{issue_number}"
        return f"{base}/issues"
    
    def github_pulls_url(self, pr_number: Optional[int] = None) -> Optional[str]:
        """Get URL for PRs or a specific PR."""
        base = self.github_url
        if not base:
            return None
        if pr_number:
            return f"{base}/pull/{pr_number}"
        return f"{base}/pulls"
    
    def github_branch_url(self, branch_name: str) -> Optional[str]:
        """Get URL for a specific branch."""
        base = self.github_url
        if not base:
            return None
        return f"{base}/tree/{branch_name}"
    
    def github_releases_url(self, tag: Optional[str] = None) -> Optional[str]:
        """Get URL for releases or a specific release."""
        base = self.github_url
        if not base:
            return None
        if tag:
            return f"{base}/releases/tag/{tag}"
        return f"{base}/releases"


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


class ProjectVersion(SQLModel, table=True):
    """A semantic version tracked for a project.
    
    This model represents versions as linkable entities that can be:
    - Extracted from releases (tag_name)
    - Parsed from pyproject.toml, package.json, etc.
    - Manually specified
    
    Versions follow semver (https://semver.org/) format: MAJOR.MINOR.PATCH[-PRERELEASE][+BUILD]
    """
    
    __tablename__ = "project_version"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="project.id", index=True)
    version: str  # Full version string (e.g., "1.2.3-beta.1+build.123")
    major: int = 0  # Major version number
    minor: int = 0  # Minor version number
    patch: int = 0  # Patch version number
    prerelease: Optional[str] = None  # Prerelease identifier (e.g., "alpha.1", "beta.2", "rc.1")
    build_metadata: Optional[str] = None  # Build metadata (e.g., "build.123")
    source: str = "release"  # Where this version came from: release, pyproject, package_json, manual
    release_id: Optional[int] = Field(default=None, foreign_key="project_release.id")  # Link to release if from release
    is_latest: bool = False  # Whether this is the latest version
    release_url: Optional[str] = None  # URL to the release page
    changelog_url: Optional[str] = None  # URL to changelog for this version
    release_date: Optional[datetime] = None  # When this version was released
    created_at: datetime = Field(default_factory=utcnow)
    
    @classmethod
    def parse_version(cls, version_str: str) -> dict:
        """Parse a semver string into its components.
        
        Args:
            version_str: Version string like "1.2.3", "v1.2.3-beta.1+build.123"
            
        Returns:
            Dictionary with major, minor, patch, prerelease, build_metadata
        """
        import re
        
        # Strip leading 'v' if present
        ver = version_str.lstrip("vV")
        
        # Semver regex pattern
        # Matches: MAJOR.MINOR.PATCH[-PRERELEASE][+BUILD]
        pattern = r'^(\d+)(?:\.(\d+))?(?:\.(\d+))?(?:-([0-9A-Za-z.-]+))?(?:\+([0-9A-Za-z.-]+))?$'
        match = re.match(pattern, ver)
        
        if match:
            major = int(match.group(1)) if match.group(1) else 0
            minor = int(match.group(2)) if match.group(2) else 0
            patch = int(match.group(3)) if match.group(3) else 0
            prerelease = match.group(4)
            build_metadata = match.group(5)
        else:
            # Fallback: try to extract numbers
            numbers = re.findall(r'\d+', ver)
            major = int(numbers[0]) if len(numbers) > 0 else 0
            minor = int(numbers[1]) if len(numbers) > 1 else 0
            patch = int(numbers[2]) if len(numbers) > 2 else 0
            prerelease = None
            build_metadata = None
        
        return {
            "version": version_str,
            "major": major,
            "minor": minor,
            "patch": patch,
            "prerelease": prerelease,
            "build_metadata": build_metadata,
        }
    
    @classmethod
    def from_version_string(cls, project_id: int, version_str: str, **kwargs) -> "ProjectVersion":
        """Create a ProjectVersion from a version string.
        
        Args:
            project_id: The project ID
            version_str: Version string to parse
            **kwargs: Additional fields (source, release_id, etc.)
            
        Returns:
            ProjectVersion instance
        """
        parsed = cls.parse_version(version_str)
        return cls(
            project_id=project_id,
            version=parsed["version"],
            major=parsed["major"],
            minor=parsed["minor"],
            patch=parsed["patch"],
            prerelease=parsed["prerelease"],
            build_metadata=parsed["build_metadata"],
            **kwargs,
        )


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


class ProjectDelta(SQLModel, table=True):
    """A delta (change) tracked for a project.

    Deltas represent discrete units of work (features, bugfixes, refactors)
    that progress through phases: brainstorm -> planning -> implementation ->
    review -> documentation -> complete.
    """

    __tablename__ = "project_delta"

    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="project.id", index=True)

    # Core fields
    name: str  # Short identifier (e.g., "add-dark-mode", "fix-auth-bug")
    title: str  # Human-readable title
    description: Optional[str] = None

    # Phase tracking
    phase: DeltaPhase = Field(default=DeltaPhase.BRAINSTORM)
    phase_changed_at: datetime = Field(default_factory=utcnow)

    # Priority and categorization
    priority: str = Field(default="medium")  # low, medium, high, critical
    delta_type: str = Field(default="feature")  # feature, bugfix, refactor, docs, chore

    # Timestamps
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    # Optional linking to GitHub entities
    issue_number: Optional[int] = None  # Link to related GitHub issue
    pr_number: Optional[int] = None  # Link to related PR
    branch_name: Optional[str] = None  # Associated branch

    # Phase sequence for advancing
    PHASE_ORDER: ClassVar[list[DeltaPhase]] = [
        DeltaPhase.BRAINSTORM,
        DeltaPhase.PLANNING,
        DeltaPhase.IMPLEMENTATION,
        DeltaPhase.REVIEW,
        DeltaPhase.DOCUMENTATION,
        DeltaPhase.COMPLETE,
    ]

    def advance_phase(self) -> bool:
        """Advance to the next phase in the sequence.

        Returns True if phase was advanced, False if already at final phase.
        """
        if self.phase == DeltaPhase.ABANDONED:
            return False

        try:
            current_idx = self.PHASE_ORDER.index(self.phase)
            if current_idx < len(self.PHASE_ORDER) - 1:
                self.phase = self.PHASE_ORDER[current_idx + 1]
                self.phase_changed_at = utcnow()
                self.updated_at = utcnow()

                # Set started_at when entering implementation
                if self.phase == DeltaPhase.IMPLEMENTATION and not self.started_at:
                    self.started_at = utcnow()

                # Set completed_at when entering complete
                if self.phase == DeltaPhase.COMPLETE:
                    self.completed_at = utcnow()

                return True
        except ValueError:
            pass
        return False

    def can_advance(self) -> bool:
        """Check if the delta can advance to the next phase."""
        if self.phase == DeltaPhase.ABANDONED:
            return False
        try:
            current_idx = self.PHASE_ORDER.index(self.phase)
            return current_idx < len(self.PHASE_ORDER) - 1
        except ValueError:
            return False


class DeltaNote(SQLModel, table=True):
    """A note or update for a delta during a specific phase."""

    __tablename__ = "delta_note"

    id: Optional[int] = Field(default=None, primary_key=True)
    delta_id: int = Field(foreign_key="project_delta.id", index=True)

    phase: DeltaPhase  # Phase this note was created during
    content: str  # Markdown content

    created_at: datetime = Field(default_factory=utcnow)


class DeltaLink(SQLModel, table=True):
    """Links a delta to related entities (issues, PRs, branches, other deltas)."""

    __tablename__ = "delta_link"

    id: Optional[int] = Field(default=None, primary_key=True)
    delta_id: int = Field(foreign_key="project_delta.id", index=True)

    # What this delta links to
    link_type: str  # "issue", "pr", "branch", "delta", "doc"
    target_id: Optional[int] = None  # ID for issues, PRs, deltas
    target_name: Optional[str] = None  # Name for branches, etc.

    created_at: datetime = Field(default_factory=utcnow)
