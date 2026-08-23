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


# --- the harness -------------------------------------------------------------

HARNESS_COLUMNS = ("harness", "invocation", "tool", "status", "ran")


def _harness_row(row: Any) -> tuple[str, ...]:
    # The address's last segment, not the whole address: the column beside it
    # already carries the harness, and repeating `owner/repo` on every line
    # pushes the part that differs off the edge.
    identifier = row.address.rsplit("/", 1)[-1]
    return (
        _trim(row.project, 22),
        identifier[:12],
        _trim(row.tool_name, 16),
        row.status or "--",
        _trim(row.ran_at, 19),
    )


def harness_org(session: Any, ids, limit: int) -> Section:
    """Every invocation this control panel has been shown.

    Not scoped by `ids`: a harness is named by `owner/repo` in its own payload
    and is not a row in `project`, so filtering by project ids would return
    nothing and look like an idle harness.
    """
    from dossier.models.harness import HarnessInvocation

    rows = tuple(
        _harness_row(row)
        for row in session.exec(
            select(HarnessInvocation)
            .order_by(HarnessInvocation.ran_at.desc())
            .limit(limit)
        ).all()
    )
    return Section(
        "Harness invocations", HARNESS_COLUMNS, rows,
        note=("What the harness reports having run, most recent first. It is an "
              "excerpt: the payload carries recent rows, and the totals it "
              "reports over its whole history are shown separately because they "
              "cannot be recomputed from these."),
    )


def harness_project(session: Any, project: Any, limit: int) -> Section:
    from dossier.models.harness import HarnessInvocation

    name = project.full_name or project.name
    rows = tuple(
        _harness_row(row)
        for row in session.exec(
            select(HarnessInvocation)
            .where(HarnessInvocation.project == name)
            .order_by(HarnessInvocation.ran_at.desc())
        ).all()
    )
    return Section(
        "Harness invocations", HARNESS_COLUMNS, rows,
        note=("Invocations a harness reported under this repository's address. "
              "Empty means none were reported, not that none ran."),
    )


# --- the registry ------------------------------------------------------------

# --- what is waiting on a person ---------------------------------------------

WAITING_COLUMNS = ("harness", "question", "asked", "options", "answer")


def _waiting_row(row: Any) -> tuple[str, ...]:
    return (
        _trim(row.project, 22),
        _trim(row.address.rsplit("/", 1)[-1], 22),
        _trim(row.prompt, 44),
        _trim((row.options or "").replace("\n", "/"), 18),
        row.answered_with or "-- waiting --",
    )


def _waiting_rows(session: Any, limit: int, project: str | None = None):
    """Outstanding first, because that is the order somebody acts in.

    Answered rows are kept and shown after them: what was asked and what was
    said is the audit trail, and a queue that hides its answers cannot show
    anybody why a thing was decided.

    Sorted here rather than in SQL. `answered_with IS NULL` orders correctly in
    sqlite and this has to hold for whatever a reader points it at, so the rule
    lives with the reason for it.
    """
    from dossier.models.harness import HarnessAsk

    query = select(HarnessAsk)
    if project is not None:
        query = query.where(HarnessAsk.project == project)
    rows = list(session.exec(query).all())
    rows.sort(key=lambda row: (row.answered_with is not None, row.asked_at or ""))
    return tuple(_waiting_row(row) for row in rows[:limit])


def waiting_org(session: Any, ids, limit: int) -> Section:
    """Every question a harness has put to a person.

    Not scoped by `ids`, for the same reason the harness facet is not: a
    harness is named by `owner/repo` in its own payload and is not a row in
    `project`.
    """
    return Section(
        "Waiting on a person", WAITING_COLUMNS,
        _waiting_rows(session, limit),
        note=("Questions a harness could not answer for itself. This panel "
              "shows them; it does not answer them -- the answer goes back "
              "across the seam as a payload, the same way the question came, "
              "because two systems believing they own one row is how a queue "
              "starts disagreeing with itself."),
    )


