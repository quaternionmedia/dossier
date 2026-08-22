"""Greying out: what a host cannot do is shown, and cannot be chosen.

THE TEST WORTH READING IS THE FIRST ONE. An unavailable wedge keeps its cell.
Dropping it would be the obvious implementation and it renumbers every command
after it -- and the numbers are written down, in `docs/rad-commands.md` and in
this repository's README. A menu that renumbers itself depending on which host
is running it cannot be documented at all.

The rest are the routes to a cell. There are five -- a digit, an arrow, a
diagonal chord, a rotate, and the highlight you were left on -- and a guard that
closes four of them is not a guard.
"""

from __future__ import annotations

from dossier.rad.session import RadSession, Wedge

# One verb with a mix, one verb with nothing available, one with everything.
# The mix is what makes skipping observable; the dead verb is what makes
# "a submenu is available if anything under it is" observable.
PALETTE = (
    Wedge("go", "Go", children=(
        Wedge("go.a", "A", action="live.a"),
        Wedge("go.b", "B", action="dead.b"),
        Wedge("go.c", "C", action="live.c"),
    )),
    Wedge("do", "Do", children=(
        Wedge("do.a", "DA", action="dead.x"),
        Wedge("do.b", "DB", action="dead.y"),
    )),
    Wedge("show", "Show", children=(
        Wedge("show.a", "SA", action="live.s"),
    )),
)

LIVE = {"live.a", "live.c", "live.s"}


def build(available=True):
    """A session over PALETTE. `available=True` means nobody declared."""
    return RadSession(
        resolve=lambda context=None: PALETTE,
        available=None if available is True else available,
    )


def wired(wedge):
    return (wedge.action or wedge.id) in LIVE


# --- the cell is kept ---------------------------------------------------------


def test_an_unavailable_wedge_keeps_its_cell():
    """THE ONE THAT MATTERS.

    Greyed is not removed. `Go`'s three children sit on 8, 6 and 2 whether or
    not the middle one can be chosen, so `8.2` names the same thing in every
    host -- and `docs/rad-commands.md` can be a document rather than a guess.

    Mutation: filter unavailable wedges out of the resolved list and this
    fails -- C moves from 2 to 6.
    """
    session = build(wired)
    session.open_at()
    session.press_cell(8)                      # into Go

    view = session.view
    assert [w.label for w in view.wedges] == ["A", "B", "C"]
    assert view.placement.by_cell == {8: 0, 6: 1, 2: 2}
    assert view.wedge_at(6).label == "B", "the unavailable one still holds 6"
    assert view.is_available(1) is False


def test_the_numbering_is_the_same_with_and_without_availability():
    """The strongest form of the above: two sessions over one palette, one
    declaring availability and one not, place every wedge identically."""
    plain, marked = build(), build(wired)
    plain.open_at()
    marked.open_at()
    assert plain.view.placement.by_cell == marked.view.placement.by_cell


# --- every route to a cell ----------------------------------------------------


def test_a_digit_press_on_an_unavailable_cell_is_refused():
    """Route one of five.

    Mutation: drop the availability check in `press_cell` and this fails.
    """
    session = build(wired)
    session.open_at()
    session.press_cell(8)                      # into Go, lands on A
    before = session.view.highlighted

    assert session.press_cell(6) is None, "B was committed"
    assert session.view.highlighted == before, "the highlight moved onto B"


def test_enter_refuses_an_unavailable_wedge_even_if_the_highlight_got_there():
    """Route five: the highlight you were left on.

    Nothing should ever leave it on an unavailable wedge, which is exactly why
    this reaches in and puts it there. A guard that holds only while its callers
    behave is one nobody can rely on.

    Mutation: drop the check in `enter` and this fails.
    """
    session = build(wired)
    session.open_at()
    session.press_cell(8)
    session._highlight[-1] = 1                 # B, by force
    assert session.view.current.label == "B"

    assert session.enter() is None
    assert session.intents == [], "an unavailable wedge was committed"


def test_arrows_step_over_an_unavailable_cell():
    """Route two. `A` is on 8 and `C` is on 2, with the dead `B` on 6 between
    them; walking right from A must reach C rather than stopping on B.

    Mutation: drop `allowed` from `step_to_item` and this fails.
    """
    session = build(wired)
    session.open_at()
    session.press_cell(8)
    assert session.view.cursor_cell == 8       # A

    session.move("down")
    assert session.view.current.label == "C", (
        f"landed on {session.view.current.label}, which cannot be chosen")


def test_a_diagonal_chord_will_not_land_on_an_unavailable_cell():
    """Route three, and the one most easily forgotten: the chord bypasses
    `step_to_item` entirely and names a corner directly.

    Mutation: drop the `allowed` check from the chord branch and this fails.
    """
    dead_corner = (
        Wedge("v", "V", children=tuple(
            Wedge(f"v.{i}", f"W{i}", action="dead" if i == 4 else "live")
            for i in range(5))),
    )
    session = RadSession(resolve=lambda c=None: dead_corner,
                         available=lambda w: w.action == "live")
    session.open_at()
    session.press_cell(8)
    # Five children: 8, 6, 2, 4, then 9 -- the fifth is the corner, and it is
    # the dead one.
    assert session.view.placement.by_index[4] == 9
    session._highlight[-1] = 0                 # on 8

    session.move("up", now=0.0)
    session.move("right", now=0.05)            # chord -> 9, which is dead
    assert session.view.cursor_cell != 9, "the chord landed on a dead corner"


