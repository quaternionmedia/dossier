"""The mouse can open the ring and press a cell in it.

**IT COULD DO NEITHER.** `RingScreen` had no click handler of any kind — the
file contained no `on_click`, no `on_mouse_down`, nothing — so somebody reaching
for the mouse could see the menu and not use it. Every act the ring reaches was,
for them, reachable only through whichever buttons a tab happened to carry, and
the two views of what this application can do were different depending on which
hand you used.

**A CLICK IS AN INPUT, AND IT IS METERED.** `ring.py`'s stated rule is that
every key goes through the session so it is charged exactly once, because a
widget handling one itself would make the IPA figure quietly too low. A click
handled outside `press_cell` would do the same thing to every mouse user, so it
goes through the same door a digit does.

**AND THE GAPS BELONG TO NO CELL.** A click that lands between two boxes does
nothing rather than snapping to the nearest, because a menu acting on a cell the
person did not press is the one failure a menu must not have.
"""

from __future__ import annotations

import pytest
from textual.app import App, ComposeResult
from textual.widgets import Static

from dossier.rad import numpad
from dossier.rad.palette import resolve
from dossier.rad.ring import Ring, RingScreen
from dossier.rad.session import RadSession


def a_drawn_ring() -> Ring:
    ring = Ring()
    session = RadSession(resolve=resolve)
    view = session.open_at(None)
    ring.render_view(view)
    return ring


# --- the geometry ------------------------------------------------------------


def test_a_drawn_ring_remembers_where_it_put_the_cells():
    """Kept rather than recomputed: the box width depends on the longest label
    at that level, so a second derivation would need the view as well.

    Mutation: stop recording `last_geometry` and every click test fails.
    """
    ring = a_drawn_ring()
    assert ring.last_geometry is not None
    width, columns, rows = ring.last_geometry
    assert width > 0
    assert len(columns) == 3 and len(rows) == 3
    assert columns == sorted(columns) and rows == sorted(rows)


def test_a_click_in_a_box_finds_that_cell():
    """THE ONE THIS EXISTS FOR.

    Every one of the nine, at the top-left of its box and inside it.

    Mutation: swap the column and row lookups in `cell_at` and this fails on
    every cell that is not on the diagonal.
    """
    ring = a_drawn_ring()
    width, columns, rows = ring.last_geometry

    for cell, (column, row) in numpad.POSITION.items():
        found = ring.cell_at(columns[column] + 1, rows[row] + 1)
        assert found == cell, (cell, found)


def test_a_click_in_the_gap_finds_nothing():
    """Snapping to the nearest cell would act on one the person did not press.

    Mutation: clamp instead of returning None and this fails.
    """
    ring = a_drawn_ring()
    width, columns, rows = ring.last_geometry

    # Between the first and second column: past the box, before the next.
    between = columns[0] + width
    assert between < columns[1], "there is no gap to test"
    assert ring.cell_at(between, rows[0] + 1) is None

    # Below the first row's box, in the step between rows.
    under = rows[0] + Ring.CELL_ROWS
    assert under < rows[1], "there is no gap to test"
    assert ring.cell_at(columns[0] + 1, under) is None


def test_a_click_outside_the_ring_finds_nothing():
    ring = a_drawn_ring()
    width, columns, rows = ring.last_geometry
    assert ring.cell_at(columns[-1] + width + 50, 0) is None
    assert ring.cell_at(0, rows[-1] + 50) is None


def test_an_undrawn_ring_finds_nothing():
    """Before the first render there is no geometry, and guessing at one would
    be a click acting on a menu nobody has seen."""
    assert Ring().cell_at(0, 0) is None


# --- the click is an input ---------------------------------------------------


class Recorded:
    """A session that records what the screen asked it, and answers nothing."""

    def __init__(self):
        self.cells: list[int] = []
        self.backs = 0
        self.view = None

    def press_cell(self, cell):
        self.cells.append(cell)
        return None

    def back(self):
        self.backs += 1
        return None


def test_a_click_goes_through_press_cell_like_a_digit_does(monkeypatch):
    """THE OTHER ONE THIS EXISTS FOR.

    rad meters every input once, through the session. A click handled beside
    that door would be an input rad never charged for, and the IPA figure would
    be quietly too low for anybody using a mouse.

    Mutation: act on the cell directly instead of calling `press_cell` and this
    fails.
    """
    screen = RingScreen(RadSession(resolve=resolve))
    recorded = Recorded()
    screen._session = recorded
    monkeypatch.setattr(RingScreen, "_cell_under", lambda self, event: 8)
    monkeypatch.setattr(RingScreen, "dismiss", lambda self, result: None)

    screen.on_click(_Click())

    assert recorded.cells == [8], recorded.cells


