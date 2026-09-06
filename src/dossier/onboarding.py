"""Whether this installation is set up, and what to press when it is not.

**THE FIRST RUN HAD NO WAY TO ASK "IS THIS WORKING?"** A person who had cloned
this, run `uv sync` and opened the dashboard saw empty panes, and every one of
the reasons looked identical from the outside: no database, an unmigrated one, a
database with no rows, no GitHub token, no harness, no clones. Six causes, one
symptom, and nothing that told them apart.

`diagnostics.py` is the neighbouring idea and a different one. It looks
**inward** -- at this repository, its source and its sibling clone -- for
defects a green test run does not see, and every check there is a bug that
actually happened. This looks **outward**, at one person's installation, and
every check here is a step somebody has to complete before the panel can show
them anything. A developer runs the first; anybody runs the second.

**EVERY STEP THAT IS NOT DONE NAMES THE ROUTE THAT DOES IT, AND THE ROUTE COMES
FROM THE MENU.** `rad.index.keystroke` computes it from the palette, so a
checklist item cannot tell somebody to press keys that stopped reaching the act
-- which is the failure `test_no_typed_routes.py` exists to prevent, and a
checklist is the worst possible place to reintroduce it. A step with no ring
route says its command instead; a step with neither says so.

**REQUIRED AND OPTIONAL ARE DIFFERENT, AND BOTH ARE REPORTED.** The harness and
the governance corpus are ordinary things not to have -- most installations
never want them -- so a missing one is `skipped`, not `failed`. A checklist that
showed six red rows to somebody correctly set up would be a checklist nobody
reads twice.

WHAT THIS CANNOT DO.

  * Tell you the token is valid. Reading `GITHUB_TOKEN` says a token is present;
    only a request says it works, and a checklist that spent an API call on
    every open would be one that hits a rate limit for a diagnostic.
  * Fix anything. Every step reports and names the route; pressing it is a
    person's act, and three of the six write to somebody's disk or network.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Callable

DONE = "done"
TODO = "todo"
SKIPPED = "skipped"
UNKNOWN = "unknown"
"""The step could not be established. **Not a pass and not a failure** -- the
distinction `diagnostics.py` makes for the same reason, and the one
`threads.Archive` makes between a count of zero and a count nobody took."""


@dataclass(frozen=True)
class Step:
    """One thing a working installation has, and how to get it."""

    name: str
    state: str
    detail: str
    """What was actually found. A number where there is one."""

    action: str = ""
    """The ring action that completes this step, or empty.

    An action id rather than a keystroke: the keys are computed from it, so
    this cannot go stale when the palette moves.
    """

    command: str = ""
    """A command that completes it, for a step the ring cannot reach."""

    required: bool = True

    @property
    def ok(self) -> bool:
        return self.state in (DONE, SKIPPED)

    def keys(self) -> str:
        """The keystrokes that complete this step, read from the ring."""
        if not self.action:
            return ""
        from dossier.rad.index import keystroke

        return keystroke(self.action)

    def remedy(self) -> str:
        """What to do about it, in the words a person can act on.

        Empty for a step already done: a checklist that told somebody how to
        do what they have done is one they stop reading.
        """
        if self.state in (DONE, SKIPPED):
            return ""
        keys = self.keys()
        if keys and self.command:
            return f"press {keys}, or run `{self.command}`"
        if keys:
            return f"press {keys}"
        if self.command:
            return f"run `{self.command}`"
        return "no route reaches this, which is itself the finding"


@dataclass
class Checklist:
    """Every step, and whether this installation is ready."""

    steps: list[Step] = field(default_factory=list)

    @property
    def outstanding(self) -> list[Step]:
        return [s for s in self.steps if s.state == TODO and s.required]

    @property
    def unknown(self) -> list[Step]:
        return [s for s in self.steps if s.state == UNKNOWN]

    @property
    def is_ready(self) -> bool:
        """Every required step done, and nothing unestablished.

        An `unknown` is not a pass, for the reason `diagnostics.Report`
        gives: a checklist that went quiet because something moved would
        otherwise report a working installation while checking nothing.
        """
        return bool(self.steps) and not self.outstanding and not self.unknown

    def summary(self) -> str:
        """One sentence, and it always names a number."""
        if not self.steps:
            return "no steps ran at all, which is itself the finding"
        done = sum(1 for s in self.steps if s.state == DONE)
        said = f"{done} of {len(self.steps)} step(s) done"
        if self.outstanding:
            said += f", {len(self.outstanding)} still to do"
        if self.unknown:
            said += f", {len(self.unknown)} could not be established"
        if self.is_ready:
            said += " -- this dossier is ready"
        return said

    def next_step(self) -> Step | None:
        """The one to do now. Order is the order they have to happen in."""
        return self.outstanding[0] if self.outstanding else None


# --- the steps ----------------------------------------------------------------


def a_database(session: Any = None, **_: Any) -> Step:
    """There is a database, and the migrations have been run against it.

    **IT ASKS THE SESSION FIRST, NOT THE WORKING DIRECTORY.** `health.check`
    inspects the candidate files on disk, which is the right reading for the
    command line and the wrong one for a panel: `DOSSIER_DATABASE_URL` moves
    which database is open, and a checklist that reported on a file the panel
    is not using would be the two-databases failure `health.py` exists for,
    wearing a tick.
    """
    from dossier import health

    if _is_in_memory(session):
        # **REPORTED, NOT FALLEN BACK FROM.** A panel open on an in-memory
        # database is not reading the file on disk, and naming that file here
        # would be the two-databases failure this docstring warns about with a
        # tick beside it.
        return Step("A database, migrated", DONE,
                    "in memory, so there is no file and nothing to migrate")

    bound = _bound_to(session)
    if bound is not None:
        missing = health.missing_columns(bound) if bound.exists() else {}
        if missing:
            return Step("A database, migrated", TODO,
                        f"{bound.name} is missing "
                        f"{sum(len(c) for c in missing.values())} column(s) "
                        f"across {len(missing)} table(s)",
                        command="dossier db upgrade")
        return Step("A database, migrated", DONE, str(bound))

    found = health.check()
    blocking = [f for f in found if getattr(f, "blocking", False)]
    if blocking:
        return Step("A database, migrated", TODO,
                    "; ".join(f.detail for f in blocking[:2]),
                    command="dossier db upgrade")
    where = health.candidate_databases()
    return Step("A database, migrated", DONE,
                str(where[0]) if where else "in memory, with no file to check")


def _url_of(session: Any) -> str:
    """The session's database URL, or empty when there is no session."""
    if session is None:
        return ""
    try:
        return str(session.get_bind().url)
    except Exception:                              # noqa: BLE001
        return ""


