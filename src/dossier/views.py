"""Every view this application has, once.

**THE SET OF VIEWS WAS WRITTEN DOWN IN THREE PLACES** -- the `TabPane` calls in
`tui/app.py`, `config.AVAILABLE_TABS`, and `PROJECT_TABS` in the tests -- and all
three had to be edited by hand whenever one moved. They had already drifted:
`AVAILABLE_TABS` listed thirteen of twenty-one, missing Sweep, Threads, Hygiene,
Harness, Waiting, Disk, Topology and Overview. A settings screen offering a
reader thirteen of the views is not a smaller menu; it is a wrong one.

So this is the registry, and the ring, the settings list, the command sheet and
the index all read it. Adding a view here gives it a keystroke, a place in the
settings, a line in the index and a `dossier show` route, in one edit.

**THE GROUP IS A LEVEL OF THE RING, WHICH IS WHY THERE ARE FOUR.** rad places at
most eight cells per level and `Go` cannot hold eighteen children. A group is
therefore a real thing a person presses through -- `m` `8` `6` `8` is Go, Work,
On deck -- rather than a heading invented for a document. Reordering a group
here moves every number after it, in the menu and on the page alike, which is
the honest behaviour of an index computed from the menu instead of typed beside
it.

**AND EACH VIEW DECLARES WHAT IT NEEDS BEFORE IT CAN SHOW ANYTHING.** This file
used to close by admitting that "an empty view and a broken one look identical
from here", and that admission cost something real: several of this application's views
render nothing until a precondition is met, and not one of them said so. A
reader who opened Details before choosing a repository saw a blank panel, and so
did one who opened Topology with no harness running. Two different facts, one
blank panel.

`needs` is that precondition, and **every need names what satisfies it** -- a
view to visit, or a command to run. That is what turns a list of
independent tabs into something a person can move through: a view that cannot answer yet says
which view answers first. The edges are declared here rather than inferred from
whatever happens to be empty at the time.

WHAT THIS STILL CANNOT DO. Say whether a view whose needs are met has anything
*interesting* in it. `Outstanding` reads zero rows when nobody has asked a
question, and that is the state it exists to show. A met precondition and a
quiet estate look alike, and they should.
"""

from __future__ import annotations

from dataclasses import dataclass

# The order the ring places them in, and therefore the order of the index.
#
# **THE GROUPS ARE JOBS, NOT DATA DOMAINS.** They used to be Repositories, Work,
# Code and Machine -- where a fact lived, so a reader had to know a branch was
# "Code" and an issue was "Work" before they could reach either. These are the
# five things a person opens dossier to *do*: react to what is urgent (Triage),
# decide what to change next (Plan), understand what exists (Explore), check the
# estate and this box are sound (Health), and read the boundary where dossier
# meets other systems (Seams). A view moves to the group whose job it serves,
# not the shelf its data sits on.
GROUPS = ("Triage", "Plan", "Explore", "Health", "Seams")


@dataclass(frozen=True)
class Need:
    """One precondition, and the thing that satisfies it.

    **A NEED THAT DOES NOT NAME ITS REMEDY IS A DEAD END.** Telling a reader
    that a view needs a repository selected, without saying where one is
    selected, leaves them exactly where the blank panel did.
    """

    key: str
    """What is missing. One of `NEEDS`."""

    because: str
    """What the view cannot compute without it, in a person's words."""

    satisfied_by: str
    """The view name that provides it, or a command to run.

    **THE THING THAT FIXES IT, NOT THE THING THAT REPORTS IT.** Two views
    needing a running harness pointed at `dossier harness queue`, which reads
    the harness -- so a reader whose harness was down ran it, got the same
    problem back, and was then told the real answer. One hop, and the hop has
    to be the fix.

    A name matching the registry is a route; anything else is a command, and
    `test_readiness.py` refuses one that does not resolve."""


