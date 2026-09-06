"""The checklist, where somebody with an empty panel will actually meet it.

**A MODULE NOBODY CAN RUN IS NOT A FEATURE.** `diagnostics.py` shipped with a
docstring reading `dossier selfcheck`, eight checks, its own test file — and no
such command. It was five hundred lines that answered a real question and could
not be asked it, which is the same failure this repository already documented
about `dossier.topology`: "a renderer nobody could run, which reads exactly like
a finished feature".

So the checklist gets three surfaces and each is tested here: the pane at
`m 8 4 3`, the command that both docstrings promised, and the one line an empty
dossier says on startup so nobody has to already know the other two exist.
"""

from __future__ import annotations

import pytest
from sqlmodel import Session, SQLModel, create_engine
from textual.widgets import DataTable, Static

from dossier.models.schemas import Project
from dossier.tui import DossierApp


def app_for(fill=0):
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    if fill:
        with Session(engine) as session:
            for n in range(fill):
                session.add(Project(name=f"qm/r{n}", full_name=f"qm/r{n}"))
            session.commit()
    return DossierApp(session_factory=lambda: Session(engine)), engine


@pytest.fixture()
def no_token(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)


# --- the route ----------------------------------------------------------------


def test_the_checklist_has_a_route_in_the_ring():
    """THE ONE THIS EXISTS FOR.

    Registered in `views.py`, so the ring, the settings list, the command
    sheet and `docs/commands.md` all get it in one edit.

    Mutation: drop the view and this fails.
    """
    from dossier.rad.index import keystroke
    from dossier.views import BY_TAB

    view = BY_TAB["tab-setup"]
    assert view.title == "Setup"
    assert keystroke(view.action) == "m 8 4 3"


def test_the_command_the_view_names_exists():
    """**IT DID NOT, FOR THE MODULE NEXT DOOR.** `diagnostics.py` has named
    `dossier selfcheck` in its docstring since it was written, and nothing
    registered it.

    Mutation: unregister the command and this fails.
    """
    from click.testing import CliRunner

    from dossier.cli import cli
    from dossier.views import BY_TAB

    named = BY_TAB["tab-setup"].cli
    assert named == "dossier selfcheck"

    result = CliRunner().invoke(cli, ["selfcheck", "--help"])
    assert result.exit_code == 0, result.output
    assert "--inward" in result.output


def test_the_module_that_promised_the_command_can_now_be_run():
    """`diagnostics.run()` had no caller outside its own tests.

    Mutation: drop `--inward` and the inward checks go unreachable again.
    """
    import inspect

    from dossier.cli import selfcheck

    source = inspect.getsource(selfcheck.callback)
    assert "diagnostics" in source, (
        "nothing runs the repository's own diagnostics")


# --- the pane -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_pane_draws_the_checklist(no_token):
    """Every step, with the remedy column filled for the outstanding ones.

    Mutation: drop the loader and the table stays empty — which is exactly the
    failure the Conversations pane had for as long as it had no loader.
    """
    app, _ = app_for()
    async with app.run_test(size=(160, 45)) as pilot:
        await pilot.pause()
        app._load_tab_data("tab-setup")
        await pilot.pause()

        # Read inside the context manager: the app is torn down on exit,
        # and querying a dead one raises something unrelated to the claim.
        table = app.query_one("#setup-table", DataTable)
        rows = [table.get_row(key) for key in table.rows]
        columns = [str(c.label) for c in table.columns.values()]
        note = str(app.query_one("#setup-note", Static).render())

    from dossier import onboarding

    assert len(rows) == len(onboarding.STEPS), rows
    assert columns == list(onboarding.COLUMNS), columns
    assert "step(s) done" in note, note


