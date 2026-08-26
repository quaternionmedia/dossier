"""One GIF per narrative, one frame per step, and what refuses to be drawn.

**THE COMMITTED ONE IS RECORDED HERE.** `first-run` is embedded in the README,
which GitHub renders and builds nothing for, so it has to be in the tree. This
test writes it on every run: a change to the dashboard shows up in
`git status` rather than waiting for somebody to remember. The others are
recorded by `mkdocs build` and are gitignored.

**THE TESTS WORTH READING ARE THE ONES ABOUT REFUSING.** Every defect this
pipeline had produced a picture that looked fine:

  * a cell size written into the renderer rather than read from the document,
    so long runs drifted and overlapped;
  * `&#160;` drawn literally, because only named entities were decoded;
  * a settle check that measured the whole screen, which the tree and footer
    keep constant, so it passed instantly over an empty panel;
  * a minimum content length compared against markers like `rows=1`, which
    refused panes that had real tables in them.

None of those raised. Each was found by looking at the picture, which is the
one thing a test cannot do -- so what is asserted here is everything that
*can* be: that the switch took effect, that the pane filled, and that two
frames of one narrative are not the same frame.

THE MUTATION, per P16, quoted as it printed. `_settled` made to capture at once
instead of waiting for the pane:

    Failed: DID NOT RAISE <class 'AssertionError'>

-- so the empty-panel frame is taken and published, which is the whole defect.

**AND ONE GUARD THAT TURNED OUT TO BE PARTLY REDUNDANT, SAID SO RATHER THAN
CLAIMED.** `tour_frames` asserts that the switch took effect. Removing it and
asking for a tab that does not exist still raises, from Textual itself:
`ValueError: No Tab with id '--content-tab-tab-nope'`. So for a *missing* tab
the framework already refuses. The assertion earns its place only for the case
that actually happened -- a tab that exists while the switch silently does not
take, which is what `#main-tabs` did for thirty-three pictures -- and that case
cannot be provoked here now that the container is queried correctly.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dossier import narratives, views
from dossier.filmstrip import Frame, parse, unescape


# --- what the narratives declare ------------------------------------------------


def test_every_step_names_a_view_this_application_has():
    """`_tour` refuses at import, so this asserts the refusal still bites."""
    known = {view.tab for view in views.VIEWS}
    for narrative in narratives.NARRATIVES:
        for step in narrative.steps:
            assert step.tab in known, (
                f"{narrative.name} shows {step.tab}, which is not a view")


def test_a_narrative_naming_a_view_that_does_not_exist_is_refused():
    with pytest.raises(ValueError, match="not a view"):
        narratives._tour(("tab-nope", "a view nobody has"))


def test_only_the_readme_s_narrative_declares_itself_committed():
    """Everything else is drawn where it is served."""
    committed = [n.name for n in narratives.NARRATIVES if n.committed]

    assert committed == ["first-run"]
    assert "README.md" in narratives.by_name()["first-run"].shown_in


def test_every_narrative_has_more_than_one_step():
    """A narrative with one frame is a screenshot, and should be one."""
    for narrative in narratives.NARRATIVES:
        assert len(narrative.steps) > 1, f"{narrative.name} is a still"


# --- the renderer ---------------------------------------------------------------


def test_numeric_entities_are_decoded():
    """Rich writes every non-breaking space as `&#160;`.

    A version that handled only named entities drew those six characters
    across every panel of the picture.
    """
    assert unescape("a&#160;b") == "a\xa0b"
    assert unescape("&lt;tag&gt; &amp; more") == "<tag> & more"


def test_the_grid_is_read_from_the_document_not_assumed(tmp_path: Path):
    """A cell size written into the renderer is a cell size that drifts.

    The real grid is 12.2 wide at a 20px face; the first version carried 8x18
    and every long run overlapped the next.
    """
    svg = (
        '<style>.terminal-1-r1 { fill: #ffffff }\n'
        '.terminal-1-matrix { font-size: 20px }</style>'
        '<rect fill="#000000" x="0" y="0" width="100" height="50"/>'
        '<text class="terminal-1-r1" x="0" y="20">a</text>'
        '<text class="terminal-1-r1" x="12.2" y="20">b</text>'
        '<text class="terminal-1-r1" x="0" y="44.4">c</text>')
    screen = parse(svg)

    assert screen.cell_w == pytest.approx(12.2)
    assert screen.line_h == pytest.approx(24.4)
    assert screen.font_px == pytest.approx(20.0)


def test_cell_backgrounds_are_read_whatever_order_the_attributes_come_in():
    """Rich writes `fill x y width height shape-rendering`.

    A pattern that matched `x y width height` in that order dropped 632 of 673
    rects, and the picture still rendered.
    """
    svg = ('<rect fill="#000000" x="0" y="0" width="100" height="50"/>'
           '<rect fill="#ff0000" x="10" y="10" width="20" height="20"'
           ' shape-rendering="crispEdges"/>')
    screen = parse(svg)

    assert screen.background == "#000000"
    assert screen.rects == [(10.0, 10.0, 20.0, 20.0, "#ff0000")]


def test_a_narrative_with_no_steps_is_refused(tmp_path: Path):
    from dossier.filmstrip import write_gif

    with pytest.raises(ValueError, match="not a narrative"):
        write_gif([], tmp_path / "nothing.gif")


# --- recording, which is the slow one -------------------------------------------


def drawable() -> bool:
    """Whether this machine has data for a narrative to be a picture of.

    **THE RUNNER HAS AN EMPTY DATABASE, AND THAT IS NOT A DEFECT.** These
    narratives tour views that render rows -- On deck, Branches, Dependencies --
    and a fresh checkout has no projects in it, so those panes are correctly
    empty and `_settled` correctly refuses to photograph them. Asserting
    otherwise would be asserting that whoever runs the suite has synced a
    GitHub account first.

    Conditioned on the data rather than on being CI: an empty database on a
    contributor's laptop should read the same way as an empty one on a runner.
    """
    from sqlmodel import select

    from dossier.cli import get_session
    from dossier.models.schemas import Project

    try:
        with get_session() as session:
            return session.exec(select(Project)).first() is not None
    except Exception:                                  # noqa: BLE001
        return False


needs_data = pytest.mark.skipif(
    not drawable(),
    reason=("no projects in this database, so the narrative views have nothing "
            "to draw. **The committed picture is therefore regenerated only "
            "where there is data** -- a local run, which is where `git status` "
            "surfaces a change to it. Nothing on a bare runner checks it for "
            "staleness, and that limit is real rather than hidden."))


@needs_data
@pytest.mark.asyncio
async def test_the_committed_narrative_is_recorded_on_every_run():
    """**THIS IS WHAT KEEPS IT FROM GOING STALE.**

    The README's picture has to be in the tree because GitHub builds nothing.
    Writing it here means a change to the dashboard turns up as a diff instead
    of waiting for somebody to remember a command.
    """
    narrative = narratives.by_name()["first-run"]
    written = await narratives.record(narrative)

    assert written.is_file()
    assert written == narrative.path


@needs_data
@pytest.mark.asyncio
async def test_the_frames_of_one_narrative_are_not_the_same_frame():
    """Two steps that render identically is the failure with no other symptom.

    Thirty-three pictures of one screen shipped under eleven names because
    nothing compared them.
    """
    narrative = narratives.by_name()["first-run"]
    frames = await narratives.tour_frames(narrative)

    assert len(frames) == len(narrative.steps)
    rendered = [frame.svg for frame in frames]
    assert len(set(rendered)) == len(rendered), (
        "two steps of this narrative produced the same screen")


@pytest.mark.asyncio
async def test_a_step_whose_pane_never_fills_is_refused():
    """A picture of a loading panel reads as "this view is blank".

    `tab-topology` reads a separate process on its own port. With that process
    not running the pane stays empty, which is the honest state of the machine
    -- and the frame is refused rather than published.
    """
    from textual.widgets import TabbedContent

    from dossier.tui import DossierApp

    app = DossierApp()
    async with app.run_test(size=narratives.TERMINAL) as pilot:
        await pilot.pause()
        tabs = app.query_one("#project-tabs", TabbedContent)
        tabs.active = "tab-topology"
        await pilot.pause()

        with pytest.raises(AssertionError, match="never filled"):
            await narratives._settled(app, pilot, "tab-topology")


def test_a_frame_holds_long_enough_to_be_read():
    """Leisurely on purpose. A frame that turns over before a line can be read
    is a frame that was not shown."""
    from dossier.filmstrip import HOLD_MS

    assert HOLD_MS >= 3000
    assert all(step.hold_ms >= 3000
               for narrative in narratives.NARRATIVES
               for step in narrative.steps)
