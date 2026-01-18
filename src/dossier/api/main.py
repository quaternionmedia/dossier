"""FastAPI application for Dossier documentation API."""

import os
import time
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import Session, SQLModel, create_engine, select

from dossier.models import (
    DocumentationLevel,
    DocumentationQuery,
    DocumentationResponse,
    DocumentSection,
    Project,
    ProjectComponent,
    utcnow,
)
from dossier.parsers import GitHubClient, GitHubParser

# Database setup
DATABASE_URL = "sqlite:///dossier.db"
engine = create_engine(DATABASE_URL, echo=False)


def get_session() -> Session:
    """Get database session."""
    return Session(engine)


def init_db() -> None:
    """Initialize database tables."""
    SQLModel.metadata.create_all(engine)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup/shutdown."""
    init_db()
    yield


app = FastAPI(
    title="Dossier API",
    description="Documentation standardization API - query project docs at different detail levels",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/")
def root() -> dict:
    """Root endpoint with API info."""
    return {
        "name": "Dossier API",
        "version": "0.1.0",
        "description": "Documentation standardization API",
        "docs_url": "/docs",
    }


@app.get("/health")
def health_check() -> dict:
    """Health check endpoint."""
    return {"status": "healthy"}


@app.get("/projects", response_model=list[Project])
def list_projects() -> list[Project]:
    """List all registered projects."""
    with get_session() as session:
        statement = select(Project)
        return list(session.exec(statement).all())


@app.post("/projects", response_model=Project)
def create_project(project: Project) -> Project:
    """Register a new project."""
    with get_session() as session:
        session.add(project)
        session.commit()
        session.refresh(project)
        return project


@app.get("/projects/{project_name}", response_model=Project)
def get_project(project_name: str) -> Project:
    """Get project by name."""
    with get_session() as session:
        statement = select(Project).where(Project.name == project_name)
        project = session.exec(statement).first()
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        return project


@app.get("/docs/{project_name}", response_model=DocumentationResponse)
def query_documentation(
    project_name: str,
    level: DocumentationLevel = Query(
        default=DocumentationLevel.OVERVIEW,
        description="Level of detail for documentation",
    ),
    section_type: Optional[str] = Query(
        default=None,
        description="Filter by section type (e.g., 'api', 'setup', 'usage')",
    ),
    search: Optional[str] = Query(
        default=None,
        description="Search term to filter sections",
    ),
) -> DocumentationResponse:
    """Query documentation for a project at specified detail level."""
    start_time = time.time()
    
    with get_session() as session:
        # Get project
        project_stmt = select(Project).where(Project.name == project_name)
        project = session.exec(project_stmt).first()
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        
        # Build query for sections
        section_stmt = select(DocumentSection).where(
            DocumentSection.project_id == project.id
        )
        
        # Filter by level (include current level and below)
        level_order = [
            DocumentationLevel.SUMMARY,
            DocumentationLevel.OVERVIEW,
            DocumentationLevel.DETAILED,
            DocumentationLevel.TECHNICAL,
        ]
        max_level_idx = level_order.index(level)
        allowed_levels = level_order[: max_level_idx + 1]
        section_stmt = section_stmt.where(DocumentSection.level.in_(allowed_levels))
        
        # Filter by section type
        if section_type:
            section_stmt = section_stmt.where(
                DocumentSection.section_type == section_type
            )
        
        # Order by section order
        section_stmt = section_stmt.order_by(DocumentSection.order)
        
        sections = list(session.exec(section_stmt).all())
        
        # Apply search filter in memory (for simplicity)
        if search:
            search_lower = search.lower()
            sections = [
                s
                for s in sections
                if search_lower in s.title.lower() or search_lower in s.content.lower()
            ]
        
        query_time = (time.time() - start_time) * 1000
        
        return DocumentationResponse(
            project_name=project_name,
            level=level,
            sections=[
                {
                    "title": s.title,
                    "content": s.content,
                    "section_type": s.section_type,
                    "level": s.level.value,
                }
                for s in sections
            ],
            total_sections=len(sections),
            query_time_ms=round(query_time, 2),
        )


# GitHub API endpoints

class GitHubSyncRequest(BaseModel):
    """Request model for GitHub sync."""
    repo_url: str
    name: Optional[str] = None
    description: Optional[str] = None
    include_docs: bool = True


class GitHubSyncResponse(BaseModel):
    """Response model for GitHub sync."""
    project_name: str
    repo_full_name: str
    description: Optional[str]
    stars: int
    language: Optional[str]
    sections_parsed: int


class GitHubRepoInfo(BaseModel):
    """GitHub repository information."""
    owner: str
    name: str
    full_name: str
    description: Optional[str]
    html_url: Optional[str]
    default_branch: str
    language: Optional[str]
    stars: int
    topics: list[str]
    has_readme: bool
    doc_files: list[str]


class GitHubSearchResult(BaseModel):
    """GitHub search result."""
    repos: list[dict]
    total: int


def get_github_token() -> Optional[str]:
    """Get GitHub token from environment."""
    return os.environ.get("GITHUB_TOKEN")


@app.post("/github/sync", response_model=GitHubSyncResponse)
def sync_github_repo(request: GitHubSyncRequest) -> GitHubSyncResponse:
    """Sync a GitHub repository as a Dossier project.
    
    This endpoint will:
    1. Fetch repository metadata from GitHub
    2. Register or update the project
    3. Parse README and documentation files
    
    Set GITHUB_TOKEN environment variable for private repos.
    """
    token = get_github_token()
    
    with get_session() as session:
        with GitHubParser(token) as parser:
            try:
                repo, sections = parser.parse_repo_url(
                    request.repo_url,
                    include_docs_folder=request.include_docs,
                )
            except Exception as e:
                raise HTTPException(
                    status_code=400,
                    detail=f"Error fetching repository: {str(e)}",
                )
            
            # Use owner/repo format for disambiguation
            project_name = request.name or f"{repo.owner}/{repo.name}"
            
            # Check if project exists
            existing = session.exec(
                select(Project).where(Project.name == project_name)
            ).first()
            
            if existing:
                existing.description = request.description or repo.description
                existing.repository_url = repo.html_url
                existing.github_owner = repo.owner
                existing.github_repo = repo.name
                existing.github_stars = repo.stars
                existing.github_language = repo.language
                existing.last_synced_at = utcnow()
                existing.updated_at = utcnow()
                project = existing
                
                # Remove old sections
                old_sections = session.exec(
                    select(DocumentSection).where(
                        DocumentSection.project_id == existing.id
                    )
                ).all()
                for old_section in old_sections:
                    session.delete(old_section)
            else:
                project = Project(
                    name=project_name,
                    full_name=f"{repo.owner}/{repo.name}",
                    description=request.description or repo.description,
                    repository_url=repo.html_url,
                    github_owner=repo.owner,
                    github_repo=repo.name,
                    github_stars=repo.stars,
                    github_language=repo.language,
                    last_synced_at=utcnow(),
                )
                session.add(project)
                session.flush()
            
            # Add sections
            for section in sections:
                section.project_id = project.id
                session.add(section)
            
            session.commit()
            
            return GitHubSyncResponse(
                project_name=project_name,
                repo_full_name=repo.full_name,
                description=repo.description,
                stars=repo.stars,
                language=repo.language,
                sections_parsed=len(sections),
            )


@app.get("/github/info", response_model=GitHubRepoInfo)
def get_github_repo_info(
    repo_url: str = Query(..., description="GitHub repository URL"),
) -> GitHubRepoInfo:
    """Get information about a GitHub repository.
    
    Returns repository metadata and available documentation files.
    """
    token = get_github_token()
    
    with GitHubClient(token) as client:
        try:
            repo = client.get_repo_from_url(repo_url)
            readme = client.get_readme(repo.owner, repo.name)
            docs = client.list_docs_files(repo.owner, repo.name)
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=f"Error fetching repository: {str(e)}",
            )
        
        return GitHubRepoInfo(
            owner=repo.owner,
            name=repo.name,
            full_name=repo.full_name,
            description=repo.description,
            html_url=repo.html_url,
            default_branch=repo.default_branch,
            language=repo.language,
            stars=repo.stars,
            topics=repo.topics or [],
            has_readme=readme is not None,
            doc_files=[doc["path"] for doc in docs],
        )


@app.get("/github/search", response_model=GitHubSearchResult)
def search_github_repos(
    query: str = Query(..., description="Search query"),
    sort: str = Query("stars", description="Sort by: stars, forks, updated"),
    limit: int = Query(10, ge=1, le=100, description="Number of results"),
) -> GitHubSearchResult:
    """Search GitHub repositories.
    
    Uses GitHub search syntax. Examples:
    - "fastapi" - search by name/description
    - "language:python topic:cli" - filter by language and topic
    - "org:microsoft" - search within an organization
    """
    token = get_github_token()
    
    with GitHubClient(token) as client:
        try:
            repos = client.search_repos(query, sort=sort, per_page=limit)
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=f"Error searching repositories: {str(e)}",
            )
        
        return GitHubSearchResult(
            repos=[
                {
                    "owner": r.owner,
                    "name": r.name,
                    "full_name": r.full_name,
                    "description": r.description,
                    "html_url": r.html_url,
                    "language": r.language,
                    "stars": r.stars,
                    "topics": r.topics or [],
                }
                for r in repos
            ],
            total=len(repos),
        )


# Dossier file format endpoints

class DossierResponse(BaseModel):
    """Response model for dossier export."""
    dossier: dict
    project: dict
    overview: Optional[dict] = None
    tech_stack: Optional[list] = None
    dependencies: Optional[dict] = None
    activity: Optional[dict] = None
    links: Optional[dict] = None


@app.get("/dossier/{project_name}", response_model=DossierResponse)
def get_project_dossier(
    project_name: str,
    include_docs: bool = Query(True, description="Include documentation overview"),
    include_activity: bool = Query(True, description="Include activity metrics"),
) -> DossierResponse:
    """Get a project's dossier in standardized format.
    
    Returns a structured overview of the project including:
    - Project metadata
    - Tech stack (languages)
    - Dependencies
    - Activity metrics (issues, PRs, releases)
    - Useful links
    
    This endpoint returns JSON. For YAML format, use the CLI:
        dossier export dossier <project_name>
    """
    from dossier.dossier_file import generate_dossier
    
    with get_session() as session:
        project = session.exec(
            select(Project).where(Project.name == project_name)
        ).first()
        
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        
        dossier_data = generate_dossier(
            session,
            project,
            include_docs=include_docs,
            include_activity=include_activity,
        )
        
        return DossierResponse(**dossier_data)


# Project Components API endpoints

class ComponentCreateRequest(BaseModel):
    """Request to create a component relationship."""
    parent_name: str
    child_name: str
    relationship_type: str = "component"
    order: int = 0


class ComponentInfo(BaseModel):
    """Information about a component relationship."""
    parent_id: int
    parent_name: str
    child_id: int
    child_name: str
    relationship_type: str
    order: int


class ComponentListResponse(BaseModel):
    """List of components."""
    parent_name: str
    components: list[ComponentInfo]
    total: int


class ComponentUpdateRequest(BaseModel):
    """Request to update a component relationship."""
    relationship_type: Optional[str] = None
    order: Optional[int] = None


@app.get("/projects/{project_name}/components", response_model=ComponentListResponse)
def list_project_components(
    project_name: str,
    include_parents: bool = Query(False, description="Also list projects this is a component of"),
) -> ComponentListResponse:
    """List components (subprojects) of a project.
    
    Returns all projects that are linked as components/subprojects
    of the specified parent project.
    """
    with get_session() as session:
        # Get parent project
        parent = session.exec(
            select(Project).where(Project.name == project_name)
        ).first()
        
        if not parent:
            raise HTTPException(status_code=404, detail="Project not found")
        
        # Get child components
        components = session.exec(
            select(ProjectComponent)
            .where(ProjectComponent.parent_id == parent.id)
            .order_by(ProjectComponent.order)
        ).all()
        
        component_infos = []
        for comp in components:
            child = session.get(Project, comp.child_id)
            if child:
                component_infos.append(ComponentInfo(
                    parent_id=parent.id,
                    parent_name=parent.name,
                    child_id=child.id,
                    child_name=child.name,
                    relationship_type=comp.relationship_type,
                    order=comp.order,
                ))
        
        # Optionally include parents (projects this is a component of)
        if include_parents:
            parent_links = session.exec(
                select(ProjectComponent)
                .where(ProjectComponent.child_id == parent.id)
            ).all()
            
            for link in parent_links:
                parent_proj = session.get(Project, link.parent_id)
                if parent_proj:
                    component_infos.append(ComponentInfo(
                        parent_id=parent_proj.id,
                        parent_name=parent_proj.name,
                        child_id=parent.id,
                        child_name=parent.name,
                        relationship_type=f"parent:{link.relationship_type}",
                        order=link.order,
                    ))
        
        return ComponentListResponse(
            parent_name=project_name,
            components=component_infos,
            total=len(component_infos),
        )


@app.post("/projects/{project_name}/components", response_model=ComponentInfo)
def add_project_component(
    project_name: str,
    child_name: str = Query(..., description="Name of the child/subproject"),
    relationship_type: str = Query("component", description="Type: component, dependency, related"),
    order: int = Query(0, description="Display order"),
) -> ComponentInfo:
    """Add a component (subproject) to a project.
    
    Creates a parent-child relationship between two projects.
    
    Relationship types:
    - **component**: A submodule or part of the parent project
    - **dependency**: The parent depends on this project
    - **related**: Projects are related but not hierarchical
    """
    with get_session() as session:
        # Get parent project
        parent = session.exec(
            select(Project).where(Project.name == project_name)
        ).first()
        
        if not parent:
            raise HTTPException(status_code=404, detail=f"Parent project '{project_name}' not found")
        
        # Get child project
        child = session.exec(
            select(Project).where(Project.name == child_name)
        ).first()
        
        if not child:
            raise HTTPException(status_code=404, detail=f"Child project '{child_name}' not found")
        
        # Check if relationship already exists
        existing = session.exec(
            select(ProjectComponent)
            .where(ProjectComponent.parent_id == parent.id)
            .where(ProjectComponent.child_id == child.id)
        ).first()
        
        if existing:
            raise HTTPException(
                status_code=409,
                detail=f"Component relationship already exists between '{project_name}' and '{child_name}'"
            )
        
        # Prevent self-reference
        if parent.id == child.id:
            raise HTTPException(
                status_code=400,
                detail="A project cannot be a component of itself"
            )
        
        # Create relationship
        component = ProjectComponent(
            parent_id=parent.id,
            child_id=child.id,
            relationship_type=relationship_type,
            order=order,
        )
        session.add(component)
        session.commit()
        
        return ComponentInfo(
            parent_id=parent.id,
            parent_name=parent.name,
            child_id=child.id,
            child_name=child.name,
            relationship_type=relationship_type,
            order=order,
        )


@app.put("/projects/{project_name}/components/{child_name}", response_model=ComponentInfo)
def update_project_component(
    project_name: str,
    child_name: str,
    update: ComponentUpdateRequest,
) -> ComponentInfo:
    """Update a component relationship.
    
    Modify the relationship type or display order of an existing
    parent-child relationship.
    """
    with get_session() as session:
        # Get parent project
        parent = session.exec(
            select(Project).where(Project.name == project_name)
        ).first()
        
        if not parent:
            raise HTTPException(status_code=404, detail=f"Parent project '{project_name}' not found")
        
        # Get child project
        child = session.exec(
            select(Project).where(Project.name == child_name)
        ).first()
        
        if not child:
            raise HTTPException(status_code=404, detail=f"Child project '{child_name}' not found")
        
        # Get existing relationship
        component = session.exec(
            select(ProjectComponent)
            .where(ProjectComponent.parent_id == parent.id)
            .where(ProjectComponent.child_id == child.id)
        ).first()
        
        if not component:
            raise HTTPException(
                status_code=404,
                detail=f"No component relationship exists between '{project_name}' and '{child_name}'"
            )
        
        # Update fields
        if update.relationship_type is not None:
            component.relationship_type = update.relationship_type
        if update.order is not None:
            component.order = update.order
        
        session.add(component)
        session.commit()
        
        return ComponentInfo(
            parent_id=parent.id,
            parent_name=parent.name,
            child_id=child.id,
            child_name=child.name,
            relationship_type=component.relationship_type,
            order=component.order,
        )


@app.delete("/projects/{project_name}/components/{child_name}")
def remove_project_component(
    project_name: str,
    child_name: str,
) -> dict:
    """Remove a component relationship.
    
    Removes the parent-child relationship between two projects.
    Does not delete either project.
    """
    with get_session() as session:
        # Get parent project
        parent = session.exec(
            select(Project).where(Project.name == project_name)
        ).first()
        
        if not parent:
            raise HTTPException(status_code=404, detail=f"Parent project '{project_name}' not found")
        
        # Get child project
        child = session.exec(
            select(Project).where(Project.name == child_name)
        ).first()
        
        if not child:
            raise HTTPException(status_code=404, detail=f"Child project '{child_name}' not found")
        
        # Get existing relationship
        component = session.exec(
            select(ProjectComponent)
            .where(ProjectComponent.parent_id == parent.id)
            .where(ProjectComponent.child_id == child.id)
        ).first()
        
        if not component:
            raise HTTPException(
                status_code=404,
                detail=f"No component relationship exists between '{project_name}' and '{child_name}'"
            )
        
        session.delete(component)
        session.commit()
        
        return {
            "status": "removed",
            "parent": project_name,
            "child": child_name,
        }


@app.get("/components", response_model=list[ComponentInfo])
def list_all_components(
    relationship_type: Optional[str] = Query(None, description="Filter by relationship type"),
) -> list[ComponentInfo]:
    """List all component relationships in the database.
    
    Returns all parent-child relationships, optionally filtered
    by relationship type.
    """
    with get_session() as session:
        stmt = select(ProjectComponent)
        
        if relationship_type:
            stmt = stmt.where(ProjectComponent.relationship_type == relationship_type)
        
        stmt = stmt.order_by(ProjectComponent.parent_id, ProjectComponent.order)
        
        components = session.exec(stmt).all()
        
        results = []
        for comp in components:
            parent = session.get(Project, comp.parent_id)
            child = session.get(Project, comp.child_id)
            if parent and child:
                results.append(ComponentInfo(
                    parent_id=parent.id,
                    parent_name=parent.name,
                    child_id=child.id,
                    child_name=child.name,
                    relationship_type=comp.relationship_type,
                    order=comp.order,
                ))
        
        return results