@pytest.mark.asyncio
async def test_the_pane_loads_without_a_project_selected(no_token):
    """**THE GATE THAT BROKE THE OTHER UNSCOPED PANES.** `_load_tab_data`
    returns early when nothing is selected, and a checklist that only drew
    after you had picked a repository would be unreachable on precisely the
    installation that needs it — one with no repositories.

    Mutation: take `tab-setup` out of `unscoped` and this fails.
    """
    app, _ = app_for(fill=0)
    async with app.run_test(size=(160, 45)) as pilot:
        await pilot.pause()
        assert getattr(app, "_current_project", None) is None
        app._load_tab_data("tab-setup")
        await pilot.pause()

        rows = app.query_one("#setup-table", DataTable).row_count

    assert rows > 0, "the checklist is blank on a dossier with no projects"


@pytest.mark.asyncio
async def test_the_pane_says_what_to_press_and_reads_it_from_the_ring(no_token):
    """The remedy column carries real keystrokes, computed from the palette.

    Mutation: hardcode them and `test_no_route_is_typed_into_text_a_person_
    reads` fails.
    """
    from dossier.rad.index import keystroke

    app, _ = app_for(fill=0)
    async with app.run_test(size=(160, 45)) as pilot:
        await pilot.pause()
        app._load_tab_data("tab-setup")
        await pilot.pause()

        table = app.query_one("#setup-table", DataTable)
        cells = [str(c) for key in table.rows for c in table.get_row(key)]

    wanted = keystroke("reach.download")
    assert wanted, "the ring cannot reach the download, so this checks nothing"
    assert any(wanted in cell for cell in cells), (
        f"no row tells anybody to press {wanted}")


# --- the one line that makes it findable --------------------------------------


@pytest.mark.asyncio
async def test_an_empty_dossier_says_what_to_do_on_startup(no_token):
    """**OTHERWISE THE CHECKLIST IS ONLY FOUND BY SOMEBODY WHO KNEW IT WAS
    THERE**, and that is the one person who does not need it.

    Mutation: drop the call from `on_mount` and a first run is silent again.
    """
    app, _ = app_for(fill=0)
    said = []

    async with app.run_test(size=(140, 45)) as pilot:
        app.notify = lambda message, **kwargs: said.append(message)
        await pilot.pause()
        app._point_at_setup_if_empty()
        await pilot.pause()

    assert said, "an empty dossier said nothing"
    assert "empty" in said[0].lower()
    assert "m 8 4 3" in said[0], f"it does not say where the checklist is: {said[0]}"


@pytest.mark.asyncio
async def test_a_dossier_with_rows_in_it_stays_quiet(no_token):
    """A notification somebody learns to dismiss is one they will dismiss on
    the day it matters.

    Mutation: drop the emptiness check and this fires on every startup.
    """
    app, _ = app_for(fill=2)
    said = []

    async with app.run_test(size=(140, 45)) as pilot:
        app.notify = lambda message, **kwargs: said.append(message)
        await pilot.pause()
        app._point_at_setup_if_empty()
        await pilot.pause()

    assert said == [], said


@pytest.mark.asyncio
async def test_the_startup_line_reads_its_route_from_the_ring(no_token):
    """It names both the next step's keys and the checklist's, and neither is
    typed into the source.

    Mutation: type `m 8 4 3` into `_point_at_setup_if_empty` and
    `test_no_route_is_typed_into_text_a_person_reads` fails.
    """
    import inspect

    source = inspect.getsource(DossierApp._point_at_setup_if_empty)
    assert "keystroke(" in source
    assert "m 8 4 3" not in source


def test_a_database_it_cannot_read_does_not_raise_out_of_the_pointer(no_token):
    """A panel that cannot read its own database has a louder problem than an
    empty one, and `on_mount` is not where it gets reported.

    Called directly rather than through a running app: a table-less database
    breaks several of the dashboard's startup workers, and asserting the whole
    dashboard survives one would be asserting something it does not promise.
    What this owns is that *this* function stays quiet.

    Mutation: drop the `except` and this raises.
    """
    engine = create_engine("sqlite://")  # no tables created
    app = DossierApp(session_factory=lambda: Session(engine))
    said = []
    app.notify = lambda message, **kwargs: said.append(message)

    DossierApp._point_at_setup_if_empty(app)

    assert said == []
