"""The two routes somebody needs on their first run, and their last.

**`6.1` ARCHIVE AND START OVER.** The only way back to an empty dossier was
`dossier dev reset`, which drops every table with no backup and whose entire
safety net is the words "Use with caution in production!" in a help text.

**`4.3` DOWNLOAD AN OWNER, AND READ WHAT ARRIVED.** Fetching an organisation
used to leave a board with nothing on it: the repositories land, their open
pull requests land with them, and the Deltas pane stays empty because a delta
is *derived* from a pull request by a second command nobody had a reason to
know existed.

Both read before they act, and each says so in its own way. The download asks
for a name, looks it up, and only fetches on a second press. The restart opens
with the row counts already on screen, the button carrying the number, and the
focus on Cancel -- so the reflex Enter after `m` `6` `1` abandons the dialog.

Neither reaches GitHub or drops a table in any test here.
"""

from __future__ import annotations

import pytest
from sqlmodel import Session, SQLModel, create_engine, select
from textual.widgets import Button, Input, Static

from dossier.models.schemas import Project, ProjectPullRequest
from dossier.rad.index import applied_by, by_number, keystroke
from dossier.tui import DossierApp


def app_for(engine=None):
    engine = engine or create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    return DossierApp(session_factory=lambda: Session(engine)), engine


# --- the routes ---------------------------------------------------------------


def test_six_one_is_archive_and_start_over():
    """Pinned: it is written into the command sheet and this file.

    Mutation: reorder `Do` and this fails.
    """
    found = by_number()["6.1"]
    assert found.action == "project.restart"
    assert found.path == ("Do", "Archive and start over")
    assert keystroke("project.restart") == "m 6 1"


def test_both_first_run_routes_are_wired():
    """A wedge the host does not handle is greyed out and refuses the digit.

    Mutation: drop either from `RAD_ACTIONS` and this fails.
    """
    wired = {c.action: ok for c, ok in applied_by(DossierApp.RAD_HANDLED)}
    assert wired["project.restart"], "6.1 is in the ring and does nothing"
    assert wired["reach.download"], "4.3 is in the ring and does nothing"


def test_the_seventh_child_of_do_cost_a_keystroke_and_says_so():
    """rad's budget is `1 + ceil(N/2) + 1`: six children cost 5 and seven cost
    6. A cost paid is fine; a cost paid silently is not.

    Mutation: add an eighth without a reason and the palette stops explaining
    itself.
    """
    from pathlib import Path

    from dossier.rad.palette import resolve
    from dossier.rad.session import budget_for

    do = next(w for w in resolve() if w.id == "do")
    assert len(do.children) == 7
    assert budget_for(7) == budget_for(6) + 1

    source = Path("src/dossier/rad/palette.py").read_text(encoding="utf-8")
    assert "SEVENTH" in source, "the keystroke it costs is not written down"


def test_both_have_a_command_outside_the_application():
    """An act reachable only from inside the panel cannot be scripted, and one
    reachable only from the command line is invisible to somebody in the
    panel.
    """
    from dossier.toc import ACT_ROUTES

    assert ACT_ROUTES["project.restart"] == "dossier db restart"
    assert ACT_ROUTES["reach.download"] == "dossier github download"


@pytest.mark.parametrize("argv,must_have", [
    (["db", "restart", "--help"], "--apply"),
    (["github", "download", "--help"], "--no-deltas"),
])
def test_those_commands_exist_and_can_be_asked_to_hold_back(argv, must_have):
    """Both are destructive or expensive, and both default to saying what they
    would do."""
    from click.testing import CliRunner

    from dossier.cli import cli

    result = CliRunner().invoke(cli, argv)
    assert result.exit_code == 0, result.output
    assert must_have in result.output


# --- archive and start over ---------------------------------------------------


def test_the_restart_command_archives_the_database_it_is_about_to_empty():
    """**THE DATA-LOSS PATH THIS CLOSES.**

    `DOSSIER_DATABASE_URL` moves which database the session opens.
    `dossier db backup` hardcodes `Path("dossier.db")`, and a *restart* that
    did the same would copy whichever file happened to be under the working
    directory and then drop every table in the one actually in use --
    `start_over` would see a backup, call itself safe, and empty the wrong
    database. That is `health.py`'s two-databases failure with teeth.

    Mutation: hardcode the filename again and this fails.
    """
    import inspect

    from dossier.cli import db_restart

    source = inspect.getsource(db_restart.callback)
    assert "candidate_databases" in source, (
        "the restart resolves its own database name rather than asking "
        "health.py which one is open")
    assert 'Path("dossier.db")' not in source


