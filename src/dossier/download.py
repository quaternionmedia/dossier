"""Bringing a repository -- or everything one owner has -- into this database.

**THREE COPIES OF ONE WRITE, AND THEY DISAGREED.** Before this module existed,
"fetch a GitHub repository and store it" was implemented three times:

- `cli.py::_sync_repos_batch`, ~340 lines, the complete one;
- `tui/app.py::run_sync`, which wrote the same eight tables from the same
  client, reading `branch["committed_at"]` and `pr["created_at"]`,
  `pr["merged_at"]`, `pr["closed_at"]` -- **four keys the client does not
  emit**. SQLModel accepts unknown keyword arguments silently, so every branch
  landed with no commit date and every pull request with no timestamps, in the
  panel and not on the command line, for as long as both existed;
- `tui/app.py::run_sync_batch`, which fetched contributors, issues, languages,
  dependencies, branches, pull requests and releases -- seven calls per
  repository -- **discarded all seven**, and then called `.get()` on a
  `GitHubRepo` dataclass. That raises `AttributeError`, its `except Exception`
  caught it, and the dashboard reported "Failed to sync" for every project in
  every batch. That is the path `s` and the ring's sync both end in.

None of that is visible from inside any one of the three. It is visible from a
list, which is the same argument `actions.py` makes about routes, applied to
the write instead of the route.

**SO THERE IS ONE WRITER.** `absorb` puts one repository and everything hanging
off it into the database, and it is the only place that knows which column takes
which key. A caller chooses *what* to fetch and *what to say about it*; none of
them chooses how it is stored.

**REPORTING IS A CALLBACK, NOT A PRINT.** The command line renders a coloured
line per repository and the panel moves a progress bar; both are presentation,
and a shared engine that called `click.echo` would be one that only the command
line could use. `download` reports a `Fetched` per repository and decides
nothing about how it reads.

WHAT THIS CANNOT DO.

  * Decide whether you may read something. A private repository fetched without
    a token fails at the network, and the failure is carried in the words the
    API used rather than translated into a guess.
  * Fetch what GitHub will not serve. A rate limit stops the run and says so;
    the rows already committed stay committed, so running it again continues
    rather than starting over. That is the same contract the command line
    already promised in its help text.
  * Know whether an owner is a person or an organisation without asking. It
    asks -- one call -- rather than trying `/orgs` and falling back, because a
    fallback that fires on any error reports "no such organisation" for a
    network outage.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Sequence

from sqlmodel import select

from dossier.models import utcnow
from dossier.models.schemas import (
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

USER, ORGANIZATION = "user", "organization"

# What happened to one repository. `SKIPPED` is not a failure and `RATE_LIMITED`
# is not one either -- it is the run stopping early with everything so far
# saved, which is a different thing from a repository that could not be read.
FETCHED, SKIPPED, FAILED, RATE_LIMITED = (
    "fetched", "skipped", "failed", "rate limited")

# How recently a repository must have been synced for a run to pass over it.
# Hours rather than the overview's days: this is "somebody just did this", not
# "this is current".
RECENTLY_SYNCED_HOURS = 1

# Below this many calls left, a batch waits for the window rather than spending
# the remainder on half a repository.
RATE_LIMIT_FLOOR = 20


@dataclass(frozen=True)
class Owner:
    """A GitHub login, what kind of account it is, and what it has."""

    login: str
    kind: str
    """`user` or `organization`. It decides which endpoint lists the
    repositories, and the two are not interchangeable: `/users/x/repos` returns
    nothing for an organisation rather than failing."""

    repos: tuple[Any, ...] = ()

    @property
    def is_organization(self) -> bool:
        return self.kind == ORGANIZATION


@dataclass(frozen=True)
class Inventory:
    """What an owner has, and which of it this database already holds.

    **LIST FIRST, ACT SECOND** -- the pattern `clone.py` already uses, for the
    same reason. Downloading an owner is tens of repositories and hundreds of
    API calls against a budget that runs out, so what it would do is something
    a person gets to read before it happens rather than after.
    """

    owner: Owner
    held: frozenset[str] = frozenset()
    """`owner/name` for every repository of this owner's the database has."""

    @property
    def repos(self) -> tuple[Any, ...]:
        return self.owner.repos

    @property
    def new(self) -> tuple[Any, ...]:
        """The ones this database has never seen."""
        return tuple(r for r in self.repos if r.full_name not in self.held)

    @property
    def already(self) -> tuple[Any, ...]:
        return tuple(r for r in self.repos if r.full_name in self.held)

    def summary(self) -> str:
        """One sentence, and it always names a number.

        A refresh that says nothing is indistinguishable from one that did not
        run -- `tui/app.py::_sync_current_view` states the same rule about the
        same key.
        """
        if not self.repos:
            return (f"{self.owner.login} is a {self.owner.kind} with no "
                    f"repositories this token can see")
        new, already = len(self.new), len(self.already)
        if not already:
            return (f"{self.owner.login} ({self.owner.kind}): {len(self.repos)} "
                    f"repository(ies), none of them held here yet")
        return (f"{self.owner.login} ({self.owner.kind}): {len(self.repos)} "
                f"repository(ies) -- {new} new, {already} already held and "
                f"due a refresh")


