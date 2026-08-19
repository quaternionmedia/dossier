"""The sidebar work board, and the fork exclusion behind the figures it sits by.

The fork tests are here because they are the same finding: a row can be real,
correctly synced and still not be the organisation's work.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlmodel import Session, SQLModel, create_engine

from dossier import overview as ov
from dossier.models.schemas import (
    DeltaPhase,
    Project,
    ProjectContributor,
    ProjectDelta,
)
from dossier.tui.delta_board import DeltaBoard, group_by_phase, label_for

NOW = datetime(2026, 8, 18, tzinfo=timezone.utc)


@pytest.fixture()
def session():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        own = Project(name="org/own", full_name="org/own", github_owner="org",
                      github_stars=5, description="ours", github_language="Python",
                      last_synced_at=NOW)
        fork = Project(name="org/fork", full_name="org/fork", github_owner="org",
                       github_stars=40_000, description="upstream's", is_fork=True,
                       github_language="Python", last_synced_at=NOW)
        s.add_all([own, fork])
        s.commit()
        s.refresh(own)
        s.refresh(fork)
        s.add_all([
            ProjectContributor(project_id=own.id, username="ada", contributions=3),
            ProjectContributor(project_id=fork.id, username="upstream", contributions=1880),
            ProjectDelta(project_id=own.id, name="pr-7", title="Add a thing",
                         phase=DeltaPhase.REVIEW, pr_number=7, updated_at=NOW),
            ProjectDelta(project_id=own.id, name="planned", title="Think about it",
                         phase=DeltaPhase.PLANNING, description="x", updated_at=NOW),
            ProjectDelta(project_id=own.id, name="done", title="Finished",
                         phase=DeltaPhase.COMPLETE, description="y", updated_at=NOW),
        ])
        s.commit()
        yield s


# --- forks -------------------------------------------------------------------


def test_a_fork_is_excluded_from_the_org_figures(session):
    """Its contributors are upstream's, and they are most of the names."""
    scoped = {c.label: c.value for c in ov.build(session, now=NOW, owner="org").masthead}
    assert scoped["repositories"] == "1"
    assert scoped["contributors"] == "1", "an upstream author is not an org contributor"
    assert scoped["stars"] == "5", "a fork's stars are upstream's"


def test_forks_can_be_asked_for(session):
    both = {c.label: c.value for c in
            ov.build(session, now=NOW, owner="org", include_forks=True).masthead}
    assert both["repositories"] == "2"
    assert both["contributors"] == "2"


def test_the_scope_line_says_forks_were_excluded(session):
    assert "forks excluded" in ov.build(session, now=NOW, owner="org").scope
    assert "forks excluded" not in ov.build(
        session, now=NOW, owner="org", include_forks=True).scope


def test_the_fork_is_kept_not_deleted(session):
    """The aggregate excludes it; the data stays."""
    from sqlmodel import select

    assert len(session.exec(select(Project)).all()) == 2


# --- the board ---------------------------------------------------------------


def test_open_phases_come_before_closed_ones(session):
    from sqlmodel import select

    grouped = group_by_phase(list(session.exec(select(ProjectDelta)).all()))
    assert [phase for phase, _ in grouped] == ["planning", "review", "complete"]


def test_a_phase_with_nothing_in_it_is_not_a_heading(session):
    from sqlmodel import select

    grouped = group_by_phase(list(session.exec(select(ProjectDelta)).all()))
    assert "brainstorm" not in [phase for phase, _ in grouped]


def test_the_label_carries_the_evidence_you_act_on():
    delta = ProjectDelta(project_id=1, name="pr-7", title="Add a thing", pr_number=7)
    assert "#7" in label_for(delta, "org/own")
    branchy = ProjectDelta(project_id=1, name="b", title="On a branch",
                           branch_name="feat/x")
    assert "feat/x" in label_for(branchy, "org/own")


@pytest.mark.asyncio
async def test_the_board_draws_the_open_deltas(session):
    from dossier.tui.app import DossierApp

    app = DossierApp(session_factory=lambda: _Borrowed(session))
    async with app.run_test(size=(160, 50)) as pilot:
        await pilot.pause()
        board = app.query_one(DeltaBoard)
        headings = [str(node.label) for node in board.root.children]
    assert any("review" in h for h in headings)
    assert any("planning" in h for h in headings)


