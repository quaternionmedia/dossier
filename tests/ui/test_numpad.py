"""Nine cells, and the several ways a key reaches one.

    7 8 9
    4 5 6      5 always backs out
    1 2 3
"""

from __future__ import annotations

import pytest

from dossier.rad import numpad
from dossier.rad.session import RadSession, Wedge


def menu(count: int):
    """A resolver with `count` leaf items, labelled by position."""
    items = tuple(
        Wedge(f"item{index}", f"Item {index}", action=f"do.{index}")
        for index in range(count)
    )
    return lambda context=None: items


# --- placement ---------------------------------------------------------------


def test_four_items_sit_at_the_cardinals():
    """Where a ring would have put them, so the common menu reads the same."""
    assert numpad.place(4).cells == (2, 4, 6, 8)


def test_eight_items_fill_every_cell_but_the_centre():
    assert numpad.place(8).cells == (1, 2, 3, 4, 6, 7, 8, 9)
    assert numpad.BACK not in numpad.place(8).cells


def test_the_first_item_is_at_the_top():
    assert numpad.place(4).by_index[0] == 8


def test_a_ninth_item_is_refused_rather_than_dropped():
    """A menu missing an item looks exactly like a menu that never had it."""
    with pytest.raises(ValueError) as raised:
        numpad.place(9)
    assert "will not fit" in str(raised.value)


# --- keys --------------------------------------------------------------------


def test_every_digit_names_its_own_cell():
    assert [numpad.digit_of(str(n)) for n in range(1, 10)] == list(range(1, 10))


def test_wasd_and_the_arrows_are_the_same_directions():
    for arrow, letter in (("up", "w"), ("left", "a"), ("down", "s"), ("right", "d")):
        assert numpad.direction_of(arrow) == numpad.direction_of(letter) == arrow


def test_a_key_that_is_neither_is_neither():
    assert numpad.digit_of("q") is None
    assert numpad.direction_of("q") is None
    assert numpad.digit_of("0") is None, "there is no cell 0"


# --- movement ----------------------------------------------------------------


def test_up_then_left_reaches_seven():
    """The requirement, spelled out: two presses land on the up-left corner."""
    layout = numpad.place(8)
    after_up = numpad.step_to_item(2, "up", layout)
    assert after_up == 8
    assert numpad.step_to_item(after_up, "left", layout) == 7


def test_every_cell_is_reachable_by_arrows_in_a_four_item_menu():
    """Walking the row or column left cell 4 unreachable from the top, in the
    most common menu size there is."""
    layout = numpad.place(4)
    reached = {8}
    frontier = [8]
    while frontier:
        cell = frontier.pop()
        for direction in ("up", "down", "left", "right"):
            moved = numpad.step_to_item(cell, direction, layout)
            if moved not in reached:
                reached.add(moved)
                frontier.append(moved)
    assert reached == set(layout.cells)


def test_movement_never_lands_on_an_empty_cell():
    layout = numpad.place(4)
    for cell in layout.cells:
        for direction in ("up", "down", "left", "right"):
            assert numpad.step_to_item(cell, direction, layout) in layout.cells


def test_movement_stops_at_the_edge_rather_than_wrapping():
    """A grid has corners. A cursor that leaps from one side to the other is
    one a reader has to watch rather than predict."""
    layout = numpad.place(8)
    assert numpad.step_to_item(7, "up", layout) == 7
    assert numpad.step_to_item(7, "left", layout) == 7


def test_pressing_a_direction_never_moves_you_backwards():
    layout = numpad.place(8)
    assert numpad.step_to_item(8, "left", layout) == 7
    assert numpad.step_to_item(8, "right", layout) == 9


# --- the chord ---------------------------------------------------------------


def test_two_directions_together_name_the_diagonal_between_them():
    assert numpad.chord("up", "left") == 7
    assert numpad.chord("up", "right") == 9
    assert numpad.chord("down", "left") == 1
    assert numpad.chord("down", "right") == 3


def test_the_order_of_the_pair_does_not_matter():
    assert numpad.chord("left", "up") == numpad.chord("up", "left")


def test_two_presses_along_one_axis_are_not_a_chord():
    assert numpad.chord("up", "down") is None
    assert numpad.chord("left", "left") is None


# --- the session ---------------------------------------------------------


def test_a_digit_chooses_its_item_in_one_press():
    """The point of a keypad: the fastest path does not depend on where the
    highlight happens to be."""
    committed = []
    session = RadSession(resolve=menu(8), on_intent=committed.append)
    session.open_at(None)
    intent = session.press_cell(3)
    assert intent is not None
    assert intent.action == "do.5", "cell 3 holds the sixth item in placement order"
    assert intent.ipa == 2, "open, then one digit"