def test_clicking_the_centre_backs_out_rather_than_committing(monkeypatch):
    """The centre is never an item, at any depth. A click on it that committed
    something would make the one cell you can use without looking into the one
    you cannot.

    Mutation: route the centre through `press_cell` and this fails.
    """
    screen = RingScreen(RadSession(resolve=resolve))
    recorded = Recorded()
    screen._session = recorded
    monkeypatch.setattr(RingScreen, "_cell_under",
                        lambda self, event: numpad.BACK)
    monkeypatch.setattr(RingScreen, "dismiss", lambda self, result: None)

    screen.on_click(_Click())

    assert recorded.backs == 1
    assert recorded.cells == [], "the centre committed something"


def test_a_click_on_nothing_does_nothing(monkeypatch):
    screen = RingScreen(RadSession(resolve=resolve))
    recorded = Recorded()
    screen._session = recorded
    monkeypatch.setattr(RingScreen, "_cell_under", lambda self, event: None)
    monkeypatch.setattr(RingScreen, "dismiss", lambda self, result: None)

    screen.on_click(_Click())

    assert recorded.cells == [] and recorded.backs == 0


class _Click:
    screen_x = 0
    screen_y = 0
    button = 1

    def stop(self):
        pass


class _At:
    """A click at a place on the screen."""

    button = 1

    def __init__(self, x: int, y: int) -> None:
        self.screen_x, self.screen_y = x, y

    def stop(self) -> None:
        pass


# --- the click lands where the box is drawn ----------------------------------
#
# **EVERY TEST ABOVE MONKEYPATCHES `_cell_under`, WHICH IS WHY THE POINTER WAS
# BROKEN WITH ALL OF THEM GREEN.** They prove a cell reaches `press_cell`; they
# say nothing about which cell a person's click resolves to, because the one
# step that converts a screen position into a cell was replaced by a constant.
#
# So these run a real screen and use the geometry the ring actually drew.
# Measured before the fix: of the four corners of each of the nine boxes,
# twenty-seven landed on the wrong cell or on nothing, and a click on the
# middle of a box did nothing at all.


class _Host(App):
    """Something for the ring to float over, so the screen has a real size."""

    def compose(self) -> ComposeResult:
        yield Static("a dashboard would be here")


async def _open_ring(pilot, app):
    session = RadSession(resolve=resolve)
    screen = RingScreen(session)
    app.push_screen(screen)
    await pilot.pause()
    return screen, session