# The preconditions this application has. Named rather than written as free
# text so that two views needing the same thing say so identically, and so a
# resolver can answer them.
PROJECT = "project"
HARNESS = "harness"
CLONE = "clone"
CORPUS = "corpus"
ATTENTION = "attention"

NEEDS = (PROJECT, HARNESS, CLONE, CORPUS, ATTENTION)


@dataclass(frozen=True)
class View:
    """One tab, and every way to reach what it shows."""

    tab: str
    """The `TabPane` id, e.g. `tab-overview`. The identity."""

    title: str
    """What the tab is called on screen."""

    group: str
    """Which of `GROUPS` it sits under in the ring."""

    summary: str
    """One line: what a person came to this view to find out."""

    cli: str = ""
    """A command that reaches the same reading, or empty.

    **A NAMED ROUTE ONLY.** Every facet-backed view is also reachable through
    `dossier show <name>`, which is derived and needs no entry here. This field
    is for the views that have a command of their own, because a person who
    knows the command should not be told to use the generic one.
    """

    needs: tuple["Need", ...] = ()
    """What must be true before this view can show anything.

    Empty means the view answers from this database alone. **Declared rather
    than discovered**: a precondition found by noticing that a panel is blank
    is a precondition nobody can be warned about in advance, which is the
    state this registry was in when several of this application's views rendered nothing
    and none of them said why.
    """

    @property
    def name(self) -> str:
        """The short name, e.g. `overview`. What `dossier show` takes."""
        return self.tab.removeprefix("tab-")

    @property
    def action(self) -> str:
        """The ring action that opens it, e.g. `view.overview`."""
        return f"view.{self.name}"


def _of_one_repository(what: str) -> tuple[Need, ...]:
    """The commonest need there is, said the same way each time.

    Eight views answer about *a* repository and cannot answer until one is
    chosen. Writing that need out eight times invites eight slightly different
    sentences, and a reader who meets two of them learns that the application
    is inconsistent rather than that it needs a selection.
    """
    return (Need(PROJECT, f"{what} belong to one repository, and none is "
                          f"selected yet", "overview"),)