def _is_in_memory(session: Any) -> bool:
    url = _url_of(session)
    return bool(url) and (":memory:" in url or url.endswith("sqlite://"))


def _bound_to(session: Any):
    """The file the session is open on, or None for in-memory and no session."""
    from pathlib import Path

    url = _url_of(session)
    if not url:
        return None
    if "sqlite" not in url or ":memory:" in url or url.endswith("sqlite://"):
        return None
    return Path(url.split("sqlite:///")[-1])


def something_in_it(session: Any = None, **_: Any) -> Step:
    """A dossier with no projects in it is the first-run state itself."""
    from sqlmodel import select

    from dossier.models.schemas import Project

    if session is None:
        return Step("Repositories indexed", UNKNOWN,
                    "no database session to count with",
                    action="reach.download")
    held = len(session.exec(select(Project)).all())
    if held:
        return Step("Repositories indexed", DONE, f"{held} project(s)")
    return Step("Repositories indexed", TODO,
                "nothing is indexed yet, so every pane is empty",
                action="reach.download")


def a_github_token(**_: Any) -> Step:
    """Without one, GitHub allows sixty requests an hour for the whole machine.

    Sixty is fewer than one repository costs, so an unauthenticated download
    fails partway through and looks like a network problem.
    """
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if token:
        # The value is never rendered. A checklist that printed somebody's
        # token would put it in a screenshot the first time they asked for
        # help.
        return Step("A GitHub token", DONE,
                    f"GITHUB_TOKEN is set ({len(token)} characters)")
    return Step("A GitHub token", TODO,
                "GITHUB_TOKEN is unset, so GitHub allows 60 requests an hour "
                "for this whole machine -- fewer than one repository costs",
                command="export GITHUB_TOKEN=... "
                        "(github.com/settings/tokens)")


