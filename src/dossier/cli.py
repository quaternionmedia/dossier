"""Click CLI for Dossier."""

import os
from pathlib import Path
from typing import Optional

import click
from sqlmodel import Session, SQLModel, create_engine, select
from trogon import tui

from dossier.models import (
    DocumentationLevel,
    DocumentSection,
    Project,
    ProjectBranch,
    ProjectComponent,
    ProjectContributor,
    ProjectDependency,
    ProjectIssue,
    ProjectLanguage,
    ProjectPullRequest,
    ProjectRelease,
)
from dossier.parsers import GitHubParser, ParserRegistry


# Database setup
DATABASE_URL = "sqlite:///dossier.db"
engine = create_engine(DATABASE_URL, echo=False)


def init_db() -> None:
    """Initialize the database."""
    SQLModel.metadata.create_all(engine)


def get_session() -> Session:
    """Get database session."""
    return Session(engine)


@tui()
@click.group()
@click.version_option(version="0.1.0", prog_name="dossier")
def cli() -> None:
    """Dossier - Documentation standardization tool.
    
    Auto-parse project documentation and query at different detail levels.
    
    Quick start:
        dossier dashboard         Launch interactive TUI dashboard
        dossier tui               Launch command explorer (Trogon)
        dossier projects list     List all projects
        dossier github sync URL   Sync a GitHub repo
    """
    init_db()


@cli.command()
def dashboard() -> None:
    """Launch the interactive TUI dashboard.
    
    Full-featured terminal UI for project tracking with:
    - Project list with search
    - Real-time sync status
    - Documentation browser
    - Component tree view
    
    Keyboard shortcuts:
        q - Quit
        r - Refresh
        s - Sync selected project
        a - Add project
        d - Delete project
        / - Search
        ? - Help
    """
    from dossier.tui import DossierApp
    app = DossierApp()
    app.run()


# =============================================================================
# Projects Commands - Manage registered projects
# =============================================================================


@cli.group()
def projects() -> None:
    """Manage registered projects.
    
    Commands for listing, adding, removing, and inspecting projects.
    """
    pass


@projects.command("list")
@click.option("--verbose", "-v", is_flag=True, help="Show detailed information")
@click.option("--synced", is_flag=True, help="Show only GitHub-synced projects")
def projects_list(verbose: bool, synced: bool) -> None:
    """List all registered projects."""
    with get_session() as session:
        stmt = select(Project)
        projects = session.exec(stmt).all()
        
        if synced:
            projects = [p for p in projects if p.last_synced_at]
        
        if not projects:
            click.echo("No projects registered.")
            return
        
        click.echo("\n📁 Registered Projects:")
        click.echo("=" * 50)
        
        for project in sorted(projects, key=lambda p: p.name):
            # Count docs for this project
            doc_count = len(session.exec(
                select(DocumentSection).where(DocumentSection.project_id == project.id)
            ).all())
            
            # Project name with badges
            badges = []
            if project.github_stars:
                badges.append(f"⭐{project.github_stars}")
            if doc_count:
                badges.append(f"📄{doc_count}")
            
            badge_str = f" [{' '.join(badges)}]" if badges else ""
            click.echo(f"\n  {project.name}{badge_str}")
            
            if verbose or project.description:
                if project.description:
                    desc = project.description[:60] + "..." if len(project.description) > 60 else project.description
                    click.echo(f"    {desc}")
            
            if verbose:
                if project.repository_url:
                    click.echo(f"    URL: {project.repository_url}")
                if project.documentation_path:
                    click.echo(f"    Docs: {project.documentation_path}")
                if project.last_synced_at:
                    click.echo(f"    Synced: {project.last_synced_at.strftime('%Y-%m-%d %H:%M')}")
        
        click.echo(f"\nTotal: {len(projects)} projects")


@projects.command("add")
@click.argument("name")
@click.option("--description", "-d", help="Project description")
@click.option("--repo-url", "-r", help="Repository URL")
@click.option("--docs-path", "-p", help="Path to documentation files")
def projects_add(
    name: str,
    description: Optional[str],
    repo_url: Optional[str],
    docs_path: Optional[str],
) -> None:
    """Add a new project.
    
    NAME: Unique name for the project
    """
    with get_session() as session:
        existing = session.exec(
            select(Project).where(Project.name == name)
        ).first()
        if existing:
            click.echo(f"Error: Project '{name}' already exists.", err=True)
            raise SystemExit(1)
        
        project = Project(
            name=name,
            description=description,
            repository_url=repo_url,
            documentation_path=docs_path,
        )
        session.add(project)
        session.commit()
        click.echo(f"✓ Added project: {name}")


@projects.command("remove")
@click.argument("name")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
@click.option("--keep-docs", is_flag=True, help="Keep associated documentation")
def projects_remove(name: str, yes: bool, keep_docs: bool) -> None:
    """Remove a project.
    
    NAME: Name of the project to remove
    """
    with get_session() as session:
        project = session.exec(
            select(Project).where(Project.name == name)
        ).first()
        if not project:
            click.echo(f"Error: Project '{name}' not found.", err=True)
            raise SystemExit(1)
        
        # Count docs
        doc_count = len(session.exec(
            select(DocumentSection).where(DocumentSection.project_id == project.id)
        ).all())
        
        if not yes:
            msg = f"Remove project '{name}'"
            if doc_count and not keep_docs:
                msg += f" and {doc_count} documentation sections"
            msg += "?"
            click.confirm(msg, abort=True)
        
        # Remove docs unless keeping
        if not keep_docs:
            docs = session.exec(
                select(DocumentSection).where(DocumentSection.project_id == project.id)
            ).all()
            for doc in docs:
                session.delete(doc)
        
        # Remove component relationships
        components = session.exec(
            select(ProjectComponent).where(
                (ProjectComponent.parent_id == project.id) | 
                (ProjectComponent.child_id == project.id)
            )
        ).all()
        for comp in components:
            session.delete(comp)
        
        session.delete(project)
        session.commit()
        
        click.echo(f"✓ Removed project: {name}")
        if doc_count and not keep_docs:
            click.echo(f"  Deleted {doc_count} documentation sections")


@projects.command("show")
@click.argument("name")
def projects_show(name: str) -> None:
    """Show detailed information about a project.
    
    NAME: Name of the project to inspect
    """
    with get_session() as session:
        project = session.exec(
            select(Project).where(Project.name == name)
        ).first()
        if not project:
            click.echo(f"Error: Project '{name}' not found.", err=True)
            raise SystemExit(1)
        
        # Count docs by level
        docs = session.exec(
            select(DocumentSection).where(DocumentSection.project_id == project.id)
        ).all()
        
        level_counts = {}
        for doc in docs:
            level_counts[doc.level.value] = level_counts.get(doc.level.value, 0) + 1
        
        # Get components
        child_components = session.exec(
            select(ProjectComponent).where(ProjectComponent.parent_id == project.id)
        ).all()
        parent_components = session.exec(
            select(ProjectComponent).where(ProjectComponent.child_id == project.id)
        ).all()
        
        click.echo(f"\n{'=' * 50}")
        click.echo(f"  {project.name}")
        click.echo(f"{'=' * 50}")
        
        if project.description:
            click.echo(f"\n{project.description}")
        
        click.echo("\n📋 Details:")
        click.echo(f"  ID: {project.id}")
        if project.repository_url:
            click.echo(f"  Repository: {project.repository_url}")
        if project.documentation_path:
            click.echo(f"  Docs Path: {project.documentation_path}")
        click.echo(f"  Created: {project.created_at.strftime('%Y-%m-%d %H:%M')}")
        click.echo(f"  Updated: {project.updated_at.strftime('%Y-%m-%d %H:%M')}")
        
        if project.github_owner or project.github_stars:
            click.echo("\n🐙 GitHub:")
            if project.github_owner:
                click.echo(f"  Owner: {project.github_owner}")
            if project.github_repo:
                click.echo(f"  Repo: {project.github_repo}")
            if project.github_stars:
                click.echo(f"  Stars: {project.github_stars:,}")
            if project.github_language:
                click.echo(f"  Language: {project.github_language}")
            if project.last_synced_at:
                click.echo(f"  Last Synced: {project.last_synced_at.strftime('%Y-%m-%d %H:%M')}")
        
        if docs:
            click.echo("\n📄 Documentation:")
            click.echo(f"  Total Sections: {len(docs)}")
            for level, count in sorted(level_counts.items()):
                click.echo(f"    {level}: {count}")
        
        if child_components:
            click.echo("\n🔗 Components (children):")
            for comp in child_components:
                child = session.exec(select(Project).where(Project.id == comp.child_id)).first()
                if child:
                    click.echo(f"  → {child.name} [{comp.relationship_type}]")
        
        if parent_components:
            click.echo("\n🔗 Part of (parents):")
            for comp in parent_components:
                parent = session.exec(select(Project).where(Project.id == comp.parent_id)).first()
                if parent:
                    click.echo(f"  ← {parent.name} [{comp.relationship_type}]")
        
        click.echo()


