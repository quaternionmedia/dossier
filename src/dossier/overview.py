"""The org at a glance, computed from what has been synced.

WHY A MODULE AND NOT A WIDGET. Everything here is a plain query returning plain
dataclasses. It imports no Textual, no Rich and no renderer, for the same reason
`rad/session.py` imports no Textual: the overview is wanted in three places --
the TUI tab, the API, and eventually a `Show` verb in the ring -- and a
computation living inside a widget is a computation that can only be had by
mounting a widget.

WHAT IT WILL AND WILL NOT SAY.

  * **Governance values are passed through verbatim.** `seed_drift`, `phase`,
    `release_state` and `slot_state` are the generator's words. This module
    counts how many rows carry each value and never renames one or rules on it
    -- a renderer that re-spells a governance value has defined a second
    vocabulary for it, and the corpus's word is the one that governs.
  * **Claim and evidence stay in separate columns.** `phase` is a human's entry
    in the corpus roster; `precondition` is what landed on a default branch.
    They are rendered side by side because the gap between them is the signal,
    and merging them would delete exactly the fact worth having.
  * **Staleness is an age, not a verdict**, and the threshold used to sort is
    stated in the section's note rather than hidden in a comparison. dossier
    does not own the corpus's staleness budgets.

WHAT IT CANNOT DO. Tell you the org is healthy. Every figure is *as last
synced*, and a repository that was never synced is absent from most of these
counts rather than counted as zero -- which is why `never_synced` is a masthead
figure and not a footnote. `generated_from` carries the sync horizon so a reader
can see how old the whole picture is before reading any number in it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Sequence

from sqlalchemy import func
from sqlmodel import select

from dossier.models.governance import GovernanceRepository
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

# Deltas in these phases are not on anyone's deck.
CLOSED_PHASES = (DeltaPhase.COMPLETE, DeltaPhase.ABANDONED)

# Used only to order the attention list. Stated in the section note, never
# rendered as a pass or a fail.
STALE_AFTER_DAYS = 30


@dataclass(frozen=True)
class Cell:
    """One masthead figure. `note` qualifies it; it is not decoration."""

    label: str
    value: str
    note: str = ""


@dataclass(frozen=True)
class Section:
    """A titled table. `note` states what the rows do and do not mean."""

    title: str
    headers: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]
    note: str = ""

    @property
    def is_empty(self) -> bool:
        return not self.rows


@dataclass(frozen=True)
class OrgOverview:
    masthead: tuple[Cell, ...] = ()
    sections: tuple[Section, ...] = ()
    generated_from: str = ""
    scope: str = ""

    def section(self, title: str) -> Section | None:
        for s in self.sections:
            if s.title == title:
                return s
        return None


def _one(session: Any, statement: Any, default: Any = 0) -> Any:
    result = session.exec(statement).one_or_none()
    if result is None:
        return default
    return result if not isinstance(result, tuple) else result[0]


def _count(session: Any, model: Any, *where: Any) -> int:
    stmt = select(func.count()).select_from(model)
    for clause in where:
        stmt = stmt.where(clause)
    return int(_one(session, stmt) or 0)


def _age_days(then: datetime | None, now: datetime) -> float | None:
    if then is None:
        return None
    if then.tzinfo is None:
        then = then.replace(tzinfo=timezone.utc)
    return (now - then).total_seconds() / 86400.0


def _ago(days: float | None) -> str:
    """An age a reader can act on. `never` is a fact, not a missing value."""
    if days is None:
        return "never"
    if days < 1:
        return "today"
    if days < 45:
        return f"{int(days)}d"
    return f"{int(days / 30)}mo"


def _pct(part: int, whole: int) -> str:
    return f"{(100 * part / whole):.0f}%" if whole else "--"


def _trim(text: str | None, width: int) -> str:
    text = (text or "").replace("\n", " ").strip()
    if not text:
        return "--"
    return text if len(text) <= width else text[: width - 1] + "\u2026"


# --- the sections -----------------------------------------------------------


def _masthead(session: Any, now: datetime) -> tuple[Cell, ...]:
    repos = _count(session, Project)
    synced = _count(session, Project, Project.last_synced_at.isnot(None))
    stars = int(_one(session, select(func.sum(Project.github_stars))) or 0)
    langs = int(_one(session, select(func.count(func.distinct(ProjectLanguage.language)))) or 0)
    people = int(_one(session, select(func.count(func.distinct(ProjectContributor.username)))) or 0)
    open_prs = _count(session, ProjectPullRequest, ProjectPullRequest.state == "open")
    open_issues = _count(session, ProjectIssue, ProjectIssue.state == "open")
    on_deck = _count(session, ProjectDelta, ProjectDelta.phase.notin_(CLOSED_PHASES))

    return (
        Cell("repositories", str(repos), f"{synced} synced, {_pct(synced, repos)}"),
        Cell("never synced", str(repos - synced), "absent from the counts below"),
        Cell("stars", f"{stars:,}", "as last synced"),
        Cell("languages", str(langs), "distinct, across synced repos"),
        Cell("contributors", str(people), "distinct logins"),
        Cell("open PRs", str(open_prs), f"{_count(session, ProjectPullRequest)} tracked"),
        Cell("open issues", str(open_issues), f"{_count(session, ProjectIssue)} tracked"),
        Cell("branches", str(_count(session, ProjectBranch)), "all repos"),
        Cell("releases", str(_count(session, ProjectRelease)), "tags seen"),
        Cell("deltas on deck", str(on_deck), f"{_count(session, ProjectDelta)} total"),
        Cell("under governance", str(_count(session, GovernanceRepository)), "repos in the roster"),
    )


def _governance(session: Any, now: datetime) -> Section:
    rows: list[tuple[str, ...]] = []
    for repo in session.exec(select(GovernanceRepository).order_by(GovernanceRepository.name)):
        rows.append((
            _trim(repo.name, 22),
            repo.phase or "--",
            repo.precondition or repo.precondition_unknown or "--",
            repo.release_state or repo.release_unknown or "--",
            repo.release_latest or "--",
            f"{repo.records_ratified or 0}/{repo.records_total or 0}",
            repo.seed_drift or repo.seed_drift_unknown or "--",
            str(repo.behind_corpus) if repo.behind_corpus is not None else "--",
            repo.slot_state or repo.slot_unknown or "--",
            _ago(_age_days(repo.governance_generated_at, now)),
        ))
    return Section(
        "Governance posture",
        ("repo", "phase", "precondition", "release", "tag", "ratified",
         "seed", "behind", "slot", "doc age"),
        tuple(rows),
        note=(
            "phase is a claim entered by a human; precondition and release are evidence "
            "from the default branch. Read across, not down: the gap between the claim "
            "and the evidence is the signal. Values are the generator's own words. A tag "
            "asserts a human reviewed the change set, manually tested it against its real "
            "runtime, and validation passed; main asserts nothing, so unreleased and "
            "current are not the same state."
        ),
    )


def _deltas(session: Any, now: datetime) -> Section:
    counts = dict(session.exec(
        select(ProjectDelta.phase, func.count()).group_by(ProjectDelta.phase)
    ).all())
    named = {getattr(p, "value", str(p)): n for p, n in counts.items()}
    rows = tuple(
        (phase.value, str(named.get(phase.value, 0)),
         "closed" if phase in CLOSED_PHASES else "on deck")
        for phase in DeltaPhase
    )
    return Section(
        "Deltas by phase",
        ("phase", "count", ""),
        rows,
        note=("One unit of work moving brainstorm, planning, implementation, review, "
              "documentation, complete. A disagreement between two views is one of these."),
    )


def _on_deck(session: Any, now: datetime, limit: int) -> Section:
    stmt = (
        select(ProjectDelta, Project.name)
        .join(Project, Project.id == ProjectDelta.project_id)
        .where(ProjectDelta.phase.notin_(CLOSED_PHASES))
        .order_by(ProjectDelta.updated_at.desc())
        .limit(limit)
    )
    rows = []
    for delta, project in session.exec(stmt):
        rows.append((
            _trim(project, 18),
            _trim(delta.title, 40),
            getattr(delta.phase, "value", str(delta.phase)),
            delta.priority or "--",
            delta.delta_type or "--",
            _trim(delta.branch_name, 24),
            _ago(_age_days(delta.updated_at, now)),
        ))
    return Section(
        "On deck",
        ("repo", "delta", "phase", "priority", "type", "branch", "moved"),
        tuple(rows),
        note=("Open deltas, most recently moved first. An empty branch column is work "
              "with no branch yet, not work with no home."),
    )


def _activity(session: Any, now: datetime, limit: int) -> Section:
    prs = dict(session.exec(
        select(ProjectPullRequest.project_id, func.count())
        .where(ProjectPullRequest.state == "open")
        .group_by(ProjectPullRequest.project_id)
    ).all())
    issues = dict(session.exec(
        select(ProjectIssue.project_id, func.count())
        .where(ProjectIssue.state == "open")
        .group_by(ProjectIssue.project_id)
    ).all())
    branches = dict(session.exec(
        select(ProjectBranch.project_id, func.count()).group_by(ProjectBranch.project_id)
    ).all())
    releases = dict(session.exec(
        select(ProjectRelease.project_id, func.count()).group_by(ProjectRelease.project_id)
    ).all())

    scored = []
    for project in session.exec(select(Project).where(Project.last_synced_at.isnot(None))):
        open_pr, open_issue = prs.get(project.id, 0), issues.get(project.id, 0)
        score = open_pr * 3 + open_issue + branches.get(project.id, 0) * 0.5
        if score:
            scored.append((score, project, open_pr, open_issue))
    scored.sort(key=lambda item: -item[0])

    rows = tuple(
        (
            _trim(project.get_full_name(), 30),
            project.github_language or "--",
            str(project.github_stars or 0),
            str(open_pr),
            str(open_issue),
            str(branches.get(project.id, 0)),
            str(releases.get(project.id, 0)),
            _ago(_age_days(project.last_synced_at, now)),
        )
        for _, project, open_pr, open_issue in scored[:limit]
    )
    return Section(
        "Where the work is",
        ("repo", "language", "stars", "open PRs", "open issues", "branches", "releases", "synced"),
        rows,
        note=("Ordered by open PRs weighted over issues and branches. It ranks visible "
              "activity, which is not the same as importance."),
    )


def _languages(session: Any, limit: int) -> Section:
    seen = list(session.exec(
        select(ProjectLanguage.language, func.count(), func.sum(ProjectLanguage.bytes_count))
        .group_by(ProjectLanguage.language)
        .order_by(func.sum(ProjectLanguage.bytes_count).desc())
        .limit(limit)
    ))
    total = sum(int(b or 0) for _, _, b in seen) or 1
    rows = tuple(
        (_trim(name, 18), str(repo_count), f"{int(b or 0) / 1_000_000:.1f}MB",
         f"{100 * int(b or 0) / total:.0f}%",
         "#" * max(1, round(24 * int(b or 0) / total)))
        for name, repo_count, b in seen
    )
    return Section(
        "Language mix",
        ("language", "repos", "bytes", "share", ""),
        rows,
        note=("Share is of the bytes in this table, not of the org: languages past the "
              "cut are not in the denominator."),
    )


def _dependencies(session: Any, limit: int) -> Section:
    rows = tuple(
        (_trim(name, 28), str(repos), "#" * min(int(repos), 24))
        for name, repos in session.exec(
            select(ProjectDependency.name, func.count(func.distinct(ProjectDependency.project_id)))
            .group_by(ProjectDependency.name)
            .order_by(func.count(func.distinct(ProjectDependency.project_id)).desc())
            .limit(limit)
        )
    )
    return Section(
        "Shared dependencies",
        ("package", "repos", ""),
        rows,
        note=("How many synced repositories declare each package. A high count is a "
              "blast radius, not an endorsement."),
    )


def _people(session: Any, limit: int) -> Section:
    rows = tuple(
        (_trim(login, 24), str(repos), f"{int(commits or 0):,}")
        for login, repos, commits in session.exec(
            select(ProjectContributor.username,
                   func.count(func.distinct(ProjectContributor.project_id)),
                   func.sum(ProjectContributor.contributions))
            .group_by(ProjectContributor.username)
            .order_by(func.count(func.distinct(ProjectContributor.project_id)).desc())
            .limit(limit)
        )
    )
    return Section(
        "Contributors by reach",
        ("login", "repos", "commits"),
        rows,
        note=("Ordered by repositories touched. Commit counts are as GitHub reports "
              "them and include merges."),
    )


def _attention(session: Any, now: datetime, limit: int) -> Section:
    ranked = []
    for project in session.exec(select(Project)):
        age = _age_days(project.last_synced_at, now)
        reasons = []
        if age is None:
            reasons.append("never synced")
        elif age > STALE_AFTER_DAYS:
            reasons.append(f"synced {_ago(age)} ago")
        if not project.description:
            reasons.append("no description")
        if not project.github_language:
            reasons.append("no language")
        if reasons:
            ranked.append((
                age if age is not None else float("inf"),
                (_trim(project.get_full_name(), 30), _ago(age), ", ".join(reasons)),
            ))
    ranked.sort(key=lambda item: item[0], reverse=True)
    return Section(
        "Wants attention",
        ("repo", "synced", "why"),
        tuple(row for _, row in ranked[:limit]),
        note=(
            f"Sorted by sync age; {STALE_AFTER_DAYS} days is the threshold used to list "
            "one, and it is this view's own convention rather than a governance budget. "
            "A listed repository is one nothing is known about, which is not the same as "
            "one in trouble."
        ),
    )


def build(session: Any, limit: int = 12, now: datetime | None = None) -> OrgOverview:
    """Everything the overview shows, from one session.

    `now` is injectable so a test can assert an age rather than assert around
    one: a clock read inside this function would make every age untestable.
    """
    now = now or datetime.now(timezone.utc)
    horizon = _one(session, select(func.max(Project.last_synced_at)), default=None)
    return OrgOverview(
        masthead=_masthead(session, now),
        sections=(
            _governance(session, now),
            _on_deck(session, now, limit),
            _deltas(session, now),
            _activity(session, now, limit),
            _languages(session, limit),
            _dependencies(session, limit),
            _people(session, limit),
            _attention(session, now, limit),
        ),
        generated_from=(
            f"most recent sync {_ago(_age_days(horizon, now))} ago"
            if horizon else "nothing synced yet"
        ),
        scope=f"{_count(session, Project)} repositories in this dossier",
    )