@dataclass(frozen=True)
class Fetched:
    """What happened to one repository, as it happened.

    Carries `detail` in the words the tool used rather than a category. A
    repository that does not exist, one the token cannot read and one whose
    disk is full all fail, and only the API can say which -- the same argument
    `clone.Outcome` makes.
    """

    repo: str
    index: int
    total: int
    outcome: str
    detail: str = ""

    @property
    def ok(self) -> bool:
        return self.outcome == FETCHED


@dataclass
class Report:
    """The tally, and whether the run stopped early."""

    outcomes: list[Fetched] = field(default_factory=list)
    rate_limited: bool = False

    @property
    def fetched(self) -> int:
        return sum(1 for o in self.outcomes if o.outcome == FETCHED)

    @property
    def skipped(self) -> int:
        return sum(1 for o in self.outcomes if o.outcome == SKIPPED)

    @property
    def failed(self) -> int:
        return sum(1 for o in self.outcomes if o.outcome == FAILED)

    def summary(self) -> str:
        parts = [f"{self.fetched} fetched"]
        if self.failed:
            parts.append(f"{self.failed} failed")
        if self.skipped:
            parts.append(f"{self.skipped} already current")
        said = ", ".join(parts)
        if self.rate_limited:
            said += ". The rate limit stopped it; what was fetched is saved, " \
                    "so running it again continues"
        return said


# --- who an owner is, and what they have -------------------------------------


def look_up(client: Any, login: str) -> Owner:
    """Resolve a login and list its repositories. Two calls, in that order.

    **IT ASKS WHICH KIND OF ACCOUNT THIS IS.** Trying `/orgs/{login}/repos` and
    falling back to `/users/{login}/repos` on any error would report "not an
    organisation" for a timeout, an expired token and a typo alike -- three
    different things a person would act on differently. `/users/{login}` answers
    it in one call, for organisations too, and it is the answer GitHub itself
    gives.
    """
    login = (login or "").strip().strip("/")
    if not login:
        raise ValueError("no owner named")
    # A pasted profile URL is a login somebody had in their hand. Accepting it
    # costs one line and saves the failure mode where the field looks right.
    if "github.com/" in login:
        login = login.split("github.com/", 1)[1].split("/")[0]

    account = client.get(f"/users/{login}").json()
    kind = ORGANIZATION if account.get("type") == "Organization" else USER
    listed = (client.list_org_repos(login) if kind == ORGANIZATION
              else client.list_user_repos(login))
    return Owner(login=login, kind=kind, repos=tuple(listed))


def inventory(session: Any, client: Any, login: str) -> Inventory:
    """What `login` has, and which of it is already here."""
    owner = look_up(client, login)
    wanted = {repo.full_name for repo in owner.repos}
    if not wanted:
        return Inventory(owner=owner)
    held = {
        (project.full_name or project.name)
        for project in session.exec(select(Project)).all()
        if (project.full_name or project.name) in wanted
    }
    return Inventory(owner=owner, held=frozenset(held))