@pytest.mark.asyncio
async def test_every_box_resolves_to_its_own_cell_where_it_is_drawn():
    """THE ONE THIS FILE WAS MISSING.

    Not the top-left corner -- the whole box. The bug that shipped resolved the
    top-left corner of each box correctly and everything else wrongly, so a
    test that probed one point per cell would have passed throughout.

    Mutation: translate by `region` instead of `content_region` in
    `_cell_under` and this fails on twenty-seven of the thirty-six corners.
    """
    app = _Host()
    async with app.run_test(size=(120, 40)) as pilot:
        screen, _ = await _open_ring(pilot, app)
        ring = screen._ring
        width, columns, rows = ring.last_geometry
        content = ring.content_region

        wrong = []
        for cell, (column, row) in numpad.POSITION.items():
            left, top = content.x + columns[column], content.y + rows[row]
            for x in (left, left + width // 2, left + width - 1):
                for y in (top, top + 1, top + Ring.CELL_ROWS - 1):
                    found = screen._cell_under(_At(x, y))
                    if found != cell:
                        wrong.append((cell, (x, y), found))

    assert not wrong, (
        f"{len(wrong)} of 81 points inside a box resolved elsewhere: "
        f"{wrong[:6]}")


@pytest.mark.asyncio
async def test_the_middle_of_a_box_is_where_a_person_clicks():
    """**THE FAILURE AS SOMEBODY MET IT.** Not a corner case: the centre of the
    box, which is where a pointer goes. It resolved to nothing, so the menu
    opened and could not be used.

    Mutation: translate by `region` and this returns None.
    """
    app = _Host()
    async with app.run_test(size=(120, 40)) as pilot:
        screen, session = await _open_ring(pilot, app)
        ring = screen._ring
        width, columns, rows = ring.last_geometry
        content = ring.content_region
        column, row = numpad.POSITION[6]

        await pilot.click(offset=(content.x + columns[column] + width // 2,
                                  content.y + rows[row] + 1))
        await pilot.pause()

        assert session.is_open, "the click closed the ring"
        opened = [wedge.label for wedge in session.view.wedges]

    assert "Sync project" in opened, (
        f"clicking the middle of `6 Do` did not open Do; it showed {opened}")


@pytest.mark.asyncio
async def test_the_gaps_between_the_boxes_still_belong_to_no_cell():
    """The fix moves the hit boxes; it must not widen them. A click in the gap
    acting on the nearest cell is the one failure a menu must not have.

    Mutation: clamp in `cell_at` and this fails.
    """
    app = _Host()
    async with app.run_test(size=(120, 40)) as pilot:
        screen, _ = await _open_ring(pilot, app)
        ring = screen._ring
        width, columns, rows = ring.last_geometry
        content = ring.content_region

        # One column past the first box, and one row past the first box: both
        # are inside the ring and inside no cell.
        assert screen._cell_under(
            _At(content.x + columns[0] + width, content.y + rows[0] + 1)) is None
        assert screen._cell_under(
            _At(content.x + columns[0] + 1,
                content.y + rows[0] + Ring.CELL_ROWS)) is None


@pytest.mark.asyncio
async def test_the_border_and_padding_are_what_the_translation_has_to_cross():
    """**THE REASON, ASSERTED RATHER THAN DESCRIBED.** `region` and
    `content_region` differ here by a border and `padding: 1 3 0 3`. If they
    ever stop differing, the test above stops proving anything and this says
    so -- the two origins would be interchangeable and the bug unreachable.

    Mutation: drop the padding from `RingScreen.DEFAULT_CSS` and this fails,
    which is the signal that the regression tests have gone vacuous.
    """
    app = _Host()
    async with app.run_test(size=(120, 40)) as pilot:
        screen, _ = await _open_ring(pilot, app)
        region, content = screen._ring.region, screen._ring.content_region

    assert (content.x, content.y) != (region.x, region.y), (
        "the ring's content now starts where its region does, so translating "
        "by either works and these tests no longer catch the difference")


# --- and the mouse can open it -----------------------------------------------


def test_right_click_opens_the_ring():
    """`m` from the keyboard, right-click from the mouse: same menu, same
    numbers, same cost.

    Mutation: drop the `on_mouse_down` handler and this fails.
    """
    import inspect

    from dossier.tui.app import DossierApp

    assert hasattr(DossierApp, "on_mouse_down")
    source = inspect.getsource(DossierApp.on_mouse_down)
    assert "action_rad_menu" in source


def test_a_left_click_does_not_open_the_ring():
    """Opening the menu on every click would make the application unusable.

    Mutation: drop the button check and this fails.
    """
    import inspect

    from dossier.tui.app import DossierApp

    source = inspect.getsource(DossierApp.on_mouse_down)
    assert "!= 3" in source, "it does not distinguish which button was pressed"

# --- and the whole way to an act, with the mouse alone ------------------------


@pytest.mark.asyncio
async def test_a_pointer_can_reach_an_act_without_touching_the_keyboard():
    """**THE CLAIM THIS FILE MAKES, END TO END.** Click the row on the keypad's
    middle rank, then click a wedge, and the act opens. Every other test here
    checks one link of that chain; this is the chain.

    It was broken in the middle. The row opened the ring correctly and the ring
    resolved every click to the wrong cell, so the two halves each passed their
    own tests and the route did not exist.

    Mutation: translate by `region` in `_cell_under` and this fails.
    """
    from sqlmodel import Session, SQLModel, create_engine
    from textual.widgets import Input

    from dossier.tui import DossierApp

    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    app = DossierApp(session_factory=lambda: Session(engine))

    async with app.run_test(size=(140, 45)) as pilot:
        await pilot.pause()

        await pilot.click("#btn-rank-4")
        await pilot.pause()
        assert isinstance(app.screen, RingScreen), (
            "clicking the row did not open the ring")

        ring = app.screen._ring
        width, columns, rows = ring.last_geometry
        content = ring.content_region
        cell = next(c for c, label in
                    ((c, w.label) for c, w in
                     ((app.screen._session.view.placement.by_index[i], w)
                      for i, w in enumerate(app.screen._session.view.wedges)))
                    if label == "Download an owner")
        column, row = numpad.POSITION[cell]

        await pilot.click(offset=(content.x + columns[column] + width // 2,
                                  content.y + rows[row] + 1))
        await pilot.pause()
        await pilot.pause()

        field = app.screen.query_one("#download-owner", Input)
        assert app.screen.focused is field, (
            "the act opened but the cursor is not where the name goes")