@projects.command("rename")
@click.argument("old_name")
@click.argument("new_name")
def projects_rename(old_name: str, new_name: str) -> None:
    """Rename a project.
    
    OLD_NAME: Current name of the project
    NEW_NAME: New name for the project
    """
    with get_session() as session:
        project = session.exec(
            select(Project).where(Project.name == old_name)
        ).first()
        if not project:
            click.echo(f"Error: Project '{old_name}' not found.", err=True)
            raise SystemExit(1)
        
        # Check if new name exists
        existing = session.exec(
            select(Project).where(Project.name == new_name)
        ).first()
        if existing:
            click.echo(f"Error: Project '{new_name}' already exists.", err=True)
            raise SystemExit(1)
        
        project.name = new_name
        session.add(project)
        session.commit()
        click.echo(f"✓ Renamed '{old_name}' to '{new_name}'")


# =============================================================================
# Parse and Query Commands
# =============================================================================


@cli.command()
@click.argument("project_name")
@click.argument("path", type=click.Path(exists=True))
def parse(project_name: str, path: str) -> None:
    """Parse documentation files for a project.
    
    PROJECT_NAME: Name of the registered project
    PATH: Path to documentation file or directory
    """
    with get_session() as session:
        # Get project
        project = session.exec(
            select(Project).where(Project.name == project_name)
        ).first()
        if not project:
            click.echo(f"Error: Project '{project_name}' not found.", err=True)
            raise SystemExit(1)
        
        registry = ParserRegistry.default()
        path_obj = Path(path)
        files_to_parse: list[Path] = []
        
        if path_obj.is_file():
            files_to_parse = [path_obj]
        else:
            # Find all parseable files in directory
            for ext in [".md", ".markdown"]:
                files_to_parse.extend(path_obj.rglob(f"*{ext}"))
        
        total_sections = 0
        for file_path in files_to_parse:
            parser = registry.get_parser(file_path)
            if not parser:
                click.echo(f"  Skipping {file_path} (no parser available)")
                continue
            
            content = file_path.read_text(encoding="utf-8")
            sections = parser.parse(
                content,
                source_file=str(file_path),
                project_id=project.id,
            )
            
            for section in sections:
                session.add(section)
                total_sections += 1
            
            click.echo(f"  Parsed {file_path.name}: {len(sections)} sections")
        
        session.commit()
        click.echo(f"\nTotal sections added: {total_sections}")


@cli.command()
@click.argument("project_name")
@click.option(
    "--level",
    "-l",
    type=click.Choice(["summary", "overview", "detailed", "technical"]),
    default="overview",
    help="Level of detail",
)
@click.option("--section-type", "-t", help="Filter by section type")
@click.option("--search", "-s", help="Search term")
def query(
    project_name: str,
    level: str,
    section_type: Optional[str],
    search: Optional[str],
) -> None:
    """Query documentation for a project.
    
    PROJECT_NAME: Name of the project to query
    """
    doc_level = DocumentationLevel(level)
    
    with get_session() as session:
        # Get project
        project = session.exec(
            select(Project).where(Project.name == project_name)
        ).first()
        if not project:
            click.echo(f"Error: Project '{project_name}' not found.", err=True)
            raise SystemExit(1)
        
        # Build query
        level_order = [
            DocumentationLevel.SUMMARY,
            DocumentationLevel.OVERVIEW,
            DocumentationLevel.DETAILED,
            DocumentationLevel.TECHNICAL,
        ]
        max_level_idx = level_order.index(doc_level)
        allowed_levels = level_order[: max_level_idx + 1]
        
        stmt = select(DocumentSection).where(
            DocumentSection.project_id == project.id,
            DocumentSection.level.in_(allowed_levels),
        )
        
        if section_type:
            stmt = stmt.where(DocumentSection.section_type == section_type)
        
        stmt = stmt.order_by(DocumentSection.order)
        sections = list(session.exec(stmt).all())
        
        # Apply search filter
        if search:
            search_lower = search.lower()
            sections = [
                s
                for s in sections
                if search_lower in s.title.lower() or search_lower in s.content.lower()
            ]
        
        if not sections:
            click.echo("No documentation found matching criteria.")
            return
        
        click.echo(f"\n=== {project_name} Documentation ({level}) ===\n")
        for section in sections:
            click.echo(f"## {section.title}")
            click.echo(f"   Type: {section.section_type} | Level: {section.level.value}")
            click.echo(f"\n{section.content}\n")
            click.echo("-" * 40)


@cli.command()
@click.option("--host", default="127.0.0.1", help="Host to bind to")
@click.option("--port", default=8000, help="Port to bind to")
@click.option("--reload", is_flag=True, help="Enable auto-reload")
def serve(host: str, port: int, reload: bool) -> None:
    """Start the Dossier API server."""
    import uvicorn
    
    click.echo(f"Starting Dossier API server at http://{host}:{port}")
    click.echo("Press Ctrl+C to stop")
    uvicorn.run(
        "dossier.api.main:app",
        host=host,
        port=port,
        reload=reload,
    )


# GitHub commands group
@cli.group()
def github() -> None:
    """GitHub repository commands."""
    pass


@github.command("sync")
@click.argument("repo_url")
@click.option("--name", "-n", help="Project name (default: repo name)")
@click.option("--token", "-t", envvar="GITHUB_TOKEN", help="GitHub personal access token")
@click.option("--description", "-d", help="Override repository description")
@click.option("--no-docs", is_flag=True, help="Skip parsing docs/ folder")
def github_sync(
    repo_url: str,
    name: Optional[str],
    token: Optional[str],
    description: Optional[str],
    no_docs: bool,
) -> None:
    """Sync a GitHub repository as a project.
    
    REPO_URL: GitHub repository URL (e.g., https://github.com/owner/repo)
    
    This command will:
    1. Fetch repository metadata from GitHub
    2. Register or update the project in Dossier
    3. Parse README and documentation files
    4. Fetch languages, dependencies, contributors, and issues
    
    Set GITHUB_TOKEN environment variable for private repos or higher rate limits.
    """
    from dossier.parsers.github import GitHubClient
    from dossier.models import utcnow
    
    with get_session() as session:
        with GitHubParser(token) as parser:
            click.echo(f"Fetching repository: {repo_url}")
            
            try:
                repo, sections = parser.parse_repo_url(
                    repo_url,
                    include_docs_folder=not no_docs,
                )
            except Exception as e:
                click.echo(f"Error fetching repository: {e}", err=True)
                raise SystemExit(1)
            
            project_name = name or f"{repo.owner}/{repo.name}"
            
            # Check if project exists
            existing = session.exec(
                select(Project).where(Project.name == project_name)
            ).first()
            
            if existing:
                click.echo(f"Updating existing project: {project_name}")
                existing.description = description or repo.description
                existing.repository_url = repo.html_url
                existing.github_owner = repo.owner
                existing.github_repo = repo.name
                existing.github_stars = repo.stars
                existing.github_language = repo.language
                existing.last_synced_at = utcnow()
                existing.updated_at = utcnow()
                project = existing
                
                # Remove old sections for this project
                old_sections = session.exec(
                    select(DocumentSection).where(
                        DocumentSection.project_id == existing.id
                    )
                ).all()
                for old_section in old_sections:
                    session.delete(old_section)
            else:
                click.echo(f"Creating new project: {project_name}")
                project = Project(
                    name=project_name,
                    description=description or repo.description,
                    repository_url=repo.html_url,
                    github_owner=repo.owner,
                    github_repo=repo.name,
                    github_stars=repo.stars,
                    github_language=repo.language,
                    last_synced_at=utcnow(),
                )
                session.add(project)
                session.flush()  # Get project ID
            
            # Add sections with correct project_id
            for section in sections:
                section.project_id = project.id
                session.add(section)
            
            # Fetch extended data
            click.echo("  Fetching extended data...")
            
            with GitHubClient(token) as client:
                # Languages
                languages = client.get_languages(repo.owner, repo.name)
                old_langs = session.exec(
                    select(ProjectLanguage).where(ProjectLanguage.project_id == project.id)
                ).all()
                for old in old_langs:
                    session.delete(old)
                for lang in languages:
                    session.add(ProjectLanguage(
                        project_id=project.id,
                        language=lang["language"],
                        bytes_count=lang.get("bytes_count", 0),
                        percentage=lang.get("percentage", 0.0),
                        file_extensions=lang.get("file_extensions"),
                        encoding=lang.get("encoding"),
                    ))
                
                # Dependencies
                dependencies = client.get_dependencies(repo.owner, repo.name)
                old_deps = session.exec(
                    select(ProjectDependency).where(ProjectDependency.project_id == project.id)
                ).all()
                for old in old_deps:
                    session.delete(old)
                for dep in dependencies:
                    session.add(ProjectDependency(
                        project_id=project.id,
                        name=dep["name"],
                        version_spec=dep.get("version_spec"),
                        dep_type=dep.get("dep_type", "runtime"),
                        source=dep.get("source", "unknown"),
                    ))
                
                # Contributors
                contributors = client.get_contributors(repo.owner, repo.name)
                old_contribs = session.exec(
                    select(ProjectContributor).where(ProjectContributor.project_id == project.id)
                ).all()
                for old in old_contribs:
                    session.delete(old)
                for contrib in contributors:
                    session.add(ProjectContributor(
                        project_id=project.id,
                        username=contrib["username"],
                        avatar_url=contrib.get("avatar_url"),
                        contributions=contrib.get("contributions", 0),
                        profile_url=contrib.get("profile_url"),
                    ))
                
                # Issues
                issues = client.get_issues(repo.owner, repo.name, state="all")
                old_issues = session.exec(
                    select(ProjectIssue).where(ProjectIssue.project_id == project.id)
                ).all()
                for old in old_issues:
                    session.delete(old)
                for issue in issues:
                    session.add(ProjectIssue(
                        project_id=project.id,
                        issue_number=issue["issue_number"],
                        title=issue["title"],
                        state=issue.get("state", "open"),
                        author=issue.get("author"),
                        labels=issue.get("labels"),
                    ))
                
                # Branches
                branches = client.get_branches(repo.owner, repo.name)
                old_branches = session.exec(
                    select(ProjectBranch).where(ProjectBranch.project_id == project.id)
                ).all()
                for old in old_branches:
                    session.delete(old)
                for branch in branches:
                    session.add(ProjectBranch(
                        project_id=project.id,
                        name=branch["name"],
                        is_default=branch.get("is_default", False),
                        is_protected=branch.get("is_protected", False),
                        commit_sha=branch.get("commit_sha"),
                        commit_message=branch.get("commit_message"),
                        commit_author=branch.get("commit_author"),
                        commit_date=branch.get("commit_date"),
                    ))
                
                # Pull Requests
                pull_requests = client.get_pull_requests(repo.owner, repo.name, state="all")
                old_prs = session.exec(
                    select(ProjectPullRequest).where(ProjectPullRequest.project_id == project.id)
                ).all()
                for old in old_prs:
                    session.delete(old)
                for pr in pull_requests:
                    session.add(ProjectPullRequest(
                        project_id=project.id,
                        pr_number=pr["pr_number"],
                        title=pr["title"],
                        state=pr.get("state", "open"),
                        author=pr.get("author"),
                        base_branch=pr.get("base_branch"),
                        head_branch=pr.get("head_branch"),
                        is_draft=pr.get("is_draft", False),
                        is_merged=pr.get("is_merged", False),
                        additions=pr.get("additions", 0),
                        deletions=pr.get("deletions", 0),
                        labels=pr.get("labels"),
                        pr_created_at=pr.get("pr_created_at"),
                        pr_updated_at=pr.get("pr_updated_at"),
                        pr_merged_at=pr.get("pr_merged_at"),
                    ))
                
                # Releases
                releases = client.get_releases(repo.owner, repo.name)
                old_releases = session.exec(
                    select(ProjectRelease).where(ProjectRelease.project_id == project.id)
                ).all()
                for old in old_releases:
                    session.delete(old)
                for release in releases:
                    session.add(ProjectRelease(
                        project_id=project.id,
                        tag_name=release["tag_name"],
                        name=release.get("name"),
                        body=release.get("body"),
                        is_prerelease=release.get("is_prerelease", False),
                        is_draft=release.get("is_draft", False),
                        author=release.get("author"),
                        target_commitish=release.get("target_commitish"),
                        release_created_at=release.get("release_created_at"),
                        release_published_at=release.get("release_published_at"),
                    ))
            
            session.commit()
            
            click.echo(f"\n✓ Synced: {repo.full_name}")
            click.echo(f"  Project: {project_name}")
            click.echo(f"  Description: {repo.description or 'N/A'}")
            click.echo(f"  Stars: {repo.stars}")
            click.echo(f"  Language: {repo.language or 'N/A'}")
            click.echo(f"  📄 Docs: {len(sections)}")
            click.echo(f"  💻 Languages: {len(languages)}")
            click.echo(f"  📦 Dependencies: {len(dependencies)}")
            click.echo(f"  👥 Contributors: {len(contributors)}")
            click.echo(f"  🐛 Issues: {len(issues)}")
            click.echo(f"  🌿 Branches: {len(branches)}")
            click.echo(f"  🔀 Pull Requests: {len(pull_requests)}")
            click.echo(f"  🏷️  Releases: {len(releases)}")


