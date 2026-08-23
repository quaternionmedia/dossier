"""`4.6` -- ingesting an export from the menu.

WHY THIS ROUTE EXISTS AT ALL. Somebody tried to ingest an export through the
Threads tab and could not: the button's handler was on another class, and the
button itself had been pushed off the right edge of the screen by an unstyled
input beside it. Both are fixed and guarded in `test_button_wiring.py`. This is
the other half -- `PRINCIPLES.md` P14 says a needed change that could only be
completed by typing schedules interface work, and this is that work.

WHAT THE RING CANNOT DO, STATED RATHER THAN WORKED AROUND. It commits an intent
and closes; that is what makes a keystroke count mean anything. A command
needing free text therefore hands off to a surface that can hold one, and the
handoff lands on the tab where the result appears.
"""

from __future__ import annotations

import pytest
from sqlmodel import Session, SQLModel, create_engine
from textual.widgets import Input

from dossier.rad.index import by_number
from dossier.tui import DossierApp


class Intent:
    def __init__(self, action):
        self.action = action
        self.ipa = 3


def app_for():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    return DossierApp(session_factory=lambda: Session(engine))


# --- the number ---------------------------------------------------------------


def test_four_six_is_the_ingest_command():
    """Pinned, because it is about to be written into instructions. A palette
    reorder that moved it must be loud rather than silent."""
    found = by_number()["4.6"]
    assert found.action == "reach.ingest"
    assert found.path == ("Reach", "Ingest deltas")
    assert found.keys == ("m", "4", "6")


def test_the_ingest_command_is_wired():
    """It was greyed out until this work. `Reach` was greyed with it, because
    a verb whose every child is unavailable is unavailable too -- so wiring
    this is what makes the whole verb reachable."""
    from dossier.rad.index import applied_by

    marked = {c.number: ok for c, ok in applied_by(DossierApp.RAD_HANDLED)}
    assert marked["4.6"] is True
    assert marked["4"] is True, "Reach is reachable now that it holds something"


# --- what pressing it does ----------------------------------------------------


@pytest.mark.asyncio
async def test_it_opens_the_archive_and_focuses_the_field():
    """THE ONE THAT MATTERS.

    Opening the tab is not enough. A route that leaves somebody hunting for
    where to type has moved the work rather than done it, and that is the exact
    complaint P13 is about.

    Mutation: drop the `focus()` and this fails -- the tab is right and the
    cursor is somewhere else.
    """
    app = app_for()
    async with app.run_test(size=(100, 35)) as pilot:
        await pilot.pause()
        assert app.query_one("#project-tabs").active != "tab-threads"

        app._apply_rad_intent(Intent("reach.ingest"))
        await pilot.pause()
        await pilot.pause()

        assert app.query_one("#project-tabs").active == "tab-threads"
        assert app.focused is app.query_one("#thread-export-path", Input), (
            f"focus landed on {app.focused!r}")


@pytest.mark.asyncio
async def test_typing_a_path_and_pressing_enter_completes_the_route(monkeypatch):
    """End to end from the menu, with nothing reaching the harness.

    This is the whole reported failure, run as a test: open the menu route,
    type a path, press Enter, and have the ingest actually be asked for.
    """
    app = app_for()
    asked = []
    async with app.run_test(size=(100, 35)) as pilot:
        await pilot.pause()
        import dossier.threads as threads_module

        # `monkeypatch`, not a bare assignment. A plain assignment here leaks
        # the stub into every test that runs afterwards in the same process --
        # which is invisible under a fixed order and immediate under a random
        # one. Three tests in `test_threads_client.py` failed on the first
        # randomised run because this module had already replaced the real
        # `request_import` and never put it back.
        monkeypatch.setattr(threads_module, "request_import",
            lambda path, *a, **k: asked.append(path) or {"ok": False, "error": "stub"})

        app._apply_rad_intent(Intent("reach.ingest"))
        await pilot.pause()
        await pilot.pause()

        for character in "an/export":
            await pilot.press(character if character != "/" else "slash")
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        await pilot.pause()

    assert asked == ["an/export"], (
        "typing into the focused field and pressing Enter did not ingest")


@pytest.mark.asyncio
async def test_an_empty_field_says_so_rather_than_ingesting_nothing(monkeypatch):
    """The first thing somebody does with a focused field is press Enter."""
    app = app_for()
    asked = []
    async with app.run_test(size=(100, 35)) as pilot:
        await pilot.pause()
        import dossier.threads as threads_module

        # `monkeypatch`, not a bare assignment. A plain assignment here leaks
        # the stub into every test that runs afterwards in the same process --
        # which is invisible under a fixed order and immediate under a random
        # one. Three tests in `test_threads_client.py` failed on the first
        # randomised run because this module had already replaced the real
        # `request_import` and never put it back.
        monkeypatch.setattr(threads_module, "request_import",
                            lambda path, *a, **k: asked.append(path))

        app._apply_rad_intent(Intent("reach.ingest"))
        await pilot.pause()
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()

    assert asked == [], "an empty path was sent to the harness"


@pytest.mark.asyncio
async def test_a_quoted_path_is_accepted(monkeypatch):
    """Windows' "Copy as path" wraps the result in double quotes, and pasting
    it is the ordinary way somebody gets a path into this field. Rejecting it
    would fail on the most likely input there is."""
    app = app_for()
    asked = []
    async with app.run_test(size=(100, 35)) as pilot:
        await pilot.pause()
        import dossier.threads as threads_module

        # `monkeypatch`, not a bare assignment. A plain assignment here leaks
        # the stub into every test that runs afterwards in the same process --
        # which is invisible under a fixed order and immediate under a random
        # one. Three tests in `test_threads_client.py` failed on the first
        # randomised run because this module had already replaced the real
        # `request_import` and never put it back.
        monkeypatch.setattr(threads_module, "request_import",
            lambda path, *a, **k: asked.append(path) or {"ok": False, "error": "stub"})

        app._apply_rad_intent(Intent("reach.ingest"))
        await pilot.pause()
        await pilot.pause()
        # leaks: allow an invented export path, to prove quotes are stripped
        app.query_one("#thread-export-path", Input).value = '"C:\\Users\\x\\export"'
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        await pilot.pause()

    # leaks: allow an invented export path, to prove quotes are stripped
    assert asked == ["C:\\Users\\x\\export"], "the quotes were not stripped"
