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


def owner_of(project: Any) -> str | None:
    """Who owns a project row, from the column or from `owner/repo`.

    One definition, used by both the overview's scoping and the purge. Two
    definitions of ownership would let a row be counted in the org's figures
    and deleted as somebody else's in the same afternoon.
    """
    if project.github_owner:
        return project.github_owner
    if project.full_name and "/" in project.full_name:
        return project.full_name.split("/", 1)[0]
    return None


def dominant_owner(session: Any) -> str | None:
    """The owner holding the most non-fork repositories here, or None.

    What "local" means for a dashboard opening cold: whichever organisation
    this database is actually about. Opening unscoped shows a total mixed
    across every owner that was ever synced, which is a number about the
    database rather than about anybody's work.
    """
    from collections import Counter

    tally = Counter(
        owner_of(project)
        for project in session.exec(select(Project)).all()
        if not project.is_fork and owner_of(project)
    )
    if not tally:
        return None
    return tally.most_common(1)[0][0]


def scope_ids(session: Any, owner: str | None,
              include_forks: bool = False) -> list[int] | None:
    """Project ids belonging to `owner`, or None for everything in the dossier.

    WHY THIS EXISTS. A dossier holds more than one organisation: a dependency
    synced for its own sake is a `Project` row like any other. Unscoped, this
    view reported 104,576 stars for an organisation that has 54, because a
    third party's repositories were in the denominator. An org overview that
    sums whatever happens to be in the database is not an org overview.
    """
    if owner is None and include_forks:
        return None
    return [
        p.id for p in session.exec(select(Project)).all()
        if (owner is None or owner_of(p) == owner)
        and (include_forks or not p.is_fork)
    ]


def _in_scope(stmt: Any, column: Any, ids: list[int] | None) -> Any:
    """Restrict a statement to the scope, if there is one."""
    return stmt if ids is None else stmt.where(column.in_(ids))


def _one(session: Any, statement: Any, default: Any = 0) -> Any:
    result = session.exec(statement).one_or_none()
    if result is None:
        return default
    return result if not isinstance(result, tuple) else result[0]


def _count(session: Any, model: Any, *where: Any, ids: list[int] | None = None,
           column: Any = None) -> int:
    stmt = select(func.count()).select_from(model)
    for clause in where:
        stmt = stmt.where(clause)
    if column is not None:
        stmt = _in_scope(stmt, column, ids)
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


