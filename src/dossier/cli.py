"""Click CLI for Dossier."""

import os
import sys
import textwrap
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


def _make_output_encodable() -> None:
    """Stop a glyph in a progress message aborting the command that printed it.

    A Windows console is cp1252 by default, and this CLI prints emoji. The
    failure mode is the bad one: `sync-org` raised UnicodeEncodeError on its
    first status line, and `projects remove` raised on the line it printed
    *after* committing the deletion -- so the command reported a crash for work
    that had already happened. Setting the stream encoding once at the entry
    point fixes every message, including ones not written yet; replacing the
    glyphs one at a time fixes only the ones somebody remembered.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                # A stream that will not be reconfigured (a pipe under some
                # runners) is left as it is: `errors` cannot be set on it
                # either, so there is nothing further to try.
                pass


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
    _make_output_encodable()
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
    from dossier.health import BLOCKED, prepare, render, summary_line, worst
    from dossier.tui import DossierApp

    # The dashboard is the only command a fresh clone needs after `uv sync`.
    # `prepare` is the whole of init: it creates a database that does not
    # exist, applies migrations that have not run, and corrects a stamp that
    # claims they did. It runs every launch rather than behind a first-run
    # flag, because the state it repairs arrives from outside -- pulling a
    # branch with a new migration is the ordinary way to get it.
    actions, findings = prepare()
    for action in actions:
        click.echo(f"  {action}")

    if worst(findings) == BLOCKED:
        # Refusing is the point: the app would open and then fail on the first
        # query naming a missing column, in the middle of a screen, with a
        # driver error that says nothing about what to do next.
        click.echo(render(findings), err=True)
        raise SystemExit(1)

    click.echo(summary_line(findings))
    app = DossierApp()
    app.run()


# =============================================================================
# Projects Commands - Manage registered projects
# =============================================================================


@cli.group()
def deltas() -> None:
    """Deltas: units of work, including ones another system emitted."""
    pass


@deltas.command("ingest")
@click.argument("payload", type=click.Path(exists=True, path_type=Path))
@click.option("--write", is_flag=True,
              help="apply the plan; without it nothing is written")
def deltas_ingest(payload: Path, write: bool) -> None:
    """Ingest delta payloads another system emitted.

    What crosses is a schema, not an import: the payload's `delta` key holds
    this project's own column names. Reports by default -- a sync that wrote on
    sight is one nobody dares run against real data.
    """
    from sqlmodel import select

    from dossier.ingest import WRITABLE, load, plan, render
    from dossier.models import Project, ProjectDelta

    payloads = load(payload)
    init_db()
    with get_session() as session:
        def lookup_project(full_name: str):
            return session.exec(
                select(Project).where(Project.full_name == full_name)
            ).first() or session.exec(
                select(Project).where(Project.name == full_name)
            ).first()

        def lookup_delta(project_id: int, name: str):
            return session.exec(
                select(ProjectDelta)
                .where(ProjectDelta.project_id == project_id)
                .where(ProjectDelta.name == name)
            ).first()

        verdicts = plan(payloads, lookup_project, lookup_delta)

        if write:
            by_name = {v.name: v for v in verdicts}
            for item in payloads:
                row = item.get("delta") or {}
                verdict = by_name.get(str(row.get("name") or ""))
                if verdict is None or verdict.action not in ("create", "update"):
                    continue
                project = lookup_project(item["project"])
                fields = {k: row[k] for k in WRITABLE if k in row}
                if verdict.action == "create":
                    session.add(ProjectDelta(project_id=project.id, **fields))
                else:
                    existing = lookup_delta(project.id, fields["name"])
                    for key, value in fields.items():
                        setattr(existing, key, value)
                    session.add(existing)
            session.commit()

        click.echo(render(verdicts, write))


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
        click.echo(f"OK Added project: {name}")


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
        
        click.echo(f"OK Removed project: {name}")
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
        click.echo(f"OK Renamed '{old_name}' to '{new_name}'")


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
                existing.is_fork = repo.is_fork
                existing.is_archived = repo.is_archived
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
                    full_name=f"{repo.owner}/{repo.name}",
                    description=description or repo.description,
                    repository_url=repo.html_url,
                    github_owner=repo.owner,
                    github_repo=repo.name,
                    github_stars=repo.stars,
                    is_fork=repo.is_fork,
                    is_archived=repo.is_archived,
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
            
            click.echo(f"\nOK Synced: {repo.full_name}")
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
                            existing.is_fork = repo.is_fork
                            existing.is_archived = repo.is_archived
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
                                full_name=f"{repo.owner}/{repo.name}",
                                description=repo.description,
                                repository_url=repo.html_url,
                                github_owner=repo.owner,
                                github_repo=repo.name,
                                github_stars=repo.stars,
                                is_fork=repo.is_fork,
                                is_archived=repo.is_archived,
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
                        click.echo(click.style(f" OK ({len(sections)} sections)", fg="green"))
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
                    full_name=f"github/user/{username}",
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
                    full_name=f"github/org/{org}",
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
    
    click.echo(click.style("OK Database reset to fresh state", fg="green"))
    
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
    
    click.echo(click.style("OK Cleared:", fg="green"))
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
    
    click.echo(click.style("OK Database vacuumed", fg="green"))
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
                full_name="example/project",
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
            click.echo(click.style("OK Created example project with 4 doc sections", fg="green"))
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
        click.echo(click.style(f"\nOK Purged {len(matches)} projects", fg="green"))


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
        click.echo(click.style("OK Database upgraded successfully", fg="green"))
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
        click.echo(click.style("OK Database downgraded successfully", fg="green"))
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
        click.echo(click.style("OK Migration created successfully", fg="green"))
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
        click.echo(click.style("OK Database stamped successfully", fg="green"))
    except Exception as e:
        click.echo(click.style(f"✗ Failed to stamp: {e}", fg="red"))
        raise click.Abort()


# =============================================================================
# Graph/Autolinker Commands
# =============================================================================


@cli.group("graph")
def graph_group() -> None:
    """Build and manage entity/link graphs.
    
    Automatically discover and link entities within projects to build
    a hierarchical graph of related projects.
    
    Entity Scoping:
      - Global: lang/*, pkg/* (same entity everywhere)
      - App-scoped: github/user/* (same user across all repos)
      - Repo-scoped: owner/repo/branch/*, owner/repo/issue/*, etc.
    
    Examples:
        dossier graph build owner/repo    Build graph for one project
        dossier graph build-all           Build graphs for all projects
        dossier graph stats               Show graph statistics
    """
    pass


@graph_group.command("build")
@click.argument("project_name")
@click.option("--no-contributors", is_flag=True, help="Skip contributors")
@click.option("--no-languages", is_flag=True, help="Skip languages")
@click.option("--no-dependencies", is_flag=True, help="Skip dependencies")
@click.option("--no-branches", is_flag=True, help="Skip branches")
@click.option("--no-issues", is_flag=True, help="Skip issues")
@click.option("--no-prs", is_flag=True, help="Skip pull requests")
@click.option("--no-versions", is_flag=True, help="Skip versions/releases")
@click.option("--no-docs", is_flag=True, help="Skip documentation")
@click.option("--max-contributors", default=10, help="Max contributors to link")
@click.option("--max-issues", default=50, help="Max issues to link")
@click.option("--max-prs", default=50, help="Max PRs to link")
def graph_build(
    project_name: str,
    no_contributors: bool,
    no_languages: bool,
    no_dependencies: bool,
    no_branches: bool,
    no_issues: bool,
    no_prs: bool,
    no_versions: bool,
    no_docs: bool,
    max_contributors: int,
    max_issues: int,
    max_prs: int,
) -> None:
    """Build entity graph for a project.
    
    PROJECT_NAME is the project to build graph for (e.g., owner/repo).
    
    This command discovers all entities (contributors, languages, dependencies,
    branches, issues, PRs, versions, docs) and creates linked project nodes
    for each, building a navigable entity graph.
    
    Examples:
        dossier graph build microsoft/vscode
        dossier graph build astral-sh/ruff --no-issues --no-prs
        dossier graph build myorg/myrepo --max-contributors 5
    """
    from dossier.parsers.autolinker import AutoLinker
    
    with get_session() as session:
        project = session.exec(
            select(Project).where(Project.name == project_name)
        ).first()
        
        if not project:
            click.echo(click.style(f"Project '{project_name}' not found", fg="red"))
            raise click.Abort()
        
        click.echo(f"🔗 Building entity graph for {project_name}...")
        
        linker = AutoLinker(session)
        stats = linker.build_graph(
            project,
            include_contributors=not no_contributors,
            include_languages=not no_languages,
            include_dependencies=not no_dependencies,
            include_branches=not no_branches,
            include_issues=not no_issues,
            include_prs=not no_prs,
            include_versions=not no_versions,
            include_docs=not no_docs,
            max_contributors=max_contributors,
            max_issues=max_issues,
            max_prs=max_prs,
        )
        
        click.echo(f"\nOK Graph built successfully!")
        click.echo(f"  Projects: {stats.projects_created} created, {stats.projects_found} existing")
        click.echo(f"  Links: {stats.links_created} created, {stats.links_found} existing")
        
        if stats.errors:
            click.echo(click.style(f"\n⚠ {len(stats.errors)} errors occurred:", fg="yellow"))
            for error in stats.errors[:5]:
                click.echo(f"    • {error}")
            if len(stats.errors) > 5:
                click.echo(f"    ... and {len(stats.errors) - 5} more")


@graph_group.command("build-all")
@click.option("--no-contributors", is_flag=True, help="Skip contributors")
@click.option("--no-languages", is_flag=True, help="Skip languages")
@click.option("--no-dependencies", is_flag=True, help="Skip dependencies")
@click.option("--no-branches", is_flag=True, help="Skip branches")
@click.option("--no-issues", is_flag=True, help="Skip issues")
@click.option("--no-prs", is_flag=True, help="Skip pull requests")
@click.option("--no-versions", is_flag=True, help="Skip versions/releases")
@click.option("--no-docs", is_flag=True, help="Skip documentation")
@click.option("--max-contributors", default=10, help="Max contributors per project")
@click.option("--max-issues", default=50, help="Max issues per project")
@click.option("--max-prs", default=50, help="Max PRs per project")
def graph_build_all(
    no_contributors: bool,
    no_languages: bool,
    no_dependencies: bool,
    no_branches: bool,
    no_issues: bool,
    no_prs: bool,
    no_versions: bool,
    no_docs: bool,
    max_contributors: int,
    max_issues: int,
    max_prs: int,
) -> None:
    """Build entity graphs for all synced projects.
    
    This processes all projects with GitHub owner/repo info and builds
    their entity graphs, creating a fully-linked knowledge base.
    
    Examples:
        dossier graph build-all
        dossier graph build-all --no-issues --no-prs
        dossier graph build-all --max-contributors 5
    """
    from dossier.parsers.autolinker import AutoLinker
    
    with get_session() as session:
        # Count projects first
        projects = session.exec(
            select(Project).where(
                Project.github_owner.isnot(None),
                Project.github_repo.isnot(None),
            )
        ).all()
        
        if not projects:
            click.echo(click.style("No synced projects found", fg="yellow"))
            return
        
        click.echo(f"🔗 Building entity graphs for {len(projects)} projects...")
        
        linker = AutoLinker(session)
        total_stats = linker.build_all_graphs(
            include_contributors=not no_contributors,
            include_languages=not no_languages,
            include_dependencies=not no_dependencies,
            include_branches=not no_branches,
            include_issues=not no_issues,
            include_prs=not no_prs,
            include_versions=not no_versions,
            include_docs=not no_docs,
            max_contributors=max_contributors,
            max_issues=max_issues,
            max_prs=max_prs,
        )
        
        click.echo(f"\nOK All graphs built successfully!")
        click.echo(f"  Projects: {total_stats.projects_created} created, {total_stats.projects_found} existing")
        click.echo(f"  Links: {total_stats.links_created} created, {total_stats.links_found} existing")
        
        if total_stats.errors:
            click.echo(click.style(f"\n⚠ {len(total_stats.errors)} errors occurred", fg="yellow"))


@graph_group.command("stats")
def graph_stats() -> None:
    """Show graph statistics.
    
    Display counts of projects and links by type, showing the
    structure of the entity graph.
    """
    with get_session() as session:
        # Count projects by type
        all_projects = session.exec(select(Project)).all()
        
        # Categorize by prefix
        categories = {
            "GitHub Repos": 0,
            "Users (github/user/)": 0,
            "Languages (lang/)": 0,
            "Packages (pkg/)": 0,
            "Branches": 0,
            "Issues": 0,
            "PRs": 0,
            "Versions": 0,
            "Docs": 0,
            "Other": 0,
        }
        
        for p in all_projects:
            name = p.name
            if name.startswith("github/user/"):
                categories["Users (github/user/)"] += 1
            elif name.startswith("lang/"):
                categories["Languages (lang/)"] += 1
            elif name.startswith("pkg/"):
                categories["Packages (pkg/)"] += 1
            elif "/branch/" in name:
                categories["Branches"] += 1
            elif "/issue/" in name:
                categories["Issues"] += 1
            elif "/pr/" in name:
                categories["PRs"] += 1
            elif "/ver/" in name:
                categories["Versions"] += 1
            elif "/doc/" in name:
                categories["Docs"] += 1
            elif "/" in name and not any(x in name for x in ["/branch/", "/issue/", "/pr/", "/ver/", "/doc/"]):
                categories["GitHub Repos"] += 1
            else:
                categories["Other"] += 1
        
        # Count links by type
        links = session.exec(select(ProjectComponent)).all()
        link_types: dict[str, int] = {}
        for link in links:
            rel_type = link.relationship_type or "unknown"
            link_types[rel_type] = link_types.get(rel_type, 0) + 1
        
        click.echo("📊 Graph Statistics\n")
        click.echo("Projects by Type:")
        for cat, count in categories.items():
            if count > 0:
                click.echo(f"  {cat}: {count}")
        click.echo(f"  {'─' * 30}")
        click.echo(f"  Total: {len(all_projects)}")
        
        click.echo("\nLinks by Relationship:")
        for rel_type, count in sorted(link_types.items()):
            click.echo(f"  {rel_type}: {count}")
        click.echo(f"  {'─' * 30}")
        click.echo(f"  Total: {len(links)}")


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
        
        click.echo(click.style(f"OK Exported to {output_path}", fg="green"))
        
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
            click.echo(f"  OK {file_path.name}")
        
        click.echo(click.style(f"\nOK Exported {len(projects)} projects", fg="green"))


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
    
    click.echo(click.style(f"OK Created {output_path}", fg="green"))
    click.echo(f"\nEdit the file to fill in project details:")
    click.echo(f"  {output_path}")


# =============================================================================
# View Command - Open docs in frogmouth viewer
# =============================================================================


def _check_frogmouth_installed() -> tuple[bool, str | None]:
    """Check if frogmouth is installed and return the path if found.
    
    Returns:
        Tuple of (is_installed, executable_path)
    """
    import shutil
    
    # First check if it's on PATH
    frogmouth_path = shutil.which("frogmouth")
    if frogmouth_path:
        return True, frogmouth_path
    
    # Try importing to see if it's installed as a Python package
    try:
        import frogmouth
        # It's installed but not on PATH - try to find the module location
        import importlib.util
        spec = importlib.util.find_spec("frogmouth")
        if spec and spec.origin:
            return True, f"python -m frogmouth"
        return True, None
    except ImportError:
        pass
    
    return False, None


@cli.command("view")
@click.argument("project_name")
@click.option("--section", "-s", help="Specific documentation section to view")
@click.option("--readme", "-r", is_flag=True, help="View README only")
@click.option("--export", "-e", is_flag=True, help="View exported .dossier file")
def view_cmd(
    project_name: str,
    section: Optional[str],
    readme: bool,
    export: bool,
) -> None:
    """Open project documentation in frogmouth viewer.
    
    Opens documentation in the frogmouth terminal markdown viewer.
    Requires frogmouth to be installed separately (due to dependency constraints).
    
    PROJECT_NAME: Name of the project (e.g., owner/repo)
    
    Examples:
        dossier view astral-sh/ruff              # View all docs
        dossier view astral-sh/ruff --readme     # View README only
        dossier view astral-sh/ruff -s "API"     # View specific section
        dossier view astral-sh/ruff --export     # View .dossier export
    """
    import tempfile
    import subprocess
    
    is_installed, frogmouth_cmd = _check_frogmouth_installed()
    if not is_installed:
        click.echo(click.style("frogmouth is not installed.", fg="yellow"))
        click.echo()
        click.echo("Install frogmouth using one of these methods:")
        click.echo(click.style("  pipx install frogmouth", fg="cyan") + "  (recommended - isolated install)")
        click.echo(click.style("  pip install frogmouth", fg="cyan") + "   (global install)")
        click.echo(click.style("  uv tool install frogmouth", fg="cyan") + "  (uv tool install)")
        click.echo()
        click.echo("Note: frogmouth is installed separately due to dependency version constraints.")
        raise SystemExit(1)
    
    with get_session() as session:
        project = session.exec(
            select(Project).where(Project.name == project_name)
        ).first()
        
        if not project:
            click.echo(click.style(f"Project '{project_name}' not found", fg="red"))
            raise SystemExit(1)
        
        if export:
            # Generate and view .dossier file
            from dossier.dossier_file import generate_dossier
            import yaml
            
            dossier = generate_dossier(session, project)
            content = yaml.dump(
                dossier,
                default_flow_style=False,
                allow_unicode=True,
                sort_keys=False,
            )
            suffix = ".yaml"
        else:
            # Build markdown from documentation sections
            stmt = select(DocumentSection).where(
                DocumentSection.project_id == project.id
            ).order_by(DocumentSection.order)
            
            docs = session.exec(stmt).all()
            
            if section:
                docs = [d for d in docs if section.lower() in d.title.lower()]
            elif readme:
                docs = [d for d in docs if "readme" in (d.source_file or "").lower()]
            
            if not docs:
                click.echo(click.style(
                    f"No documentation found for '{project_name}'", fg="yellow"
                ))
                if section:
                    click.echo(f"  (searched for section matching '{section}')")
                raise SystemExit(1)
            
            # Build combined markdown
            content = f"# {project.name}\n\n"
            if project.description:
                content += f"> {project.description}\n\n"
            content += "---\n\n"
            
            for doc in docs:
                content += f"## {doc.title}\n\n"
                content += f"{doc.content}\n\n"
                content += "---\n\n"
            
            suffix = ".md"
        
        # Write to temp file and open in frogmouth
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=suffix,
            delete=False,
            encoding="utf-8",
        ) as f:
            f.write(content)
            temp_path = f.name
        
        try:
            click.echo(f"Opening in frogmouth: {project_name}")
            subprocess.run(["frogmouth", temp_path], check=True)
        finally:
            # Clean up temp file
            import os
            try:
                os.unlink(temp_path)
            except OSError:
                pass


@cli.group(name="governance")
def governance_group() -> None:
    """Read the corpus's generated governance documents.

    dossier renders these documents; it does not decide governance. They are
    generated in the corpus from git and the host, and nothing here writes
    back to them.

    Examples:
        dossier governance dashboard --corpus-dir ../qm --refresh
        dossier governance load       Read both documents into the store
        dossier governance show       Where every project stands
        dossier governance threads    What work is in flight, and where
    """
    _warn_if_run_outside_dossier()


def _warn_if_run_outside_dossier() -> None:
    """Say so when the store is being created somewhere unexpected.

    Every command calls `init_db()`, which creates `dossier.db` in the current
    directory. Run from the corpus checkout, that leaves a stray database in a
    repository it has nothing to do with, and the store is then separate from
    the one the dossier checkout uses -- so `load` here and `show` there
    disagree for a reason neither command mentions.

    A warning rather than an error: running from elsewhere with an explicit
    --corpus-dir does work, and the operator may mean it.
    """
    cwd = Path.cwd()
    if (cwd / "src" / "dossier").is_dir():
        return  # a dossier checkout, which is the expected place
    click.echo(
        click.style("note:", fg="yellow")
        + f" the store for this run is {cwd / 'dossier.db'}, which is per-directory."
        "\n      Running from elsewhere gets a different store, and the two will"
        " not agree.",
        err=True,
    )


@governance_group.command(name="load")
@click.option(
    "--corpus-dir",
    type=click.Path(path_type=Path),
    default=None,
    help="Where the corpus is mounted. Defaults to governance/qm.",
)
def governance_load(corpus_dir: Optional[Path]) -> None:
    """Read governance-status.yaml and harness-status.json into the store.

    A document that cannot be read is reported and leaves what it owns
    untouched, rather than emptying it. An empty table reads as "nothing is
    wrong", which is the one thing an unreadable document does not mean.
    """
    from dossier import governance as gov

    with get_session() as session:
        report = gov.load_documents(session, corpus_dir=corpus_dir)

    for label, outcome in (("governance", report.governance), ("harness", report.harness)):
        mark = "ok  " if outcome.loaded else "MISS"
        click.echo(f"{mark} {label:<11} {outcome.path}")
        click.echo(f"     {outcome.summary}")

    if report.threads:
        click.echo(f"     {report.threads} thread(s) in flight")
    if report.removed:
        click.echo(f"     removed: {', '.join(report.removed)}")

    if not report.anything_loaded:
        click.echo(
            "\nNeither document could be read, so nothing was changed. Anything "
            "already stored is still there and still carries its own age."
        )
        click.echo(
            "\nBoth documents are generated by the corpus's own ci/ and live at "
            "the corpus root. The vendored copy at governance/qm is pinned to\n"
            "this project's branch, which is cut from the corpus's main -- and "
            "they are not on main yet, so the default path is empty by\n"
            "construction rather than by accident."
        )
        click.echo(
            "\nPoint the loader at a corpus checkout that has them:\n"
            "    dossier governance load --corpus-dir ../qm\n"
            "\nThat checkout needs to be on a branch carrying ci/ and the two "
            "documents. To confirm before running:\n"
            "    ls <corpus>/governance-status.yaml <corpus>/harness-status.json\n"
            "\nThe default path starts working on its own once the corpus change "
            "adding them lands on main and this project's pin is bumped."
        )
        raise SystemExit(1)


@governance_group.command(name="show")
def governance_show() -> None:
    """Where every project stands: current, drifted, or unmeasured."""
    from dossier import governance as gov

    with get_session() as session:
        rows = gov.repositories(session)
        ages = gov.document_age(session)
        # The reverse link: which governed repositories this store has synced.
        synced = {}
        for row in rows:
            match, how = gov.project_for_repository(session, row)
            synced[row.name] = gov.coverage_text(match, how)

    if not rows:
        click.echo("Nothing stored. Run: dossier governance load")
        raise SystemExit(1)

    click.echo(_age_line("governance-status.yaml", ages["governance"], None))
    click.echo()

    header = (
        f"{'REPOSITORY':<25} {'PHASE':<8} {'CORPUS':<12} {'SEED':<7} "
        f"{'SLOT':<6} {'RELEASE':<22} {'IN DOSSIER':<14} EVIDENCE"
    )
    click.echo(header)
    click.echo("-" * len(header))
    for row in rows:
        state = gov.health(row)
        prefix = {"unknown": "?", "drift": "!", "ok": " "}[state]
        evidence = gov.show_pair(row.precondition, row.precondition_unknown)
        if row.precondition_missing:
            evidence = f"{evidence} ({row.precondition_missing})"
        if row.slot_violations:
            evidence = f"{evidence} [holds {row.slot_violations}]"
        click.echo(
            f"{prefix}{_fit(row.name, 24):<24} "
            f"{_fit(row.phase, 8):<8} "
            f"{gov.drift_text(row):<12} "
            f"{gov.show_pair(row.seed_drift, row.seed_drift_unknown):<7} "
            f"{gov.show_pair(row.slot_state, row.slot_unknown):<6} "
            f"{_fit(gov.release_text(row), 22):<22} "
            f"{_fit(synced.get(row.name), 14):<14} "
            f"{evidence}"
        )
    click.echo()
    click.echo("? unknown - nobody could measure it, which is not the same as compliant")
    click.echo("! drift   - behind the corpus, seed drift, or over the slot limit")
    click.echo("phase is a claim a human entered; evidence is what has landed")
    click.echo("in dossier - the project this store holds for it, if any")
    click.echo("release   - main is readiness; a v tag is governance passed")


@governance_group.command(name="threads")
def governance_threads() -> None:
    """Every line of work in flight, most idle first.

    Stages are observable states, not progress. Nothing here estimates
    completion: the corpus has no definition of done a tool could read.
    """
    from dossier import governance as gov

    with get_session() as session:
        rows = gov.threads(session)
        ages = gov.document_age(session)
        budget = next(
            (r.harness_staleness_budget_hours for r in gov.repositories(session)
             if r.harness_staleness_budget_hours),
            None,
        )

    if ages["harness"] is None:
        click.echo(
            "harness-status.json has never been read into this store, so nothing "
            "is known about work in flight.\nThat is not the same as nothing "
            "being in flight. Run: dossier governance load"
        )
        raise SystemExit(1)

    click.echo(_age_line("harness-status.json", ages["harness"], budget))
    click.echo()

    if not rows:
        click.echo("The document was read and reports no threads in flight.")
        return

    header = f"{'REPOSITORY':<16} {'THREAD':<38} {'STAGE':<15} {'DELTA':<22} {'IDLE':<8} PR"
    click.echo(header)
    click.echo("-" * len(header))
    for t in rows:
        stage = (t.stage or "-") + (" STALLED" if t.stalled else "")
        delta = (
            f"{t.commits or 0}c {t.changed_files or 0}f "
            f"+{t.additions or 0}/-{t.deletions or 0}"
        )
        idle = f"{t.idle_hours:.0f}h" if t.idle_hours is not None else "unknown"
        click.echo(
            f"{t.repository_name:<16} {_fit(t.name, 37):<38} {stage:<15} "
            f"{delta:<22} {idle:<8} {('#' + str(t.pr)) if t.pr else '-'}"
        )


@governance_group.command(name="dashboard")
@click.option(
    "--corpus-dir",
    type=click.Path(path_type=Path),
    default=None,
    help="Corpus checkout to read. Found automatically when omitted: the "
    "current directory, then governance/qm, then ../qm.",
)
@click.option(
    "--refresh/--no-refresh",
    default=True,
    help="Regenerate both documents first, by running the corpus's own "
    "generators. On by default; reads the network and writes into the "
    "corpus checkout.",
)
@click.option(
    "--offline",
    is_flag=True,
    default=False,
    help="With a refresh, pass --offline to the governance generator.",
)
@click.option(
    "--no-load",
    is_flag=True,
    default=False,
    help="Open the view on what is already stored, reading no document.",
)
@click.option(
    "--no-tui",
    is_flag=True,
    default=False,
    help="Print both tables instead of launching the dashboard.",
)
def governance_dashboard(
    corpus_dir: Optional[Path],
    refresh: bool,
    offline: bool,
    no_load: bool,
    no_tui: bool,
) -> None:
    """Get the latest and open the dashboard, in one command.

    Refresh -> load -> launch, on the Governance tab.

    \b
    From a corpus checkout, or from a project that vendors one:
        dossier governance dashboard
        dossier governance dashboard --no-refresh      # read what is on disk
        dossier governance dashboard --corpus-dir ../qm

    \b
    The corpus is found automatically: the current directory, then
    governance/qm, then ../qm. Whichever wins is printed, because a resolution
    that stays silent is how a reader ends up looking at a different
    repository than the one they think they are.

    \b
    A refresh runs the corpus's own generators, so it queries the host for
    every repository in the org and rewrites two committed files in that
    checkout. That diff is yours to review. --no-refresh skips it and reads
    what is on disk; either way the view prints how old the documents are.
    """
    from dossier import corpus as corpus_tools
    from dossier import governance as gov

    root, why = gov.resolve_corpus_dir(corpus_dir)
    click.echo(f"corpus  {root}  ({why})")

    if refresh:
        blocked = corpus_tools.can_refresh(root)
        if blocked:
            click.echo(f"skip    refresh - {blocked}")
        else:
            click.echo("refresh running the corpus's own generators ...")
            for outcome in corpus_tools.refresh(root, offline=offline):
                mark = "ok  " if outcome.ok else ("skip" if not outcome.ran else "FAIL")
                click.echo(f"{mark}    {outcome.document:<24} {outcome.summary}")
                if outcome.output and not outcome.ok:
                    for line in outcome.output.splitlines():
                        click.echo(f"           {line}")
            click.echo(
                f"        two committed files in {root} now differ -- that diff "
                "is yours to review"
            )
    click.echo()

    if not no_load:
        with get_session() as session:
            report = gov.load_documents(session, corpus_dir=root)
        for label, outcome in (
            ("governance", report.governance),
            ("harness", report.harness),
        ):
            mark = "ok  " if outcome.loaded else "MISS"
            click.echo(f"{mark} {label:<11} {outcome.summary}")
        if report.threads:
            click.echo(f"     {report.threads} thread(s) in flight")

        if not report.anything_loaded:
            click.echo(
                f"\nNeither document could be read under {root}, so there is "
                "nothing new to show."
            )
            if corpus_dir is None:
                click.echo(
                    "Nothing was found in the current directory, in "
                    "governance/qm, or in ../qm. A project's vendored copy is\n"
                    "pinned to a branch cut from the corpus's main, and the "
                    "documents are not on main yet, so it is empty by\n"
                    "construction. Point at a corpus checkout that has them:\n"
                    "    dossier governance dashboard --corpus-dir <corpus>"
                )
            raise SystemExit(1)
        click.echo()

    if no_tui:
        ctx = click.get_current_context()
        ctx.invoke(governance_show)
        click.echo()
        ctx.invoke(governance_threads)
        return

    from dossier.tui import DossierApp

    DossierApp(initial_tab="tab-governance").run()


# =============================================================================
# Disk Commands - keeping the workstation off the floor
# =============================================================================


@cli.group(name="disk")
def disk_group() -> None:
    """Watch and reclaim disk space, through the corpus's own tooling.

    dossier measures nothing here and decides nothing. Every figure comes from
    the corpus's ci/disk_status.py, and every deletion is authorised by
    ci/disk-policy.yaml there -- a reviewed file, not a script.

    \b
    Examples:
        dossier disk check        Is anything under its floor? Writes nothing.
        dossier disk status       What is eating the disk, largest first
        dossier disk reclaim      What could be freed -- a dry run
        dossier disk cookbook     The recipes, where the work happens
    """
    _warn_if_run_outside_dossier()


def _disk_corpus(corpus_dir: Optional[Path]) -> Path:
    """Resolve the corpus and print the choice, or explain and exit.

    Resolution is `governance.resolve_corpus_dir` unchanged -- one definition of
    "where is the corpus", shared with the governance commands. What differs is
    what this group needs once it gets there, so the suitability check is
    `disk.can_measure` and its reason is printed rather than swallowed.
    """
    from dossier import disk as disk_tools
    from dossier import governance as gov

    root, why = gov.resolve_corpus_dir(corpus_dir)
    click.echo(f"corpus  {root}  ({why})")

    blocked = disk_tools.can_measure(root)
    if blocked:
        click.echo(f"\nThis checkout cannot run the disk tooling: {blocked}", err=True)
        if corpus_dir is None:
            click.echo(
                "\nNothing carrying ci/ was found in the current directory, in "
                "governance/qm, or in ../qm. A project's vendored copy is\n"
                "pinned to a branch cut from the corpus's main, and the disk "
                "tooling is not on main yet, so that path is empty by\n"
                "construction rather than by accident. Point at a corpus "
                "checkout that has it:\n"
                "    dossier disk status --corpus-dir <corpus>",
                err=True,
            )
        raise SystemExit(1)
    return root


@disk_group.command(name="check")
@click.option(
    "--corpus-dir",
    type=click.Path(path_type=Path),
    default=None,
    help="Corpus checkout to run. Found automatically when omitted: the "
    "current directory, then governance/qm, then ../qm.",
)
def disk_check(corpus_dir: Optional[Path]) -> None:
    """Is any volume under its floor? Fast, and writes nothing.

    \b
    The cheap call -- put it in front of anything that writes a lot:
        dossier disk check && make build

    \b
    The exit status is the corpus tool's, unmodified:
        2   a volume is critical
        1   a volume is low, or could not be read
        0   every volume measured is above both thresholds

    A volume nobody could measure exits 1 rather than 0, because an unreadable
    volume is not a volume with room on it.
    """
    from dossier import disk as disk_tools

    root = _disk_corpus(corpus_dir)
    outcome = disk_tools.check(root)
    if outcome.stdout:
        click.echo(outcome.stdout)
    if not outcome.ran or outcome.status is None:
        click.echo(f"FAIL    {outcome.summary}", err=True)
        raise SystemExit(1)
    raise SystemExit(outcome.status)


@disk_group.command(name="status")
@click.option(
    "--corpus-dir",
    type=click.Path(path_type=Path),
    default=None,
    help="Corpus checkout to run. Found automatically when omitted.",
)
@click.option(
    "--measure/--no-measure",
    default=True,
    help="Take a fresh measurement first. On by default; it is a filesystem "
    "walk, not a network call. --no-measure reads the document already there.",
)
@click.option(
    "--search-root",
    type=click.Path(path_type=Path),
    multiple=True,
    help="Where this stack's clones live, for the sweeps that cross projects. "
    "Repeatable. Defaults to the corpus tool's own choice.",
)
@click.option(
    "--html",
    "as_html",
    is_flag=True,
    default=False,
    help="Write a self-contained page beside the document and print its path.",
)
def disk_status(
    corpus_dir: Optional[Path],
    measure: bool,
    search_root: tuple[Path, ...],
    as_html: bool,
) -> None:
    """Measure the disk and print what is eating it, largest first.

    \b
        dossier disk status
        dossier disk status --no-measure          # read what is on disk
        dossier disk status --html                # a page instead of a table

    \b
    The document lands in ~/.dossier/disk-status.json -- outside every
    repository, deliberately. Free space, cache sizes and paths under a home
    directory are one machine at one moment, so it is never committed
    anywhere, and this command refuses a destination inside a git repository
    rather than trusting anyone to remember.

    Every figure carries its own age and the corpus's staleness budget. A
    target that could not be measured is reported as unknown with its reason,
    never as a target with nothing in it.
    """
    from dossier import disk as disk_tools

    root = _disk_corpus(corpus_dir)
    document = disk_tools.document_path()

    if measure:
        click.echo("measure walking the policy's targets ...")
        outcome = disk_tools.measure(root, search_roots=search_root)
        if not outcome.ok:
            click.echo(f"FAIL    {outcome.summary}", err=True)
            if outcome.stdout:
                click.echo(outcome.stdout, err=True)
            raise SystemExit(1)
        click.echo(f"ok      {outcome.stdout or document}")
        click.echo()

    if as_html:
        page = document.with_suffix(".html")
        outcome = disk_tools.render(root, fmt="html", out=page)
        if not outcome.ok:
            click.echo(f"FAIL    {outcome.summary}", err=True)
            raise SystemExit(1)
        click.echo(f"page    {page}")
        return

    outcome = disk_tools.render(root, fmt="md")
    if not outcome.ok:
        click.echo(f"FAIL    {outcome.summary}", err=True)
        if not measure:
            click.echo(
                "\nNothing has been measured on this machine yet. Drop "
                "--no-measure to take a reading first.",
                err=True,
            )
        raise SystemExit(1)
    click.echo(outcome.stdout)


@disk_group.command(name="reclaim")
@click.option(
    "--corpus-dir",
    type=click.Path(path_type=Path),
    default=None,
    help="Corpus checkout to run. Found automatically when omitted.",
)
@click.option(
    "--apply",
    "apply_",
    is_flag=True,
    default=False,
    help="Actually delete. Without it nothing is removed and the plan is "
    "printed. There is no setting that changes this default.",
)
@click.option(
    "--allow",
    type=click.Choice(("refetched", "rebuilt", "destructive")),
    default="refetched",
    help="The most expensive tier permitted. Permits every cheaper tier too.",
)
@click.option(
    "--target",
    multiple=True,
    help="Run only this policy entry, by name. Repeatable. Names come from "
    "`dossier disk status`.",
)
@click.option(
    "--until-free",
    type=float,
    metavar="GB",
    help="Stop once the volume has this many GB free, rather than clearing "
    "every permitted target.",
)
@click.option(
    "--search-root",
    type=click.Path(path_type=Path),
    multiple=True,
    help="Where this stack's clones live. Repeatable.",
)
def disk_reclaim(
    corpus_dir: Optional[Path],
    apply_: bool,
    allow: str,
    target: tuple[str, ...],
    until_free: Optional[float],
    search_root: tuple[Path, ...],
) -> None:
    """Free space, and print what it would take before it takes it.

    \b
        dossier disk reclaim                        # a dry run, always
        dossier disk reclaim --apply
        dossier disk reclaim --target uv-cache --apply
        dossier disk reclaim --allow rebuilt --apply

    \b
    Safety is the cost of getting the bytes back, not a guess at risk:
        refetched     the owning tool downloads it again, unprompted
        rebuilt       a command you run: an install, a build, a download
        destructive   nothing comes back

    \b
    The tiers are a ratchet. --allow rebuilt permits refetched as well, so
    there is no invocation that empties the recycle bin while sparing a
    download cache -- which is the shape every cleanup script grows into, one
    urgent afternoon at a time.

    The reclaimer does not read the measurement document. That document has a
    staleness budget and deletion has none, so it resolves the same policy
    against the filesystem now.
    """
    from dossier import disk as disk_tools
    from dossier import disk_store

    root = _disk_corpus(corpus_dir)

    with get_session() as session:
        record, outcome = disk_tools.reclaim_and_record(
            session,
            root,
            allow=allow,
            apply=apply_,
            targets=target,
            until_free=until_free,
            search_roots=search_root,
        )
        if outcome.stdout:
            click.echo(outcome.stdout)

        click.echo()
        click.echo(f"recorded run {record.id} [{record.outcome}]")

        # Claimed and freed are printed together, always, and the gap between
        # them is named rather than left for the reader to subtract. They
        # diverge for ordinary reasons -- a concurrent write, or space freed
        # inside a container disk that does not shrink -- and printing only the
        # first would let this tool claim space that never came back.
        click.echo(f"  claimed  {_size(record.claimed_bytes)}   (what the reclaimer removed)")
        if record.applied:
            if record.freed_bytes is None:
                click.echo(
                    f"  freed    unknown  ({record.freed_unknown or 'not measured'})"
                )
            elif record.freed_bytes < 0:
                # Not "gave back -37KB". The volume finished the run with less
                # space than it started, because something else was writing
                # throughout -- which is a true and useful thing to say, and
                # a negative number wearing the word `freed` is not.
                click.echo(
                    f"  freed    none — the volume ended "
                    f"{_size(abs(record.freed_bytes))} smaller than it started."
                    "\n           Something else was writing during the run; "
                    "what this removed still went."
                )
            else:
                click.echo(
                    f"  freed    {_size(record.freed_bytes)}   "
                    "(what the volume gave back)"
                )
                gap = (record.claimed_bytes or 0) - record.freed_bytes
                if record.claimed_bytes and abs(gap) > 10**9:
                    click.echo(
                        f"  gap      {_size(gap)} — the two disagree. Space freed "
                        "inside a container disk does not\n"
                        "           shrink the host file, and anything else "
                        "writing at the time counts too."
                    )
            delta = disk_store.reclaim_delta(session, record)
            if delta.available:
                shrank = [t for t in delta.targets if t.status == "shrank"]
                for target_change in sorted(shrank, key=lambda t: t.change or 0)[:8]:
                    click.echo(
                        f"    {_fit(target_change.name, 26):<26} "
                        f"{_change(target_change.change)}"
                    )
        else:
            click.echo("  freed    nothing — this was a dry run")

    if not outcome.ok:
        click.echo(f"FAIL    {outcome.summary}", err=True)
        raise SystemExit(outcome.status or 1)


def _size(count: Optional[int]) -> str:
    """Bytes at a scale a person reads, and never rounded to nothing.

    A 40MB cache rendered as `0.0GB` reads as empty, which is the same failure
    as rendering an unknown as a zero.
    """
    if count is None:
        return "unknown"
    negative = count < 0
    value = abs(count)
    if value >= 10**9:
        text = f"{value / 10**9:.1f}GB"
    elif value >= 10**6:
        text = f"{value / 10**6:.0f}MB"
    elif value >= 10**3:
        text = f"{value / 10**3:.0f}KB"
    else:
        text = f"{value}B"
    return f"-{text}" if negative else text


def _change(count: Optional[int]) -> str:
    """A signed change, with the sign kept even at zero-ish sizes."""
    if count is None:
        return "unknown"
    if count == 0:
        return "no change"
    return f"+{_size(count)}" if count > 0 else _size(count)


@disk_group.command(name="load")
@click.option(
    "--corpus-dir",
    type=click.Path(path_type=Path),
    default=None,
    help="Corpus checkout to run. Found automatically when omitted.",
)
@click.option(
    "--measure/--no-measure",
    default=True,
    help="Take a fresh reading first. On by default.",
)
@click.option(
    "--search-root",
    type=click.Path(path_type=Path),
    multiple=True,
    help="Where this stack's clones live. Repeatable.",
)
@click.option(
    "--keep",
    type=int,
    default=None,
    help="Snapshots to keep for this machine. Older ones are pruned.",
)
def disk_load(
    corpus_dir: Optional[Path],
    measure: bool,
    search_root: tuple[Path, ...],
    keep: Optional[int],
) -> None:
    """Read a disk document into the store as a new snapshot.

    \b
        dossier disk load                  # measure, then store
        dossier disk load --no-measure     # store the reading already taken

    Appends rather than replaces, which is the difference between this and
    `governance load`. The question worth asking of a disk is what grew since
    last time, and no single reading can answer it -- so every load keeps the
    previous ones, and `dossier disk delta` compares them.

    Old snapshots are pruned per machine, so a second machine sharing a store
    cannot evict this one's history.
    """
    from dossier import disk as disk_tools
    from dossier import disk_store

    if measure:
        root = _disk_corpus(corpus_dir)
        click.echo("measure walking the policy's targets ...")
        outcome = disk_tools.measure(root, search_roots=search_root)
        if not outcome.ok:
            click.echo(f"FAIL    {outcome.summary}", err=True)
            raise SystemExit(1)
        click.echo(f"ok      {outcome.stdout or disk_tools.document_path()}")

    with get_session() as session:
        report = disk_store.load_document(
            session,
            keep=keep if keep is not None else disk_store.DEFAULT_KEEP,
        )

    mark = "ok  " if report.loaded else "MISS"
    click.echo(f"{mark} disk        {report.summary}")
    if not report.loaded:
        click.echo(
            "\nNothing was stored, and nothing already stored was changed. "
            "Take a reading first:\n    dossier disk load",
            err=True,
        )
        raise SystemExit(1)
    click.echo(f"     machine {report.machine}")
    if report.pruned:
        click.echo(f"     pruned {report.pruned} older snapshot(s)")


@disk_group.command(name="delta")
@click.option(
    "--machine",
    default=None,
    help="Which machine's history to read. Defaults to this one.",
)
@click.option(
    "--limit",
    type=int,
    default=12,
    help="How many changed targets to print.",
)
def disk_delta(machine: Optional[str], limit: int) -> None:
    """What changed between the two most recent readings.

    \b
        dossier disk delta

    The question a single reading cannot answer. Volumes first -- the change
    shown is in FREE space, so a negative number is the disk filling up --
    then the targets that moved, largest growth first.

    \b
    A change is only ever printed where subtracting was honest. Four cases
    print a word instead of a number, because the arithmetic would have
    invented a fact:
        unknown   nobody could measure one of the two readings
        new       the target is not in the earlier snapshot
        gone      the target is not in the later one
        different the two readings describe different machines

    One reading is not an error. It is a machine measured once, and the
    honest report is that there is nothing to compare it with yet.
    """
    from dossier import disk_store

    with get_session() as session:
        delta = disk_store.latest_delta(session, machine=machine)

        if not delta.available:
            click.echo(f"no delta: {delta.reason}")
            click.echo(
                "\nThis is not a claim that nothing changed -- it is the "
                "absence of a second measurement.\nRun `dossier disk load` "
                "again later, and the comparison becomes available."
            )
            return

        click.echo(
            f"machine {delta.machine}   over {delta.hours:.0f}h   "
            f"{delta.older.generated_at} -> {delta.newer.generated_at}"
        )
        click.echo()

        click.echo("Volumes (change in FREE space; negative is filling up)")
        header = f"  {'Volume':<12} {'Free now':>10} {'Change':>12}  State"
        click.echo(header)
        click.echo("  " + "-" * (len(header) - 2))
        for volume in delta.volumes:
            if volume.unknown:
                click.echo(
                    f"  {volume.path:<12} {'unknown':>10} {'unknown':>12}  "
                    f"{volume.unknown}"
                )
                continue
            click.echo(
                f"  {volume.path:<12} {_size(volume.after_free):>10} "
                f"{_change(volume.change):>12}  {volume.severity or '-'}"
            )
        click.echo()

        moved = [t for t in delta.targets if t.status in ("grew", "shrank")]
        moved.sort(key=lambda t: -(t.change or 0))
        click.echo("Targets that moved")
        if not moved:
            click.echo("  nothing measurable changed size")
        else:
            header = f"  {'Target':<28} {'Now':>10} {'Change':>12}  Safety"
            click.echo(header)
            click.echo("  " + "-" * (len(header) - 2))
            for target in moved[:limit]:
                click.echo(
                    f"  {_fit(target.name, 28):<28} {_size(target.after):>10} "
                    f"{_change(target.change):>12}  {target.safety or '-'}"
                )
            if len(moved) > limit:
                click.echo(f"  ... and {len(moved) - limit} more")

        # Never folded into the table above. A target nobody could compare is
        # not a target that did not change, and a row of dashes among real
        # numbers is read as the second thing.
        gaps = delta.unreadable
        if gaps:
            click.echo()
            click.echo(f"No change could be established for {len(gaps)} target(s):")
            for target in gaps:
                click.echo(f"  {target.name:<28} {target.status:<8} {target.unknown}")


@disk_group.command(name="reclaims")
@click.option(
    "--machine", default=None, help="Whose history. Defaults to this machine."
)
@click.option("--limit", type=int, default=15, help="How many, newest first.")
@click.option(
    "--compose",
    "compose_all",
    is_flag=True,
    default=False,
    help="Chain the listed runs into one delta over the whole span.",
)
def disk_reclaims(machine: Optional[str], limit: int, compose_all: bool) -> None:
    """What has been reclaimed here, and what actually came back.

    \b
        dossier disk reclaims
        dossier disk reclaims --compose      # the whole session as one delta

    Every run is stored as the pair of readings it sits between, so what it
    did is the same kind of fact as any other change and composes with them.

    \b
    Two columns that are not the same number, deliberately:
        claimed   what the reclaimer removed
        freed     what the volume gave back
    They diverge for ordinary reasons -- something else writing at the time,
    or space freed inside a container disk that does not shrink -- and a tool
    that printed only the first would claim space that never returned.
    """
    from dossier import disk_store

    with get_session() as session:
        rows = disk_store.reclaims(
            session, machine=machine or disk_store.this_machine(), limit=limit
        )
        if not rows:
            click.echo("No reclaim run has been recorded on this machine.")
            click.echo(
                "That is not a claim that nothing was ever cleaned up -- it is "
                "the absence of a record.\nRun `dossier disk reclaim --apply`."
            )
            return

        header = (
            f"{'#':>4}  {'when':<20} {'tier':<12} {'outcome':<9} "
            f"{'claimed':>10} {'freed':>10}"
        )
        click.echo(header)
        click.echo("-" * len(header))
        for row in rows:
            freed = (
                "dry run" if not row.applied
                else "unknown" if row.freed_bytes is None
                else _size(row.freed_bytes)
            )
            click.echo(
                f"{row.id:>4}  {row.started_at:%Y-%m-%d %H:%M:%S}  "
                f"{row.allow:<12} {row.outcome:<9} "
                f"{_size(row.claimed_bytes):>10} {freed:>10}"
            )
            if row.targets:
                click.echo(f"      targets: {row.targets}")

        if not compose_all:
            return

        # Composed from the endpoints, never by adding the rows up: an unknown
        # is not zero, so a sum would launder a run nobody measured into a
        # confident total.
        deltas = [disk_store.reclaim_delta(session, row) for row in rows]
        combined = disk_store.compose(session, *deltas)
        click.echo()
        if not combined.available:
            click.echo(f"composed: {combined.reason}")
            return
        click.echo(
            f"composed over {combined.hours:.0f}h, "
            f"{combined.older.generated_at} -> {combined.newer.generated_at}"
        )
        if not combined.contiguous:
            # Stated as the ordinary case it is, not as an anomaly. Each run
            # takes its own reading before it starts, so consecutive runs never
            # meet exactly -- the gap is the time between them. A warning that
            # fires every time is one people stop reading, and the fact worth
            # carrying is what the figure includes, not that something is off.
            click.echo(
                "  The runs are separated by the time between them, so this "
                "span also holds\n  ordinary drift. The total is what the "
                "volume did; not all of it is what the runs did."
            )
        for volume in combined.volumes:
            if volume.unknown:
                click.echo(f"  {volume.path:<10} unknown — {volume.unknown}")
                continue
            click.echo(
                f"  {volume.path:<10} free {_size(volume.after_free)}  "
                f"{_change(volume.change)}"
            )


@disk_group.command(name="dashboard")
@click.option(
    "--corpus-dir",
    type=click.Path(path_type=Path),
    default=None,
    help="Corpus checkout to run. Found automatically when omitted.",
)
@click.option(
    "--load/--no-load",
    "do_load",
    default=True,
    help="Measure and store a fresh reading first. On by default.",
)
@click.option(
    "--no-tui",
    is_flag=True,
    default=False,
    help="Print the delta instead of launching the dashboard.",
)
def disk_dashboard(
    corpus_dir: Optional[Path], do_load: bool, no_tui: bool
) -> None:
    """Get the latest and open the dashboard, in one command.

    \b
    Measure -> store -> launch, on the Disk tab:
        dossier disk dashboard
        dossier disk dashboard --no-load       # open on what is stored
        dossier disk dashboard --no-tui        # print instead

    Unlike the governance dashboard this reads no network and writes into no
    repository: a reading is a filesystem walk, and it lands in ~/.dossier.
    """
    ctx = click.get_current_context()

    if do_load:
        ctx.invoke(disk_load, corpus_dir=corpus_dir, measure=True)
        click.echo()

    if no_tui:
        ctx.invoke(disk_delta)
        return

    from dossier.tui import DossierApp

    DossierApp(initial_tab="tab-disk").run()


@disk_group.command(name="cookbook")
@click.option(
    "--markdown",
    "as_markdown",
    is_flag=True,
    default=False,
    help="Emit the docs page instead of the terminal view. Both are generated "
    "from the same recipes, so they cannot drift.",
)
@click.option(
    "--write",
    type=click.Path(path_type=Path),
    default=None,
    help="Write the docs page here, as UTF-8 with LF endings and no byte order "
    "mark. Use this rather than a shell redirect.",
)
def disk_cookbook(as_markdown: bool, write: Optional[Path]) -> None:
    """The recipes, printed where the work happens.

    \b
        dossier disk cookbook
        dossier disk cookbook --write docs/disk.md

    docs/disk.md is generated from exactly these recipes, and tests/test_disk.py
    regenerates it and compares. A hand edit to that page fails the suite, which
    is the only reason it can be trusted after a flag changes.

    \b
    --write rather than `--markdown > docs/disk.md`, because PowerShell's
    redirect writes UTF-8 with a byte order mark. The page then differs from
    what this command produces on every other platform, and the drift test
    fails for a reason that has nothing to do with the recipes.
    """
    from dossier import disk as disk_tools

    if write is not None:
        write.write_text(disk_tools.cookbook_markdown(), encoding="utf-8", newline="\n")
        click.echo(f"wrote {write}")
        return

    if as_markdown:
        click.echo(disk_tools.cookbook_markdown(), nl=False)
        return

    click.echo(click.style("Disk - a cookbook", bold=True))
    click.echo(
        "Every command runs the corpus's own tooling. dossier measures nothing."
    )
    for recipe in disk_tools.COOKBOOK:
        click.echo()
        click.echo(click.style(recipe.task, fg="cyan"))
        click.echo(f"    {recipe.command}")
        for line in textwrap.wrap(recipe.when, width=74):
            click.echo(f"    {line}")
        if recipe.note:
            for line in textwrap.wrap(recipe.note, width=72):
                click.echo(f"      {line}")
    click.echo()
    click.echo("Full page: docs/disk.md")


def _fit(text: Optional[str], width: int) -> str:
    """Truncate to width so a long name cannot shunt every later column.

    `streaming-infrastructure` is 24 characters and broke the alignment of
    every row below it before this existed.
    """
    value = text or "-"
    return value if len(value) <= width else value[: width - 1] + "…"


def _age_line(name: str, age: Optional[float], budget: Optional[float]) -> str:
    """Say how old the document is, always, and never imply it is live."""
    if age is None:
        return f"{name}: never read into this store"
    text = f"{name}: generated {age:.0f}h ago"
    if budget is None:
        return f"{text} (the document states no staleness budget)"
    if age > budget:
        return f"{text} — PAST its {budget:.0f}h budget; treat every figure as stale"
    return f"{text}, within its {budget:.0f}h budget"


def main() -> None:
    """Entry point for the CLI."""
    cli()


if __name__ == "__main__":
    main()


# `backup` joins the existing `db` group defined above -- a second
# `@cli.group() def db()` silently replaced it, taking `db current`,
# `db history` and every other alembic route with it.
@db.command("backup")
@click.option("--to", "destination", type=click.Path(path_type=Path), default=None,
              help="Where to write it (default: beside the database, timestamped)")
def db_backup(destination: Optional[Path]) -> None:
    """Copy the database through SQLite's online backup API."""
    from dossier.maintenance import backup, timestamped_name

    source = Path("dossier.db")
    if not source.exists():
        click.echo(f"Error: {source} does not exist.", err=True)
        raise SystemExit(1)
    target = Path(destination) if destination else timestamped_name(source)
    backup(source, target)
    click.echo(f"Backed up {source} -> {target} ({target.stat().st_size:,} bytes)")


@projects.command("purge")
@click.option("--keep-owner", required=True,
              help="The only owner whose projects are kept")
@click.option("--apply", is_flag=True,
              help="Actually delete. Without this the plan is printed and nothing changes.")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
def projects_purge(keep_owner: str, apply: bool, yes: bool) -> None:
    """Remove every project not owned by KEEP-OWNER, and all of its rows.

    Prints the plan and exits unless --apply is given. A dry run walks exactly
    the same rows as a real one, so the plan is what the deletion does.
    """
    from dossier.maintenance import purge_other_owners

    with get_session() as session:
        plan = purge_other_owners(session, keep_owner, apply=False)
        if not plan.projects:
            click.echo(f"Nothing to purge: every project is owned by {keep_owner}.")
            return

        click.echo(f"Would remove {len(plan.projects)} project(s) not owned by "
                   f"{keep_owner}, and {plan.total_rows - len(plan.projects)} related row(s):")
        for table, count in sorted(plan.rows_by_table.items()):
            click.echo(f"  {table:24} {count:>6}")
        click.echo("  " + ", ".join(plan.projects[:12])
                   + (" ..." if len(plan.projects) > 12 else ""))

        if not apply:
            click.echo("\nDry run. Re-run with --apply to delete. "
                       "Back up first: dossier db backup")
            return
        if not yes:
            click.confirm(f"Delete {plan.total_rows} rows?", abort=True)

        done = purge_other_owners(session, keep_owner, apply=True)
        click.echo(f"Removed {len(done.projects)} project(s) and "
                   f"{done.total_rows - len(done.projects)} related row(s).")


@deltas.command("prune")
@click.option("--apply", is_flag=True, help="Actually delete. Without this nothing changes.")
def deltas_prune(apply: bool) -> None:
    """Remove deltas carrying no evidence of work.

    A stub has no description, no branch, no issue and no pull request -- a row
    somebody started and left, or one an old test wrote.
    """
    from dossier.maintenance import prune_stub_deltas

    with get_session() as session:
        names = prune_stub_deltas(session, apply=False)
        if not names:
            click.echo("No stub deltas.")
            return
        click.echo(f"{len(names)} stub delta(s): {', '.join(names)}")
        if not apply:
            click.echo("Dry run. Re-run with --apply to delete.")
            return
        prune_stub_deltas(session, apply=True)
        click.echo(f"Removed {len(names)} stub delta(s).")


@deltas.command("from-prs")
@click.option("--apply", is_flag=True, help="Actually write. Without this nothing changes.")
def deltas_from_prs(apply: bool) -> None:
    """Derive a delta from every open pull request.

    Identity is the project plus the PR number, so re-running updates rather
    than duplicating. A draft PR lands in implementation and a ready one in
    review, because draft means incomplete and nothing else.
    """
    from dossier.maintenance import deltas_from_pull_requests

    with get_session() as session:
        names = deltas_from_pull_requests(session, apply=False)
        if not names:
            click.echo("No open pull requests to derive from.")
            return
        click.echo(f"{len(names)} delta(s) from open pull requests.")
        if not apply:
            click.echo("Dry run. Re-run with --apply to write.")
            return
        deltas_from_pull_requests(session, apply=True)
        click.echo(f"Wrote {len(names)} delta(s).")


@deltas.command("prune-forks")
@click.option("--apply", is_flag=True, help="Actually delete. Without this nothing changes.")
def deltas_prune_forks(apply: bool) -> None:
    """Remove deltas belonging to forks.

    A fork's open pull requests are upstream's work. On a board they read
    exactly like the organisation's own.
    """
    from dossier.maintenance import prune_fork_deltas

    with get_session() as session:
        names = prune_fork_deltas(session, apply=False)
        if not names:
            click.echo("No deltas belong to forks.")
            return
        click.echo(f"{len(names)} delta(s) on forks: {', '.join(names[:10])}"
                   + (" ..." if len(names) > 10 else ""))
        if not apply:
            click.echo("Dry run. Re-run with --apply to delete.")
            return
        prune_fork_deltas(session, apply=True)
        click.echo(f"Removed {len(names)} delta(s).")


@db.command("health")
@click.option("--fix", is_flag=True,
              help="Apply the repairs this reports, backing up first")
def db_health(fix: bool) -> None:
    """Report what is wrong with this installation, and how to fix it."""
    from dossier.health import BLOCKED, check, render, repair, worst
    from dossier.health import candidate_databases

    findings = check()
    click.echo(render(findings))

    if not fix:
        if worst(findings) == BLOCKED:
            click.echo("\nRe-run with --fix to apply the repairs above.")
            raise SystemExit(1)
        return

    click.echo("")
    for path in candidate_databases():
        if not path.exists():
            continue
        for action in repair(path):
            click.echo(f"  {path.name}: {action}")
    click.echo("")
    click.echo(render(check()))