@github.command("search")
@click.argument("query")
@click.option("--limit", "-l", default=10, help="Number of results")
@click.option("--token", "-t", envvar="GITHUB_TOKEN", help="GitHub personal access token")
@click.option("--sort", type=click.Choice(["stars", "forks", "updated"]), default="stars")
def github_search(query: str, limit: int, token: Optional[str], sort: str) -> None:
    """Search GitHub repositories.
    
    QUERY: Search query (supports GitHub search syntax)
    
    Examples:
        dossier github search "fastapi"
        dossier github search "language:python topic:cli"
        dossier github search "org:microsoft language:typescript"
    """
    from dossier.parsers import GitHubClient
    
    with GitHubClient(token) as client:
        try:
            repos = client.search_repos(query, sort=sort, per_page=limit)
        except Exception as e:
            click.echo(f"Error searching: {e}", err=True)
            raise SystemExit(1)
        
        if not repos:
            click.echo("No repositories found.")
            return
        
        click.echo(f"\nFound {len(repos)} repositories:\n")
        click.echo("-" * 60)
        
        for repo in repos:
            click.echo(f"  {repo.full_name} ★ {repo.stars}")
            if repo.description:
                # Truncate long descriptions
                desc = repo.description[:60] + "..." if len(repo.description) > 60 else repo.description
                click.echo(f"    {desc}")
            if repo.language:
                click.echo(f"    Language: {repo.language}")
            click.echo(f"    URL: {repo.html_url}")
            click.echo()


@github.command("info")
@click.argument("repo_url")
@click.option("--token", "-t", envvar="GITHUB_TOKEN", help="GitHub personal access token")
def github_info(repo_url: str, token: Optional[str]) -> None:
    """Show information about a GitHub repository.
    
    REPO_URL: GitHub repository URL
    """
    from dossier.parsers import GitHubClient
    
    with GitHubClient(token) as client:
        try:
            repo = client.get_repo_from_url(repo_url)
        except Exception as e:
            click.echo(f"Error fetching repository: {e}", err=True)
            raise SystemExit(1)
        
        click.echo(f"\n{repo.full_name}")
        click.echo("=" * 40)
        click.echo(f"Description: {repo.description or 'N/A'}")
        click.echo(f"URL: {repo.html_url}")
        click.echo(f"Default branch: {repo.default_branch}")
        click.echo(f"Language: {repo.language or 'N/A'}")
        click.echo(f"Stars: {repo.stars}")
        if repo.topics:
            click.echo(f"Topics: {', '.join(repo.topics)}")
        
        # Check for docs
        docs = client.list_docs_files(repo.owner, repo.name)
        readme = client.get_readme(repo.owner, repo.name)
        
        click.echo(f"\nDocumentation:")
        click.echo(f"  README: {'Yes' if readme else 'No'}")
        click.echo(f"  Doc files: {len(docs)}")
        if docs:
            for doc in docs[:5]:  # Show first 5
                click.echo(f"    - {doc['path']}")
            if len(docs) > 5:
                click.echo(f"    ... and {len(docs) - 5} more")


