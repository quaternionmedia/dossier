"""The numbered command index, and the property that makes numbering useful.

The test worth reading is the first one: the number has to be the keystrokes.
An index whose numbers are merely unique is a lookup table, and a lookup table
is the thing numbering a numpad menu was supposed to remove.
"""

from __future__ import annotations

import pytest

from dossier.rad import numpad
from dossier.rad.index import OPEN_KEY, Command, applied_by, by_number, index
from dossier.rad.session import Wedge

# --- the number is the route --------------------------------------------------


def test_the_number_is_the_keys_you_press():
    """THE ONE THAT MATTERS.

    `6.2` means press `6` then `2`. If these ever come apart, every number in
    every instruction becomes a lookup rather than a route, and the reason for
    numbering the menu at all is gone.

    Mutation: number the commands sequentially (1, 2, 3...) and this fails.
    """
    for command in index():
        assert command.number == ".".join(str(cell) for cell in command.cells)
        assert command.keys == (OPEN_KEY, *(str(c) for c in command.cells))


def test_six_two_is_sync():
    """The case that prompted the index, pinned so a palette reorder is loud.

    This is not a redundant restatement of the rule above: that one says the
    number follows the cells, and this one says *these* cells hold sync. A
    reordering of `Do`'s children keeps the first true and breaks this, which
    is exactly the change a reader with a written-down `6.2` needs to hear
    about.
    """
    found = by_number()["6.2"]
    assert found.action == "project.sync"
    assert found.path == ("Do", "Sync project")


def test_every_number_is_unique():
    """Two items on one route is a menu that cannot be described."""
    numbers = [command.number for command in index()]
    assert len(numbers) == len(set(numbers))


# --- the centre --------------------------------------------------------------


def test_the_centre_is_never_indexed():
    """`5` backs out at every level and every depth, so there is no `6.5`.

    Mutation: add `BACK` to `numpad.PLACEMENT` and this fails.
    """
    for command in index():
        assert numpad.BACK not in command.cells, (
            f"{command.number} routes through the centre, which backs out")


# --- depth -------------------------------------------------------------------


def test_a_submenu_is_followed_by_what_it_holds():
    """Reading order, not breadth-first. A page listing every verb and then
    every child is a page a reader has to reassemble."""
    numbers = [c.number for c in index()]
    assert numbers.index("6") < numbers.index("6.2")
    assert numbers.index("6.2") < numbers.index("2"), (
        "Do's children come before the next verb")


def test_a_menu_wedge_has_no_action_and_a_leaf_does():
    for command in index():
        assert command.is_menu == (command.action is None)


def test_deeper_menus_number_all_the_way_down():
    """Nothing in dossier's palette is three deep today, so this drives the
    walk with a palette that is -- otherwise the recursion is only ever
    exercised at one depth and the dotted path is asserted by one example.
    """
    def deep(context=None):
        return (
            Wedge("a", "A", children=(
                Wedge("a.b", "B", children=(
                    Wedge("a.b.c", "C", action="deep.action"),
                )),
            )),
        )

    found = by_number(resolve=deep)
    assert "8.8.8" in found, sorted(found)
    assert found["8.8.8"].action == "deep.action"
    assert found["8.8.8"].path == ("A", "B", "C")
    assert found["8.8.8"].presses == 4, "m, then three cells"


# --- what the host actually handles -------------------------------------------


def test_an_unhandled_action_is_marked_rather_than_dropped():
    """A number missing from the index reads as a menu item that does not
    exist. It exists; it does nothing yet, and those are different facts.

    Mutation: filter unhandled commands out of `applied_by` and this fails.
    """
    marked = dict(applied_by(handled={"view.overview"}))
    by_action = {c.action: handled for c, handled in marked.items()}
    assert by_action["view.overview"] is True
    assert by_action["project.sync"] is False
    assert "project.sync" in {c.action for c in marked}, "still listed"


