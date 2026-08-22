"""`6.4` -- reviewing a sweep, batched.

THE TEST WORTH READING IS THE QUEUE ONE. A review screen that drew the batches
and stopped would report nine repositories as the sweep when the sweep is
twenty-four. The half a reader would not go looking for is the half that has to
be put where they start.
"""

from __future__ import annotations

import pytest
from sqlmodel import Session, SQLModel, create_engine
from textual.widgets import DataTable, Static

from dossier.models.schemas import Project, ProjectDependency
from dossier.rad.index import applied_by, by_number
from dossier.tui import DossierApp


class Intent:
    def __init__(self, action):
        self.action = action
        self.ipa = 3


# A NEW SESSION PER CALL, FROM ONE POOLED CONNECTION.
#
# The review runs in a worker thread, and SQLite refuses a connection used
# outside the thread that made it -- `sqlite3.ProgrammingError: SQLite objects
# created in a thread can only be used in that same thread`. The usual test
# helper here hands every caller the *same* session, which is fine on the event
# loop and fails the moment anything is dispatched.
#
# This mirrors what the application does: `session_factory()` makes a session
# each time. `StaticPool` plus `check_same_thread=False` keeps an in-memory
# database the same database across threads, which it otherwise would not be --
# each new connection to `sqlite://` gets its own empty one.
class Factory:
    def __init__(self, engine):
        self._engine = engine

    def __call__(self):
        return Session(self._engine)


