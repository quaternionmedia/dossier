"""The narratives a picture is made of, and where each one is shown.

**ONE GIF PER NARRATIVE, ONE FRAME PER STEP.** A still shows a state. A
narrative is a sequence, and a page that shows six stills of six steps asks the
reader to hold the order in their head. `dossier.filmstrip` draws the frames;
this says what the frames are.

**A FRAME IS ANY SCREEN RICH CAN EXPORT**, which is what lets one pipeline
serve two very different kinds of page:

- a *tour* walks the running application and captures a tab per step, so the
  frames are the dashboard a reader will actually see;
- a *reading* renders the steps of a page that is prose and code, through a
  Rich console, so the frames are what running those steps looks like.

Both end up as an SVG string, which is the only thing `filmstrip` accepts. A
third kind would only have to produce one too.

**THE GIFS ARE NOT COMMITTED, EXCEPT THE README'S.** They are generated where
they are served -- the mkdocs build calls `record_all` -- so a regenerated
picture is never a diff nobody reads, and a stale one cannot survive in the
tree. The README is the exception because it is read on GitHub, which builds
nothing: its picture has to be in the repository or it is a broken image.

WHAT THIS CANNOT SEE. Whether a narrative's steps are the right steps, or in
the right order. It records what it is told to record.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from dossier import views
from dossier.filmstrip import HOLD_MS, Frame

# Where the pictures land. Everything here is generated; `.gitignore` keeps all
# of it out of the tree except what the README names.
SHOTS = Path("docs/screenshots")

# The terminal the tours are recorded at. One size, because a narrative shown
# at three resolutions is three narratives and a reader only needs one.
TERMINAL = (120, 40)

# What a step that asks the reader to decide something is held for. Longer than
# an ordinary step on purpose: a gate is the frame somebody has to read twice.
GATE_MS = 7000


@dataclass(frozen=True)
class Step:
    """One frame of a narrative."""

    caption: str
    """What this step is. Recorded beside the picture rather than drawn into
    it -- burning text into a frame makes the picture untranslatable and
    unsearchable, and the page beside it can say the same thing in real text."""

    tab: str = ""
    """The view this step shows, for a tour. Empty for a reading."""

    source: str = ""
    """What to render, for a reading. Empty for a tour."""

    hold_ms: int = HOLD_MS


@dataclass(frozen=True)
class Narrative:
    """One story, and the file it becomes."""

    name: str
    title: str
    shown_in: tuple[str, ...]
    """The pages that embed it. **Checked** -- a narrative nothing shows is a
    picture nobody looks at, and a page naming a narrative that does not exist
    is a broken image."""

    steps: tuple[Step, ...] = ()
    committed: bool = False
    """Whether this one lives in the repository. True only for the README's,
    because GitHub builds nothing."""

    @property
    def path(self) -> Path:
        return SHOTS / f"{self.name}.gif"


def _tour(*pairs: tuple[str, str]) -> tuple[Step, ...]:
    """Steps that each show one registered view.

    The tab ids are checked against the registry at import rather than at
    render: a narrative naming a view that does not exist should fail where
    somebody is reading this file, not halfway through a docs build.
    """
    known = {view.tab for view in views.VIEWS}
    steps = []
    for tab, caption in pairs:
        if tab not in known:
            raise ValueError(
                f"{tab!r} is not a view this application has. The registry in "
                f"`dossier.views` is the list, and a narrative may not invent "
                f"a tab.")
        steps.append(Step(caption=caption, tab=tab))
    return tuple(steps)


# **EVERY STEP HERE IS A VIEW THAT FILLS ITSELF WHEN THE TAB IS SELECTED.**
# Thirteen of the eighteen do. The five that do not are left out rather than
# photographed empty, and each is left out for a reason:
#
#   tab-topology, tab-harness  read a separate process -- `qmcp` on its own
#                              port -- which is very often not running. An
#                              empty panel there is the honest state of this
#                              machine rather than a defect;
#   tab-details, tab-docs      fill from a project selection, which a tour
#                              that sets `tabs.active` never makes;
#   tab-waiting                fills from the overview's reading and stays
#                              empty when the tab is switched to directly.
#
# The last three are worth someone's attention: a view a person can reach and
# a script cannot is a view that behaves differently for the two, and this is
# the only thing that has ever asked.
NARRATIVES: tuple[Narrative, ...] = (
    Narrative(
        name="first-run",
        title="What the dashboard shows when it opens",
        shown_in=("README.md", "docs/quickstart.md"),
        committed=True,
        steps=_tour(
            ("tab-overview", "Every repository in one reading, attention first"),
            ("tab-deltas", "On deck: the work in flight"),
            ("tab-branches", "Branches: what carries work nowhere else"),
        ),
    ),
    Narrative(
        name="the-dashboard",
        title="A tour of the dashboard's views",
        shown_in=("docs/dashboard.md",),
        steps=_tour(
            ("tab-overview", "Overview, where the dashboard opens"),
            ("tab-dossier", "Dossier: one project's own record"),
            ("tab-branches", "Branches: what carries work nowhere else"),
            ("tab-governance", "Governance: where each project stands"),
            ("tab-disk", "Disk: what is eating the workstation"),
            ("tab-threads", "Threads: the conversations behind the work"),
        ),
    ),
    Narrative(
        name="a-sweep",
        title="One change across every repository that needs it",
        shown_in=("docs/workflows.md",),
        steps=_tour(
            ("tab-sweep", "A sweep: one delta with many parts"),
            ("tab-dependencies", "What each repository declares"),
            ("tab-deltas", "Each repository's share, on deck"),
        ),
    ),
)


def by_name() -> dict[str, Narrative]:
    return {narrative.name: narrative for narrative in NARRATIVES}


# How many turns of the event loop a view gets to fill itself. A bound rather
# than a guess at a duration: a slow machine gets as many turns as a fast one.
#
# **THERE IS NO MINIMUM CONTENT LENGTH.** An earlier version required the
# pane's description to be 24 characters, and compared that against markers
# like `rows=1` -- six characters, so a pane holding a real table was refused
# for being too short. The condition is that the pane holds *something* and
# has stopped changing; how much is not this function's business.
SETTLE_TURNS = 40


def _pane_text(app, tab: str) -> str:
    """What the *active pane* is showing, which is not what the screen shows.

    **THE DISTINCTION THAT MADE THE FIRST SETTLE USELESS.** An earlier version
    measured the whole screenshot and waited for it to stop changing. The tree,
    the header and the footer are always there and always the same, so every
    screen passed the check instantly -- including one whose pane was empty.
    The picture that came out was a correctly-selected tab over a blank panel.
    """
    pane = app.query_one(f"#{tab}")
    seen = []
    for child in pane.walk_children():
        renderable = getattr(child, "renderable", None)
        if renderable is not None:
            seen.append(str(renderable))
        rows = getattr(child, "row_count", None)
        if rows:
            seen.append(f"rows={rows}")
    return "|".join(seen)


async def _settled(app, pilot, tab: str) -> str:
    """A screenshot taken once the pane has filled. **Not before.**

    A view loads its rows in a worker, so a capture taken two turns after the
    switch photographs the loading state -- a correctly-labelled tab over an
    empty panel, which reads as "this view is blank" rather than "this view is
    slow". Found by looking at the middle frame of the first GIF this made.

    Raises rather than returning the empty one: a picture of nothing is worse
    than no picture, because only one of the two is obviously wrong.
    """
    await pilot.pause()
    try:
        await app.workers.wait_for_complete()
    except Exception:                                  # noqa: BLE001
        # No workers to wait for is not a failure; the loop below still holds
        # the capture until the pane has something in it.
        pass

    previous = ""
    for _ in range(SETTLE_TURNS):
        await pilot.pause()
        seen = _pane_text(app, tab)
        if seen and seen == previous:
            return app.export_screenshot()
        previous = seen
    raise AssertionError(
        f"{tab} never filled: its pane is still showing {previous!r} after "
        f"{SETTLE_TURNS} turns and every worker finished. A frame of it would "
        f"be a picture of an empty panel.")


async def tour_frames(narrative: Narrative, size: tuple[int, int] = TERMINAL
                      ) -> list[Frame]:
    """Walk the application and capture one screen per step.

    **The switch is asserted, not attempted.** A tab that cannot be reached
    fails here rather than producing a frame of whatever happened to be on
    screen -- the defect that published thirty-three pictures of one tab under
    eleven names.
    """
    from textual.widgets import TabbedContent

    from dossier.tui import DossierApp

    frames: list[Frame] = []
    app = DossierApp()
    async with app.run_test(size=size) as pilot:
        await pilot.pause()
        tabs = app.query_one("#project-tabs", TabbedContent)
        for step in narrative.steps:
            tabs.active = step.tab
            await pilot.pause()
            if tabs.active != step.tab:
                raise AssertionError(
                    f"asked for {step.tab} and the container is showing "
                    f"{tabs.active}; the frame would be of the wrong view")
            frames.append(Frame(svg=await _settled(app, pilot, step.tab),
                                hold_ms=step.hold_ms, note=step.caption))
    return frames


async def record(narrative: Narrative, root: Path | None = None,
                 scale: float = 0.55) -> Path:
    """One narrative, written as one file."""
    from dossier.filmstrip import write_gif

    frames = await tour_frames(narrative)
    where = (root or Path(".")) / narrative.path
    return write_gif(frames, where, scale=scale, root=root or Path("."))


async def record_all(root: Path | None = None,
                     only: Callable[[Narrative], bool] | None = None
                     ) -> list[Path]:
    """Every narrative, for the docs build to call.

    `only` narrows it -- the README's picture is recorded by the test suite so
    that it is committed, and the docs build records the rest.
    """
    written = []
    for narrative in NARRATIVES:
        if only and not only(narrative):
            continue
        written.append(await record(narrative, root=root))
    return written