def waiting_project(session: Any, project: Any, limit: int) -> Section:
    return Section(
        "Waiting on a person", WAITING_COLUMNS,
        _waiting_rows(session, limit, project.full_name or project.name),
        note=("Questions this repository's harness has put to a person, "
              "outstanding first."),
    )


# --- the harness's thread archive --------------------------------------------

THREADS_COLUMNS = ("delta", "title", "speaks as", "phase", "turns", "state")


def _thread_state(row: Any) -> str:
    """What has happened to a conversation since it was first archived.

    `disagrees` is a finding rather than an inventory entry: an export that
    contradicts an earlier record of itself means one of the two readings is
    wrong, and nothing here can say which.
    """
    if row.get("diverged"):
        return "disagrees"
    return "grew" if (row.get("changes") or 0) > 1 else "new"


def _delta_name(row: Any) -> str:
    """The delta a thread is, named by the harness that owns it.

    **NOT DERIVED HERE.** The address arrives on the row because
    `qmcp.threads.service.as_delta_row` builds it from the same function that
    builds the delta payload. Recomputing `thread-{id}` on this side would be a
    second copy of somebody else's naming rule, and the two would agree right
    up until the day the prefix changed.

    A harness that predates the field sends nothing, and that reads as `--`
    rather than as a name this side invented. Unknown is a value.
    """
    address = row.get("address")
    return address.rsplit("/", 1)[-1] if address else "--"


def _threads_rows(archive: Any) -> tuple[tuple[str, ...], ...]:
    """Conversations the harness has archived, as deltas, disagreements first.

    **THE DELTA VOCABULARY, NOT AN INVENTORY.** A thread is a delta -- that is
    `governance/qm/records/DRAFT-deltas-compose.md` and the thread-archive work
    that followed it -- so this reads in the same words as every other board:
    an address, the level it speaks at, a phase, and the evidence under it.

    A thread whose export contradicts an earlier record of itself is the only
    row here that is a finding rather than an entry, so it sorts first. A page
    that buried it under four hundred rows would be an inventory with a finding
    hidden in it.
    """
    rows = sorted(archive.threads, key=lambda row: not row.get("diverged"))
    return tuple(
        (
            # THE NAME IS NOT TRIMMED AND THE TITLE IS. What is addressable
            # stays whole; what is descriptive gets cut. A delta name trimmed
            # to `thread-0ced522c-69a1-428c...` cannot be copied, related or
            # looked up, which is the whole of what a name is for -- whereas a
            # cut title still reads as the conversation it names.
            _delta_name(row),
            _trim(row.get("title") or row.get("id"), 30),
            _trim(row.get("perspective") or "--", 20),
            _trim(row.get("phase") or "--", 12),
            str(row.get("turns", 0)),
            _thread_state(row),
        )
        for row in rows
    )


def threads_org(session: Any, ids, limit: int) -> Section:
    """The archive, read from the harness over the seam.

    Not scoped by `ids` and not read from disk. dossier does not know where the
    archive keeps its files, deliberately: what crosses is HTTP and a schema,
    the same trade the delta and harness payloads make.
    """
    from dossier.threads import fetch

    archive = fetch()
    if not archive.reachable or not archive.indexed:
        # An empty table would say the archive is empty. Nobody answered, or
        # nobody has indexed -- different facts, and neither is zero threads.
        return Section("Thread archive", THREADS_COLUMNS, (), note=archive.note)

    return Section(
        "Thread archive", THREADS_COLUMNS, _threads_rows(archive)[:limit],
        note=(archive.note + " Every thread enters at `brainstorm` and stays "
              "there: nothing automatic can establish that a conversation was "
              "read and acted on, so advancing one is a person's act. The "
              "address and the phase are the harness's, not this panel's. "
              "Conversations that disagree with an earlier record of "
              "themselves are listed first and have not been repaired."),
    )


def threads_project(session: Any, project: Any, limit: int) -> Section:
    """The archive is not scoped to one project.

    A conversation belongs to no repository. What a session *produced* is
    addressed to one and appears under Deltas; the conversation itself stays
    here, whole.
    """
    return threads_org(session, None, limit)


