"""`6.2` -- making the view on screen current.

Nothing here reaches the network: `run_sync_batch` is replaced, and what is
asserted is which repositories it was handed. The point of the feature is the
choosing, not the fetching.

THE GAP THIS CLOSES. `action_sync` (the `s` key) refuses without a selected
repository -- right for a command about repositories, wrong for one about the
view, because the org overview is the view most often stale and the one with
nothing selected.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlmodel import Session, SQLModel, create_engine

from dossier.models.schemas import Project

NOW = datetime.now(timezone.utc)


class Intent:
    """Just enough of a committed intent for the dispatcher."""

    def __init__(self, action):
        self.action = action
        self.ipa = 3


@pytest.fixture()
def session():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


class Borrowed:
    def __init__(self, session):
        self._session = session

    def __enter__(self):
        return self._session

    def __exit__(self, *exc):
        return False


def add(session, name, *, owner="org", days_ago=None):
    synced = None if days_ago is None else NOW - timedelta(days=days_ago)
    project = Project(name=name, full_name=name, github_owner=owner,
                      github_repo=name.split("/")[-1],
                      description="a repository", github_language="Python",
                      last_synced_at=synced)
    session.add(project)
    session.commit()
    session.refresh(project)
    return project


def app_for(session):
    from dossier.tui.app import DossierApp

    return DossierApp(session_factory=lambda: Borrowed(session))


class Recorder:
    """Stands in for the sync worker and remembers what it was handed."""

    def __init__(self):
        self.batches = []

    def __call__(self, projects):
        self.batches.append([p.full_name or p.name for p in projects])

    @property
    def synced(self):
        return [name for batch in self.batches for name in batch]


# --- the gap ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sync_works_with_nothing_selected(session, monkeypatch):
    """THE ONE THAT MATTERS.

    The org overview has no selected repository, and it is the view most likely
    to be stale. `action_sync` says "Select a project to sync" here; `6.2` does
    the work.

    AND THE SELECTION IS IGNORED WHILE THE OVERVIEW IS SHOWING. The app selects
    the first repository on mount, so there is always a selection -- reading it
    here would scope the organisation's refresh to one repository nobody chose,
    which is the same bug wearing the opposite coat.

    Mutation: route `project.sync` to `action_sync`, or scope on
    `_current_project` regardless of tab, and this fails.
    """
    add(session, "org/one", days_ago=90)
    add(session, "org/two", days_ago=200)

    app = app_for(session)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        recorder = Recorder()
        monkeypatch.setattr(app, "run_sync_batch", recorder)
        assert app.query_one("#project-tabs").active == "tab-overview"
        assert app._current_project is not None, (
            "the app selects one on mount, so this test would prove nothing "
            "about ignoring the selection if it did not")

        app._apply_rad_intent(Intent("project.sync"))
        await pilot.pause()

    assert sorted(recorder.synced) == ["org/one", "org/two"]


@pytest.mark.asyncio
async def test_a_selected_repository_narrows_the_sync_to_it(session, monkeypatch):
    """On a repository tab the selection is the subject, so a refresh asked for
    from that screen means that one and not its neighbours.

    The tab has to be switched away from the overview for this to mean
    anything: the overview is an org view whatever is selected behind it, which
    the test above is about.
    """
    add(session, "org/one", days_ago=90)
    chosen = add(session, "org/two", days_ago=90)

    app = app_for(session)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        recorder = Recorder()
        monkeypatch.setattr(app, "run_sync_batch", recorder)
        app.query_one("#project-tabs").active = "tab-languages"
        app._current_project = chosen
        await pilot.pause()

        app._apply_rad_intent(Intent("project.sync"))
        await pilot.pause()

    assert recorder.synced == ["org/two"]


# --- what it does not do ------------------------------------------------------


@pytest.mark.asyncio
async def test_a_current_view_is_not_refetched(session, monkeypatch):
    """The cheapest sync is the one that does not run. A key that fetches a
    hundred repositories because a person wanted reassurance is a key people
    learn not to press.

    Mutation: drop the `is_current` branch and this fails.
    """
    add(session, "org/one", days_ago=1)
    add(session, "org/two", days_ago=2)

    app = app_for(session)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        recorder = Recorder()
        monkeypatch.setattr(app, "run_sync_batch", recorder)

        app._apply_rad_intent(Intent("project.sync"))
        await pilot.pause()

    assert recorder.batches == [], "nothing was stale, so nothing was fetched"


@pytest.mark.asyncio
async def test_a_fresh_repository_is_left_alone_when_a_stale_one_is_fetched(
        session, monkeypatch):
    """A refresh touches what is wrong with the view, not everything in it."""
    add(session, "org/fresh", days_ago=1)
    add(session, "org/stale", days_ago=90)

    app = app_for(session)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        recorder = Recorder()
        monkeypatch.setattr(app, "run_sync_batch", recorder)

        app._apply_rad_intent(Intent("project.sync"))
        await pilot.pause()

    assert recorder.synced == ["org/stale"]


# --- the second press ---------------------------------------------------------


@pytest.mark.asyncio
async def test_a_large_fetch_asks_before_it_runs(session, monkeypatch):
    """A hundred requests off two keystrokes is a thing somebody should have
    meant. Repeating the route is the cheapest possible way to mean it, and it
    keeps the feature two keys for the case that is actually common.

    Mutation: sync on the first press regardless of size and this fails.
    """
    from dossier.tui.app import DossierApp

    for index in range(DossierApp.SYNC_WITHOUT_CONFIRMING + 2):
        add(session, f"org/repo-{index}", days_ago=90)

    app = app_for(session)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        recorder = Recorder()
        monkeypatch.setattr(app, "run_sync_batch", recorder)

        app._apply_rad_intent(Intent("project.sync"))
        await pilot.pause()
        assert recorder.batches == [], "asked first"

        app._apply_rad_intent(Intent("project.sync"))
        await pilot.pause()
        assert len(recorder.synced) == DossierApp.SYNC_WITHOUT_CONFIRMING + 2


@pytest.mark.asyncio
async def test_a_small_fetch_does_not_ask(session, monkeypatch):
    """The common case stays two keys. A confirmation on every sync is a
    confirmation people learn to press through without reading."""
    add(session, "org/one", days_ago=90)

    app = app_for(session)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        recorder = Recorder()
        monkeypatch.setattr(app, "run_sync_batch", recorder)

        app._apply_rad_intent(Intent("project.sync"))
        await pilot.pause()

    assert recorder.synced == ["org/one"], "no second press needed"


@pytest.mark.asyncio
async def test_doing_something_else_cancels_a_pending_confirmation(
        session, monkeypatch):
    """A confirmation that survives a trip through another menu is one that
    fires on a keystroke a person had stopped thinking about.

    Mutation: leave `_sync_pending` set in the other branches and this fails.
    """
    from dossier.tui.app import DossierApp

    for index in range(DossierApp.SYNC_WITHOUT_CONFIRMING + 2):
        add(session, f"org/repo-{index}", days_ago=90)

    app = app_for(session)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        recorder = Recorder()
        monkeypatch.setattr(app, "run_sync_batch", recorder)

        app._apply_rad_intent(Intent("project.sync"))       # asks
        app._apply_rad_intent(Intent("view.overview"))      # somewhere else
        app._apply_rad_intent(Intent("project.sync"))       # asks again
        await pilot.pause()

    assert recorder.batches == [], "the second sync press asked rather than ran"


# --- views a sync does not feed -----------------------------------------------


@pytest.mark.asyncio
async def test_a_view_a_sync_does_not_feed_says_what_does(session, monkeypatch):
    """Deltas arrive by ingest. Fetching GitHub would not change that tab, and
    reporting "nothing to do" would imply it was current."""
    add(session, "org/one", days_ago=90)

    app = app_for(session)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        recorder = Recorder()
        monkeypatch.setattr(app, "run_sync_batch", recorder)
        app.query_one("#project-tabs").active = "tab-deltas"
        await pilot.pause()

        plan = app.sync_plan()
        assert plan.inapplicable is not None

        app._apply_rad_intent(Intent("project.sync"))
        await pilot.pause()

    assert recorder.batches == []


# --- the palette and the dispatch agree ---------------------------------------


def test_the_sync_wedge_is_marked_wired():
    """`applied_by` is what the command sheet renders. A wedge this app handles
    and the sheet calls unwired sends a reader looking for a bug that is not
    there."""
    from dossier.rad.index import applied_by
    from dossier.tui.app import DossierApp

    marked = {c.number: handled
              for c, handled in applied_by(DossierApp.RAD_HANDLED)}
    assert marked["6.2"] is True


def test_every_handled_action_exists_in_the_palette():
    """The other direction: an action the app dispatches that no wedge names is
    dead code the sheet will never mention.

    Mutation: add a typo'd action to `RAD_HANDLED` and this fails.
    """
    from dossier.rad.index import index
    from dossier.tui.app import DossierApp

    named = {c.action for c in index() if c.action}
    assert DossierApp.RAD_HANDLED <= named, (
        f"dispatched but not in the palette: {DossierApp.RAD_HANDLED - named}")
