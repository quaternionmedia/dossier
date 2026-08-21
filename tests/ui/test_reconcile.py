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
async def test_every_stage_is_named_while_it_is_happening(app, monkeypatch):
    """THE ONE THAT MATTERS.

    Three stages, each announced before it starts rather than after it
    finishes, so the label says what is happening now. Driving it live, stages
    two and three went past too fast to sample -- which proves nothing either
    way, so this holds the fetch open until the label has been read.

    Mutation: report only the outcome and this fails.
    """
    holding = threading.Event()
    stub(monkeypatch, on_fetch=lambda: holding.wait(timeout=5))

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

        for _ in range(200):
            await pilot.pause()
            seen.add(str(label.render()).rsplit("  (", 1)[0])
            if any("reading the archive" in s for s in seen):
                break

        assert any("rebuild its index" in s for s in seen), seen
        assert any("reading the archive" in s for s in seen), seen

        holding.set()
        for _ in range(200):
            await pilot.pause()


@pytest.mark.asyncio
async def test_the_bar_carries_a_real_fraction(app, monkeypatch):
    """The stages are known and countable, so a pulse here would be throwing
    away a figure this one actually has -- unlike an import, which cannot."""
    stub(monkeypatch)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        app._apply_rad_intent(Intent("reach.reconcile"))
        for _ in range(200):
            await pilot.pause()
        bar = app.query_one("#work-progress-bar", ProgressBar)
        assert bar.total == len(DossierApp.RECONCILE_STAGES) == 3


@pytest.mark.asyncio
async def test_the_outcome_names_what_the_archive_holds(app, monkeypatch):
    stub(monkeypatch, threads=237)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        app._apply_rad_intent(Intent("reach.reconcile"))
        label = app.query_one("#work-progress-label", Label)
        for _ in range(300):
            await pilot.pause()
            if "237" in str(label.render()):
                break
        assert "237" in str(label.render())


# --- it is not an import ------------------------------------------------------


@pytest.mark.asyncio
async def test_it_needs_no_path_to_an_export(app, monkeypatch):
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
        for _ in range(200):
            await pilot.pause()

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