VIEWS: tuple[View, ...] = (
    # Triage -- what is urgent now, reacted to rather than gone looking for.
    View("tab-overview", "Overview", "Triage",
         "Every repository in one reading, with what needs attention first.",
         "dossier overview"),
    View("tab-waiting", "Outstanding", "Triage",
         "Everything three readings noticed -- harness questions, repositories "
         "nothing has read lately, invocations that failed -- and what would "
         "settle each. Zero is a real answer, not an empty table.",
         needs=(Need(ATTENTION,
                     "the rows are gathered from the overview's reading, and "
                     "that reading has to have been taken",
                     "overview"),)),
    View("tab-issues", "Issues", "Triage",
         "Open issues, most recently updated first.",
         needs=_of_one_repository("issues")),

    # Plan -- the proactive job: what to change next, what it would touch, and
    # the goal that sets a change in motion. This group is the work a person
    # decides on, drawn from dossier's own record; what the harness reports back
    # -- its runs, its topology, the conversations it archives -- is a reading
    # of a system dossier does not own, and lives in Seams.
    View("tab-deltas", "On deck", "Plan",
         "Open deltas and every open pull request no delta claims -- the units "
         "of work on deck. The harness's threads moved to Harness, in Seams, "
         "with the rest of what the harness reports."),
    View("tab-sweep", "Sweep", "Plan",
         "What one dependency change would touch and where it needs a person, "
         "and what a cleanup of this workstation would get back -- the two "
         "sweeps, one that spans the estate and one that spans the disk.",
         "dossier sweep"),
    # Originating a change is the most proactive act there is, so Goals sits in
    # Plan by the job it serves. That it crosses the harness seam to draft the
    # plan is the mechanism, not the job -- the same reason On deck's deltas are
    # Plan though the harness reads them too. Nothing is executed here;
    # approving the plan is the human queue's act (Outstanding).
    View("tab-goals", "Goals", "Plan",
         "Send the harness a new goal, and read the plan it drafts.",
         "dossier harness goal",
         needs=(Need(HARNESS,
                     "the goal reaches the harness's planner over its port",
                     "uv run qmcp serve"),)),

    # Explore -- understand what exists: one repository in one reading, then the
    # code, people and releases across them.
    View("tab-dossier", "Dossier", "Explore",
         "One repository in one reading: its own facts, the document and parts "
         "it is composed of, and the languages it is written in -- the "
         "consistent overview of a repository dossier holds.",
         "dossier export show",
         needs=_of_one_repository("this repository's reading")),
    View("tab-docs", "Documentation", "Explore",
         "Every documentation section parsed out of the repository.",
         "dossier query",
         needs=_of_one_repository("parsed sections")),
    View("tab-branches", "Branches", "Explore",
         "Branches from the sync, and what only the clones on this machine "
         "hold.",
         needs=(*_of_one_repository("branches"),
                Need(CLONE,
                     "the question is what would be lost if this disk died, "
                     "and that question has no answer on a server",
                     "dossier clone <repo>"))),
    View("tab-dependencies", "Dependencies", "Explore",
         "What every repository declares, and what they share.",
         needs=_of_one_repository("declared manifests")),
    View("tab-contributors", "Contributors", "Explore",
         "Who has committed where, by how many repositories they reach.",
         needs=_of_one_repository("commit counts")),
    View("tab-releases", "Releases", "Explore",
         "Tags that were cut, newest first. The one human gate a project has.",
         needs=_of_one_repository("tags")),

    # Health -- is this organisation sound against the corpus. (Disk moved to
    # Sweep: a reclaim is a sweep of the workstation, the same shape as a
    # dependency sweep of the estate.)
    View("tab-governance", "Governance", "Health",
         "Where every project stands against the corpus: current, drifted, "
         "unmeasured.", "dossier governance show",
         needs=(Need(CORPUS,
                     "the reading is generated by the corpus, and this "
                     "checkout may be pinned before those documents existed",
                     "dossier governance dashboard"),)),

    # Seams -- the boundary where dossier meets systems it does not own, read
    # rather than driven. Every view here reports what the harness did: its
    # invocations, the conversations it archived, the shape it serves. GitHub,
    # the corpus and codecarto's window are the same kind of thing and would
    # join here. Originating work is not a reading and lives in Plan.
    View("tab-harness", "Harness", "Seams",
         "What the harness ran, when and whether it finished, and the "
         "conversations it has archived as deltas.",
         "dossier harness ingest",
         needs=(Need(HARNESS,
                     "these are the harness's invocations, and it is a "
                     "separate process on a separate port",
                     "uv run qmcp serve"),)),
    View("tab-topology", "Topology", "Seams",
         "How the harness, its projects and their deltas connect.",
         "dossier topology",
         needs=(Need(HARNESS,
                     "the shapes are the harness's own, served over its port",
                     "uv run qmcp serve"),)),
)

BY_TAB = {view.tab: view for view in VIEWS}
BY_NAME = {view.name: view for view in VIEWS}
BY_ACTION = {view.action: view for view in VIEWS}

assert len(BY_TAB) == len(VIEWS), "two views share a tab id"
assert set(v.group for v in VIEWS) <= set(GROUPS), "a view names no known group"


def in_group(group: str) -> tuple[View, ...]:
    """The views under one group, in registration order."""
    return tuple(view for view in VIEWS if view.group == group)


def grouped() -> tuple[tuple[str, tuple[View, ...]], ...]:
    """Every group with its views, in `GROUPS` order.

    A group with no views is dropped rather than placed: an empty cell in the
    ring is a level of nothing, and rad's placement would still spend a
    keystroke reaching it.
    """
    found = ((group, in_group(group)) for group in GROUPS)
    return tuple((group, views) for group, views in found if views)
