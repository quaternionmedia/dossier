"""One definition per kind of fact, asked at either scope.

THE PROBLEM THIS SOLVES. The overview aggregated `project_language` its own
way and the Languages tab queried the same table its own way, so the vertical
axis of the screen and the horizontal one were two interpretations of one
table. They agreed by luck, they used different words for the same column, and
neither knew the other existed.

A **facet** is one kind of fact -- languages, branches, contributors -- with
two readings of it:

    facet.org(session, ids, limit)      across every repository in scope
    facet.project(session, project)     for one repository

Both return a `Section`, so the same renderer draws either, and the same words
name the same column at both scopes. The tab a facet belongs to is declared
here too, which is what lets a row in the overview link to the tab that holds
its detail: the link is a lookup, not a mapping maintained by hand somewhere
else.

WHAT A FACET IS NOT. A view. It says what the rows are and what they are
called; how they are drawn belongs to the renderer, and where they are shown
belongs to the app.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from sqlalchemy import func
from sqlmodel import select

from dossier.models.schemas import (
    DeltaPhase,
    Project,
    ProjectBranch,
    ProjectContributor,
    ProjectDelta,
    ProjectDependency,
    ProjectIssue,
    ProjectLanguage,
    ProjectPullRequest,
    ProjectRelease,
)
from dossier.overview import (
    CLOSED_PHASES,
    Section,
    _ago,
    _age_days,
    _in_scope,
    _trim,
)


@dataclass(frozen=True)
class Facet:
    """One kind of fact, and where it is shown."""

    key: str
    title: str            # heading at org scope
    project_title: str    # heading at one project
    tab: str              # the tab holding the detail
    table: str            # the DataTable inside that tab
    org: Callable[..., Section]
    project: Callable[..., Section]

    def at(self, session: Any, *, ids=None, project=None, limit: int = 12) -> Section:
        """Read this facet at whichever scope was given."""
        if project is not None:
            return self.project(session, project, limit)
        return self.org(session, ids, limit)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _repo_names(session: Any) -> dict[int, str]:
    return {p.id: (p.full_name or p.name) for p in session.exec(select(Project)).all()}


# --- languages ---------------------------------------------------------------


def languages_org(session: Any, ids, limit: int) -> Section:
    seen = list(session.exec(_in_scope(
        select(ProjectLanguage.language, func.count(),
               func.sum(ProjectLanguage.bytes_count))
        .group_by(ProjectLanguage.language)
        .order_by(func.sum(ProjectLanguage.bytes_count).desc())
        .limit(limit), ProjectLanguage.project_id, ids)))
    total = sum(int(b or 0) for _, _, b in seen) or 1
    rows = tuple(
        (_trim(name, 18), str(repos), f"{int(b or 0) / 1_000_000:.1f}MB",
         f"{100 * int(b or 0) / total:.0f}%")
        for name, repos, b in seen
    )
    return Section(
        "Language mix", ("language", "repos", "bytes", "share"), rows,
        note=("Share is of the bytes in this table, not of the org: languages past "
              "the cut are not in the denominator."),
    )


def languages_project(session: Any, project: Any, limit: int) -> Section:
    rows = tuple(
        (_trim(row.language, 18), "1", f"{row.bytes_count / 1_000_000:.1f}MB",
         f"{row.percentage:.0f}%", _trim(row.file_extensions, 24))
        for row in session.exec(
            select(ProjectLanguage)
            .where(ProjectLanguage.project_id == project.id)
            .order_by(ProjectLanguage.bytes_count.desc())
        ).all()
    )
    return Section(
        "Languages", ("language", "repos", "bytes", "share", "extensions"), rows,
        note="Share is of this repository, as GitHub reports it.",
    )


# --- branches ----------------------------------------------------------------


BRANCH_COLUMNS = ("repo", "branch", "role", "commit", "author", "newest commit")


def _branch_row(branch: Any, repo: str, now: datetime) -> tuple[str, ...]:
    return (
        _trim(repo, 24), _trim(branch.name, 30),
        "default" if branch.is_default else
        ("protected" if branch.is_protected else "--"),
        (branch.commit_sha or "")[:8] or "--",
        _trim(branch.commit_author, 16),
        _ago(_age_days(branch.commit_date, now)),
    )


def branches_org(session: Any, ids, limit: int) -> Section:
    """Branches in flight, across scope. Default branches are left out.

    Every repository has one, so listing them says nothing about what is in
    progress -- and a list dominated by rows that are always there is a list
    nobody reads.
    """
    names = _repo_names(session)
    now = _now()
    rows = tuple(
        _branch_row(b, names.get(b.project_id, "?"), now)
        for b in session.exec(_in_scope(
            select(ProjectBranch)
            .where(ProjectBranch.is_default == False)  # noqa: E712
            .order_by(ProjectBranch.commit_date.desc())
            .limit(limit), ProjectBranch.project_id, ids)).all()
    )
    return Section(
        "Branches in flight", BRANCH_COLUMNS, rows,
        note=("A branch here is work in flight or work never cleaned up, and the "
              "two are indistinguishable from this side."),
    )


def branches_project(session: Any, project: Any, limit: int) -> Section:
    now = _now()
    repo = project.full_name or project.name
    rows = tuple(
        _branch_row(b, repo, now)
        for b in session.exec(
            select(ProjectBranch)
            .where(ProjectBranch.project_id == project.id)
            .order_by(ProjectBranch.commit_date.desc())
        ).all()
    )
    return Section("Branches", BRANCH_COLUMNS, rows,
                   note="Every branch, default included, most recent commit first.")


def contributors_org(session: Any, ids, limit: int) -> Section:
    rows = tuple(
        (_trim(login, 24), str(repos), f"{int(commits or 0):,}")
        for login, repos, commits in session.exec(_in_scope(
            select(ProjectContributor.username,
                   func.count(func.distinct(ProjectContributor.project_id)),
                   func.sum(ProjectContributor.contributions))
            .group_by(ProjectContributor.username)
            .order_by(func.count(func.distinct(ProjectContributor.project_id)).desc())
            .limit(limit), ProjectContributor.project_id, ids))
    )
    return Section(
        "Contributors by reach", ("login", "repos", "commits"), rows,
        note=("Ordered by repositories touched. Commit counts are as GitHub reports "
              "them and include merges. Forks are excluded: their contributors are "
              "upstream's."),
    )


def contributors_project(session: Any, project: Any, limit: int) -> Section:
    rows = tuple(
        (_trim(c.username, 24), "1", f"{c.contributions:,}")
        for c in session.exec(
            select(ProjectContributor)
            .where(ProjectContributor.project_id == project.id)
            .order_by(ProjectContributor.contributions.desc())
        ).all()
    )
    return Section(
        "Contributors", ("login", "repos", "commits"), rows,
        note="Commit counts are as GitHub reports them and include merges.",
    )


# --- dependencies ------------------------------------------------------------


def dependencies_org(session: Any, ids, limit: int) -> Section:
    rows = tuple(
        (_trim(name, 28), str(repos), "")
        for name, repos in session.exec(_in_scope(
            select(ProjectDependency.name,
                   func.count(func.distinct(ProjectDependency.project_id)))
            .group_by(ProjectDependency.name)
            .order_by(func.count(func.distinct(ProjectDependency.project_id)).desc())
            .limit(limit), ProjectDependency.project_id, ids))
    )
    return Section(
        "Shared dependencies", ("package", "repos", "manifest"), rows,
        note=("How many repositories in scope declare each package. A high count is "
              "a blast radius, not an endorsement."),
    )


def dependencies_project(session: Any, project: Any, limit: int) -> Section:
    rows = tuple(
        (_trim(d.name, 28), _trim(d.version_spec, 16), _trim(d.source, 20),
         d.dep_type or "--")
        for d in session.exec(
            select(ProjectDependency)
            .where(ProjectDependency.project_id == project.id)
            .order_by(ProjectDependency.dep_type, ProjectDependency.name)
        ).all()
    )
    return Section(
        "Dependencies", ("package", "version", "manifest", "kind"), rows,
        note="As declared in the manifest, not as resolved.",
    )


# --- issues and pull requests ------------------------------------------------


ISSUE_COLUMNS = ("repo", "number", "title", "state", "author", "updated")


def _issue_row(issue: Any, repo: str, now: datetime) -> tuple[str, ...]:
    return (
        _trim(repo, 24), f"#{issue.issue_number}", _trim(issue.title, 44),
        issue.state, _trim(issue.author, 16),
        _ago(_age_days(issue.issue_updated_at, now)),
    )


def issues_org(session: Any, ids, limit: int) -> Section:
    """The same list the tab shows, across every repository in scope."""
    names = _repo_names(session)
    now = _now()
    rows = tuple(
        _issue_row(issue, names.get(issue.project_id, "?"), now)
        for issue in session.exec(_in_scope(
            select(ProjectIssue)
            .where(ProjectIssue.state == "open")
            .order_by(ProjectIssue.issue_updated_at.desc())
            .limit(limit), ProjectIssue.project_id, ids)).all()
    )
    return Section(
        "Open issues", ISSUE_COLUMNS, rows,
        note="Only issues in an open state, most recently updated first.",
    )


def issues_project(session: Any, project: Any, limit: int) -> Section:
    now = _now()
    repo = project.full_name or project.name
    rows = tuple(
        _issue_row(issue, repo, now)
        for issue in session.exec(
            select(ProjectIssue)
            .where(ProjectIssue.project_id == project.id)
            .order_by(ProjectIssue.issue_updated_at.desc())
        ).all()
    )
    return Section("Issues", ISSUE_COLUMNS, rows,
                   note="Every issue synced, open or closed.")


def _pr_row(pr: Any, repo: str, now: datetime) -> tuple[str, ...]:
    return (
        _trim(repo, 24), f"#{pr.pr_number}", _trim(pr.title, 44),
        "draft" if pr.is_draft else pr.state,
        _trim(pr.head_branch, 22), _ago(_age_days(pr.pr_updated_at, now)),
    )


PR_COLUMNS = ("repo", "number", "title", "state", "branch", "updated")


def prs_org(session: Any, ids, limit: int) -> Section:
    """The same list the tab shows, across every repository in scope.

    A count per repository would have been cheaper and it would have been a
    second interpretation: the tab lists pull requests, so the org reading
    lists pull requests too, and the only difference is how many repositories
    are in view.
    """
    names = _repo_names(session)
    now = _now()
    rows = tuple(
        _pr_row(pr, names.get(pr.project_id, "?"), now)
        for pr in session.exec(_in_scope(
            select(ProjectPullRequest)
            .where(ProjectPullRequest.state == "open")
            .order_by(ProjectPullRequest.pr_updated_at.desc())
            .limit(limit), ProjectPullRequest.project_id, ids)).all()
    )
    return Section(
        "Open pull requests", PR_COLUMNS, rows,
        note=("One open pull request per repository per contributor is the corpus "
              "rule; a repository above one is worth a look, not an alarm. Draft "
              "means incomplete and nothing else."),
    )


def prs_project(session: Any, project: Any, limit: int) -> Section:
    now = _now()
    repo = project.full_name or project.name
    rows = tuple(
        _pr_row(pr, repo, now)
        for pr in session.exec(
            select(ProjectPullRequest)
            .where(ProjectPullRequest.project_id == project.id)
            .order_by(ProjectPullRequest.pr_updated_at.desc())
        ).all()
    )
    return Section(
        "Pull requests", PR_COLUMNS, rows,
        note=("Every pull request synced, open or closed. Draft means incomplete "
              "and nothing else."),
    )


# --- releases ----------------------------------------------------------------


RELEASE_COLUMNS = ("repo", "tag", "name", "kind", "published")


def _release_row(release: Any, repo: str, now: datetime) -> tuple[str, ...]:
    return (
        _trim(repo, 24), _trim(release.tag_name, 18), _trim(release.name, 34),
        "prerelease" if release.is_prerelease else "release",
        _ago(_age_days(release.release_published_at, now)),
    )


def releases_org(session: Any, ids, limit: int) -> Section:
    names = _repo_names(session)
    now = _now()
    rows = tuple(
        _release_row(r, names.get(r.project_id, "?"), now)
        for r in session.exec(_in_scope(
            select(ProjectRelease)
            .order_by(ProjectRelease.release_published_at.desc())
            .limit(limit), ProjectRelease.project_id, ids)).all()
    )
    return Section(
        "Releases", RELEASE_COLUMNS, rows,
        note=("A tag asserts a human reviewed the change set, manually tested it "
              "against its real runtime, and validation passed. Newest first."),
    )


def releases_project(session: Any, project: Any, limit: int) -> Section:
    now = _now()
    repo = project.full_name or project.name
    rows = tuple(
        _release_row(r, repo, now)
        for r in session.exec(
            select(ProjectRelease)
            .where(ProjectRelease.project_id == project.id)
            .order_by(ProjectRelease.release_published_at.desc())
        ).all()
    )
    return Section("Releases", RELEASE_COLUMNS, rows, note="Newest first.")


# --- deltas ------------------------------------------------------------------


def deltas_org(session: Any, ids, limit: int) -> Section:
    names = _repo_names(session)
    now = _now()
    stmt = _in_scope(
        select(ProjectDelta)
        .where(ProjectDelta.phase.notin_(CLOSED_PHASES))
        .order_by(ProjectDelta.updated_at.desc())
        .limit(limit), ProjectDelta.project_id, ids)
    rows = tuple(
        (_trim(names.get(d.project_id, "?"), 24),
         _trim(d.title, 40), getattr(d.phase, "value", str(d.phase)),
         _trim(d.branch_name or (f"#{d.pr_number}" if d.pr_number else None), 24),
         _ago(_age_days(d.updated_at, now)))
        for d in session.exec(stmt).all()
    )
    return Section(
        "On deck", ("repo", "delta", "phase", "evidence", "moved"), rows,
        note=("Open deltas, most recently moved first. An empty evidence column is "
              "work with no branch yet, not work with no home."),
    )


def deltas_project(session: Any, project: Any, limit: int) -> Section:
    names = _repo_names(session)
    now = _now()
    rows = tuple(
        (_trim(names.get(d.project_id, "?"), 24),
         _trim(d.title, 40), getattr(d.phase, "value", str(d.phase)),
         _trim(d.branch_name or (f"#{d.pr_number}" if d.pr_number else None), 24),
         _ago(_age_days(d.updated_at, now)))
        for d in session.exec(
            select(ProjectDelta)
            .where(ProjectDelta.project_id == project.id)
            .order_by(ProjectDelta.updated_at.desc())
        ).all()
    )
    return Section(
        "Deltas", ("repo", "delta", "phase", "evidence", "moved"), rows,
        note="Every delta for this repository, including closed phases.",
    )


# --- the registry ------------------------------------------------------------

FACETS: tuple[Facet, ...] = (
    Facet("deltas", "On deck", "Deltas", "tab-deltas", "deltas-table",
          deltas_org, deltas_project),
    Facet("prs", "Open pull requests", "Pull requests",
          "tab-prs", "prs-table", prs_org, prs_project),
    Facet("issues", "Open issues", "Issues",
          "tab-issues", "issues-table", issues_org, issues_project),
    Facet("branches", "Branches in flight", "Branches",
          "tab-branches", "branches-table", branches_org, branches_project),
    Facet("languages", "Language mix", "Languages",
          "tab-languages", "languages-table", languages_org, languages_project),
    Facet("dependencies", "Shared dependencies", "Dependencies",
          "tab-dependencies", "dependencies-table",
          dependencies_org, dependencies_project),
    Facet("contributors", "Contributors by reach", "Contributors",
          "tab-contributors", "contributors-table",
          contributors_org, contributors_project),
    Facet("releases", "Releases", "Releases",
          "tab-releases", "releases-table", releases_org, releases_project),
)

BY_KEY = {facet.key: facet for facet in FACETS}
BY_TAB = {facet.tab: facet for facet in FACETS}
BY_TITLE = {facet.title: facet for facet in FACETS}


def facet_for_section(section: Section) -> Facet | None:
    """The facet a rendered section came from, so a row can link to its tab."""
    return BY_TITLE.get(section.title)
