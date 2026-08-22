"""`4.2` -- refreshing every cache without importing anything.

THE TEST WORTH READING IS THE STAGE ONE. A refresh that reported only its
outcome would leave somebody watching a still bar for however long re-indexing
takes, with no way to tell slow from stuck.
"""

from __future__ import annotations

import threading

import pytest
from sqlmodel import Session, SQLModel, create_engine
from textual.widgets import Label, ProgressBar

from dossier.rad.index import applied_by, by_number
from dossier.tui import DossierApp


class Intent:
    def __init__(self, action):
        self.action = action
        self.ipa = 3


class Factory:
    def __init__(self, engine):
        self._engine = engine

    def __call__(self):
        return Session(self._engine)


@pytest.fixture()
def app():
    from sqlalchemy.pool import StaticPool

    engine = create_engine("sqlite://", poolclass=StaticPool,
                           connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return DossierApp(session_factory=Factory(engine))


def stub(monkeypatch, ok=True, threads=237, on_fetch=None):
    """Replace both halves of the seam. Nothing opens a socket."""
    import dossier.threads as tm

    monkeypatch.setattr(tm, "request_reindex", lambda *a, **k: (
        {"ok": True, "indexed": {"threads": threads, "diverged": 0}} if ok
        else {"ok": False, "reason": "The harness is not answering.",
              "fix": "Start it."}))

    class Archive:
        reachable = True
        indexed = True
        threads = []
        note = "as indexed."

    def fetch(*a, **k):
        if on_fetch:
            on_fetch()
        return Archive()

    monkeypatch.setattr(tm, "fetch", fetch)


# --- the number ---------------------------------------------------------------


def test_four_two_is_reconcile_and_it_is_wired():
    found = by_number()["4.2"]
    assert found.action == "reach.reconcile"
    assert found.keys == ("m", "4", "2")
    marked = {c.number: ok for c, ok in applied_by(DossierApp.RAD_HANDLED)}
    assert marked["4.2"] is True


# --- what a person watching sees ----------------------------------------------


@pytest.mark.asyncio
async def test_every_stage_is_named_while_it_is_happening(app, monkeypatch, until, drain):
    """THE ONE THAT MATTERS.

    Three stages, each announced before it starts rather than after it
    finishes, so the label says what is happening now. Driving it live, stages
    two and three went past too fast to sample -- which proves nothing either
    way, so this holds the fetch open until the label has been read.

    Mutation: report only the outcome and this fails.
    """
    holding = threading.Event()
    # The timeout is a safety net, not the plan: the test releases the event as
    # soon as it has read the labels. Five seconds meant a failing run waited
    # five, and a passing one paid for the worker to notice.
    stub(monkeypatch, on_fetch=lambda: holding.wait(timeout=2))

    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        app._apply_rad_intent(Intent("reach.reconcile"))

        label = app.query_one("#work-progress-label", Label)
        seen = set()

        # READ BEFORE THE FIRST PAUSE. `_begin_reconcile` sets stage one
        # synchronously and the worker overwrites it with stage two at the
        # first opportunity, so a loop that pauses first samples stage two and
        # concludes stage one never happened. It did; the sampling missed it.
        seen.add(str(label.render()).rsplit("  (", 1)[0])

        await until(
            pilot,
            lambda: (seen.add(str(label.render()).rsplit("  (", 1)[0]) or
                     any("reading the archive" in s for s in seen)))

        # Released before the assertions: the sampling is done, and holding
        # the worker open while pytest formats a failure message helps nobody.
        holding.set()

        assert any("rebuild its index" in s for s in seen), seen
        assert any("reading the archive" in s for s in seen), seen
        # Let the worker finish so the app tears down cleanly. Nothing is
        # asserted after this, so it is a drain and is named one.
        await drain(pilot)


@pytest.mark.asyncio
async def test_the_bar_carries_a_real_fraction(app, monkeypatch, until, drain):
    """The stages are known and countable, so a pulse here would be throwing
    away a figure this one actually has -- unlike an import, which cannot."""
    stub(monkeypatch)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        app._apply_rad_intent(Intent("reach.reconcile"))
        bar = app.query_one("#work-progress-bar", ProgressBar)
        assert await until(pilot, lambda: bar.total), "the bar never got a total"
        assert bar.total == len(DossierApp.RECONCILE_STAGES) == 3
        # **AND LET THE WORKER FINISH.** The old unconditional wait was doing
        # this by accident; once the assertion stopped waiting for it, teardown
        # raced the worker and failed on an unrelated widget. Waiting for the
        # answer and waiting for the work to end are two things.
        await drain(pilot)


@pytest.mark.asyncio
async def test_the_outcome_names_what_the_archive_holds(app, monkeypatch, until, drain):
    stub(monkeypatch, threads=237)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        app._apply_rad_intent(Intent("reach.reconcile"))
        label = app.query_one("#work-progress-label", Label)
        assert await until(pilot, lambda: "237" in str(label.render())),             f"the count never reached the label: {label.render()!r}"


# --- it is not an import ------------------------------------------------------


@pytest.mark.asyncio
async def test_it_needs_no_path_to_an_export(app, monkeypatch, quiet):
    """The whole reason this exists. Refreshing through the import route would
    need an export somebody may no longer have, and would re-unpack megabytes
    to answer a question about what is already unpacked.

    Mutation: route reconcile through `request_import` and this fails, because
    nothing supplies a path.
    """
    import dossier.threads as tm

    called = []
    monkeypatch.setattr(tm, "request_import",
                        lambda *a, **k: called.append(a) or {"ok": True})
    stub(monkeypatch)

    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        app._apply_rad_intent(Intent("reach.reconcile"))
        # **AN ABSENCE NEEDS THE WORK TO HAVE FINISHED**, and "finished" is a
        # condition the app can answer rather than a number of cycles to guess.
        assert await quiet(pilot, app), "the reconcile never finished"

    assert called == [], "reconcile imported something"


# --- when the harness is not there --------------------------------------------


@pytest.mark.asyncio
async def test_a_harness_that_is_not_answering_is_reported_on_the_panel(
        app, monkeypatch):
    """The failure path is the one somebody is most likely watching."""
    stub(monkeypatch, ok=False)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        app._apply_rad_intent(Intent("reach.reconcile"))
        label = app.query_one("#work-progress-label", Label)
        for _ in range(300):
            await pilot.pause()
            if "not answering" in str(label.render()):
                break
        assert "not answering" in str(label.render())


# --- every cache, not just the one on screen ----------------------------------


@pytest.mark.asyncio
async def test_it_clears_the_caches_of_tabs_nobody_is_looking_at(
        app, monkeypatch):
    """A refresh that only redrew the visible tab would be one a person has to
    remember the scope of.

    Mutation: drop the `_tabs_loaded.clear()` and this fails.
    """
    stub(monkeypatch)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        app._tabs_loaded = {"tab-languages", "tab-issues"}
        app._apply_rad_intent(Intent("reach.reconcile"))
        for _ in range(300):
            await pilot.pause()
            if not app._tabs_loaded - {"tab-threads"}:
                break
        assert "tab-languages" not in app._tabs_loaded
        assert "tab-issues" not in app._tabs_loaded