HYGIENE_COLUMNS = ("repo", "at risk", "merged", "contained", "permanent",
                   "the branches only this machine has")


def _hygiene_row(survey: Any) -> tuple[str, ...]:
    if not survey.found:
        # Unknown is a value. A repository with no clone here is not a
        # repository with clean branches, and reporting zeros would say it was.
        return (_trim(survey.repo, 24), "--", "--", "--", "--",
                _trim(survey.reason, 44))

    named = ", ".join(name for name, _ in survey.at_risk[:3])
    if len(survey.at_risk) > 3:
        named += f", +{len(survey.at_risk) - 3}"
    counts = survey.counts
    return (
        _trim(survey.repo, 24),
        str(counts.get("at risk", 0)) if counts.get("at risk") else "--",
        str(counts.get("merged", 0)),
        str(counts.get("contained", 0)),
        str(counts.get("permanent", 0)),
        _trim(named or "none", 44),
    )


def _hygiene_note(surveys: list[Any]) -> str:
    read = [s for s in surveys if s.found]
    at_risk = sum(len(s.at_risk) for s in read)
    unread = len(surveys) - len(read)
    note = (
        "A branch carrying commits no other ref has is the only copy of "
        "something; a merged one is a label over history somebody already has. "
        "The Branches facet cannot tell those apart -- it reads the sync, which "
        "knows a tip and not what is reachable from elsewhere. This reads "
        "clones on this machine, so it answers what would be lost if this disk "
        "died, which is a question no server can answer. "
        f"{at_risk} branch(es) at risk across {len(read)} clone(s) read"
    )
    if unread:
        note += f", and {unread} repositor(y/ies) had no clone here to read"
    return note + (". Automation branches are counted separately and are "
                   "nobody's to lose. A branch whose work reached the default "
                   "branch by another route still shows at risk: git knows the "
                   "commit is unique and cannot know the change is redundant.")


def _surveys(names: list[str]) -> list[Any]:
    from dossier.branches import find_clone, survey

    return [survey(name, find_clone(name)) for name in sorted(set(names))]


def hygiene_org(session: Any, ids, limit: int) -> Section:
    """Branch hygiene across the repositories in scope, from local clones."""
    names = [n.split("/")[-1] for n in _repo_names(session).values() if n]
    surveys = _surveys(names[:limit])
    rows = tuple(_hygiene_row(s) for s in surveys)
    return Section("Branch hygiene", HYGIENE_COLUMNS, rows,
                   note=_hygiene_note(surveys))


def hygiene_project(session: Any, project: Any, limit: int) -> Section:
    """One repository's branches, classified."""
    name = (project.full_name or project.name or "").split("/")[-1]
    surveys = _surveys([name]) if name else []
    rows = tuple(_hygiene_row(s) for s in surveys)
    return Section("Branch hygiene", HYGIENE_COLUMNS, rows,
                   note=_hygiene_note(surveys))


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
    Facet("harness", "Harness invocations", "Harness invocations",
          "tab-harness", "harness-table", harness_org, harness_project),
    Facet("waiting", "Waiting on a person", "Waiting",
          "tab-waiting", "waiting-table", waiting_org, waiting_project),
    Facet("threads", "Thread archive", "Threads",
          "tab-threads", "threads-table", threads_org, threads_project),
    # Its own tab, not `tab-branches`. `BY_TAB` is keyed by tab, so a second
    # facet sharing one silently replaces the first -- 12 facets became 11
    # entries and the Branches tab started resolving to this.
    Facet("hygiene", "Branch hygiene", "Branch hygiene",
          "tab-hygiene", "hygiene-table", hygiene_org, hygiene_project),
)

BY_KEY = {facet.key: facet for facet in FACETS}
BY_TAB = {facet.tab: facet for facet in FACETS}
BY_TITLE = {facet.title: facet for facet in FACETS}


def facet_for_section(section: Section) -> Facet | None:
    """The facet a rendered section came from, so a row can link to its tab."""
    return BY_TITLE.get(section.title)
