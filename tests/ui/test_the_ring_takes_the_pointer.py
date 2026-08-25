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