def _sync_repos_batch(
    repos: list,
    token: Optional[str],
    session,
    parent_project,
    owner_name: str,
    no_docs: bool,
    batch_size: int = 5,
    delay_between_batches: float = 2.0,
    force: bool = False,
) -> tuple[int, int, int, bool]:
    """Sync repositories in intelligent batches with rate limit handling.
    
    Returns:
        Tuple of (synced_count, failed_count, skipped_count, was_rate_limited)
    """
    from dossier.parsers import GitHubClient
    from dossier.parsers.github import BatchResult
    from dossier.models import utcnow
    import time
    
    synced = 0
    failed = 0
    skipped = 0
    rate_limited = False
    
    total = len(repos)
    
    with GitHubClient(token, respect_rate_limit=True) as client:
        # Check rate limit before starting
        try:
            rate_info = client.check_rate_limit()
            click.echo(f"📊 Rate limit: {rate_info.remaining}/{rate_info.limit} remaining")
            if rate_info.remaining < 10:
                click.echo(click.style(
                    f"⚠️  Low rate limit! Consider using --token for higher limits.",
                    fg="yellow"
                ))
        except Exception:
            pass  # Continue without rate info
        
        with GitHubParser(token) as parser:
            # Process in batches
            for batch_start in range(0, total, batch_size):
                batch_end = min(batch_start + batch_size, total)
                batch_repos = repos[batch_start:batch_end]
                batch_num = (batch_start // batch_size) + 1
                total_batches = (total + batch_size - 1) // batch_size
                
                click.echo(f"\n📦 Batch {batch_num}/{total_batches} ({len(batch_repos)} repos)")
                
                for i, repo in enumerate(batch_repos):
                    repo_num = batch_start + i + 1
                    click.echo(f"  [{repo_num}/{total}] {repo.full_name}...", nl=False)
                    
                    # Check if already synced recently (within last hour)
                    project_name = f"{owner_name}/{repo.name}"
                    existing = session.exec(
                        select(Project).where(Project.name == project_name)
                    ).first()
                    
                    if existing and existing.last_synced_at and not force:
                        from datetime import timedelta, timezone
                        # Handle timezone-naive datetimes from SQLite
                        last_synced = existing.last_synced_at
                        if last_synced.tzinfo is None:
                            last_synced = last_synced.replace(tzinfo=timezone.utc)
                        age = utcnow() - last_synced
                        if age < timedelta(hours=1):
                            click.echo(click.style(" ⏭ skipped (recently synced)", fg="cyan"))
                            skipped += 1
                            continue
                    
                    try:
                        _, sections = parser.parse_repo(
                            repo.owner,
                            repo.name,
                            include_docs_folder=not no_docs,
                        )
                        
                        if existing:
                            existing.description = repo.description
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
                            for old in old_sections:
                                session.delete(old)
                        else:
                            project = Project(
                                name=project_name,
                                description=repo.description,
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
                        
                        # Fetch and store extended data
                        try:
                            # Languages
                            languages = client.get_languages(repo.owner, repo.name)
                            old_langs = session.exec(
                                select(ProjectLanguage).where(
                                    ProjectLanguage.project_id == project.id
                                )
                            ).all()
                            for old in old_langs:
                                session.delete(old)
                            for lang in languages:
                                session.add(ProjectLanguage(
                                    project_id=project.id,
                                    language=lang["language"],
                                    bytes_count=lang.get("bytes_count", 0),
                                    percentage=lang.get("percentage", 0.0),
                                    file_extensions=lang.get("file_extensions"),
                                    encoding=lang.get("encoding"),
                                ))
                            
                            # Dependencies
                            dependencies = client.get_dependencies(repo.owner, repo.name)
                            old_deps = session.exec(
                                select(ProjectDependency).where(
                                    ProjectDependency.project_id == project.id
                                )
                            ).all()
                            for old in old_deps:
                                session.delete(old)
                            for dep in dependencies:
                                session.add(ProjectDependency(
                                    project_id=project.id,
                                    name=dep["name"],
                                    version_spec=dep.get("version_spec"),
                                    dep_type=dep.get("dep_type", "runtime"),
                                    source=dep.get("source", "unknown"),
                                ))
                            
                            # Contributors (limit to top 10 for batch)
                            contributors = client.get_contributors(
                                repo.owner, repo.name, max_contributors=10
                            )
                            old_contribs = session.exec(
                                select(ProjectContributor).where(
                                    ProjectContributor.project_id == project.id
                                )
                            ).all()
                            for old in old_contribs:
                                session.delete(old)
                            for contrib in contributors:
                                session.add(ProjectContributor(
                                    project_id=project.id,
                                    username=contrib["username"],
                                    avatar_url=contrib.get("avatar_url"),
                                    contributions=contrib.get("contributions", 0),
                                    profile_url=contrib.get("profile_url"),
                                ))
                            
                            # Issues (limit to 20 for batch)
                            issues = client.get_issues(
                                repo.owner, repo.name, state="all", max_issues=20
                            )
                            old_issues = session.exec(
                                select(ProjectIssue).where(
                                    ProjectIssue.project_id == project.id
                                )
                            ).all()
                            for old in old_issues:
                                session.delete(old)
                            for issue in issues:
                                session.add(ProjectIssue(
                                    project_id=project.id,
                                    issue_number=issue["issue_number"],
                                    title=issue["title"],
                                    state=issue.get("state", "open"),
                                    author=issue.get("author"),
                                    labels=issue.get("labels"),
                                ))
                            
                            # Branches (limit to 20 for batch)
                            branches = client.get_branches(
                                repo.owner, repo.name, max_branches=20
                            )
                            old_branches = session.exec(
                                select(ProjectBranch).where(
                                    ProjectBranch.project_id == project.id
                                )
                            ).all()
                            for old in old_branches:
                                session.delete(old)
                            for branch in branches:
                                session.add(ProjectBranch(
                                    project_id=project.id,
                                    name=branch["name"],
                                    is_default=branch.get("is_default", False),
                                    is_protected=branch.get("is_protected", False),
                                    commit_sha=branch.get("commit_sha"),
                                    commit_message=branch.get("commit_message"),
                                    commit_author=branch.get("commit_author"),
                                    commit_date=branch.get("commit_date"),
                                ))
                            
                            # Pull Requests (limit to 20 for batch)
                            pull_requests = client.get_pull_requests(
                                repo.owner, repo.name, state="all", max_prs=20
                            )
                            old_prs = session.exec(
                                select(ProjectPullRequest).where(
                                    ProjectPullRequest.project_id == project.id
                                )
                            ).all()
                            for old in old_prs:
                                session.delete(old)
                            for pr in pull_requests:
                                session.add(ProjectPullRequest(
                                    project_id=project.id,
                                    pr_number=pr["pr_number"],
                                    title=pr["title"],
                                    state=pr.get("state", "open"),
                                    author=pr.get("author"),
                                    base_branch=pr.get("base_branch"),
                                    head_branch=pr.get("head_branch"),
                                    is_draft=pr.get("is_draft", False),
                                    is_merged=pr.get("is_merged", False),
                                    additions=pr.get("additions", 0),
                                    deletions=pr.get("deletions", 0),
                                    labels=pr.get("labels"),
                                    pr_created_at=pr.get("pr_created_at"),
                                    pr_updated_at=pr.get("pr_updated_at"),
                                    pr_merged_at=pr.get("pr_merged_at"),
                                ))
                            
                            # Releases (limit to 10 for batch)
                            releases = client.get_releases(
                                repo.owner, repo.name, max_releases=10
                            )
                            old_releases = session.exec(
                                select(ProjectRelease).where(
                                    ProjectRelease.project_id == project.id
                                )
                            ).all()
                            for old in old_releases:
                                session.delete(old)
                            for release in releases:
                                session.add(ProjectRelease(
                                    project_id=project.id,
                                    tag_name=release["tag_name"],
                                    name=release.get("name"),
                                    body=release.get("body"),
                                    is_prerelease=release.get("is_prerelease", False),
                                    is_draft=release.get("is_draft", False),
                                    author=release.get("author"),
                                    target_commitish=release.get("target_commitish"),
                                    release_created_at=release.get("release_created_at"),
                                    release_published_at=release.get("release_published_at"),
                                ))
                        except Exception:
                            pass  # Extended data is optional
                        
                        # Add as subcomponent if parent specified
                        if parent_project and project.id != parent_project.id:
                            existing_link = session.exec(
                                select(ProjectComponent).where(
                                    ProjectComponent.parent_id == parent_project.id,
                                    ProjectComponent.child_id == project.id,
                                )
                            ).first()
                            
                            if not existing_link:
                                link = ProjectComponent(
                                    parent_id=parent_project.id,
                                    child_id=project.id,
                                    relationship_type="component",
                                    order=repo_num,
                                )
                                session.add(link)
                        
                        session.commit()
                        click.echo(click.style(f" ✓ ({len(sections)} sections)", fg="green"))
                        synced += 1
                        
                    except Exception as e:
                        error_msg = str(e)
                        if "rate limit" in error_msg.lower():
                            click.echo(click.style(f" ⏸ rate limited", fg="yellow"))
                            rate_limited = True
                            # Save progress and stop
                            session.commit()
                            click.echo(click.style(
                                f"\n⚠️  Rate limit hit. Run again to continue from where you left off.",
                                fg="yellow"
                            ))
                            return synced, failed, skipped, rate_limited
                        else:
                            click.echo(click.style(f" ✗ {error_msg[:50]}", fg="red"))
                            failed += 1
                            session.rollback()
                
                # Commit batch and pause between batches (except last)
                session.commit()
                if batch_end < total:
                    # Check remaining rate limit
                    remaining = client.rate_limit.remaining
                    if remaining < 20:
                        wait_time = min(client.rate_limit.seconds_until_reset, 60)
                        if wait_time > 0:
                            click.echo(f"  ⏳ Pausing {wait_time:.0f}s (rate limit: {remaining} remaining)")
                            time.sleep(wait_time)
                    else:
                        time.sleep(delay_between_batches)
    
    return synced, failed, skipped, rate_limited


@github.command("sync-user")
@click.argument("username")
@click.option("--token", "-t", envvar="GITHUB_TOKEN", help="GitHub personal access token")
@click.option("--parent", "-p", help="Parent project to add repos as subcomponents")
@click.option("--limit", "-l", default=0, help="Max repos to sync (0 = all)")
@click.option("--skip-forks", is_flag=True, help="Skip forked repositories")
@click.option("--language", help="Filter by programming language")
@click.option("--no-docs", is_flag=True, help="Skip parsing docs/ folder")
@click.option("--batch-size", "-b", default=5, help="Repos per batch (default: 5)")
@click.option("--force", "-f", is_flag=True, help="Force re-sync even if recently synced")
def github_sync_user(
    username: str,
    token: Optional[str],
    parent: Optional[str],
    limit: int,
    skip_forks: bool,
    language: Optional[str],
    no_docs: bool,
    batch_size: int,
    force: bool,
) -> None:
    """Sync all repositories from a GitHub user account.
    
    USERNAME: GitHub username to sync repos from
    
    Features intelligent batching with:
    - Automatic retry on transient errors
    - Rate limit detection and waiting
    - Skip recently synced repos (use --force to override)
    - Resume capability (just run again to continue)
    
    Examples:
        dossier github sync-user octocat
        dossier github sync-user astral-sh --batch-size 3
        dossier github sync-user myuser --language python --force
    """
    from dossier.parsers import GitHubClient
    
    with get_session() as session:
        # Get or create parent project if specified
        parent_project = None
        if parent:
            parent_project = session.exec(
                select(Project).where(Project.name == parent)
            ).first()
            if not parent_project:
                click.echo(f"Creating parent project: {parent}")
                parent_project = Project(
                    name=parent,
                    description=f"GitHub repositories for {username}",
                    github_owner=username,
                )
                session.add(parent_project)
                session.flush()
        
        click.echo(f"🔍 Fetching repositories for user: {username}")
        
        with GitHubClient(token) as client:
            try:
                repos = client.list_user_repos(username)
            except Exception as e:
                click.echo(f"Error fetching repositories: {e}", err=True)
                raise SystemExit(1)
        
        # Apply filters
        original_count = len(repos)
        if skip_forks:
            repos = [r for r in repos if not r.name.endswith("-fork")]
        if language:
            repos = [r for r in repos if r.language and r.language.lower() == language.lower()]
        if limit > 0:
            repos = repos[:limit]
        
        click.echo(f"📋 Found {len(repos)} repositories", nl=False)
        if len(repos) != original_count:
            click.echo(f" (filtered from {original_count})")
        else:
            click.echo()
        
        if not repos:
            click.echo("No repositories to sync.")
            return
        
        synced, failed, skipped, rate_limited = _sync_repos_batch(
            repos=repos,
            token=token,
            session=session,
            parent_project=parent_project,
            owner_name=username,
            no_docs=no_docs,
            batch_size=batch_size,
            force=force,
        )
        
        click.echo(f"\n{'='*50}")
        click.echo(f"✅ Synced: {synced} | ❌ Failed: {failed} | ⏭ Skipped: {skipped}")
        if parent_project:
            click.echo(f"📁 Parent project: {parent}")
        if rate_limited:
            click.echo(click.style("💡 Tip: Run again to continue syncing remaining repos", fg="cyan"))


@github.command("sync-org")
@click.argument("org")
@click.option("--token", "-t", envvar="GITHUB_TOKEN", help="GitHub personal access token")
@click.option("--parent", "-p", help="Parent project to add repos as subcomponents")
@click.option("--limit", "-l", default=0, help="Max repos to sync (0 = all)")
@click.option("--language", help="Filter by programming language")
@click.option("--no-docs", is_flag=True, help="Skip parsing docs/ folder")
@click.option("--batch-size", "-b", default=5, help="Repos per batch (default: 5)")
@click.option("--force", "-f", is_flag=True, help="Force re-sync even if recently synced")
def github_sync_org(
    org: str,
    token: Optional[str],
    parent: Optional[str],
    limit: int,
    language: Optional[str],
    no_docs: bool,
    batch_size: int,
    force: bool,
) -> None:
    """Sync all repositories from a GitHub organization.
    
    ORG: GitHub organization name
    
    Features intelligent batching with:
    - Automatic retry on transient errors
    - Rate limit detection and waiting
    - Skip recently synced repos (use --force to override)
    - Resume capability (just run again to continue)
    
    Examples:
        dossier github sync-org microsoft --limit 10
        dossier github sync-org astral-sh --batch-size 3
        dossier github sync-org myorg --language python --force
    """
    from dossier.parsers import GitHubClient
    
    with get_session() as session:
        # Get or create parent project if specified
        parent_project = None
        if parent:
            parent_project = session.exec(
                select(Project).where(Project.name == parent)
            ).first()
            if not parent_project:
                click.echo(f"Creating parent project: {parent}")
                parent_project = Project(
                    name=parent,
                    description=f"GitHub repositories for {org}",
                    github_owner=org,
                )
                session.add(parent_project)
                session.flush()
        
        click.echo(f"🔍 Fetching repositories for org: {org}")
        
        with GitHubClient(token) as client:
            try:
                repos = client.list_org_repos(org)
            except Exception as e:
                click.echo(f"Error fetching repositories: {e}", err=True)
                raise SystemExit(1)
        
        # Apply filters
        original_count = len(repos)
        if language:
            repos = [r for r in repos if r.language and r.language.lower() == language.lower()]
        if limit > 0:
            repos = repos[:limit]
        
        click.echo(f"📋 Found {len(repos)} repositories", nl=False)
        if len(repos) != original_count:
            click.echo(f" (filtered from {original_count})")
        else:
            click.echo()
        
        if not repos:
            click.echo("No repositories to sync.")
            return
        
        synced, failed, skipped, rate_limited = _sync_repos_batch(
            repos=repos,
            token=token,
            session=session,
            parent_project=parent_project,
            owner_name=org,
            no_docs=no_docs,
            batch_size=batch_size,
            force=force,
        )
        
        click.echo(f"\n{'='*50}")
        click.echo(f"✅ Synced: {synced} | ❌ Failed: {failed} | ⏭ Skipped: {skipped}")
        if parent_project:
            click.echo(f"📁 Parent project: {parent}")
        if rate_limited:
            click.echo(click.style("💡 Tip: Run again to continue syncing remaining repos", fg="cyan"))


# Project subcomponent commands
@cli.group()
def components() -> None:
    """Manage project subcomponents."""
    pass


@components.command("add")
@click.argument("parent_name")
@click.argument("child_name")
@click.option("--type", "-t", "rel_type", default="component", 
              type=click.Choice(["component", "dependency", "related"]),
              help="Relationship type")
def add_component(parent_name: str, child_name: str, rel_type: str) -> None:
    """Add a project as a subcomponent of another project.
    
    PARENT_NAME: Name of the parent project
    CHILD_NAME: Name of the child project to add
    """
    with get_session() as session:
        parent = session.exec(
            select(Project).where(Project.name == parent_name)
        ).first()
        if not parent:
            click.echo(f"Error: Parent project '{parent_name}' not found.", err=True)
            raise SystemExit(1)
        
        child = session.exec(
            select(Project).where(Project.name == child_name)
        ).first()
        if not child:
            click.echo(f"Error: Child project '{child_name}' not found.", err=True)
            raise SystemExit(1)
        
        if parent.id == child.id:
            click.echo("Error: Cannot add a project as its own component.", err=True)
            raise SystemExit(1)
        
        existing = session.exec(
            select(ProjectComponent).where(
                ProjectComponent.parent_id == parent.id,
                ProjectComponent.child_id == child.id,
            )
        ).first()
        
        if existing:
            click.echo(f"'{child_name}' is already a {existing.relationship_type} of '{parent_name}'.")
            return
        
        # Get max order
        max_order = session.exec(
            select(ProjectComponent.order)
            .where(ProjectComponent.parent_id == parent.id)
            .order_by(ProjectComponent.order.desc())
        ).first() or 0
        
        link = ProjectComponent(
            parent_id=parent.id,
            child_id=child.id,
            relationship_type=rel_type,
            order=max_order + 1,
        )
        session.add(link)
        session.commit()
        
        click.echo(f"Added '{child_name}' as {rel_type} of '{parent_name}'")


@components.command("remove")
@click.argument("parent_name")
@click.argument("child_name")
def remove_component(parent_name: str, child_name: str) -> None:
    """Remove a subcomponent from a project.
    
    PARENT_NAME: Name of the parent project
    CHILD_NAME: Name of the child project to remove
    """
    with get_session() as session:
        parent = session.exec(
            select(Project).where(Project.name == parent_name)
        ).first()
        if not parent:
            click.echo(f"Error: Parent project '{parent_name}' not found.", err=True)
            raise SystemExit(1)
        
        child = session.exec(
            select(Project).where(Project.name == child_name)
        ).first()
        if not child:
            click.echo(f"Error: Child project '{child_name}' not found.", err=True)
            raise SystemExit(1)
        
        link = session.exec(
            select(ProjectComponent).where(
                ProjectComponent.parent_id == parent.id,
                ProjectComponent.child_id == child.id,
            )
        ).first()
        
        if not link:
            click.echo(f"'{child_name}' is not a component of '{parent_name}'.")
            return
        
        session.delete(link)
        session.commit()
        
        click.echo(f"Removed '{child_name}' from '{parent_name}'")


@components.command("list")
@click.argument("project_name")
@click.option("--recursive", "-r", is_flag=True, help="Show nested components")
def list_components(project_name: str, recursive: bool) -> None:
    """List subcomponents of a project.
    
    PROJECT_NAME: Name of the project
    """
    with get_session() as session:
        project = session.exec(
            select(Project).where(Project.name == project_name)
        ).first()
        if not project:
            click.echo(f"Error: Project '{project_name}' not found.", err=True)
            raise SystemExit(1)
        
        def print_components(proj_id: int, indent: int = 0) -> None:
            links = session.exec(
                select(ProjectComponent)
                .where(ProjectComponent.parent_id == proj_id)
                .order_by(ProjectComponent.order)
            ).all()
            
            for link in links:
                child = session.exec(
                    select(Project).where(Project.id == link.child_id)
                ).first()
                if child:
                    prefix = "  " * indent
                    type_badge = f"[{link.relationship_type}]"
                    click.echo(f"{prefix}├─ {child.name} {type_badge}")
                    if child.description:
                        click.echo(f"{prefix}│  {child.description[:50]}...")
                    if recursive:
                        print_components(child.id, indent + 1)
        
        click.echo(f"\n{project_name}")
        click.echo("=" * len(project_name))
        print_components(project.id)
        click.echo()


# =============================================================================
# Dev Commands - Development and iteration helpers
# =============================================================================


@cli.group()
def dev() -> None:
    """Development utilities for quick iteration.
    
    Commands for managing database state, debugging, and rapid development.
    """
    pass


@dev.command("reset")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt")
def dev_reset(yes: bool) -> None:
    """Reset database to fresh state (deletes all data).
    
    This will:
    - Drop all tables
    - Recreate empty tables
    - Remove any orphaned data
    
    Use with caution in production!
    """
    if not yes:
        click.confirm(
            click.style("⚠️  This will delete ALL data. Continue?", fg="yellow"),
            abort=True,
        )
    
    db_path = Path("dossier.db")
    
    # Drop and recreate tables
    SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)
    
    click.echo(click.style("✓ Database reset to fresh state", fg="green"))
    
    if db_path.exists():
        size = db_path.stat().st_size
        click.echo(f"  Database file: {db_path} ({size} bytes)")


@dev.command("clear")
@click.option("--projects", "-p", is_flag=True, help="Clear all projects")
@click.option("--docs", "-d", is_flag=True, help="Clear all document sections")
@click.option("--components", "-c", is_flag=True, help="Clear all component relationships")
@click.option("--all", "-a", "clear_all", is_flag=True, help="Clear everything")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt")
def dev_clear(
    projects: bool,
    docs: bool,
    components: bool,
    clear_all: bool,
    yes: bool,
) -> None:
    """Clear specific data from the database.
    
    Selectively remove data while keeping tables intact.
    
    Examples:
        dossier dev clear --docs          # Clear only document sections
        dossier dev clear --projects -y   # Clear projects without confirmation
        dossier dev clear --all           # Clear everything
    """
    if not any([projects, docs, components, clear_all]):
        click.echo("Specify what to clear: --projects, --docs, --components, or --all")
        raise SystemExit(1)
    
    if clear_all:
        projects = docs = components = True
    
    targets = []
    if docs:
        targets.append("document sections")
    if components:
        targets.append("component relationships")
    if projects:
        targets.append("projects")
    
    if not yes:
        click.confirm(
            f"Clear {', '.join(targets)}?",
            abort=True,
        )
    
    with get_session() as session:
        counts = {}
        
        # Order matters for foreign key constraints
        if docs:
            result = session.exec(select(DocumentSection)).all()
            counts["Document sections"] = len(result)
            for item in result:
                session.delete(item)
        
        if components:
            result = session.exec(select(ProjectComponent)).all()
            counts["Component relationships"] = len(result)
            for item in result:
                session.delete(item)
        
        if projects:
            result = session.exec(select(Project)).all()
            counts["Projects"] = len(result)
            for item in result:
                session.delete(item)
        
        session.commit()
    
    click.echo(click.style("✓ Cleared:", fg="green"))
    for name, count in counts.items():
        click.echo(f"  {name}: {count} deleted")


@dev.command("status")
def dev_status() -> None:
    """Show database status and statistics."""
    db_path = Path("dossier.db")
    
    click.echo("\n📊 Database Status")
    click.echo("=" * 40)
    
    # File info
    if db_path.exists():
        size = db_path.stat().st_size
        size_kb = size / 1024
        click.echo(f"File: {db_path.absolute()}")
        click.echo(f"Size: {size_kb:.1f} KB ({size:,} bytes)")
    else:
        click.echo(f"File: {db_path} (not created yet)")
    
    click.echo()
    
    # Table counts
    with get_session() as session:
        project_count = len(session.exec(select(Project)).all())
        doc_count = len(session.exec(select(DocumentSection)).all())
        component_count = len(session.exec(select(ProjectComponent)).all())
        
        click.echo("📁 Tables:")
        click.echo(f"  Projects:       {project_count:>6}")
        click.echo(f"  Doc Sections:   {doc_count:>6}")
        click.echo(f"  Components:     {component_count:>6}")
        
        # GitHub sync info
        synced_projects = [p for p in session.exec(select(Project)).all() if p.last_synced_at]
        
        if synced_projects:
            click.echo()
            click.echo("🔄 Recently Synced:")
            for proj in sorted(synced_projects, key=lambda p: p.last_synced_at, reverse=True)[:5]:
                sync_time = proj.last_synced_at.strftime("%Y-%m-%d %H:%M") if proj.last_synced_at else "never"
                stars = f"⭐{proj.github_stars}" if proj.github_stars else ""
                click.echo(f"  {proj.name}: {sync_time} {stars}")
    
    click.echo()


@dev.command("vacuum")
def dev_vacuum() -> None:
    """Optimize database by running VACUUM.
    
    Reclaims unused space and defragments the database file.
    """
    from sqlalchemy import text
    
    db_path = Path("dossier.db")
    size_before = db_path.stat().st_size if db_path.exists() else 0
    
    with engine.connect() as conn:
        conn.execute(text("VACUUM"))
        conn.commit()
    
    size_after = db_path.stat().st_size if db_path.exists() else 0
    saved = size_before - size_after
    
    click.echo(click.style("✓ Database vacuumed", fg="green"))
    click.echo(f"  Before: {size_before:,} bytes")
    click.echo(f"  After:  {size_after:,} bytes")
    if saved > 0:
        click.echo(f"  Saved:  {saved:,} bytes ({saved/1024:.1f} KB)")


@dev.command("dump")
@click.option("--output", "-o", type=click.Path(), help="Output file (default: stdout)")
@click.option("--format", "-f", "fmt", type=click.Choice(["json", "summary"]), default="summary")
def dev_dump(output: Optional[str], fmt: str) -> None:
    """Dump database contents for inspection.
    
    Useful for debugging and understanding current state.
    """
    import json
    
    with get_session() as session:
        projects = session.exec(select(Project)).all()
        docs = session.exec(select(DocumentSection)).all()
        components = session.exec(select(ProjectComponent)).all()
        
        if fmt == "json":
            data = {
                "projects": [
                    {
                        "id": p.id,
                        "name": p.name,
                        "description": p.description,
                        "github_owner": p.github_owner,
                        "github_stars": p.github_stars,
                        "last_synced_at": p.last_synced_at.isoformat() if p.last_synced_at else None,
                        "doc_count": len([d for d in docs if d.project_id == p.id]),
                    }
                    for p in projects
                ],
                "components": [
                    {
                        "parent_id": c.parent_id,
                        "child_id": c.child_id,
                        "relationship_type": c.relationship_type,
                    }
                    for c in components
                ],
                "stats": {
                    "total_projects": len(projects),
                    "total_docs": len(docs),
                    "total_components": len(components),
                },
            }
            content = json.dumps(data, indent=2)
        else:
            lines = ["=== Database Dump ===", ""]
            lines.append(f"Projects ({len(projects)}):")
            for p in projects:
                doc_count = len([d for d in docs if d.project_id == p.id])
                lines.append(f"  [{p.id}] {p.name} ({doc_count} docs)")
            
            lines.append("")
            lines.append(f"Components ({len(components)}):")
            for c in components:
                parent = next((p.name for p in projects if p.id == c.parent_id), "?")
                child = next((p.name for p in projects if p.id == c.child_id), "?")
                lines.append(f"  {parent} -> {child} [{c.relationship_type}]")
            
            content = "\n".join(lines)
        
        if output:
            Path(output).write_text(content)
            click.echo(f"Dumped to {output}")
        else:
            click.echo(content)


@dev.command("seed")
@click.option("--example", "-e", is_flag=True, help="Create example project with docs")
def dev_seed(example: bool) -> None:
    """Seed database with sample data for testing.
    
    Creates sample projects and documentation for development.
    """
    from dossier.models import utcnow
    
    with get_session() as session:
        if example:
            # Create a sample project
            project = Project(
                name="example-project",
                description="An example project for testing Dossier",
                repository_url="https://github.com/example/project",
                documentation_path="./docs",
            )
            session.add(project)
            session.flush()
            
            # Add sample documentation
            sections = [
                DocumentSection(
                    project_id=project.id,
                    title="Getting Started",
                    content="This is the getting started guide for the example project.",
                    level=DocumentationLevel.SUMMARY,
                    source_file="README.md",
                    section_type="guide",
                ),
                DocumentSection(
                    project_id=project.id,
                    title="Installation",
                    content="Run `pip install example-project` to install.\n\nRequirements:\n- Python 3.11+\n- pip",
                    level=DocumentationLevel.OVERVIEW,
                    source_file="README.md",
                    section_type="setup",
                ),
                DocumentSection(
                    project_id=project.id,
                    title="API Reference",
                    content="## Functions\n\n### `do_something(arg: str) -> bool`\n\nDoes something important.",
                    level=DocumentationLevel.DETAILED,
                    source_file="docs/api.md",
                    section_type="reference",
                ),
                DocumentSection(
                    project_id=project.id,
                    title="Architecture",
                    content="The system uses a layered architecture with:\n- CLI layer (Click)\n- API layer (FastAPI)\n- Data layer (SQLModel)",
                    level=DocumentationLevel.TECHNICAL,
                    source_file="docs/architecture.md",
                    section_type="development",
                ),
            ]
            for section in sections:
                session.add(section)
            
            session.commit()
            click.echo(click.style("✓ Created example project with 4 doc sections", fg="green"))
        else:
            click.echo("Use --example to create sample data")


@dev.command("test")
@click.option("--verbose", "-v", is_flag=True, help="Verbose output")
@click.option("--coverage", "-c", is_flag=True, help="Run with coverage")
@click.option("--file", "-f", "test_file", help="Run specific test file")
@click.option("--keyword", "-k", help="Run tests matching keyword")
@click.option("--failed", "-x", is_flag=True, help="Stop on first failure")
def dev_test(
    verbose: bool,
    coverage: bool,
    test_file: Optional[str],
    keyword: Optional[str],
    failed: bool,
) -> None:
    """Run the test suite.
    
    Wrapper around pytest with common options.
    
    Examples:
        dossier dev test                    # Run all tests
        dossier dev test -v                 # Verbose output
        dossier dev test -c                 # With coverage report
        dossier dev test -f test_cli.py    # Run specific file
        dossier dev test -k "github"       # Match keyword
        dossier dev test -x                 # Stop on first failure
    """
    import subprocess
    import sys
    
    cmd = [sys.executable, "-m", "pytest"]
    
    if verbose:
        cmd.append("-v")
    
    if failed:
        cmd.append("-x")
    
    if coverage:
        cmd.extend(["--cov=dossier", "--cov-report=term-missing"])
    
    if keyword:
        cmd.extend(["-k", keyword])
    
    if test_file:
        # Allow both "test_cli.py" and "tests/test_cli.py"
        if not test_file.startswith("tests/"):
            test_file = f"tests/{test_file}"
        cmd.append(test_file)
    
    click.echo(f"Running: {' '.join(cmd)}")
    click.echo("-" * 60)
    
    result = subprocess.run(cmd)
    raise SystemExit(result.returncode)


@dev.command("purge")
@click.option("--pattern", "-p", default="test", help="Pattern to match project names")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt")
@click.option("--dry-run", "-n", is_flag=True, help="Show what would be deleted")
def dev_purge(pattern: str, yes: bool, dry_run: bool) -> None:
    """Purge test/temporary projects from the database.
    
    Removes projects matching a pattern (default: 'test').
    Useful for cleaning up after test runs or development.
    
    Examples:
        dossier dev purge                   # Remove projects containing 'test'
        dossier dev purge -p "temp"        # Remove projects containing 'temp'
        dossier dev purge -n               # Dry run - show what would be deleted
        dossier dev purge -y               # Skip confirmation
    """
    with get_session() as session:
        # Find matching projects
        all_projects = session.exec(select(Project)).all()
        matches = [p for p in all_projects if pattern.lower() in p.name.lower()]
        
        if not matches:
            click.echo(f"No projects matching '{pattern}' found.")
            return
        
        click.echo(f"Found {len(matches)} projects matching '{pattern}':")
        for p in matches:
            synced = "🔄" if p.last_synced_at else "○"
            click.echo(f"  {synced} {p.name}")
        
        if dry_run:
            click.echo(click.style("\n(Dry run - no changes made)", fg="yellow"))
            return
        
        if not yes:
            click.confirm(
                click.style(f"\n⚠️  Delete {len(matches)} projects?", fg="yellow"),
                abort=True,
            )
        
        # Delete related data first
        for project in matches:
            # Delete related records
            session.exec(
                select(DocumentSection).where(DocumentSection.project_id == project.id)
            )
            for section in session.exec(
                select(DocumentSection).where(DocumentSection.project_id == project.id)
            ).all():
                session.delete(section)
            
            for lang in session.exec(
                select(ProjectLanguage).where(ProjectLanguage.project_id == project.id)
            ).all():
                session.delete(lang)
            
            for branch in session.exec(
                select(ProjectBranch).where(ProjectBranch.project_id == project.id)
            ).all():
                session.delete(branch)
            
            for dep in session.exec(
                select(ProjectDependency).where(ProjectDependency.project_id == project.id)
            ).all():
                session.delete(dep)
            
            for contrib in session.exec(
                select(ProjectContributor).where(ProjectContributor.project_id == project.id)
            ).all():
                session.delete(contrib)
            
            for issue in session.exec(
                select(ProjectIssue).where(ProjectIssue.project_id == project.id)
            ).all():
                session.delete(issue)
            
            for pr in session.exec(
                select(ProjectPullRequest).where(ProjectPullRequest.project_id == project.id)
            ).all():
                session.delete(pr)
            
            for release in session.exec(
                select(ProjectRelease).where(ProjectRelease.project_id == project.id)
            ).all():
                session.delete(release)
            
            # Delete component relationships
            for comp in session.exec(
                select(ProjectComponent).where(
                    (ProjectComponent.parent_id == project.id) |
                    (ProjectComponent.child_id == project.id)
                )
            ).all():
                session.delete(comp)
            
            session.delete(project)
        
        session.commit()
        click.echo(click.style(f"\n✓ Purged {len(matches)} projects", fg="green"))


# =============================================================================
# Database Migrations Commands
# =============================================================================


@cli.group()
def db() -> None:
    """Database migration commands (Alembic).
    
    Manage database schema migrations for consistent updates.
    
    Examples:
        dossier db upgrade          Apply all pending migrations
        dossier db downgrade        Rollback one migration
        dossier db history          Show migration history
        dossier db current          Show current revision
        dossier db revision "msg"   Create new migration
    """
    pass


@db.command("upgrade")
@click.argument("revision", default="head")
def db_upgrade(revision: str) -> None:
    """Apply migrations up to a revision.
    
    REVISION is the target revision (default: head for latest).
    
    Examples:
        dossier db upgrade           # Apply all pending migrations
        dossier db upgrade head      # Same as above
        dossier db upgrade +1        # Apply next migration only
    """
    from alembic import command
    from alembic.config import Config
    
    alembic_cfg = Config("alembic.ini")
    click.echo(f"🔄 Upgrading database to {revision}...")
    
    try:
        command.upgrade(alembic_cfg, revision)
        click.echo(click.style("✓ Database upgraded successfully", fg="green"))
    except Exception as e:
        click.echo(click.style(f"✗ Migration failed: {e}", fg="red"))
        raise click.Abort()


@db.command("downgrade")
@click.argument("revision", default="-1")
def db_downgrade(revision: str) -> None:
    """Rollback migrations.
    
    REVISION is the target revision (default: -1 for previous).
    
    Examples:
        dossier db downgrade         # Rollback one migration
        dossier db downgrade -1      # Same as above
        dossier db downgrade base    # Rollback all migrations
    """
    from alembic import command
    from alembic.config import Config
    
    alembic_cfg = Config("alembic.ini")
    click.echo(f"🔄 Downgrading database to {revision}...")
    
    try:
        command.downgrade(alembic_cfg, revision)
        click.echo(click.style("✓ Database downgraded successfully", fg="green"))
    except Exception as e:
        click.echo(click.style(f"✗ Migration failed: {e}", fg="red"))
        raise click.Abort()


@db.command("current")
def db_current() -> None:
    """Show current database revision."""
    from alembic import command
    from alembic.config import Config
    
    alembic_cfg = Config("alembic.ini")
    click.echo("📊 Current database revision:")
    command.current(alembic_cfg, verbose=True)


@db.command("history")
@click.option("--verbose", "-v", is_flag=True, help="Show detailed history")
def db_history(verbose: bool) -> None:
    """Show migration history."""
    from alembic import command
    from alembic.config import Config
    
    alembic_cfg = Config("alembic.ini")
    click.echo("📜 Migration history:")
    command.history(alembic_cfg, verbose=verbose)


@db.command("revision")
@click.argument("message")
@click.option("--autogenerate", "-a", is_flag=True, help="Auto-detect schema changes")
def db_revision(message: str, autogenerate: bool) -> None:
    """Create a new migration revision.
    
    MESSAGE is a short description of the migration.
    
    Examples:
        dossier db revision "add user table"
        dossier db revision "add index" -a   # Auto-detect changes
    """
    from alembic import command
    from alembic.config import Config
    
    alembic_cfg = Config("alembic.ini")
    click.echo(f"📝 Creating migration: {message}")
    
    try:
        command.revision(alembic_cfg, message=message, autogenerate=autogenerate)
        click.echo(click.style("✓ Migration created successfully", fg="green"))
    except Exception as e:
        click.echo(click.style(f"✗ Failed to create migration: {e}", fg="red"))
        raise click.Abort()


@db.command("stamp")
@click.argument("revision")
def db_stamp(revision: str) -> None:
    """Stamp database with revision without running migrations.
    
    Useful for marking an existing database as up-to-date.
    
    Examples:
        dossier db stamp head       # Mark as current
        dossier db stamp 001_init   # Mark specific revision
    """
    from alembic import command
    from alembic.config import Config
    
    alembic_cfg = Config("alembic.ini")
    click.echo(f"🔖 Stamping database with {revision}...")
    
    try:
        command.stamp(alembic_cfg, revision)
        click.echo(click.style("✓ Database stamped successfully", fg="green"))
    except Exception as e:
        click.echo(click.style(f"✗ Failed to stamp: {e}", fg="red"))
        raise click.Abort()


# =============================================================================
# Dossier File Commands
# =============================================================================


@cli.group("export")
def export_group() -> None:
    """Export project data to various formats.
    
    Generate .dossier files, JSON exports, and other formats.
    
    Examples:
        dossier export dossier owner/repo
        dossier export dossier owner/repo -o project.dossier
        dossier export all --format json
    """
    pass


@export_group.command("dossier")
@click.argument("project_name")
@click.option("--output", "-o", type=click.Path(), help="Output file path")
@click.option("--no-docs", is_flag=True, help="Exclude documentation overview")
@click.option("--no-activity", is_flag=True, help="Exclude activity metrics")
def export_dossier(
    project_name: str,
    output: Optional[str],
    no_docs: bool,
    no_activity: bool,
) -> None:
    """Export a project to .dossier format.
    
    PROJECT_NAME is the project to export (e.g., owner/repo).
    
    The .dossier format is a YAML-based file that provides a standardized
    overview of a project's metadata, tech stack, dependencies, and activity.
    
    Examples:
        dossier export dossier astral-sh/ruff
        dossier export dossier myproject -o myproject.dossier
    """
    from pathlib import Path
    from dossier.dossier_file import export_dossier_yaml
    
    with get_session() as session:
        project = session.exec(
            select(Project).where(Project.name == project_name)
        ).first()
        
        if not project:
            click.echo(click.style(f"Project '{project_name}' not found", fg="red"))
            raise click.Abort()
        
        # Generate output path if not specified
        if output:
            output_path = Path(output)
        else:
            # Default to {repo_name}.dossier in current directory
            safe_name = project_name.replace("/", "_")
            output_path = Path(f"{safe_name}.dossier")
        
        # Generate the dossier
        from dossier.dossier_file import generate_dossier
        import yaml
        
        dossier = generate_dossier(
            session,
            project,
            include_docs=not no_docs,
            include_activity=not no_activity,
        )
        
        # Write to file
        yaml_content = yaml.dump(
            dossier,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
            width=100,
        )
        output_path.write_text(yaml_content, encoding="utf-8")
        
        click.echo(click.style(f"✓ Exported to {output_path}", fg="green"))
        
        # Show summary
        click.echo(f"\n📄 {project.name}")
        if project.description:
            click.echo(f"   {project.description[:60]}...")
        if "tech_stack" in dossier:
            langs = ", ".join(t["name"] for t in dossier["tech_stack"][:3])
            click.echo(f"   Languages: {langs}")
        if "activity" in dossier:
            act = dossier["activity"]
            click.echo(f"   Activity: {act.get('open_issues', 0)} issues, {act.get('open_prs', 0)} PRs")


@export_group.command("all")
@click.option("--output-dir", "-d", type=click.Path(), default=".", help="Output directory")
@click.option("--format", "-f", type=click.Choice(["dossier", "json"]), default="dossier")
@click.option("--synced-only", is_flag=True, help="Only export synced projects")
def export_all(output_dir: str, format: str, synced_only: bool) -> None:
    """Export all projects.
    
    Creates one file per project in the output directory.
    
    Examples:
        dossier export all
        dossier export all -d ./exports
        dossier export all --format json
    """
    from pathlib import Path
    import json
    from dossier.dossier_file import generate_dossier
    import yaml
    
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    with get_session() as session:
        stmt = select(Project).order_by(Project.name)
        projects = session.exec(stmt).all()
        
        if synced_only:
            projects = [p for p in projects if p.last_synced_at]
        
        if not projects:
            click.echo("No projects to export")
            return
        
        click.echo(f"Exporting {len(projects)} projects to {output_path}/")
        
        for project in projects:
            safe_name = project.name.replace("/", "_")
            
            if format == "dossier":
                file_path = output_path / f"{safe_name}.dossier"
                dossier = generate_dossier(session, project)
                content = yaml.dump(
                    dossier,
                    default_flow_style=False,
                    allow_unicode=True,
                    sort_keys=False,
                )
            else:  # json
                file_path = output_path / f"{safe_name}.json"
                dossier = generate_dossier(session, project)
                content = json.dumps(dossier, indent=2, default=str)
            
            file_path.write_text(content, encoding="utf-8")
            click.echo(f"  ✓ {file_path.name}")
        
        click.echo(click.style(f"\n✓ Exported {len(projects)} projects", fg="green"))


@export_group.command("show")
@click.argument("project_name")
def export_show(project_name: str) -> None:
    """Show project dossier without saving to file.
    
    Displays the .dossier format content to stdout.
    
    Examples:
        dossier export show astral-sh/ruff
        dossier export show myproject | less
    """
    from dossier.dossier_file import generate_dossier
    import yaml
    
    with get_session() as session:
        project = session.exec(
            select(Project).where(Project.name == project_name)
        ).first()
        
        if not project:
            click.echo(click.style(f"Project '{project_name}' not found", fg="red"))
            raise click.Abort()
        
        dossier = generate_dossier(session, project)
        yaml_content = yaml.dump(
            dossier,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
            width=100,
        )
        
        click.echo(yaml_content)


# =============================================================================
# Test Command - Quick test runner
# =============================================================================


@cli.command("test")
@click.option("--verbose", "-v", is_flag=True, help="Verbose output")
@click.option("--coverage", "-c", is_flag=True, help="Run with coverage")
@click.option("--file", "-f", "test_file", help="Run specific test file")
@click.option("--keyword", "-k", help="Run tests matching keyword")
@click.option("--failed", "-x", is_flag=True, help="Stop on first failure")
@click.option("--screenshots", is_flag=True, help="Generate TUI screenshots")
def test_cmd(
    verbose: bool,
    coverage: bool,
    test_file: Optional[str],
    keyword: Optional[str],
    failed: bool,
    screenshots: bool,
) -> None:
    """Run the test suite (quick by default).
    
    Runs pytest with sensible defaults for fast iteration.
    
    Examples:
        dossier test                    # Quick run, all tests
        dossier test -v                 # Verbose output
        dossier test -c                 # With coverage report
        dossier test -f test_cli.py    # Run specific file
        dossier test -k "github"       # Match keyword
        dossier test -x                 # Stop on first failure
        dossier test --screenshots      # Generate TUI screenshots
    """
    import subprocess
    import sys
    
    cmd = [sys.executable, "-m", "pytest"]
    
    if verbose:
        cmd.append("-v")
    
    if failed:
        cmd.append("-x")
    
    if coverage:
        cmd.extend(["--cov=dossier", "--cov-report=term-missing"])
    
    if keyword:
        cmd.extend(["-k", keyword])
    
    if screenshots:
        cmd.append("--screenshots")
    
    if test_file:
        # Allow both "test_cli.py" and "tests/test_cli.py"
        if not test_file.startswith("tests/"):
            test_file = f"tests/{test_file}"
        cmd.append(test_file)
    
    click.echo(f"Running: {' '.join(cmd)}")
    click.echo("-" * 60)
    
    result = subprocess.run(cmd)
    raise SystemExit(result.returncode)


@cli.command("init")
@click.argument("project_name", required=False)
@click.option("--output", "-o", type=click.Path(), help="Output file path")
def init_dossier(project_name: Optional[str], output: Optional[str]) -> None:
    """Initialize a new .dossier file.
    
    Creates a template .dossier file that can be edited manually.
    If PROJECT_NAME is provided, it will be used as the project name.
    
    Examples:
        dossier init                    # Create template
        dossier init myproject          # Create with name
        dossier init myproject -o .dossier
    """
    from pathlib import Path
    from dossier.dossier_file import create_dossier_from_scratch
    import yaml
    
    # Determine project name
    if not project_name:
        # Try to infer from current directory
        project_name = Path.cwd().name
    
    # Create template dossier
    dossier = create_dossier_from_scratch(
        name=project_name,
        description="TODO: Add project description",
        repository=None,
    )
    
    # Add template sections
    dossier["overview"] = {
        "summary": "TODO: Brief one-line summary",
        "purpose": "TODO: What does this project do?",
        "audience": "TODO: Who is this project for?",
    }
    
    dossier["tech_stack"] = [
        {"name": "TODO", "percentage": 100.0},
    ]
    
    dossier["dependencies"] = {
        "runtime": [
            {"name": "TODO", "version": "^1.0"},
        ],
    }
    
    dossier["links"] = {
        "documentation": "TODO",
        "repository": "TODO",
    }
    
    # Write to file
    output_path = Path(output) if output else Path(f"{project_name}.dossier")
    yaml_content = yaml.dump(
        dossier,
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
        width=100,
    )
    output_path.write_text(yaml_content, encoding="utf-8")
    
    click.echo(click.style(f"✓ Created {output_path}", fg="green"))
    click.echo(f"\nEdit the file to fill in project details:")
    click.echo(f"  {output_path}")


def main() -> None:
    """Entry point for the CLI."""
    cli()


if __name__ == "__main__":
    main()
