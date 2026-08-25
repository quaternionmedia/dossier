"""One index, numbered by the keys that reach each thing.

**THE FAILURE THIS EXISTS TO STOP IS A SECOND LIST.** The set of views was
written down in three places -- the `TabPane` calls, `config.AVAILABLE_TABS` and
the tests' own `PROJECT_TABS` -- and they had already drifted: the settings
screen offered thirteen of twenty-one views. An index typed beside the menu
would have been a fourth.

So the registry is `dossier.views`, the tree is computed from the palette, and
these tests assert that nothing keeps a copy.
"""

from __future__ import annotations

import re
from pathlib import Path

from dossier import toc, views
from dossier.tui.app import DossierApp

PAGE = Path("docs/commands.md")
APP = Path("src/dossier/tui/app.py")


# --- the property the page is for --------------------------------------------


def test_every_view_is_reachable_by_a_keystroke():
    """THE ONE THIS EXISTS FOR.

    Six of eighteen views had a rad ordinal; the other twelve were reachable
    by mouse only, which for somebody driving from the keyboard is not
    reachable. The group level in `Go` is what pays for the other twelve.

    Mutation: drop a view from `dossier.views.GROUPS` and this fails.
    """
    missed = [v.title for v in toc.unreachable_views()]
    assert not missed, f"no keystroke reaches: {missed}"


def test_every_view_has_a_route_outside_the_application_too():
    """A view only the TUI can show is unreachable from a script, a pipe or a
    machine with no terminal to spare.

    Eight views have a command of their own; the rest are facet-backed and get
    `dossier show <name>` from one command rather than ten.

    Mutation: return "" from `_cli_for` for facet-backed views and this fails.
    """
    without = [e.title for e in toc.entries()
               if e.action.startswith("view.") and not e.cli]
    assert not without, f"no command reaches: {without}"


def test_every_act_says_whether_it_has_a_command():
    """The acts are not views, and most of them act on what is on screen --
    advancing a phase, filtering the list. Having no command is correct for
    those and wrong for others, and the difference has to be written down or a
    reader cannot tell a decision from an omission.

    Mutation: add a wedge with a new action and this fails until it is
    declared.
    """
    undeclared = sorted(
        e.action for e in toc.entries()
        if e.action and not e.action.startswith("view.")
        and e.action not in toc.ACT_ROUTES)
    assert not undeclared, f"say whether these have a command: {undeclared}"


def test_an_act_with_no_command_says_so_on_the_page():
    """A blank where a command would go reads as one nobody wrote.

    Mutation: drop the `in the application only` line and this fails.
    """
    rendered = toc.as_markdown(DossierApp.RAD_HANDLED)
    assert "*in the application only*" in rendered


def test_the_number_is_the_keystroke_and_not_a_label():
    """`8.6.6` has to *be* the keys, or the page is a second naming scheme.

    Mutation: number the entries sequentially and this fails.
    """
    for entry in toc.entries():
        assert entry.keys[0] == "m", entry.keys
        assert ".".join(entry.keys[1:]) == entry.number, entry
        assert "5" not in entry.number.split("."), (
            "the centre backs out; it is never an item")


# --- nothing keeps a second copy ---------------------------------------------


def test_the_settings_list_is_the_registry():
    """It listed thirteen of twenty-one before it was derived, missing Sweep,
    Threads, Harness, Waiting, Disk, Topology and Overview.

    Mutation: hardcode `AVAILABLE_TABS` again and this fails as soon as the
    registry moves.
    """
    from dossier.config import AVAILABLE_TABS

    assert AVAILABLE_TABS == [(v.tab, v.title) for v in views.VIEWS]


def test_the_composed_tabs_are_the_registry():
    """A view in the registry with no tab is a keystroke onto nothing; a tab
    with no registry entry is a view with no keystroke. Both were real.

    Mutation: compose a TabPane that the registry does not name and this fails.
    """
    composed = set(re.findall(r'TabPane\([^)]*id="(tab-[a-z-]+)"',
                              APP.read_text(encoding="utf-8")))
    assert composed == {v.tab for v in views.VIEWS}


def test_the_dispatch_is_the_registry():
    """`RAD_VIEWS` held six of eighteen, and once held a seventh that no wedge
    named -- a dead entry making the dispatch look wider than the menu.

    Mutation: drop an entry from `RAD_VIEWS` and this fails.
    """
    assert DossierApp.RAD_VIEWS == {v.action: v.tab for v in views.VIEWS}
    for action in DossierApp.RAD_VIEWS:
        assert action in DossierApp.RAD_HANDLED


# --- the page ------------------------------------------------------------------


def test_the_index_is_recorded():
    """P12: it rides the ordinary test command, so a run leaves it current.

    Recorded rather than compared, for the reason the command sheet is: an
    exact-text assertion fails on every palette change and teaches a reader to
    regenerate without looking at what moved.
    """
    PAGE.parent.mkdir(parents=True, exist_ok=True)
    rendered = toc.as_markdown(DossierApp.RAD_HANDLED)
    PAGE.write_text(rendered, encoding="utf-8")

    assert PAGE.stat().st_size > 0
    for entry in toc.entries():
        assert f"`{entry.number}`" in rendered, f"{entry.number} is missing"


def test_the_page_says_what_it_leaves_out():
    """A page showing the ring and stopping reads as the whole application.

    The count comes from `cli.list_commands` at the moment of writing, which is
    the one place a bare figure belongs: its subject is one run at one commit.

    Mutation: drop the `Outside the ring` section and this fails.
    """
    rendered = toc.as_markdown(DossierApp.RAD_HANDLED)
    assert "## Outside the ring" in rendered
    figures = re.findall(r"\*\*(\d+)\*\*", rendered)
    assert len(figures) >= 2, "the section states no count at all"
    assert int(figures[0]) > int(figures[1]), (
        "more commands are named in the ring than the CLI has leaves")


def test_a_group_carries_no_action_and_a_view_carries_one():
    """A group that committed something would be a menu item pretending to be
    a level, and a view that opened one would be a level pretending to act."""
    for entry in toc.entries():
        assert entry.is_menu == (not entry.action), entry
        if not entry.is_menu and entry.action.startswith("view."):
            assert entry.summary, f"{entry.title} says nothing about itself"