def test_rotate_skips_an_unavailable_wedge():
    """Route four.

    Mutation: restore the plain modulo step and this fails.
    """
    session = build(wired)
    session.open_at()
    session.press_cell(8)                      # A, index 0
    session.rotate(1)
    assert session.view.current.label == "C", "rotate stopped on B"


def test_opening_starts_on_something_choosable():
    """The highlight a person is given before they press anything.

    Mutation: go back to `self._highlight = [0]` and this fails, because Go's
    first child is available but `Do`'s is not.
    """
    session = build(wired)
    session.open_at()
    # `Do` holds nothing available, so pressing it is refused and the ring stays
    # at the top level -- asserted here because it is the precondition for the
    # rest of the test meaning anything.
    session.press_cell(6)
    assert session.view.path == ()

    session.press_cell(2)                      # Show, whose only child is live
    assert session.view.current.label == "SA"


def test_entering_a_submenu_lands_on_its_first_available_child():
    dead_first = (
        Wedge("v", "V", children=(
            Wedge("v.a", "DEAD", action="dead"),
            Wedge("v.b", "LIVE", action="live"),
        )),
    )
    session = RadSession(resolve=lambda c=None: dead_first,
                         available=lambda w: w.action == "live")
    session.open_at()
    session.press_cell(8)
    assert session.view.current.label == "LIVE"


# --- submenus -----------------------------------------------------------------


def test_a_submenu_with_nothing_available_is_itself_unavailable():
    """Greying the leaves and leaving the verb bright walks a reader into a
    level where every cell is dead -- two keystrokes to be told nothing is
    there, which is worse than not opening.

    Mutation: return True for every submenu and this fails.
    """
    session = build(wired)
    session.open_at()
    view = session.view
    labels = {w.label: view.is_available(i) for i, w in enumerate(view.wedges)}
    assert labels == {"Go": True, "Do": False, "Show": True}


def test_a_dead_submenu_cannot_be_entered():
    session = build(wired)
    session.open_at()
    assert session.press_cell(6) is None       # Do
    assert session.view.path == (), "descended into a submenu with nothing in it"


def test_availability_is_recursive_not_one_level_deep():
    """A palette deeper than dossier's own, so the recursion is exercised
    rather than assumed from a two-level menu."""
    deep = (
        Wedge("a", "A", children=(
            Wedge("a.b", "B", children=(
                Wedge("a.b.c", "C", action="live"),
            )),
        )),
        Wedge("x", "X", children=(
            Wedge("x.y", "Y", children=(
                Wedge("x.y.z", "Z", action="dead"),
            )),
        )),
    )
    session = RadSession(resolve=lambda c=None: deep,
                         available=lambda w: w.action == "live")
    session.open_at()
    view = session.view
    assert view.is_available(0) is True, "A holds a live grandchild"
    assert view.is_available(1) is False, "X's only grandchild is dead"


# --- a host that never said ---------------------------------------------------


def test_without_a_predicate_everything_is_available():
    """A host that does not know about availability is unchanged, and
    `available` is None rather than a tuple of Trues -- "nobody said" and
    "all of these" are different answers."""
    session = build()
    session.open_at()
    assert session.view.available is None
    assert session.view.is_available(1) is True
    # Placement order, not sorted: the cells come back in the order the menu
    # lays them out (8, 6, 2 -- clockwise from the top), which is the order a
    # reader sees. Sorting would put 2 first and describe nothing.
    assert session.view.available_cells() == tuple(session.view.placement.by_cell)


def test_an_empty_availability_tuple_is_not_the_same_as_none():
    """A real answer about a menu with no wedges, and it must not be read as
    "nobody said"."""
    from dossier.rad.session import RingView

    assert RingView(wedges=(), highlighted=0, path=(), available=()).available == ()


# --- what it costs ------------------------------------------------------------


def test_a_refused_press_is_still_charged_as_an_input():
    """It cost the person a keystroke, and rad's IPA should say so: a menu with
    dead cells ought to show up as a worse number rather than as a free
    mistake.

    Mutation: charge `recognized=False` and the eventual commit's IPA drops,
    hiding what the dead cell cost.
    """
    session = build(wired)
    session.open_at()
    session.press_cell(8)                      # into Go
    before = session.meter.inputs_since_open

    session.press_cell(6)                      # refused
    assert session.meter.inputs_since_open == before + 1


def test_the_meter_still_reconciles_after_refusals():
    """rad's L1 <= L0 and L3 <= L2. A refusal that broke this would make every
    IPA figure in the session untrustworthy, not just the refused one."""
    session = build(wired)
    session.open_at()
    session.press_cell(8)
    session.press_cell(6)
    session.press_cell(6)
    session.press_cell(2)
    assert session.meter.reconciles()


def test_a_refusal_is_not_a_transition():
    """Nothing moved and nothing was chosen, so L2 does not advance."""
    session = build(wired)
    session.open_at()
    session.press_cell(8)
    before = session.meter.counts["l2_transitions"]
    session.press_cell(6)
    assert session.meter.counts["l2_transitions"] == before