@pytest.mark.asyncio
async def test_a_filter_that_matches_nothing_is_not_restored(session):
    """The saved state said `unsynced` and everything had since been synced,
    so the sidebar was blank and the control explaining it was two panels away."""
    from dossier.config import ViewState
    from dossier.tui.app import DossierApp

    app = DossierApp(session_factory=lambda: _Borrowed(session))
    app._config.view_state = ViewState(filter_synced=False)
    async with app.run_test(size=(160, 50)) as pilot:
        await pilot.pause()
        assert app.filter_synced is None


class _Borrowed:
    """Lends the fixture's session without letting the app close it."""

    def __init__(self, session):
        self._session = session

    def __enter__(self):
        return self._session

    def __exit__(self, *exc):
        return False


@pytest.mark.asyncio
async def test_selecting_the_owner_group_shows_that_owner_s_overview(session):
    """A category is a selectable thing. Selecting the org showed nothing
    before; a heading you can highlight and not open reads as broken."""
    from dossier.tui.app import DossierApp
    from dossier.tui.overview_panel import OverviewPanel

    app = DossierApp(session_factory=lambda: _Borrowed(session))
    async with app.run_test(size=(160, 50)) as pilot:
        await pilot.pause()
        app.show_org_overview("org")
        await pilot.pause()
        panel = app.query_one(OverviewPanel)
        assert panel.owner == "org"
        assert "owned by org" in panel.overview.scope
        assert app.query_one("#project-tabs").active == "tab-overview"


@pytest.mark.asyncio
async def test_the_owner_group_node_carries_its_owner(session):
    """Without this the handler would have to parse a display label."""
    from textual.widgets import Tree

    from dossier.tui.app import DossierApp

    app = DossierApp(session_factory=lambda: _Borrowed(session))
    async with app.run_test(size=(160, 50)) as pilot:
        await pilot.pause()
        tree = app.query_one("#project-tree", Tree)
        owners = [node.data.get("owner") for node in tree.root.children
                  if node.data and node.data.get("type") == "group"]
    assert "org" in owners


def test_forks_are_excluded_even_without_an_owner(session):
    """The question is what the organisation built, and dropping the owner
    argument must not quietly change the subject."""
    unscoped = {c.label: c.value for c in ov.build(session, now=NOW).masthead}
    assert unscoped["repositories"] == "1"
    assert unscoped["contributors"] == "1"
    assert "forks excluded" in ov.build(session, now=NOW).scope


def test_a_forks_open_pull_requests_are_not_org_work(session):
    from dossier.maintenance import deltas_from_pull_requests
    from dossier.models.schemas import Project as P, ProjectPullRequest
    from sqlmodel import select

    fork = session.exec(select(P).where(P.is_fork == True)).first()  # noqa: E712
    session.add(ProjectPullRequest(project_id=fork.id, pr_number=99,
                                   title="Bump certifi", state="open"))
    session.commit()
    assert "pr-99" not in deltas_from_pull_requests(session)


def test_fork_deltas_already_stored_are_prunable(session):
    """A database synced before the rule existed still holds them."""
    from dossier.maintenance import prune_fork_deltas
    from dossier.models.schemas import Project as P, ProjectDelta as D
    from sqlmodel import select

    fork = session.exec(select(P).where(P.is_fork == True)).first()  # noqa: E712
    session.add(D(project_id=fork.id, name="upstream-work", title="Theirs",
                  description="x"))
    session.commit()
    assert prune_fork_deltas(session, apply=True) == ["upstream-work"]
    assert prune_fork_deltas(session) == []


@pytest.mark.asyncio
async def test_the_board_does_not_show_a_forks_deltas(session):
    from dossier.models.schemas import Project as P, ProjectDelta as D
    from dossier.tui.app import DossierApp
    from sqlmodel import select

    fork = session.exec(select(P).where(P.is_fork == True)).first()  # noqa: E712
    session.add(D(project_id=fork.id, name="theirs", title="Upstream thing",
                  phase=DeltaPhase.REVIEW, description="x"))
    session.commit()

    app = DossierApp(session_factory=lambda: _Borrowed(session))
    async with app.run_test(size=(160, 50)) as pilot:
        await pilot.pause()
        board = app.query_one(DeltaBoard)
        labels = [str(leaf.label) for node in board.root.children
                  for leaf in node.children]
    assert not any("Upstream thing" in label for label in labels)
