"""Dossier file format - standardized project overview files.

The .dossier file format provides a consistent way to describe and share
project overviews. It's a YAML-based format that captures key project metadata.

Format specification:
```yaml
dossier:
  version: "1.0"
  generated_at: "2026-01-17T10:30:00Z"

project:
  name: "owner/repo"
  description: "Project description"
  repository: "https://github.com/owner/repo"
  language: "Python"
  stars: 1234
  
overview:
  summary: "Brief one-line summary"
  purpose: "What the project does"
  audience: "Who it's for"
  
tech_stack:
  - name: "Python"
    percentage: 85.5
  - name: "JavaScript"
    percentage: 14.5

dependencies:
  runtime:
    - name: "click"
      version: "^8.0"
  dev:
    - name: "pytest"
      version: "^8.0"

activity:
  last_release: "v1.0.0"
  open_issues: 5
  open_prs: 2
  contributors: 10
  default_branch: "main"

links:
  documentation: "https://docs.example.com"
  changelog: "https://github.com/owner/repo/blob/main/CHANGELOG.md"
  issues: "https://github.com/owner/repo/issues"
```
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml
from sqlmodel import Session, select

from dossier.models import (
    DocumentSection,
    Project,
    ProjectBranch,
    ProjectContributor,
    ProjectDependency,
    ProjectIssue,
    ProjectLanguage,
    ProjectPullRequest,
    ProjectRelease,
    ProjectVersion,
)


DOSSIER_VERSION = "1.0"


def generate_dossier(
    session: Session,
    project: Project,
    include_docs: bool = True,
    include_activity: bool = True,
) -> dict:
    """Generate a dossier dictionary for a project.
    
    Args:
        session: Database session
        project: Project to generate dossier for
        include_docs: Include documentation sections summary
        include_activity: Include activity metrics
        
    Returns:
        Dictionary in dossier format
    """
    dossier = {
        "dossier": {
            "version": DOSSIER_VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
        "project": {
            "name": project.name,
            "description": project.description,
            "repository": project.repository_url,
            "language": project.github_language,
            "stars": project.github_stars,
            "synced_at": project.last_synced_at.isoformat() if project.last_synced_at else None,
        },
    }
    
    # Add overview from documentation sections
    if include_docs:
        sections = session.exec(
            select(DocumentSection)
            .where(DocumentSection.project_id == project.id)
            .order_by(DocumentSection.order)
        ).all()
        
        readme_section = None
        for section in sections:
            if section.section_type == "readme":
                readme_section = section
                break
        
        dossier["overview"] = {
            "summary": project.description or "",
            "readme_title": readme_section.title if readme_section else None,
            "doc_sections": len(sections),
        }
    
    # Add tech stack (languages)
    languages = session.exec(
        select(ProjectLanguage)
        .where(ProjectLanguage.project_id == project.id)
        .order_by(ProjectLanguage.percentage.desc())
    ).all()
    
    if languages:
        dossier["tech_stack"] = [
            {
                "name": lang.language,
                "percentage": round(lang.percentage, 1),
                "bytes": lang.bytes_count,
            }
            for lang in languages
        ]
    
    # Add dependencies
    dependencies = session.exec(
        select(ProjectDependency)
        .where(ProjectDependency.project_id == project.id)
        .order_by(ProjectDependency.dep_type, ProjectDependency.name)
    ).all()
    
    if dependencies:
        deps_by_type = {}
        for dep in dependencies:
            if dep.dep_type not in deps_by_type:
                deps_by_type[dep.dep_type] = []
            deps_by_type[dep.dep_type].append({
                "name": dep.name,
                "version": dep.version_spec,
                "source": dep.source,
            })
        dossier["dependencies"] = deps_by_type
    
    # Add activity metrics
    if include_activity:
        # Get branches
        branches = session.exec(
            select(ProjectBranch)
            .where(ProjectBranch.project_id == project.id)
        ).all()
        
        default_branch = None
        for branch in branches:
            if branch.is_default:
                default_branch = branch.name
                break
        
        # Get latest release
        releases = session.exec(
            select(ProjectRelease)
            .where(ProjectRelease.project_id == project.id)
            .order_by(ProjectRelease.release_published_at.desc())
            .limit(1)
        ).all()
        
        latest_release = releases[0] if releases else None
        
        # Get open issues/PRs count
        open_issues = session.exec(
            select(ProjectIssue)
            .where(ProjectIssue.project_id == project.id)
            .where(ProjectIssue.state == "open")
        ).all()
        
        open_prs = session.exec(
            select(ProjectPullRequest)
            .where(ProjectPullRequest.project_id == project.id)
            .where(ProjectPullRequest.state == "open")
        ).all()
        
        # Get contributor count
        contributors = session.exec(
            select(ProjectContributor)
            .where(ProjectContributor.project_id == project.id)
        ).all()
        
        dossier["activity"] = {
            "last_release": latest_release.tag_name if latest_release else None,
            "release_date": latest_release.release_published_at.isoformat() if latest_release and latest_release.release_published_at else None,
            "open_issues": len(open_issues),
            "open_prs": len(open_prs),
            "contributors": len(contributors),
            "branches": len(branches),
            "default_branch": default_branch,
        }
    
    # Add versions (semver)
    versions = session.exec(
        select(ProjectVersion)
        .where(ProjectVersion.project_id == project.id)
        .order_by(ProjectVersion.major.desc(), ProjectVersion.minor.desc(), ProjectVersion.patch.desc())
    ).all()
    
    if versions:
        dossier["versions"] = [
            {
                "version": ver.version,
                "semver": {
                    "major": ver.major,
                    "minor": ver.minor,
                    "patch": ver.patch,
                    "prerelease": ver.prerelease,
                    "build_metadata": ver.build_metadata,
                },
                "source": ver.source,
                "is_latest": ver.is_latest,
                "release_url": ver.release_url,
                "changelog_url": ver.changelog_url,
                "release_date": ver.release_date.isoformat() if ver.release_date else None,
            }
            for ver in versions
        ]
        
        # Find and mark the latest version
        latest_ver = next((v for v in versions if v.is_latest), versions[0] if versions else None)
        if latest_ver:
            dossier["project"]["version"] = latest_ver.version
    
    # Add links
    if project.github_owner and project.github_repo:
        base_url = f"https://github.com/{project.github_owner}/{project.github_repo}"
        dossier["links"] = {
            "repository": project.repository_url,
            "issues": f"{base_url}/issues",
            "pull_requests": f"{base_url}/pulls",
            "releases": f"{base_url}/releases",
        }
    
    return dossier


def export_dossier_yaml(
    session: Session,
    project: Project,
    output_path: Optional[Path] = None,
) -> str:
    """Export a project's dossier to YAML format.
    
    Args:
        session: Database session
        project: Project to export
        output_path: Optional path to write file to
        
    Returns:
        YAML string
    """
    dossier = generate_dossier(session, project)
    
    # Custom YAML representer for clean output
    def str_representer(dumper, data):
        if '\n' in data:
            return dumper.represent_scalar('tag:yaml.org,2002:str', data, style='|')
        return dumper.represent_scalar('tag:yaml.org,2002:str', data)
    
    yaml.add_representer(str, str_representer)
    
    yaml_content = yaml.dump(
        dossier,
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
        width=100,
    )
    
    if output_path:
        output_path.write_text(yaml_content, encoding="utf-8")
    
    return yaml_content


def parse_dossier_file(path: Path) -> dict:
    """Parse a .dossier file.
    
    Args:
        path: Path to .dossier file
        
    Returns:
        Parsed dossier dictionary
    """
    content = path.read_text(encoding="utf-8")
    return yaml.safe_load(content)


def validate_dossier(dossier: dict) -> tuple[bool, list[str]]:
    """Validate a dossier dictionary.
    
    Args:
        dossier: Dictionary to validate
        
    Returns:
        Tuple of (is_valid, list of error messages)
    """
    errors = []
    
    # Check required top-level keys
    if "dossier" not in dossier:
        errors.append("Missing required 'dossier' section")
    elif "version" not in dossier["dossier"]:
        errors.append("Missing dossier version")
    
    if "project" not in dossier:
        errors.append("Missing required 'project' section")
    elif "name" not in dossier["project"]:
        errors.append("Missing project name")
    
    return len(errors) == 0, errors


def create_dossier_from_scratch(
    name: str,
    description: Optional[str] = None,
    repository: Optional[str] = None,
    **kwargs,
) -> dict:
    """Create a new dossier dictionary from scratch.
    
    Args:
        name: Project name
        description: Project description
        repository: Repository URL
        **kwargs: Additional fields
        
    Returns:
        Dossier dictionary
    """
    return {
        "dossier": {
            "version": DOSSIER_VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
        "project": {
            "name": name,
            "description": description,
            "repository": repository,
            **kwargs,
        },
    }