def test_a_submenu_counts_as_handled():
    """Opening it is the whole of what it does, so it is never 'not applied'."""
    for command, handled in applied_by(handled=()):
        if command.is_menu:
            assert handled, f"{command.number} is a submenu and was marked unhandled"


# --- placement is the palette's, not this module's ----------------------------


def test_the_fifth_child_lands_on_a_diagonal_not_on_five():
    """`Go` has five children, so one of them is past the cardinals. Reading
    the list in order would number that one `5`, which is the centre.

    This is the bug the cell lookup in `_walk` exists to prevent, and it is
    only reachable with a menu of more than four.
    """
    fifth = by_number()["8.9"]
    assert fifth.path == ("Go", "Details")
    assert fifth.cells == (8, 9)


def test_a_menu_too_big_to_lay_out_raises_rather_than_losing_an_item():
    """`numpad.place` refuses past eight, and the index does not soften it:
    an index quietly missing the ninth item is worse than one that will not
    build."""
    def crowded(context=None):
        return tuple(Wedge(f"w{i}", f"W{i}", action=f"a{i}") for i in range(9))

    with pytest.raises(ValueError, match="will not fit"):
        index(resolve=crowded)


# --- the dataclass ------------------------------------------------------------


def test_presses_counts_the_open_key():
    """`6.2` costs three keys from the dashboard, not two. An instruction that
    says two is one a reader follows and gets nothing."""
    assert by_number()["6.2"].presses == 3
    assert by_number()["6"].presses == 2


def test_label_is_the_last_step_of_the_path():
    command = Command(number="6.2", path=("Do", "Sync project"),
                      action="project.sync", cells=(6, 2))
    assert command.label == "Sync project"
    assert command.depth == 2


# --- the sheet, recorded rather than compared ---------------------------------

SHEET = __import__("pathlib").Path("docs/rad-commands.md")


def test_the_command_sheet_is_recorded():
    """P12: it rides the ordinary test command, so a run leaves it current.

    RECORDED, NOT COMPARED. Asserting the file's exact text would fail on every
    palette change and teach a reader to regenerate without looking at what
    moved -- and what moved is the interesting part, because a reordered
    palette renumbers commands that other pages may have written down.

    What is asserted is that the sheet was written, is not empty, and carries
    the wired/unwired split from the app's real dispatch rather than a guess.
    """
    from dossier.rad.index import as_markdown
    from dossier.tui.app import DossierApp

    SHEET.parent.mkdir(parents=True, exist_ok=True)
    rendered = as_markdown(DossierApp.RAD_HANDLED)
    SHEET.write_text(rendered, encoding="utf-8")

    assert SHEET.stat().st_size > 0
    assert "`6.2`" in rendered
    assert "Sync project" in rendered
    # From the app's dispatch, not from this test's opinion of it.
    assert ("delta.advance" in rendered) and ("not yet" in rendered), (
        "the sheet no longer marks unwired commands")


def test_the_sheet_names_every_command_the_index_holds():
    """A sheet missing a number reads as a menu item that does not exist.

    Mutation: render only the wired commands and this fails.
    """
    from dossier.rad.index import as_markdown
    from dossier.tui.app import DossierApp

    rendered = as_markdown(DossierApp.RAD_HANDLED)
    for command in index():
        assert f"`{command.number}`" in rendered, f"{command.number} is missing"


def test_the_sheet_states_no_figure_it_did_not_read_from_the_code():
    """Durable text carries as few integers as it can, and the ones it carries
    come from the thing they describe. Both figures on the page are read out
    of the constants that decide the behaviour, so neither can go stale
    silently.

    Mutation: hard-code either threshold in `_sync_section` and this fails when
    the constant moves.
    """
    from dossier.freshness import STALE_AFTER_DAYS
    from dossier.rad.index import as_markdown
    from dossier.tui.app import DossierApp

    rendered = as_markdown(DossierApp.RAD_HANDLED)
    assert f"older than {STALE_AFTER_DAYS} days" in rendered
    assert f"Above {DossierApp.SYNC_WITHOUT_CONFIRMING} repositories" in rendered
