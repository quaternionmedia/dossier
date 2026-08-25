"""One row of buttons, and it is the ring's middle rank.

**THIRTEEN AFFORDANCES BECAME THREE.** Four buttons in the command bar and nine
more scattered across two tabs, none of which said what its keyboard route was —
so a person learned the buttons or learned the ring, and the two were different
maps of the same application.

The ring already holds every act, numbered, and it takes the pointer now. So the
row is `4`, `5`, `6` — the cells on the middle row of the keypad — and pressing
one opens the ring there. The label a person clicks and the digit they would
have pressed are the same character.

**WHAT STAYS, AND WHY.** The Threads and Topology rows sit beside a text field.
rad's own note says the ring cannot ask for free text: it commits and closes,
which is what makes a keystroke count mean anything. A row carrying an input is
not a row of buttons that failed to consolidate.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from sqlmodel import Session, SQLModel, create_engine
from textual.widgets import Button

from dossier.tui.app import DossierApp

APP = Path("src/dossier/tui/app.py")

GONE = (
    "btn-sync", "btn-add", "btn-delete", "btn-help",
    "btn-new-delta", "btn-advance-phase", "btn-add-note",
    "btn-add-delta-link",
)

# **THE THREE THE CONSOLIDATION GAVE BACK.** Removing them made component
# editing unreachable -- none of the three has a wedge, and `Do` already holds
# six children after `Add` and `Remove`, so three more would be nine on a level
# with eight cells. The guard from #36 caught it. A consolidation that deletes
# the only route to an act is not one.
STAYED = ("btn-add-component", "btn-link-parent", "btn-remove-component")


@pytest.fixture()
def engine():
    from sqlalchemy.pool import StaticPool

    made = create_engine("sqlite://", poolclass=StaticPool,
                         connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(made)
    return made


class Factory:
    def __init__(self, engine):
        self._engine = engine

    def __call__(self):
        return Session(self._engine)


def composed() -> set[str]:
    return set(re.findall(r'Button\([^)]*id="([a-z0-9-]+)"',
                          APP.read_text(encoding="utf-8")))


# --- the row -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_row_is_the_middle_rank(engine):
    """THE ONE THIS EXISTS FOR.

    Three buttons, carrying the numbers of the cells they open.

    Mutation: rename any of them and this fails.
    """
    app = DossierApp(session_factory=Factory(engine))
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        labels = [str(button.label)
                  for button in app.query("#command-bar Button")]

    assert len(labels) == 3, labels
    assert labels[0].startswith("4") and labels[1].startswith("5")
    assert labels[2].startswith("6")


def test_the_consolidated_buttons_are_gone():
    """Mutation: compose any of the eleven again and this fails."""
    still_here = sorted(set(GONE) & composed())
    assert not still_here, still_here


def test_the_component_row_stayed_because_nothing_else_reaches_it():
    """Mutation: remove it again and `test_the_components_pane_moved_rather_
    than_went` goes red, which is how this was found."""
    from dossier.rad.index import keystroke

    assert set(STAYED) <= composed(), sorted(set(STAYED) - composed())
    for action in ("component.add", "component.link", "component.remove"):
        assert not keystroke(action), (
            f"{action} has a wedge now, so its button could go")


def test_no_handler_is_left_pointing_at_them():
    """A handler for a button nothing composes is a route to nowhere.

    Mutation: leave `on_sync_pressed` behind and this fails.
    """
    source = APP.read_text(encoding="utf-8")
    orphans = [name for name in GONE
               if f'@on(Button.Pressed, "#{name}")' in source]
    assert not orphans, orphans


# --- nothing became unreachable ----------------------------------------------


def test_every_act_that_lost_its_button_kept_a_route():
    """THE OTHER ONE THIS EXISTS FOR.

    Consolidating is only a consolidation if the acts survive it. Each of these
    was a button; each is a wedge now, and `Add` and `Delete` are wedges that
    did not exist before — `Do` grew from four children to six, which costs one
    step in rad's budget, and the alternative was an act only the keyboard
    could reach.

    Mutation: drop `do.add` or `do.remove` from the palette and this fails.
    """
    from dossier.rad.index import keystroke

    for action in ("project.sync", "project.add", "project.remove",
                   "delta.advance", "delta.note"):
        assert keystroke(action), f"{action} has no keystroke"
        assert action in DossierApp.RAD_HANDLED, f"{action} is not dispatched"


def test_the_registry_says_why_each_one_has_no_button():
    """An action with one route is a decision, and the difference between a
    decision and an oversight has to be written down.

    Mutation: remove the `only` reason from any of them and
    `test_a_one_route_action_says_why` fails.
    """
    from dossier import actions

    for name in ("delta.advance", "delta.note", "project.remove"):
        found = actions.BY_ID[name]
        assert found.button is None
        assert "consolidated" in found.only, found.only


# --- the cost stays honest ---------------------------------------------------


def test_a_click_on_the_row_costs_what_the_keystrokes_cost():
    """**TWO INPUTS, BECAUSE IT IS TWO INPUTS.** The click opens the menu and
    the cell chooses a verb, exactly as `m` then `6` does.

    Seeding the session's state directly would put the same menu on screen for
    one charged input, and the cost ledger would quietly disagree with the
    keyboard.

    Mutation: set the session's cursor instead of calling `press_cell` in
    `RingScreen.on_mount` and this fails.
    """
    import inspect

    from dossier.rad.ring import RingScreen

    source = inspect.getsource(RingScreen.on_mount)
    assert "press_cell" in source, (
        "the opening cell is not pressed, so it is not charged")


def test_five_does_not_get_a_second_meaning():
    """The centre is the one cell whose meaning never changes. A button
    carrying its number that did something else outside the ring would undo
    exactly that.

    Mutation: make `5` open the ring and this fails.
    """
    import inspect

    source = inspect.getsource(DossierApp.on_rank_five_pressed)
    assert "action_rad_menu" not in source
    assert "Nothing to close" in source


def test_the_rows_that_stay_are_the_ones_carrying_a_field():
    """rad commits and closes, which is what makes a keystroke count mean
    anything — so it cannot ask for free text, and a row holding an input is
    not a row that failed to consolidate.

    Mutation: consolidate the Threads row away and its export path has nowhere
    to be typed.
    """
    source = APP.read_text(encoding="utf-8")
    for row, field in (("thread-buttons", "thread-export-path"),
                       ("topology-picker", "topology-subject")):
        assert f'id="{row}"' in source or f'id="{field}"' in source, row