def narrow(repos: Sequence[Any], *, skip_forks: bool = False,
           language: str | None = None, limit: int = 0) -> tuple[Any, ...]:
    """The filters `sync-user` and `sync-org` both offered, applied once.

    `skip_forks` reads the repository's own `is_fork` flag. The command line
    used to test whether the *name* ended in `-fork`, which is not what a fork
    is and matched almost nothing.
    """
    found = list(repos)
    if skip_forks:
        found = [r for r in found if not r.is_fork]
    if language:
        found = [r for r in found
                 if r.language and r.language.lower() == language.lower()]
    if limit > 0:
        found = found[:limit]
    return tuple(found)


# --- the one writer ----------------------------------------------------------


def _replace(session: Any, model: Any, project_id: int) -> None:
    """Drop what this project had of `model`, so a refresh is not an append."""
    for old in session.exec(
            select(model).where(model.project_id == project_id)).all():
        session.delete(old)


def absorb(session: Any, parser: Any, client: Any, repo: Any, *,
           include_docs: bool = True, parent: Any = None,
           order: int = 0, extended: bool = True) -> Project:
    """Put one repository, and everything hanging off it, into the database.

    **THE ONLY PLACE THAT KNOWS WHICH COLUMN TAKES WHICH KEY.** That knowledge
    was in three places and two of them had it wrong; the keys the client emits
    are `commit_date`, `pr_created_at`, `pr_updated_at`, `pr_merged_at`, and a
    caller reading `committed_at` or `closed_at` wrote nulls in silence because
    SQLModel drops keyword arguments it does not recognise.

    `extended` is the one axis a caller may vary: the eight related tables cost
    seven API calls per repository, and a caller with a rate limit to spend may
    want the project row and its documents alone. **It is not a failure path.**
    Fetching the seven and then discarding them, which is what the panel's
    batch sync did, is the worst of both -- the calls are spent and the rows
    are not there.

    Extended data is best-effort as a whole rather than per table, deliberately:
    an owner whose token cannot read issues can still have their branches
    stored, and a partial refresh is worth more than a refusal.
    """
    project_name = repo.full_name
    existing = session.exec(
        select(Project).where(Project.name == project_name)).first()

    _, sections = parser.parse_repo(
        repo.owner, repo.name, include_docs_folder=include_docs)

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
        _replace(session, DocumentSection, project.id)
    else:
        project = Project(
            name=project_name,
            full_name=repo.full_name,
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

    for section in sections:
        section.project_id = project.id
        session.add(section)

    if extended:
        _absorb_extended(session, client, project, repo)

    if parent is not None and project.id != parent.id:
        linked = session.exec(
            select(ProjectComponent).where(
                ProjectComponent.parent_id == parent.id,
                ProjectComponent.child_id == project.id,
            )).first()
        if not linked:
            session.add(ProjectComponent(
                parent_id=parent.id, child_id=project.id,
                relationship_type="component", order=order))

    return project


def _absorb_extended(session: Any, client: Any, project: Project,
                     repo: Any) -> None:
    """The eight related tables. Best-effort, and it says nothing if it fails.

    Silent because the caller already has a route for saying so -- `download`
    turns an exception here into a `Fetched` the caller renders. Raising past
    `absorb` would lose the project row that was already written, which is the
    part worth keeping.
    """
    owner, name = repo.owner, repo.name

    try:
        _replace(session, ProjectLanguage, project.id)
        for language in client.get_languages(owner, name):
            session.add(ProjectLanguage(
                project_id=project.id,
                language=language["language"],
                bytes_count=language.get("bytes_count", 0),
                percentage=language.get("percentage", 0.0),
                file_extensions=language.get("file_extensions"),
                encoding=language.get("encoding"),
            ))

        _replace(session, ProjectDependency, project.id)
        for dependency in client.get_dependencies(owner, name):
            session.add(ProjectDependency(
                project_id=project.id,
                name=dependency["name"],
                version_spec=dependency.get("version_spec"),
                dep_type=dependency.get("dep_type", "runtime"),
                source=dependency.get("source", "unknown"),
            ))

        _replace(session, ProjectContributor, project.id)
        for contributor in client.get_contributors(owner, name,
                                                   max_contributors=10):
            session.add(ProjectContributor(
                project_id=project.id,
                username=contributor["username"],
                avatar_url=contributor.get("avatar_url"),
                contributions=contributor.get("contributions", 0),
                profile_url=contributor.get("profile_url"),
            ))

        _replace(session, ProjectIssue, project.id)
        for issue in client.get_issues(owner, name, state="all", max_issues=20):
            session.add(ProjectIssue(
                project_id=project.id,
                issue_number=issue["issue_number"],
                title=issue["title"],
                state=issue.get("state", "open"),
                author=issue.get("author"),
                labels=issue.get("labels"),
                # **WRITTEN, AND THEY WERE NOT BY ANY OF THE THREE.** The
                # client has emitted these since it learned to page; every
                # writer dropped them, so `project_issue` carried the row's
                # own creation time and nothing about the issue's.
                issue_created_at=issue.get("issue_created_at"),
                issue_updated_at=issue.get("issue_updated_at"),
            ))

        _replace(session, ProjectBranch, project.id)
        for branch in client.get_branches(owner, name, max_branches=20):
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

        _replace(session, ProjectPullRequest, project.id)
        for pull in client.get_pull_requests(owner, name, state="all",
                                             max_prs=20):
            session.add(ProjectPullRequest(
                project_id=project.id,
                pr_number=pull["pr_number"],
                title=pull["title"],
                state=pull.get("state", "open"),
                author=pull.get("author"),
                base_branch=pull.get("base_branch"),
                head_branch=pull.get("head_branch"),
                is_draft=pull.get("is_draft", False),
                is_merged=pull.get("is_merged", False),
                additions=pull.get("additions", 0),
                deletions=pull.get("deletions", 0),
                labels=pull.get("labels"),
                pr_created_at=pull.get("pr_created_at"),
                pr_updated_at=pull.get("pr_updated_at"),
                pr_merged_at=pull.get("pr_merged_at"),
            ))

        _replace(session, ProjectRelease, project.id)
        for release in client.get_releases(owner, name, max_releases=10):
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
    except Exception:                              # noqa: BLE001
        # The project row and its documents are already written and are worth
        # keeping. See the docstring: the caller is where this is reported.
        pass


# --- the batch ---------------------------------------------------------------


def is_current(project: Any, *, hours: int = RECENTLY_SYNCED_HOURS) -> bool:
    """Whether a project was synced recently enough to pass over.

    Timezone-naive datetimes come back out of SQLite, and comparing one to an
    aware `utcnow()` raises -- which, inside a per-repository `try`, read as
    the repository failing to fetch.
    """
    from datetime import timedelta, timezone

    last = getattr(project, "last_synced_at", None)
    if last is None:
        return False
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    return (utcnow() - last) < timedelta(hours=hours)


def download(session: Any, parser: Any, client: Any, repos: Sequence[Any], *,
             on_each: Callable[[Fetched], None] | None = None,
             include_docs: bool = True, parent: Any = None,
             force: bool = False, extended: bool = True,
             batch_size: int = 5, delay_between_batches: float = 2.0,
             sleep: Callable[[float], None] = time.sleep) -> Report:
    """Fetch every repository in `repos`, reporting each as it lands.

    **IT COMMITS PER REPOSITORY, NOT AT THE END.** A rate limit or a stopped
    process then leaves everything already fetched in the database, which is
    what makes "run it again to continue" true rather than a hope.

    `on_each` is how this is rendered. The command line paints a coloured line
    and the panel moves a progress bar; neither is this module's business, and
    a shared engine that printed would be one only the command line could use.
    """
    report = Report()
    total = len(repos)

    def say(one: Fetched) -> None:
        report.outcomes.append(one)
        if on_each is not None:
            on_each(one)

    for start in range(0, total, max(batch_size, 1)):
        batch = repos[start:start + max(batch_size, 1)]

        for offset, repo in enumerate(batch):
            index = start + offset + 1
            existing = session.exec(
                select(Project).where(Project.name == repo.full_name)).first()
            if existing is not None and not force and is_current(existing):
                say(Fetched(repo.full_name, index, total, SKIPPED,
                            "synced within the hour"))
                continue

            try:
                absorb(session, parser, client, repo,
                       include_docs=include_docs, parent=parent,
                       order=index, extended=extended)
                session.commit()
                say(Fetched(repo.full_name, index, total, FETCHED))
            except Exception as exc:               # noqa: BLE001
                session.rollback()
                detail = str(exc)
                if "rate limit" in detail.lower():
                    report.rate_limited = True
                    say(Fetched(repo.full_name, index, total, RATE_LIMITED,
                                detail))
                    return report
                say(Fetched(repo.full_name, index, total, FAILED, detail))

        if start + len(batch) < total:
            remaining = getattr(getattr(client, "rate_limit", None),
                                "remaining", None)
            if remaining is not None and remaining < RATE_LIMIT_FLOOR:
                wait = min(getattr(client.rate_limit,
                                   "seconds_until_reset", 0) or 0, 60)
                if wait > 0:
                    sleep(wait)
            elif delay_between_batches > 0:
                sleep(delay_between_batches)

    return report


@dataclass(frozen=True)
class Onboarded:
    """A first run, stage by stage: what was found, fetched, and made of it."""

    inventory: Inventory
    report: Report
    deltas: tuple[str, ...] = ()
    derived: bool = True
    """False when deriving was not asked for, which is different from deriving
    nothing. An owner whose repositories have no open pull requests really has
    no work in flight, and that is a reading rather than a step that was
    skipped."""

    def summary(self) -> str:
        """Every stage says its own number.

        **ONE SENTENCE PER STAGE, NOT ONE FOR THE RUN.** A first run that fetched
        thirty repositories and derived nothing has done something worth seeing,
        and a single combined figure hides which half did it.
        """
        said = [self.inventory.summary(), self.report.summary()]
        if not self.derived:
            said.append("Work in flight was not derived")
        elif self.deltas:
            said.append(f"{len(self.deltas)} delta(s) from open pull requests")
        else:
            said.append("No open pull requests, so there is no work in flight "
                        "to put on the board")
        return ". ".join(part.rstrip(".") for part in said) + "."


def onboard(session: Any, parser: Any, client: Any, login: str, *,
            derive: bool = True,
            on_each: Callable[[Fetched], None] | None = None,
            on_stage: Callable[[str], None] | None = None,
            **kwargs: Any) -> Onboarded:
    """The whole first run for one owner: fetch what they have, then read it.

    **FETCHING AN ORGANISATION LEAVES A BOARD WITH NOTHING ON IT.** The repos
    land, their open pull requests land with them, and the Deltas pane stays
    empty -- because a delta is derived from a pull request by
    `maintenance.deltas_from_pull_requests`, which until now only
    `dossier deltas from-prs` called. So somebody who had just downloaded an
    organisation saw an empty board and had no reason to think a second
    command existed.

    **THE STAGES REPORT SEPARATELY, WHICH IS THE POINT.** A derivation that
    finds nothing and a download that failed look identical in one combined
    number, and they are not the same thing at all.
    """
    found = inventory(session, client, login)
    if on_stage is not None:
        on_stage(found.summary())

    wanted = narrow(found.repos,
                    skip_forks=kwargs.pop("skip_forks", False),
                    language=kwargs.pop("language", None),
                    limit=kwargs.pop("limit", 0))
    report = download(session, parser, client, wanted, on_each=on_each,
                      **kwargs)
    if on_stage is not None:
        on_stage(report.summary())

    if not derive:
        return Onboarded(inventory=found, report=report, derived=False)

    from dossier.maintenance import deltas_from_pull_requests

    # **DERIVED FROM THE DATABASE, NOT FROM THE FETCH.** The pull requests are
    # rows by now; reading them back is one query and cannot disagree with
    # what landed. It also picks up repositories fetched on an earlier run,
    # which is what somebody re-running this expects.
    names = tuple(deltas_from_pull_requests(session, apply=True))
    if on_stage is not None:
        on_stage(f"{len(names)} delta(s) from open pull requests")
    return Onboarded(inventory=found, report=report, deltas=names)