def _masthead(session: Any, now: datetime, ids: list[int] | None) -> tuple[Cell, ...]:
    repos = _count(session, Project, ids=ids, column=Project.id)
    synced = _count(session, Project, Project.last_synced_at.isnot(None),
                    ids=ids, column=Project.id)
    stars = int(_one(session, _in_scope(
        select(func.sum(Project.github_stars)), Project.id, ids)) or 0)
    langs = int(_one(session, _in_scope(
        select(func.count(func.distinct(ProjectLanguage.language))),
        ProjectLanguage.project_id, ids)) or 0)
    people = int(_one(session, _in_scope(
        select(func.count(func.distinct(ProjectContributor.username))),
        ProjectContributor.project_id, ids)) or 0)
    open_prs = _count(session, ProjectPullRequest, ProjectPullRequest.state == "open",
                      ids=ids, column=ProjectPullRequest.project_id)
    open_issues = _count(session, ProjectIssue, ProjectIssue.state == "open",
                         ids=ids, column=ProjectIssue.project_id)
    on_deck = _count(session, ProjectDelta, ProjectDelta.phase.notin_(CLOSED_PHASES),
                     ids=ids, column=ProjectDelta.project_id)

    return (
        Cell("repositories", str(repos), f"{synced} synced, {_pct(synced, repos)}"),
        Cell("never synced", str(repos - synced), "absent from the counts below"),
        Cell("stars", f"{stars:,}", "as last synced"),
        Cell("languages", str(langs), "distinct, across synced repos"),
        Cell("contributors", str(people), "distinct logins"),
        Cell("open PRs", str(open_prs),
             f"{_count(session, ProjectPullRequest, ids=ids, column=ProjectPullRequest.project_id)} tracked"),
        Cell("open issues", str(open_issues),
             f"{_count(session, ProjectIssue, ids=ids, column=ProjectIssue.project_id)} tracked"),
        Cell("branches", str(_count(session, ProjectBranch, ids=ids,
                                    column=ProjectBranch.project_id)), "in scope"),
        Cell("releases", str(_count(session, ProjectRelease, ids=ids,
                                    column=ProjectRelease.project_id)), "tags seen"),
        Cell("deltas on deck", str(on_deck),
             f"{_count(session, ProjectDelta, ids=ids, column=ProjectDelta.project_id)} total"),
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


def _deltas(session: Any, now: datetime, ids: list[int] | None) -> Section:
    counts = dict(session.exec(_in_scope(
        select(ProjectDelta.phase, func.count()).group_by(ProjectDelta.phase),
        ProjectDelta.project_id, ids)).all())
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







def _harness_totals(session: Any, now: datetime) -> Section:
    """What each harness reports about itself, and how old the reading is.

    Stored rather than derived. The payload carries an excerpt of the rows and
    the totals over the harness's whole history; recomputing them from the
    excerpt would report the size of the excerpt and call it the history.
    """
    from dossier.models.harness import HarnessSnapshot

    latest: dict[str, Any] = {}
    for snapshot in session.exec(
        select(HarnessSnapshot).order_by(HarnessSnapshot.loaded_at)
    ).all():
        latest[snapshot.project] = snapshot

    rows = tuple(
        (
            _trim(project, 26),
            str(snapshot.invocations),
            str(snapshot.failures),
            f"{snapshot.human_responses}/{snapshot.human_requests}",
            _ago(_age_days(snapshot.loaded_at, now)),
        )
        for project, snapshot in sorted(latest.items())
    )
    return Section(
        "Harness", ("harness", "invocations", "failures", "human answered", "read"),
        rows,
        note=("Reported by the harness about itself, not counted here. `read` is "
              "how long ago this control panel was shown those figures: a "
              "harness that has run since is not reflected until the next "
              "`dossier harness ingest`."),
    )


def _attention(session: Any, now: datetime, limit: int, ids: list[int] | None) -> Section:
    from dossier.naming import is_a_repository

    ranked = []
    for project in session.exec(_in_scope(select(Project), Project.id, ids)):
        if not is_a_repository(project):
            # **A DELTA ADDRESS CANNOT BE SYNCED, SO LISTING IT IS NOISE THAT
            # NEVER CLEARS.** Four rows in this table are addresses inside a
            # repository rather than repositories, and every one of them read
            # as never synced, with no description and no language -- three
            # reasons apiece, permanently, for something that has no sync to
            # be missing.
            continue
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


def _horizon_phrase(days: float | None) -> str:
    """How old the whole picture is, read as English.

    `_ago` returns "today" for anything under a day, and appending "ago" to it
    produced "most recent sync today ago" -- a figure a reader would mistrust
    for a reason that has nothing to do with the number.
    """
    age = _ago(days)
    return f"most recent sync {age}" if age == "today" else f"most recent sync {age} ago"


def _facet_section(facet: Any, session: Any, ids: Any, limit: int,
                   allowed: bool) -> Section:
    """One facet's section, or a placeholder saying where to get it.

    **THE OVERVIEW IS ON THE STARTUP PATH AND MUST NOT SPAWN OR DIAL.** A facet
    that reads only the database answers in about a millisecond; the two that
    cross a process boundary were six seconds of an eight-second build. Those
    costs are the ones that grow worst on small hardware, and this panel is
    meant to run on some.

    Skipped is not empty, and the section says which it is. A heading with no
    rows and no sentence reads as a facet that failed.
    """
    if facet.beyond_the_database and not allowed:
        return Section(
            facet.title, ("",), (),
            note=(f"Not read here: it {facet.beyond_the_database}, and the "
                  f"overview is what opens first. Open the "
                  f"{facet.tab.removeprefix('tab-')} tab, which reads it on "
                  f"demand because by then a person has asked and can wait. "
                  f"This is a skipped reading, not an empty one."))
    return facet.at(session, ids=ids, limit=limit)


def build(session: Any, limit: int = 12, now: datetime | None = None,
          owner: str | None = None, include_forks: bool = False,
          beyond_the_database: bool = False) -> OrgOverview:
    """Everything the overview shows, from one session.

    `now` is injectable so a test can assert an age rather than assert around
    one: a clock read inside this function would make every age untestable.
    """
    # Imported here rather than at module scope: `facets` reads `Section` and
    # the helpers from this module, and a top-level import both ways is a
    # cycle. The registry is the single definition of each kind of fact; this
    # module owns only the sections that exist at org scope alone.
    from dossier.facets import FACETS

    now = now or datetime.now(timezone.utc)
    ids = scope_ids(session, owner, include_forks=include_forks)
    horizon = _one(session, _in_scope(
        select(func.max(Project.last_synced_at)), Project.id, ids), default=None)
    return OrgOverview(
        masthead=_masthead(session, now, ids),
        sections=(
            _governance(session, now),
            *(_facet_section(facet, session, ids, limit, beyond_the_database)
              for facet in FACETS),
            _deltas(session, now, ids),
            _harness_totals(session, now),
            _attention(session, now, limit, ids),
        ),
        generated_from=_horizon_phrase(_age_days(horizon, now)) if horizon
        else "nothing synced yet",
        scope=(
            f"{_count(session, Project, ids=ids, column=Project.id)} repositories "
            + (f"owned by {owner}" if owner else "in this dossier")
            + ("" if include_forks else ", forks excluded")
        ),
    )
