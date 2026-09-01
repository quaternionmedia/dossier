"""The Dossier tab's in-flight region: a repository's deltas, and the graph.

The delta-link pane is dossier's own data, so it draws with the harness down --
which is exactly the state a UI test runs in, and the reason this asserts on it
rather than on the harness-topology pane the conftest stubs out.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlmodel import Session, SQLModel, create_engine
from textual.widgets import DataTable, Static

from dossier.models.schemas import (
    DeltaLink,
    DeltaPhase,
    Project,
    ProjectDelta,
)

NOW = datetime(2026, 8, 18, tzinfo=timezone.utc)


@pytest.fixture()
def session():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        repo = Project(name="org/app", full_name="org/app", github_owner="org",
                       description="the app", github_language="Python",
                       last_synced_at=NOW)
        s.add(repo)
        s.commit()
        s.refresh(repo)
        epic = ProjectDelta(project_id=repo.id, name="epic",
                            title="A big one", phase=DeltaPhase.PLANNING,
                            updated_at=NOW)
        sub = ProjectDelta(project_id=repo.id, name="sub-task",
                           title="Part of it", phase=DeltaPhase.IMPLEMENTATION,
                           updated_at=NOW)
        lonely = ProjectDelta(project_id=repo.id, name="lonely",
                              title="No links", phase=DeltaPhase.BRAINSTORM,
                              updated_at=NOW)
        s.add_all([epic, sub, lonely])
        s.commit()
        s.refresh(epic)
        s.refresh(sub)
        # The epic nests the sub-task: a delta-to-delta link.
        s.add(DeltaLink(delta_id=epic.id, link_type="delta", target_id=sub.id))
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


@pytest.mark.asyncio
async def test_the_dossier_tab_lists_the_repositorys_deltas(session):
    """The census: every delta the repository holds, in the in-flight table."""
    app = app_for(session)
    async with app.run_test(size=(160, 60)) as pilot:
        await pilot.pause()
        project = session.get(Project, 1)
        app._current_project = project
        app._activate_tab("tab-dossier")
        await pilot.pause()
        app._load_dossier_tab(project)
        await pilot.pause()
        table = app.query_one("#dossier-deltas-table", DataTable)
        assert table.columns, "the in-flight deltas table drew no columns"
        assert table.row_count >= 3, "not every delta reached the table"


@pytest.mark.asyncio
async def test_the_delta_graph_draws_the_nesting_without_a_harness(session):
    """dossier's own reading: the epic-to-sub-task link is drawn, and the
    unlinked delta is reported as standalone rather than silently absent."""
    app = app_for(session)
    async with app.run_test(size=(160, 60)) as pilot:
        await pilot.pause()
        project = session.get(Project, 1)
        app._current_project = project
        app._activate_tab("tab-dossier")
        await pilot.pause()
        app._load_dossier_tab(project)
        await pilot.pause()
        drawing = app.query_one("#dossier-delta-graph", Static).render()
        text = getattr(drawing, "plain", str(drawing))
        assert "epic" in text and "sub-task" in text, "the nesting was not drawn"
        note = app.query_one("#dossier-delta-graph-note", Static).render()
        note_text = getattr(note, "plain", str(note))
        assert "1 delta" in note_text, "the unlinked delta was not accounted for"
