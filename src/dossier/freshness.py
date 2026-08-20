"""How stale the view in front of you is, and what would fix it.

**THE QUESTION THIS ANSWERS IS "IS WHAT I AM LOOKING AT STILL TRUE".** Every
figure in this application is *as last synced*, and the tabs say so in words
without saying how long ago. A reader who wants to act on a number has to know
its age, and until now the only route to that was reading the sync column of a
different view.

**A PLAN IS BUILT BEFORE ANYTHING IS FETCHED, AND IT NAMES WHAT IT WOULD TOUCH.**
Refreshing the org overview means reaching every repository in scope, and on
this org that is around a hundred requests. A menu item that quietly does that
because somebody pressed two keys is the shape of thing
`governance/qm/records/DRAFT-no-unattended-spending.md` is about. So `plan_for`
is pure and cheap: it reads ages out of the database and returns what a refresh
*would* do, and something else decides whether to do it.

**NEVER-SYNCED IS NOT INFINITELY STALE, AND IT IS NOT FRESH.** It is its own
state. A repository nobody has ever synced has `age_hours=None` -- unknown,
never zero, the same convention the harness payload uses -- and lands in
`never` rather than in `stale`. The two want different words: one is out of
date, the other has never had a date. Collapsing them would let a first-time
setup read as a hundred stale repositories, and let a stale repository hide
among things nobody expected to be current.

WHAT THIS MODULE CANNOT DO. Fetch. It names subjects and ages; the fetching is
`dossier.cli`'s `github sync` and the app's sync worker, and keeping those apart
is what lets this be tested without a network and read without a token.

WHAT FEEDS A VIEW. All of dossier's repository-shaped tabs -- languages,
contributors, issues, pull requests, branches, releases -- are filled by the
same `github sync` against the same repository, so their freshness is that
repository's `last_synced_at`. Modelling a per-tab age would be inventing a
distinction the sync does not make. Tabs fed by something other than a GitHub
sync are named in `NOT_FROM_SYNC`, and asking for a plan on one of those says
so rather than returning an empty plan that reads like "nothing to do".
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable

from sqlmodel import select

from dossier.models.schemas import Project

# Reused, not redeclared: `dossier.overview` already sorts the attention list on
# this figure and states it in that section's note. A second threshold here
# would be a second definition of the same word on the same screen.
from dossier.overview import STALE_AFTER_DAYS

STALE_AFTER_HOURS = STALE_AFTER_DAYS * 24

# Tabs whose contents do not come from a GitHub sync, and what does fill them.
# A refresh plan for one of these is not empty -- it is inapplicable, and those
# read the same way on screen unless one of them says so.
NOT_FROM_SYNC: dict[str, str] = {
    "tab-deltas": "deltas arrive by ingest, not by sync -- see Reach > Ingest deltas",
    "tab-harness": "the harness reports about itself; dossier does not fetch it",
    "tab-threads": "the thread archive is the harness's, reached over HTTP",
    "tab-waiting": "questions are raised by a harness run, not fetched",
    "tab-docs": "documents are read from disk",
    "tab-disk": "read from disk at the moment you look",
}


@dataclass(frozen=True)
class Subject:
    """One repository a refresh would touch, and how old its data is."""

    name: str
    age_hours: float | None
    """Hours since the last sync. `None` means never synced -- unknown, and
    deliberately not zero."""

    @property
    def state(self) -> str:
        if self.age_hours is None:
            return "never"
        return "stale" if self.age_hours > STALE_AFTER_HOURS else "fresh"

    @property
    def ago(self) -> str:
        """An age in words. `never` is a fact, not a missing value."""
        if self.age_hours is None:
            return "never"
        if self.age_hours < 1:
            return "just now"
        if self.age_hours < 48:
            return f"{int(self.age_hours)}h ago"
        return f"{int(self.age_hours / 24)}d ago"


@dataclass(frozen=True)
class Plan:
    """What a refresh of the current view would do, before it does it."""

    scope: str
    """What the view is showing, in the words the view uses."""

    subjects: tuple[Subject, ...]
    """Everything in scope, whatever its state. A refresh touches all of them
    unless `stale_only` narrows it."""

    inapplicable: str | None = None
    """Set when this view is not fed by a sync at all, and says what does feed
    it. A plan with this set has no subjects and is not a plan with nothing
    to do."""

    @property
    def never(self) -> tuple[Subject, ...]:
        return tuple(s for s in self.subjects if s.state == "never")

    @property
    def stale(self) -> tuple[Subject, ...]:
        return tuple(s for s in self.subjects if s.state == "stale")

    @property
    def fresh(self) -> tuple[Subject, ...]:
        return tuple(s for s in self.subjects if s.state == "fresh")

    @property
    def wanted(self) -> tuple[Subject, ...]:
        """What a narrow refresh would touch: stale and never-synced.

        Ordered stalest first, with never-synced ahead of everything -- a
        repository with no data at all is the one making the view wrong in the
        way a reader notices.
        """
        return (*self.never,
                *sorted(self.stale, key=lambda s: -(s.age_hours or 0.0)))

    @property
    def oldest(self) -> Subject | None:
        """The subject that makes the view as stale as it is, or None.

        Never-synced wins: it is the strongest claim about the view being
        wrong, and it has no number to compare.
        """
        if self.never:
            return self.never[0]
        if not self.stale and not self.fresh:
            return None
        dated = [s for s in self.subjects if s.age_hours is not None]
        return max(dated, key=lambda s: s.age_hours) if dated else None

    @property
    def is_current(self) -> bool:
        """True only when every subject is fresh. An empty scope is not
        current -- there is nothing to be current about, and saying "up to
        date" about nothing is the more misleading of the two answers."""
        return bool(self.subjects) and not self.never and not self.stale

    def summary(self) -> str:
        """One line, for a notification or a status bar."""
        if self.inapplicable:
            return f"{self.scope}: {self.inapplicable}"
        if not self.subjects:
            return f"{self.scope}: nothing in scope to refresh"
        if self.is_current:
            oldest = self.oldest
            return (f"{self.scope}: {len(self.subjects)} up to date"
                    + (f", oldest {oldest.ago}" if oldest else ""))
        parts = []
        if self.never:
            parts.append(f"{len(self.never)} never synced")
        if self.stale:
            parts.append(f"{len(self.stale)} stale")
        return (f"{self.scope}: {', '.join(parts)} "
                f"of {len(self.subjects)} in scope")