def test_the_centre_backs_out_at_every_depth():
    parent = Wedge("go", "Go", children=(
        Wedge("child", "Child", action="do.child"),))
    session = RadSession(resolve=lambda context=None: (parent,))
    session.open_at(None)
    session.enter()
    assert session.view.path == ("go",)

    session.press_cell(numpad.BACK)
    assert session.view is not None and session.view.path == ()

    session.press_cell(numpad.BACK)
    assert session.is_open is False, "the centre closes the menu at the top level"


def test_the_centre_never_holds_an_item():
    session = RadSession(resolve=menu(8))
    view = session.open_at(None)
    assert view.wedge_at(numpad.BACK) is None
    assert numpad.BACK not in view.placement.by_cell


def test_an_empty_cell_chooses_nothing_and_is_not_a_transition():
    """Nothing moved and nothing was chosen, so the ledger records neither."""
    session = RadSession(resolve=menu(4))
    session.open_at(None)
    before = dict(session.meter.counts)
    assert session.press_cell(7) is None
    assert session.meter.counts["l2_transitions"] == before["l2_transitions"]
    assert session.meter.counts["l0_raw"] > before["l0_raw"], "the key still arrived"


def test_two_quick_directions_land_on_the_diagonal():
    session = RadSession(resolve=menu(8))
    session.open_at(None)
    session.move("down", now=10.0)
    view = session.move("left", now=10.0 + numpad.CHORD_WINDOW / 2)
    assert view.cursor_cell == 1, "down then left, quickly, is the down-left corner"


def test_two_slow_directions_walk_there_instead():
    """The same keys reach the same cell; only the number of steps differs."""
    session = RadSession(resolve=menu(8))
    session.open_at(None)
    session.move("down", now=10.0)
    view = session.move("left", now=10.0 + numpad.CHORD_WINDOW * 4)
    assert view.cursor_cell == 1


def test_a_chord_onto_an_empty_cell_falls_back_to_moving():
    """With four items the corners are empty, so the shortcut cannot apply."""
    session = RadSession(resolve=menu(4))
    session.open_at(None)
    session.move("down", now=10.0)
    view = session.move("left", now=10.0 + numpad.CHORD_WINDOW / 2)
    assert view.cursor_cell == 4, "it moved rather than landing on the empty corner"


def test_the_cursor_starts_on_the_first_item_not_the_centre():
    session = RadSession(resolve=menu(4))
    view = session.open_at(None)
    assert view.cursor_cell == 8
    assert view.current.label == "Item 0"


# --- driven through the real app ---------------------------------------------


@pytest.mark.asyncio
async def test_a_digit_key_reaches_a_view_in_two_presses():
    """`m` then a digit. Nothing depends on where the highlight was."""
    from sqlmodel import Session, SQLModel, create_engine

    from dossier.rad import resolve
    from dossier.tui import DossierApp

    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    app = DossierApp(session_factory=lambda: Session(engine))
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await pilot.press("m")
        await pilot.pause()
        await pilot.pause()

        # Cell 8 holds the first verb, which has children: pressing it descends.
        await pilot.press("8")
        await pilot.pause()
        drawn = app.screen.query_one("#rad-ring").last_render
        first_child = resolve()[0].children[0].label
        assert first_child in drawn


@pytest.mark.asyncio
async def test_wasd_moves_the_highlight_like_the_arrows():
    from sqlmodel import Session, SQLModel, create_engine

    from dossier.tui import DossierApp

    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    app = DossierApp(session_factory=lambda: Session(engine))
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await pilot.press("m")
        await pilot.pause()
        await pilot.pause()
        before = app._rad.view.cursor_cell

        await pilot.press("s")          # down
        await pilot.pause()
        assert app._rad.view.cursor_cell != before
        moved_by_letter = app._rad.view.cursor_cell

        await pilot.press("w")          # back up
        await pilot.pause()
        assert app._rad.view.cursor_cell == before
        assert moved_by_letter == 2, "s should reach the bottom cardinal"


@pytest.mark.asyncio
async def test_the_centre_key_closes_the_menu_from_the_top_level():
    from sqlmodel import Session, SQLModel, create_engine

    from dossier.tui import DossierApp

    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    app = DossierApp(session_factory=lambda: Session(engine))
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await pilot.press("m")
        await pilot.pause()
        await pilot.pause()
        assert type(app.screen).__name__ == "RingScreen"

        await pilot.press("5")
        await pilot.pause()
        await pilot.pause()
        assert type(app.screen).__name__ != "RingScreen", "5 did not close the menu"