@pytest.fixture()
def engine():
    from sqlalchemy.pool import StaticPool

    made = create_engine("sqlite://", poolclass=StaticPool,
                         connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(made)
    return made


@pytest.fixture()
def session(engine):
    with Session(engine) as s:
        yield s


def declare(session, repo, package, spec):
    from sqlmodel import select

    project = session.exec(select(Project).where(Project.name == repo)).first()
    if project is None:
        project = Project(name=repo, full_name=repo, github_owner="org")
        session.add(project)
        session.commit()
        session.refresh(project)
    session.add(ProjectDependency(project_id=project.id, name=package,
                                  version_spec=spec, source="pyproject.toml",
                                  dep_type="runtime"))
    session.commit()


def app_for(session):
    return DossierApp(session_factory=Factory(session.get_bind()))


async def settle(pilot, app, limit=400):
    for _ in range(limit):
        await pilot.pause()
        if app._sweep_review is not None:
            return True
    return False


# --- the number ---------------------------------------------------------------


def test_six_four_is_the_sweep_and_it_is_wired():
    found = by_number()["6.4"]
    assert found.action == "sweep.review"
    assert found.keys == ("m", "6", "4")
    marked = {c.number: ok for c, ok in applied_by(DossierApp.RAD_HANDLED)}
    assert marked["6.4"] is True


def test_adding_it_did_not_cost_the_menu_anything():
    """rad's budget is 1 + ceil(N/2) + 1, which is 4 for three children and 4
    for four. A fifth is the one that costs, and this is not it."""
    from dossier.rad.palette import resolve
    from dossier.rad.session import budget_for

    do = next(w for w in resolve() if w.label == "Do")
    assert len(do.children) == 4
    assert budget_for(len(do.children)) == budget_for(3)


# --- what it draws ------------------------------------------------------------


@pytest.mark.asyncio
async def test_it_opens_the_tab_and_fills_it(session):
    declare(session, "org/a", "fastapi", ">=0.100.0")
    declare(session, "org/b", "fastapi", ">=0.100.0")

    app = app_for(session)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app._apply_rad_intent(Intent("sweep.review"))
        assert await settle(pilot, app), "the review never arrived"

        assert app.query_one("#project-tabs").active == "tab-sweep"
        assert app.query_one("#sweep-table", DataTable).row_count > 0


@pytest.mark.asyncio
async def test_the_queue_is_drawn_and_counted(session):
    """THE ONE THAT MATTERS.

    A screen showing two batches and hiding fifteen waiting rows reports nine
    repositories as the sweep.

    Mutation: draw only the batches and this fails.
    """
    declare(session, "org/ready", "fastapi", ">=0.100.0")
    declare(session, "org/ahead", "fastapi", ">=9.9.9")

    app = app_for(session)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app._apply_rad_intent(Intent("sweep.review"))
        assert await settle(pilot, app)

        summary = str(app.query_one("#sweep-summary", Static).render())
        assert "waiting on a person" in summary
        assert summary.index("waiting") < summary.index("ready in")

        rows = [app.query_one("#sweep-table", DataTable).get_row(key)
                for key in app.query_one("#sweep-table", DataTable).rows]
        flattened = " ".join(str(cell) for row in rows for cell in row)
        assert "queue" in flattened
        assert "ahead" in flattened, "the queued repository is not on screen"


@pytest.mark.asyncio
async def test_a_batch_says_whether_it_is_one_approval(session):
    """Every row a person is about to approve together, and a word saying that
    is what it is. `NOT UNIFORM` is the state that must never be silent.

    **THREE REPOSITORIES, BECAUSE THE TARGET IS NOW DERIVED.** The panel used a
    constant version; it takes the furthest-ahead repository's version instead,
    so whichever repository is furthest ahead is by definition already there and
    queues rather than batching. Two repositories therefore produce one batch
    and one queued row — correct, and not what this test is about. The third is
    ahead of both, so the two below it still need two different edits.
    """
    declare(session, "org/a", "fastapi", ">=0.100.0")
    declare(session, "org/b", "fastapi", "~=0.95")
    declare(session, "org/c", "fastapi", ">=0.135.2")

    app = app_for(session)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app._apply_rad_intent(Intent("sweep.review"))
        assert await settle(pilot, app)

        # Two different edits, so two batches, each honestly one thing.
        assert len(app._sweep_review.batches) == 2
        table = app.query_one("#sweep-table", DataTable)
        flattened = " ".join(str(c) for k in table.rows for c in table.get_row(k))
        assert flattened.count("one approval") == 2
        assert "NOT UNIFORM" not in flattened


@pytest.mark.asyncio
async def test_before_any_sweep_the_tab_says_how_to_ask_for_one(session):
    """An empty table with no instruction is a screen a person leaves."""
    app = app_for(session)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.query_one("#project-tabs").active = "tab-sweep"
        app.reload_tab("tab-sweep")
        await pilot.pause()

        said = str(app.query_one("#sweep-summary", Static).render())
        assert "6 4" in said


# --- the loop keeps running ---------------------------------------------------


@pytest.mark.asyncio
async def test_the_application_responds_while_the_sweep_is_worked_out(session):
    """It reads every declared dependency and runs a worker per share. On the
    loop that is a frozen application, and the tab it just opened would not
    draw.

    Mutation: run the sweep synchronously in `_begin_sweep_review` and this
    fails.
    """
    for index in range(30):
        declare(session, f"org/r{index}", "fastapi", ">=0.100.0")

    app = app_for(session)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app._apply_rad_intent(Intent("sweep.review"))
        await pilot.pause()

        app.query_one("#project-tabs").active = "tab-overview"
        await pilot.pause()
        assert app.query_one("#project-tabs").active == "tab-overview", (
            "the event loop was blocked while the sweep was worked out")
        assert await settle(pilot, app)


@pytest.mark.asyncio
async def test_nothing_shared_is_reported_rather_than_drawn_empty(session, until):
    """One repository declaring something is not a sweep. Saying so beats an
    empty table."""
    declare(session, "org/only", "lonely-package", ">=1.0.0")

    app = app_for(session)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app._apply_rad_intent(Intent("sweep.review"))
        summary = app.query_one("#sweep-summary", Static)
        # **WAIT FOR WHAT IS ASSERTED.** The condition here was
        # `_sweep_review is not None`, which in this case never becomes true --
        # nothing is shared, so the review reports instead of producing one --
        # so the loop ran its full two hundred cycles every time.
        await until(pilot, lambda: str(summary.render()).strip())

        # Either it found nothing to sweep, or it found the lonely package and
        # said so. What it must not do is raise or draw an unexplained blank.
        said = str(summary.render())
        assert said.strip(), "the screen said nothing at all"


# --- the seam -----------------------------------------------------------------


def test_the_review_runs_without_the_harness_installed(monkeypatch):
    """The panel does not depend on the harness. A review that raised when
    `qmcp` was absent would make the seam a requirement.

    Mutation: import `qmcp.sweep` at module level and this fails wherever the
    harness is not installed.
    """
    import builtins

    from dossier.sweep import MECHANICAL, Share, Sweep
    from dossier.tui.app import _dispatch

    real_import = builtins.__import__

    def refuse(name, *args, **kwargs):
        if name.startswith("qmcp"):
            raise ImportError("no harness here")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", refuse)

    planned = Sweep(package="fastapi", to_version="0.116.0", shares=[
        Share(project="org/a", declared=">=0.100.0", manifest="pyproject.toml",
              shape=MECHANICAL, why="a manifest")])
    outcomes = _dispatch(planned, "0.116.0")

    assert len(outcomes) == 1
    assert outcomes[0].state == "done"
    assert outcomes[0].edit == ">=0.116.0"
