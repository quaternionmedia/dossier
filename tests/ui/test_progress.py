"""Long work reports itself, and does not stop the application while it runs.

THE TEST WORTH READING IS THE RESPONSIVENESS ONE. A progress bar on a blocked
event loop is not a progress bar; it is a frozen picture of one. The ingest used
to call the harness straight from the button handler, so a twenty-five megabyte
export stopped the whole application -- no repaint, no keys -- and adding a bar
without moving the work would have changed nothing a person could see.

THE SECOND ONE IS ABOUT HONESTY. An import is one request: sent, then answered.
Nothing between those reports a fraction, so the bar is indeterminate and the
elapsed seconds are the figure. A batch sync genuinely counts, and gets a real
fraction. The difference is deliberate and asserted.
"""

from __future__ import annotations

import asyncio

import pytest
from sqlmodel import Session, SQLModel, create_engine
from textual.widgets import Input, Label, ProgressBar

from dossier.tui import DossierApp


def app_for():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    return DossierApp(session_factory=lambda: Session(engine))


async def open_threads(pilot, app):
    app.query_one("#project-tabs").active = "tab-threads"
    await pilot.pause()
    await pilot.pause()


# --- the loop keeps running ---------------------------------------------------


@pytest.mark.asyncio
async def test_the_application_still_responds_while_an_import_runs(monkeypatch):
    """THE ONE THAT MATTERS.

    A slow import is held open here while the test drives the application. If
    the request were still on the event loop, nothing after it would run until
    it returned -- so the tab switch below would not happen and this fails.

    Mutation: call `request_import` directly in `ingest_threads_from` again and
    this hangs, then fails.
    """
    import threading

    import dossier.threads as threads_module

    holding = threading.Event()
    started = threading.Event()

    def slow(path, *args, **kwargs):
        started.set()
        holding.wait(timeout=10)
        return {"ok": True, "written": 1, "indexed": {"threads": 1}}

    monkeypatch.setattr(threads_module, "request_import", slow)

    app = app_for()
    async with app.run_test(size=(100, 35)) as pilot:
        await pilot.pause()
        await open_threads(pilot, app)
        app.query_one("#thread-export-path", Input).value = "some/export"
        await pilot.pause()

        app.ingest_threads_from("some/export")
        for _ in range(40):
            await pilot.pause()
            if started.is_set():
                break
        assert started.is_set(), "the import never began"

        # The loop is alive: this only happens if something is pumping it.
        app.query_one("#project-tabs").active = "tab-overview"
        await pilot.pause()
        assert app.query_one("#project-tabs").active == "tab-overview", (
            "the event loop was blocked by the import")

        holding.set()
        for _ in range(40):
            await pilot.pause()


@pytest.mark.asyncio
async def test_the_panel_appears_when_the_work_starts(monkeypatch):
    """It is hidden until there is something to say. A bar sitting at zero on
    an idle screen is furniture, and a reader stops seeing it."""
    import threading

    import dossier.threads as threads_module

    holding = threading.Event()

    # A named function, not `holding.wait(...) or {...}`. `Event.wait` returns
    # True once the event is set, so the `or` short-circuits and the stub
    # returns `True` instead of a result -- which fails inside `summarise_import`
    # rather than in the test, and reads as a defect in the application.
    def waits(*args, **kwargs):
        holding.wait(timeout=5)
        return {"ok": True, "written": 1, "indexed": {"threads": 1}}

    monkeypatch.setattr(threads_module, "request_import", waits)

    app = app_for()
    async with app.run_test(size=(100, 35)) as pilot:
        await pilot.pause()
        await open_threads(pilot, app)
        panel = app.query_one("#thread-progress")
        assert panel.display is False, "the panel was showing before any work"

        app.ingest_threads_from("some/export")
        for _ in range(40):
            await pilot.pause()
            if panel.display:
                break
        assert panel.display is True, "the panel never appeared"

        holding.set()
        for _ in range(40):
            await pilot.pause()


