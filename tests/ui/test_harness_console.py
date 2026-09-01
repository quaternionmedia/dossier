"""The Harness tab is a live console: it monitors the harness and answers it,
both from that one screen.

The client is mocked here so the tests never reach a real harness -- what is
under test is the tab wiring: status and the waiting question rendered from a
reading, and a typed answer sent to the request that is waiting.
"""

from __future__ import annotations

import pytest
from sqlmodel import Session, SQLModel, create_engine
from textual.widgets import Input, Static

from dossier.human import Ask, Monitor, Reading


def _app():
    from dossier.tui.app import DossierApp
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    return DossierApp(session_factory=lambda: Session(engine))


@pytest.mark.asyncio
async def test_the_tab_shows_the_status_and_the_waiting_question():
    app = _app()
    app._refresh_harness_live = lambda: None
    async with app.run_test(size=(160, 50)) as pilot:
        await pilot.pause()
        app._activate_tab("tab-harness")
        await pilot.pause()
        app._harness_live_drawn(
            Monitor(reachable=True, total=3, running=1,
                    by_status=(("running", 1), ("success", 2))),
            Reading(asks=(Ask(id="r1", prompt="Approve the release?",
                              options=("yes", "no")),), shown=1, total=1))
        await pilot.pause()
        assert "reachable" in str(app.query_one("#harness-status", Static).render())
        assert "3 invocation" in str(app.query_one("#harness-status", Static).render())
        assert "Approve the release?" in str(
            app.query_one("#harness-question", Static).render())
        assert app._harness_request == "r1"


@pytest.mark.asyncio
async def test_an_unreachable_harness_says_so_and_holds_no_request():
    app = _app()
    app._refresh_harness_live = lambda: None
    async with app.run_test(size=(160, 50)) as pilot:
        await pilot.pause()
        app._activate_tab("tab-harness")
        await pilot.pause()
        app._harness_live_drawn(Monitor(reachable=False, problem="nothing answering"),
                                Reading(problem="nothing answering"))
        await pilot.pause()
        assert "unreachable" in str(app.query_one("#harness-status", Static).render())
        assert app._harness_request is None


@pytest.mark.asyncio
async def test_typing_an_answer_sends_it_to_the_waiting_request():
    app = _app()
    app._refresh_harness_live = lambda: None
    sent: list[tuple] = []
    app._answer_harness = lambda rid, text, by: sent.append((rid, text, by))
    app._harness_answerer = lambda: "Ada Lovelace"
    async with app.run_test(size=(160, 50)) as pilot:
        await pilot.pause()
        app._activate_tab("tab-harness")
        await pilot.pause()
        app._harness_live_drawn(Monitor(reachable=True),
                                Reading(asks=(Ask(id="r1", prompt="Approve?"),)))
        await pilot.pause()
        field = app.query_one("#harness-answer", Input)
        field.focus()
        field.value = "yes, ship it"
        await pilot.press("enter")
        await pilot.pause()
    assert sent == [("r1", "yes, ship it", "Ada Lovelace")]


@pytest.mark.asyncio
async def test_an_answer_with_no_waiting_request_is_refused():
    app = _app()
    app._refresh_harness_live = lambda: None
    sent: list = []
    app._answer_harness = lambda *a: sent.append(a)
    app._harness_answerer = lambda: "Ada"
    async with app.run_test(size=(160, 50)) as pilot:
        await pilot.pause()
        app._activate_tab("tab-harness")
        await pilot.pause()
        app._harness_request = None
        field = app.query_one("#harness-answer", Input)
        field.focus()
        field.value = "hello?"
        await pilot.press("enter")
        await pilot.pause()
    assert sent == [], "answered when nothing was waiting"