@pytest.mark.asyncio
async def test_the_panel_archives_the_database_its_own_session_is_bound_to(tmp_path):
    """The panel's half of the same rule, and it reads the engine rather than
    guessing: whatever the session is bound to is what gets copied, wherever
    `DOSSIER_DATABASE_URL` put it.

    Mutation: return `Path("dossier.db")` and an override archives a file in
    the working directory while the restart empties the real one.
    """
    elsewhere = tmp_path / "somewhere-else.db"
    engine = create_engine(f"sqlite:///{elsewhere}")
    SQLModel.metadata.create_all(engine)
    app = DossierApp(session_factory=lambda: Session(engine))

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        found = app.database_path()

    assert found is not None and found.resolve() == elsewhere.resolve(), found



@pytest.mark.asyncio
async def test_the_restart_dialog_counts_before_it_offers_the_button():
    """THE ONE THIS EXISTS FOR.

    The rows are shown before anything is dropped, and the button carries the
    number so the reader confirms a figure rather than a word.

    Mutation: dismiss on the first press and this fails.
    """
    app, engine = app_for()
    with Session(engine) as session:
        session.add(Project(name="qm/a", full_name="qm/a"))
        session.add(Project(name="qm/b", full_name="qm/b"))
        session.commit()

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app._begin_restart()
        await pilot.pause()

        screen = app.screen
        said = str(screen.query_one("#restart-holding", Static).render())
        label = str(screen.query_one("#delete-btn", Button).label)

    assert "2 project(s)" in said, said
    assert "drop 2 rows" in label.lower() or "drop 2" in label, label


@pytest.mark.asyncio
async def test_an_empty_dossier_disables_the_button_rather_than_arming_it():
    """There is nothing to archive and nothing to drop, and a live button that
    does nothing is worse than a dead one that says why.

    Mutation: leave it enabled and this fails.
    """
    app, _ = app_for()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app._begin_restart()
        await pilot.pause()

        screen = app.screen
        assert screen.query_one("#delete-btn", Button).disabled
        assert "nothing to archive" in str(
            screen.query_one("#restart-holding", Static).render()).lower()


@pytest.mark.asyncio
async def test_the_reflex_enter_after_the_route_cancels(monkeypatch):
    """**THE FAILURE THIS DIALOG EXISTS TO PREVENT.**

    `m` `6` `1` is three keys, and the fourth a person is most likely to press
    is Enter. Focus therefore rests on Cancel and not on the button that
    empties the dossier, so the reflex press abandons rather than acts.

    Mutation: focus the destructive button on mount and this fails.
    """
    app, engine = app_for()
    with Session(engine) as session:
        session.add(Project(name="qm/a", full_name="qm/a"))
        session.commit()

    started = []
    monkeypatch.setattr(DossierApp, "_run_restart",
                        lambda self: started.append(True))

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app._begin_restart()
        await pilot.pause()

        assert app.screen.focused.id == "cancel-btn", app.screen.focused

        await pilot.press("enter")
        await pilot.pause()

    assert started == [], "the reflex Enter emptied the dossier"


@pytest.mark.asyncio
async def test_the_plan_is_on_screen_before_the_button_can_be_pressed():
    """What is confirmed is a figure, not a word. The count and the button's
    number are one reading of the same tables `reinit` empties.

    Mutation: count only after the first press and the reader confirms blind.
    """
    app, engine = app_for()
    with Session(engine) as session:
        session.add(Project(name="qm/a", full_name="qm/a"))
        session.commit()

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app._begin_restart()
        await pilot.pause()

        screen = app.screen
        said = str(screen.query_one("#restart-holding", Static).render())
        label = str(screen.query_one("#delete-btn", Button).label)

    assert "1 project(s)" in said, said
    assert "drop 1 row" in label and "1 rows" not in label, label


@pytest.mark.asyncio
async def test_the_button_acts_once_the_plan_has_been_read(monkeypatch):
    """The deliberate press, on a button naming the number.

    Mutation: never call `_run_restart` and the route does nothing.
    """
    app, engine = app_for()
    with Session(engine) as session:
        session.add(Project(name="qm/a", full_name="qm/a"))
        session.commit()

    started = []
    monkeypatch.setattr(DossierApp, "_run_restart",
                        lambda self: started.append(True))

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app._begin_restart()
        await pilot.pause()
        app.screen.query_one("#delete-btn", Button).press()
        await pilot.pause()
        await pilot.pause()

    assert started == [True], started