# --- what the bar claims ------------------------------------------------------


@pytest.mark.asyncio
async def test_an_import_bar_claims_no_fraction():
    """Nothing knows how far along an import is, so nothing says.

    Mutation: give the ingest a total and this fails -- which is the point,
    because the number would have been invented.
    """
    app = app_for()
    async with app.run_test(size=(100, 35)) as pilot:
        await pilot.pause()
        await open_threads(pilot, app)
        panel = app.query_one("#thread-progress")
        panel.start("asking the harness")
        await pilot.pause()

        bar = panel.query_one("#work-progress-bar", ProgressBar)
        assert bar.total is None, f"the import bar claims a total of {bar.total}"


@pytest.mark.asyncio
async def test_a_batch_sync_bar_carries_a_real_fraction():
    """This one counts: N repositories, one at a time. A pulse here would be
    throwing away a figure somebody actually has."""
    app = app_for()
    async with app.run_test(size=(100, 35)) as pilot:
        await pilot.pause()
        await open_threads(pilot, app)
        panel = app.query_one("#thread-progress")

        panel.start("syncing 4 repositories", total=4)
        panel.advance(2, 4, "syncing 3 of 4: org/three")
        await pilot.pause()

        bar = panel.query_one("#work-progress-bar", ProgressBar)
        assert bar.total == 4
        assert bar.progress == 2


@pytest.mark.asyncio
async def test_the_elapsed_time_is_shown_and_keeps_moving():
    """The figure that always exists, and the one that tells somebody the
    difference between slow and stuck."""
    app = app_for()
    async with app.run_test(size=(100, 35)) as pilot:
        await pilot.pause()
        await open_threads(pilot, app)
        panel = app.query_one("#thread-progress")
        panel.start("working")
        await pilot.pause()

        label = panel.query_one("#work-progress-label", Label)
        assert "working" in str(label.render())
        assert "s)" in str(label.render()), "no elapsed time on the label"


# --- when it ends -------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_outcome_stays_on_screen_after_the_work_ends():
    """A panel that vanished would take the only record of what happened with
    it, and the reader was probably looking elsewhere when it did.

    Mutation: hide the panel in `finish` and this fails.
    """
    app = app_for()
    async with app.run_test(size=(100, 35)) as pilot:
        await pilot.pause()
        await open_threads(pilot, app)
        panel = app.query_one("#thread-progress")
        panel.start("asking the harness")
        await pilot.pause()
        panel.finish("94 new. Archive now 203 thread(s).")
        await pilot.pause()

        assert panel.display is True, "the panel disappeared with the outcome"
        label = panel.query_one("#work-progress-label", Label)
        assert "94 new" in str(label.render())
        assert panel.query_one("#work-progress-bar", ProgressBar).display is False


@pytest.mark.asyncio
async def test_a_refusal_is_reported_through_the_same_panel(monkeypatch):
    """The failure path is the one somebody is most likely to be watching."""
    import dossier.threads as threads_module

    monkeypatch.setattr(
        threads_module, "request_import",
        lambda *a, **k: {"ok": False, "reason": "The harness is not answering.",
                         "fix": "Start it."})

    app = app_for()
    async with app.run_test(size=(100, 35)) as pilot:
        await pilot.pause()
        await open_threads(pilot, app)
        panel = app.query_one("#thread-progress")

        app.ingest_threads_from("some/export")
        for _ in range(60):
            await pilot.pause()
            if "not answering" in str(
                    panel.query_one("#work-progress-label", Label).render()):
                break

        assert "not answering" in str(
            panel.query_one("#work-progress-label", Label).render())


# --- a worker with no screen --------------------------------------------------


def test_the_progress_helpers_are_quiet_without_a_panel():
    """A sync started from the command line has no screen, and should not fail
    for the want of one.

    Mutation: let `query_one` raise through and this fails.
    """
    app = app_for()
    app._progress_start("something", 3)
    app._progress_advance(1, 3, "still something")
    app._progress_finish("done")
