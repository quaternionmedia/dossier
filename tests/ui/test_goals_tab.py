"""The Goals tab: originating a new goal, and reading the plan it drafts.

The send crosses the seam to the planner and is a write, so these drive the
render directly -- the plan a person sees is `_goal_planned` -- rather than
standing a harness up. The client itself is tested against a mock in
`tests/core/test_harness_run.py`; the worker is stubbed for every UI test in
`conftest.py` so no test ever posts a real goal.
"""

from __future__ import annotations

import pytest
from sqlmodel import Session, SQLModel, create_engine
from textual.widgets import Input, Static

from dossier import human
from dossier.models.schemas import Project


@pytest.fixture()
def session():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        s.add(Project(name="org/app", full_name="org/app", github_owner="org",
                      description="the app"))
        s.commit()
        yield s


class Borrowed:
    def __init__(self, session):
        self._session = session

    def __enter__(self):
        return self._session

    def __exit__(self, *exc):
        return False


def app_for(session):
    from dossier.tui.app import DossierApp

    return DossierApp(session_factory=lambda: Borrowed(session))


def _text(widget):
    rendered = widget.render()
    return getattr(rendered, "plain", str(rendered))


@pytest.mark.asyncio
async def test_a_drafted_plan_is_shown_with_its_steps(session):
    app = app_for(session)
    async with app.run_test(size=(160, 50)) as pilot:
        await pilot.pause()
        app._activate_tab("tab-goals")
        await pilot.pause()
        planned = human.Planned(
            accepted=True, goal="tidy the sweep view", invocation_id="inv-1",
            estimated=2,
            steps=(human.Step("1", "Analyze", "understand"),
                   human.Step("2", "Sequence", "order")))
        app._goal_planned(planned)
        await pilot.pause()
        plan = _text(app.query_one("#goal-plan", Static))
        assert "tidy the sweep view" in plan
        assert "Analyze" in plan and "Sequence" in plan
        status = _text(app.query_one("#goal-status", Static))
        assert "inv-1" in status
        # A finished send clears the goal for the next one.
        assert app.query_one("#goal-input", Input).value == ""


@pytest.mark.asyncio
async def test_a_refused_goal_says_why_and_draws_no_plan(session):
    app = app_for(session)
    async with app.run_test(size=(160, 50)) as pilot:
        await pilot.pause()
        app._activate_tab("tab-goals")
        await pilot.pause()
        app._goal_planned(human.Planned(accepted=False, goal="x",
                                        detail="nothing is answering"))
        await pilot.pause()
        assert "nothing is answering" in _text(app.query_one("#goal-status", Static))
        assert _text(app.query_one("#goal-plan", Static)).strip() == ""


@pytest.mark.asyncio
async def test_an_empty_goal_is_refused_before_sending(session):
    """The planner turns a goal into a plan; an empty one is a mistake, caught
    on this side so the field can show it rather than the network."""
    app = app_for(session)
    async with app.run_test(size=(160, 50)) as pilot:
        await pilot.pause()
        app._activate_tab("tab-goals")
        await pilot.pause()
        app.query_one("#goal-input", Input).value = "   "
        app._begin_send_goal()
        await pilot.pause()
        assert "needs words" in _text(app.query_one("#goal-status", Static))


@pytest.mark.asyncio
async def test_the_context_is_prefilled_from_the_selected_repo(session):
    """A goal originates from the triage base: the selected repo lands in the
    context field rather than a blank."""
    app = app_for(session)
    async with app.run_test(size=(160, 50)) as pilot:
        await pilot.pause()
        app.selected_project = session.get(Project, 1)
        app._activate_tab("tab-goals")
        await pilot.pause()
        assert "org/app" in app.query_one("#goal-context", Input).value