def clones_on_this_disk(session: Any = None, **_: Any) -> Step:
    """Facets that read a clone answer `unknown` without one.

    Optional: a repository with no clone here is an ordinary state and usually
    the right one -- `clone.py` says so -- and this reports the gap rather
    than calling it a fault.
    """
    from sqlmodel import select

    from dossier.clone import absent
    from dossier.models.schemas import Project

    if session is None:
        return Step("Clones on this disk", UNKNOWN,
                    "no database session to check against",
                    action="reach.clone", required=False)
    projects = session.exec(select(Project)).all()
    if not projects:
        return Step("Clones on this disk", SKIPPED,
                    "nothing is indexed yet, so nothing can be absent",
                    required=False)
    gone = absent(projects)
    if not gone:
        return Step("Clones on this disk", DONE,
                    f"every one of {len(projects)} has a clone here",
                    required=False)
    return Step("Clones on this disk", TODO,
                f"{len(gone)} of {len(projects)} indexed repositories have no "
                f"clone here, so branch hygiene reads `unknown` for them",
                action="reach.clone", required=False)


def the_harness(**_: Any) -> Step:
    """Optional. Most installations never want one.

    A conversation archive is the harness's and is reached over HTTP; without
    it the Conversations pane says nobody answered rather than showing zero
    rows, which is `threads.py`'s own rule.
    """
    from dossier import threads

    try:
        archive = threads.fetch()
    except Exception as exc:                       # noqa: BLE001
        return Step("The harness, for conversations", UNKNOWN,
                    f"could not be asked: {type(exc).__name__}: {exc}",
                    required=False)
    if archive.reachable:
        return Step("The harness, for conversations", DONE,
                    f"answering on {threads.base_url()}", required=False)
    return Step("The harness, for conversations", SKIPPED,
                f"nothing is answering on {threads.base_url()}; the "
                f"Conversations pane will say so rather than show zero rows",
                action="reach.ingest", required=False)


def the_governance_corpus(**_: Any) -> Step:
    """Optional. It is a submodule and most installations do not check it out."""
    from pathlib import Path

    from dossier.capabilities import DEFAULT_CORPUS_DIR

    where = Path(DEFAULT_CORPUS_DIR)
    if (where / "ci").is_dir():
        return Step("The governance corpus", DONE, f"{where} is checked out",
                    required=False)
    return Step("The governance corpus", SKIPPED,
                f"{where} is not checked out, so the Governance pane has "
                f"nothing to compare against",
                command="git submodule update --init governance/qm",
                required=False)


# The order they have to happen in. A token before a download, a download
# before a clone -- so `next_step` is genuinely the next thing to do rather
# than the first row that happens to be red.
STEPS: tuple[Callable[..., Step], ...] = (
    a_database,
    a_github_token,
    something_in_it,
    clones_on_this_disk,
    the_harness,
    the_governance_corpus,
)


def run(session: Any = None,
        steps: tuple[Callable[..., Step], ...] = STEPS) -> Checklist:
    """Every step, each surviving its neighbours' failures.

    A step that raised would otherwise take the checklist with it, and the
    remaining five are exactly what somebody needs when one is broken --
    `diagnostics.run` makes the same argument.
    """
    found = Checklist()
    for step in steps:
        try:
            found.steps.append(step(session=session))
        except Exception as exc:                   # noqa: BLE001
            # **THE FIRST LINE ONLY.** A SQLAlchemy error carries the whole
            # statement, and pasting it into a table cell makes the one row
            # that reports a problem the one nobody can read.
            said = str(exc).strip().splitlines()[0][:160]
            found.steps.append(Step(
                getattr(step, "__name__", "?"), UNKNOWN,
                f"the step itself raised: {type(exc).__name__}: {said}"))
    return found


# --- rendering ----------------------------------------------------------------

COLUMNS = ("step", "state", "what was found", "what to do")


def rows(found: Checklist) -> tuple[tuple[str, ...], ...]:
    """The checklist as a table, remedies included."""
    return tuple(
        (step.name, step.state, step.detail, step.remedy())
        for step in found.steps
    )


def render(found: Checklist) -> str:
    """The checklist for a terminal. ASCII only, as everything here is."""
    lines = [found.summary(), ""]
    mark = {DONE: "ok  ", TODO: "TODO", SKIPPED: "--  ", UNKNOWN: "??  "}
    for step in found.steps:
        lines.append(f"{mark.get(step.state, '?   ')} {step.name}")
        lines.append(f"       {step.detail}")
        remedy = step.remedy()
        if remedy:
            lines.append(f"       -> {remedy}")
    nxt = found.next_step()
    if nxt is not None:
        lines += ["", f"Next: {nxt.name} -- {nxt.remedy()}"]
    return "\n".join(lines)
