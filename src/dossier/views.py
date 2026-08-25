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

WHAT THIS CANNOT DO. Say whether a view has anything in it. `Waiting` reads zero
rows when no harness has asked a question, and that is the state it exists to
show; an empty view and a broken one look identical from here.
"""

from __future__ import annotations

from dataclasses import dataclass

# The order the ring places them in, and therefore the order of the index.
GROUPS = ("Repositories", "Work", "Code", "Machine")


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

    @property
    def name(self) -> str:
        """The short name, e.g. `overview`. What `dossier show` takes."""
        return self.tab.removeprefix("tab-")

    @property
    def action(self) -> str:
        """The ring action that opens it, e.g. `view.overview`."""
        return f"view.{self.name}"


VIEWS: tuple[View, ...] = (
    # Repositories -- all of them, then one of them.
    View("tab-overview", "Overview", "Repositories",
         "Every repository in one reading, with what needs attention first.",
         "dossier overview"),
    View("tab-details", "Details", "Repositories",
         "One repository's own facts: description, owner, when it last synced.",
         "dossier projects show"),
    View("tab-dossier", "Dossier", "Repositories",
         "The repository as a document, and the projects it is composed of.",
         "dossier export show"),
    View("tab-docs", "Documentation", "Repositories",
         "Every documentation section parsed out of the repository.",
         "dossier query"),
    View("tab-languages", "Languages", "Repositories",
         "What the repository is written in, by share of its bytes."),

    # Work -- what is moving, and what is waiting.
    View("tab-deltas", "On deck", "Work",
         "Open deltas, and every open pull request no delta claims."),
    View("tab-sweep", "Sweep", "Work",
         "What one dependency change would touch, and where it needs a person.",
         "dossier sweep"),
    View("tab-issues", "Issues", "Work",
         "Open issues, most recently updated first."),
    View("tab-waiting", "Outstanding", "Work",
         "Everything three readings noticed -- harness questions, repositories "
         "nothing has read lately, invocations that failed -- and what would "
         "settle each. Zero is a real answer, not an empty table."),

    # Code -- what is in the repositories rather than what is being done to them.
    View("tab-branches", "Branches", "Code",
         "Branches from the sync, and what only the clones on this machine "
         "hold."),
    View("tab-dependencies", "Dependencies", "Code",
         "What every repository declares, and what they share."),
    View("tab-contributors", "Contributors", "Code",
         "Who has committed where, by how many repositories they reach."),
    View("tab-releases", "Releases", "Code",
         "Tags that were cut, newest first. The one human gate a project has."),

    # Machine -- this box, this organisation, and the harness beside them.
    View("tab-governance", "Governance", "Machine",
         "Where every project stands against the corpus: current, drifted, "
         "unmeasured.", "dossier governance show"),
    View("tab-disk", "Disk", "Machine",
         "What is eating this machine, and what it would take to get it back.",
         "dossier disk status"),
    View("tab-topology", "Topology", "Machine",
         "How the harness, its projects and their deltas connect.",
         "dossier topology"),
    View("tab-harness", "Harness", "Machine",
         "What the harness ran, when, and whether it finished.",
         "dossier harness ingest"),
    View("tab-threads", "Threads", "Machine",
         "Every line of work in flight, most idle first.",
         "dossier governance threads"),
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