@pytest.mark.asyncio
async def test_a_dossier_that_could_not_be_counted_is_not_emptied(monkeypatch):
    """`_read` stays False when the count itself failed, and the button
    retries the count rather than acting. A dossier nobody could measure is
    not one to empty.

    Mutation: act regardless of `_read` and this fails.
    """
    from dossier import restart as starting

    def refuses(session, database=None):
        raise RuntimeError("database is locked")

    monkeypatch.setattr(starting, "holding", refuses)

    app, _ = app_for()
    started = []
    monkeypatch.setattr(DossierApp, "_run_restart",
                        lambda self: started.append(True))

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app._begin_restart()
        await pilot.pause()

        screen = app.screen
        assert "database is locked" in str(
            screen.query_one("#restart-holding", Static).render())

        screen.query_one("#delete-btn", Button).press()
        await pilot.pause()

    assert started == [], "it emptied a dossier it could not count"


@pytest.mark.asyncio
async def test_cancelling_changes_nothing(monkeypatch):
    app, engine = app_for()
    with Session(engine) as session:
        session.add(Project(name="qm/a", full_name="qm/a"))
        session.commit()

    started = []
    monkeypatch.setattr(DossierApp, "_run_restart",
                        lambda self: started.append(True))

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app._begin_restart()
        await pilot.pause()
        app.screen.query_one("#cancel-btn", Button).press()
        await pilot.pause()

    assert started == []
    with Session(engine) as after:
        assert len(after.exec(select(Project)).all()) == 1


@pytest.mark.asyncio
async def test_an_in_memory_dossier_reports_no_file_to_copy():
    """None is a real answer. Reporting a path that does not exist would make
    the archive look taken.

    Mutation: return a path unconditionally and this fails.
    """
    app, _ = app_for()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert app.database_path() is None


# --- download an owner, and read what arrived ---------------------------------


def test_downloading_an_owner_derives_the_work_it_just_fetched():
    """**THE ONE THIS HALF EXISTS FOR.**

    The repositories land, their open pull requests land with them, and the
    board stayed empty because deriving a delta was a second command.

    Mutation: drop the derive stage from `onboard` and this fails.
    """
    from dossier import download as fetching
    from tests.core.test_download import FakeClient, FakeParser, FakeRepo

    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)

    class WithPRs(FakeClient):
        def get_pull_requests(self, owner, name, **kwargs):
            return [{"pr_number": 4, "title": "work in flight",
                     "state": "open", "author": "someone",
                     "head_branch": "feature", "is_draft": False}]

    with Session(engine) as session:
        done = fetching.onboard(session, FakeParser(),
                                WithPRs(repos=[FakeRepo(name="a")]),
                                "qm", delay_between_batches=0)

        assert done.report.fetched == 1
        assert done.deltas, "nothing was derived from the open pull request"
        assert len(session.exec(select(ProjectPullRequest)).all()) == 1


def test_every_stage_says_its_own_number():
    """A download of thirty repositories that derived nothing has done
    something worth seeing, and one combined figure hides which half did it.

    Mutation: report a single total and this fails.
    """
    from dossier import download as fetching
    from tests.core.test_download import FakeClient, FakeParser, FakeRepo

    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)

    said = []
    with Session(engine) as session:
        done = fetching.onboard(session, FakeParser(),
                                FakeClient(repos=[FakeRepo(name="a")]),
                                "qm", on_stage=said.append,
                                delay_between_batches=0)

    assert len(said) == 3, said
    assert "repository(ies)" in said[0]
    assert "fetched" in said[1]
    assert "pull request" in said[2]
    # No open PRs in the default fake, and that is a reading rather than a
    # step that was skipped.
    assert done.derived and not done.deltas
    assert "no work in flight" in done.summary().lower()


def test_not_deriving_is_different_from_deriving_nothing():
    """An owner whose repositories have no open pull requests really has no
    work in flight; an owner nobody looked at is a different fact.

    Mutation: report `derived` the same either way and this fails.
    """
    from dossier import download as fetching
    from tests.core.test_download import FakeClient, FakeParser, FakeRepo

    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        skipped = fetching.onboard(session, FakeParser(),
                                   FakeClient(repos=[FakeRepo(name="a")]),
                                   "qm", derive=False,
                                   delay_between_batches=0)

    assert not skipped.derived
    assert "not derived" in skipped.summary().lower()


@pytest.mark.asyncio
async def test_the_ring_route_reaches_the_onboarding_flow(monkeypatch):
    """The whole point of the route: `m 4 3`, a name, and the board fills.

    Mutation: point `_run_owner_download` back at `download_owner` and this
    fails, because that one never derives.
    """
    import inspect

    source = inspect.getsource(DossierApp._run_owner_download)
    assert "onboard" in source, (
        "the ring's download does not derive the work it fetched")
    assert "tab-deltas" in source, (
        "it fills the board and never tells the board to redraw")
