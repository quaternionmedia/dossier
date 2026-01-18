"""Autolinker - Automatically build entity/link graphs from project data.

This module provides automatic discovery and linking of entities within
a project, creating a hierarchical graph of related projects.

Entity Scoping:
- Global: lang/*, pkg/* (same entity everywhere)
- App-scoped: github/user/* (same user across all repos)
- Repo-scoped: owner/repo/branch/*, owner/repo/issue/*, etc.
"""

from dataclasses import dataclass, field
from typing import Optional
from sqlmodel import Session, select

from dossier.models import (
    Project,
    ProjectComponent,
    ProjectContributor,
    ProjectIssue,
    ProjectLanguage,
    ProjectBranch,
    ProjectDependency,
    ProjectPullRequest,
    ProjectRelease,
    ProjectVersion,
    DocumentSection,
)


@dataclass
class LinkStats:
    """Statistics from an autolink operation."""
    projects_created: int = 0
    links_created: int = 0
    projects_found: int = 0
    links_found: int = 0
    errors: list[str] = field(default_factory=list)
    
    @property
    def total_projects(self) -> int:
        return self.projects_created + self.projects_found
    
    @property
    def total_links(self) -> int:
        return self.links_created + self.links_found


class AutoLinker:
    """Automatically builds entity/link graphs from project data.
    
    Usage:
        linker = AutoLinker(session)
        stats = linker.build_graph(project)
        
        # Or for all projects:
        stats = linker.build_all_graphs()
    """
    
    def __init__(self, session: Session):
        self.session = session
        self._project_cache: dict[str, Project] = {}
    
    def build_graph(
        self,
        project: Project,
        include_contributors: bool = True,
        include_languages: bool = True,
        include_dependencies: bool = True,
        include_branches: bool = True,
        include_issues: bool = True,
        include_prs: bool = True,
        include_versions: bool = True,
        include_docs: bool = True,
        max_contributors: int = 10,
        max_issues: int = 50,
        max_prs: int = 50,
    ) -> LinkStats:
        """Build an entity graph for a single project.
        
        Args:
            project: The root project to build graph for
            include_*: Flags to control which entity types to include
            max_*: Limits on certain entity types to avoid huge graphs
            
        Returns:
            LinkStats with counts of created/found projects and links
        """
        stats = LinkStats()
        
        owner = project.github_owner
        repo = project.github_repo
        
        if include_contributors:
            self._link_contributors(project, stats, max_contributors)
        
        if include_languages:
            self._link_languages(project, stats)
        
        if include_dependencies:
            self._link_dependencies(project, stats)
        
        if include_branches and owner and repo:
            self._link_branches(project, owner, repo, stats)
        
        if include_issues and owner and repo:
            self._link_issues(project, owner, repo, stats, max_issues)
        
        if include_prs and owner and repo:
            self._link_prs(project, owner, repo, stats, max_prs)
        
        if include_versions and owner and repo:
            self._link_versions(project, owner, repo, stats)
        
        if include_docs and owner and repo:
            self._link_docs(project, owner, repo, stats)
        
        self.session.commit()
        return stats
    
    def build_all_graphs(self, **kwargs) -> LinkStats:
        """Build entity graphs for all projects in the database.
        
        Returns:
            Combined LinkStats for all projects
        """
        total_stats = LinkStats()
        
        projects = self.session.exec(
            select(Project).where(
                Project.github_owner.isnot(None),
                Project.github_repo.isnot(None),
            )
        ).all()
        
        for project in projects:
            stats = self.build_graph(project, **kwargs)
            total_stats.projects_created += stats.projects_created
            total_stats.projects_found += stats.projects_found
            total_stats.links_created += stats.links_created
            total_stats.links_found += stats.links_found
            total_stats.errors.extend(stats.errors)
        
        return total_stats
    
    def _get_or_create_project(
        self,
        name: str,
        description: str,
        stats: LinkStats,
        **kwargs,
    ) -> Project:
        """Get existing project or create new one."""
        # Check cache first
        if name in self._project_cache:
            stats.projects_found += 1
            return self._project_cache[name]
        
        # Check database
        existing = self.session.exec(
            select(Project).where(Project.name == name)
        ).first()
        
        if existing:
            self._project_cache[name] = existing
            stats.projects_found += 1
            return existing
        
        # Create new project
        project = Project(name=name, description=description, **kwargs)
        self.session.add(project)
        self.session.flush()  # Get ID without committing
        self._project_cache[name] = project
        stats.projects_created += 1
        return project
    
    def _create_link(
        self,
        parent_id: int,
        child_id: int,
        relationship_type: str,
        stats: LinkStats,
        order: int = 0,
    ) -> Optional[ProjectComponent]:
        """Create a link between projects if it doesn't exist."""
        existing = self.session.exec(
            select(ProjectComponent).where(
                ProjectComponent.parent_id == parent_id,
                ProjectComponent.child_id == child_id,
            )
        ).first()
        
        if existing:
            stats.links_found += 1
            return existing
        
        link = ProjectComponent(
            parent_id=parent_id,
            child_id=child_id,
            relationship_type=relationship_type,
            order=order,
        )
        self.session.add(link)
        stats.links_created += 1
        return link
    
    def _link_contributors(
        self,
        project: Project,
        stats: LinkStats,
        max_contributors: int,
    ) -> None:
        """Link contributors as app-scoped user projects."""
        contributors = self.session.exec(
            select(ProjectContributor)
            .where(ProjectContributor.project_id == project.id)
            .order_by(ProjectContributor.contributions.desc())
            .limit(max_contributors)
        ).all()
        
        for i, contrib in enumerate(contributors):
            if not contrib.username:
                continue
            
            # App-scoped: github/user/{username}
            name = f"github/user/{contrib.username.lower()}"
            child = self._get_or_create_project(
                name=name,
                description=f"GitHub user: {contrib.username}",
                stats=stats,
                repository_url=contrib.profile_url or f"https://github.com/{contrib.username}",
                github_owner=contrib.username,
            )
            self._create_link(project.id, child.id, "contributor", stats, order=i)
    
    def _link_languages(self, project: Project, stats: LinkStats) -> None:
        """Link languages as global lang/ projects."""
        languages = self.session.exec(
            select(ProjectLanguage)
            .where(ProjectLanguage.project_id == project.id)
            .order_by(ProjectLanguage.percentage.desc())
        ).all()
        
        for i, lang in enumerate(languages):
            if not lang.language:
                continue
            
            # Global: lang/{language}
            name = f"lang/{lang.language.lower()}"
            child = self._get_or_create_project(
                name=name,
                description=f"{lang.language} programming language",
                stats=stats,
                github_language=lang.language,
            )
            self._create_link(project.id, child.id, "language", stats, order=i)
    
    def _link_dependencies(self, project: Project, stats: LinkStats) -> None:
        """Link dependencies as global pkg/ projects."""
        dependencies = self.session.exec(
            select(ProjectDependency)
            .where(ProjectDependency.project_id == project.id)
            .order_by(ProjectDependency.dep_type, ProjectDependency.name)
        ).all()
        
        for i, dep in enumerate(dependencies):
            if not dep.name:
                continue
            
            # Global: pkg/{package}
            name = f"pkg/{dep.name.lower()}"
            desc = f"{dep.name} package"
            if dep.version_spec:
                desc += f" ({dep.version_spec})"
            
            child = self._get_or_create_project(
                name=name,
                description=desc,
                stats=stats,
            )
            self._create_link(project.id, child.id, "dependency", stats, order=i)
    
    def _link_branches(
        self,
        project: Project,
        owner: str,
        repo: str,
        stats: LinkStats,
    ) -> None:
        """Link branches as repo-scoped branch/ projects."""
        branches = self.session.exec(
            select(ProjectBranch)
            .where(ProjectBranch.project_id == project.id)
            .order_by(ProjectBranch.is_default.desc(), ProjectBranch.name)
        ).all()
        
        for i, branch in enumerate(branches):
            if not branch.name:
                continue
            
            # Repo-scoped: owner/repo/branch/{name}
            branch_slug = branch.name.replace("/", "-")
            name = f"{owner}/{repo}/branch/{branch_slug}"
            desc = f"Branch: {branch.name}"
            if branch.is_default:
                desc += " (default)"
            
            child = self._get_or_create_project(
                name=name,
                description=desc,
                stats=stats,
                repository_url=f"https://github.com/{owner}/{repo}/tree/{branch.name}",
                github_owner=owner,
                github_repo=repo,
            )
            self._create_link(project.id, child.id, "branch", stats, order=i)
    
    def _link_issues(
        self,
        project: Project,
        owner: str,
        repo: str,
        stats: LinkStats,
        max_issues: int,
    ) -> None:
        """Link issues as repo-scoped issue/ projects."""
        issues = self.session.exec(
            select(ProjectIssue)
            .where(ProjectIssue.project_id == project.id)
            .order_by(ProjectIssue.issue_number.desc())
            .limit(max_issues)
        ).all()
        
        for i, issue in enumerate(issues):
            if not issue.issue_number:
                continue
            
            # Repo-scoped: owner/repo/issue/{number}
            name = f"{owner}/{repo}/issue/{issue.issue_number}"
            desc = f"Issue #{issue.issue_number}: {issue.title[:80] if issue.title else 'Untitled'}"
            
            child = self._get_or_create_project(
                name=name,
                description=desc,
                stats=stats,
                repository_url=f"https://github.com/{owner}/{repo}/issues/{issue.issue_number}",
                github_owner=owner,
                github_repo=repo,
            )
            self._create_link(project.id, child.id, "issue", stats, order=i)
    
    def _link_prs(
        self,
        project: Project,
        owner: str,
        repo: str,
        stats: LinkStats,
        max_prs: int,
    ) -> None:
        """Link pull requests as repo-scoped pr/ projects."""
        prs = self.session.exec(
            select(ProjectPullRequest)
            .where(ProjectPullRequest.project_id == project.id)
            .order_by(ProjectPullRequest.pr_number.desc())
            .limit(max_prs)
        ).all()
        
        for i, pr in enumerate(prs):
            if not pr.pr_number:
                continue
            
            # Repo-scoped: owner/repo/pr/{number}
            name = f"{owner}/{repo}/pr/{pr.pr_number}"
            desc = f"PR #{pr.pr_number}: {pr.title[:80] if pr.title else 'Untitled'}"
            if pr.is_merged:
                desc += " (merged)"
            
            child = self._get_or_create_project(
                name=name,
                description=desc,
                stats=stats,
                repository_url=f"https://github.com/{owner}/{repo}/pull/{pr.pr_number}",
                github_owner=owner,
                github_repo=repo,
            )
            self._create_link(project.id, child.id, "pr", stats, order=i)
    
    def _link_versions(
        self,
        project: Project,
        owner: str,
        repo: str,
        stats: LinkStats,
    ) -> None:
        """Link versions/releases as repo-scoped ver/ projects."""
        # Try ProjectVersion first
        versions = self.session.exec(
            select(ProjectVersion)
            .where(ProjectVersion.project_id == project.id)
            .order_by(
                ProjectVersion.major.desc(),
                ProjectVersion.minor.desc(),
                ProjectVersion.patch.desc(),
            )
        ).all()
        
        if versions:
            for i, ver in enumerate(versions):
                if not ver.version:
                    continue
                
                # Repo-scoped: owner/repo/ver/v{version}
                ver_slug = ver.version.lstrip("v").replace("/", "-")
                name = f"{owner}/{repo}/ver/v{ver_slug}"
                desc = f"Version {ver.version}"
                
                child = self._get_or_create_project(
                    name=name,
                    description=desc,
                    stats=stats,
                    repository_url=ver.release_url or f"https://github.com/{owner}/{repo}/releases/tag/v{ver.version}",
                    github_owner=owner,
                    github_repo=repo,
                )
                self._create_link(project.id, child.id, "version", stats, order=i)
        else:
            # Fall back to ProjectRelease
            releases = self.session.exec(
                select(ProjectRelease)
                .where(ProjectRelease.project_id == project.id)
                .order_by(ProjectRelease.release_published_at.desc())
            ).all()
            
            for i, rel in enumerate(releases):
                if not rel.tag_name:
                    continue
                
                # Repo-scoped: owner/repo/ver/{tag}
                tag_slug = rel.tag_name.lstrip("v").replace("/", "-")
                name = f"{owner}/{repo}/ver/v{tag_slug}"
                desc = f"Release {rel.tag_name}"
                if rel.name and rel.name != rel.tag_name:
                    desc = f"{rel.name} ({rel.tag_name})"
                
                child = self._get_or_create_project(
                    name=name,
                    description=desc,
                    stats=stats,
                    repository_url=f"https://github.com/{owner}/{repo}/releases/tag/{rel.tag_name}",
                    github_owner=owner,
                    github_repo=repo,
                )
                self._create_link(project.id, child.id, "version", stats, order=i)
    
    def _link_docs(
        self,
        project: Project,
        owner: str,
        repo: str,
        stats: LinkStats,
    ) -> None:
        """Link documentation sections as repo-scoped doc/ projects."""
        docs = self.session.exec(
            select(DocumentSection)
            .where(DocumentSection.project_id == project.id)
            .order_by(DocumentSection.order)
        ).all()
        
        for i, doc in enumerate(docs):
            if not doc.title:
                continue
            
            # Repo-scoped: owner/repo/doc/{type}-{slug}
            section_type = doc.section_type or "doc"
            slug = doc.title.lower().replace(" ", "-")[:30]
            name = f"{owner}/{repo}/doc/{section_type}-{slug}"
            desc = f"Documentation: {doc.title}"
            
            url = None
            if doc.source_file:
                url = f"https://github.com/{owner}/{repo}/blob/main/{doc.source_file}"
            
            child = self._get_or_create_project(
                name=name,
                description=desc,
                stats=stats,
                repository_url=url,
                documentation_path=doc.source_file,
                github_owner=owner,
                github_repo=repo,
            )
            self._create_link(project.id, child.id, "doc", stats, order=i)


def autolink_project(session: Session, project: Project, **kwargs) -> LinkStats:
    """Convenience function to autolink a single project."""
    linker = AutoLinker(session)
    return linker.build_graph(project, **kwargs)


def autolink_all(session: Session, **kwargs) -> LinkStats:
    """Convenience function to autolink all projects."""
    linker = AutoLinker(session)
    return linker.build_all_graphs(**kwargs)