def plan_for(session: Any, *, tab: str | None = None,
             owner: str | None = None,
             project: Any = None,
             now: datetime | None = None) -> Plan:
    """What refreshing the current view would touch.

    Scope is the narrowest of what it is given: a selected project first, then
    an owner, then everything. That order matches what the screen is showing --
    selecting a repository scopes every tab to it, so a refresh asked for from
    that screen means that repository.
    """
    now = now or datetime.now(timezone.utc)

    if tab is not None and tab in NOT_FROM_SYNC:
        return Plan(scope=_scope_words(owner, project),
                    subjects=(), inapplicable=NOT_FROM_SYNC[tab])

    if project is not None:
        rows: Iterable[Any] = [project]
    else:
        statement = select(Project)
        if owner is not None:
            statement = statement.where(Project.github_owner == owner)
        rows = session.exec(statement).all()

    subjects = tuple(
        Subject(name=getattr(row, "full_name", None) or row.name,
                age_hours=_age_hours(getattr(row, "last_synced_at", None), now))
        for row in rows
    )
    return Plan(scope=_scope_words(owner, project), subjects=subjects)


def _scope_words(owner: str | None, project: Any) -> str:
    if project is not None:
        return getattr(project, "full_name", None) or project.name
    if owner is not None:
        return owner
    return "every repository"


def _age_hours(then: datetime | None, now: datetime) -> float | None:
    """Hours since `then`, or None when there is no `then`.

    A naive timestamp is read as UTC rather than as local: the database stores
    UTC, and reading it as local would shift every age by the offset and make a
    just-synced repository look hours old in one direction or freshly synced in
    the other.
    """
    if then is None:
        return None
    if then.tzinfo is None:
        then = then.replace(tzinfo=timezone.utc)
    return (now - then).total_seconds() / 3600.0
