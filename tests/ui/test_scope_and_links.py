"""The org as a scope, and the route between the two axes of the screen.

These drive the widgets rather than calling the handlers. The previous test of
this behaviour posted the selection message itself, so it passed while a click
on the same node only collapsed it -- the handler was right and nothing reached
it.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlmodel import Session, SQLModel, create_engine
from textual.widgets import DataTable, Tree

from dossier.facets import BY_TAB, FACETS
from dossier.models.schemas import (
    Project,
    ProjectContributor,
    ProjectLanguage,
    ProjectPullRequest,
)
from dossier.tui.overview_panel import OverviewPanel

NOW = datetime(2026, 8, 18, tzinfo=timezone.utc)


@pytest.fixture()
def session():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        one = Project(name="org/one", full_name="org/one", github_owner="org",
                      description="first", github_language="Python",
                      last_synced_at=NOW)
        two = Project(name="org/two", full_name="org/two", github_owner="org",
                      description="second", github_language="Rust",
                      last_synced_at=NOW)
        s.add_all([one, two])
        s.commit()
        s.refresh(one)
        s.refresh(two)
        s.add_all([
            ProjectLanguage(project_id=one.id, language="Python",
                            bytes_count=2_000_000, percentage=100.0),
            ProjectLanguage(project_id=two.id, language="Rust",
                            bytes_count=1_000_000, percentage=100.0),
            ProjectContributor(project_id=one.id, username="ada", contributions=5),
            ProjectPullRequest(project_id=one.id, pr_number=3, title="A change",
                               state="open", head_branch="feat/x"),
        ])
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


def org_node(app):
    tree = app.query_one("#project-tree", Tree)
    return next(n for n in tree.root.children
                if n.data and n.data.get("type") == "group")


# --- the org is a selectable thing -------------------------------------------


@pytest.mark.asyncio
async def test_selecting_the_owner_does_not_collapse_it(session):
    """Textual's `auto_expand` toggles a node when it is selected, so choosing
    an owner hid its repositories and read as nothing happening."""
    app = app_for(session)
    async with app.run_test(size=(160, 50)) as pilot:
        await pilot.pause()
        tree = app.query_one("#project-tree", Tree)
        node = org_node(app)
        node.expand()
        was_expanded = node.is_expanded
        tree.focus()
        tree.cursor_line = node.line
        await pilot.press("enter")
        await pilot.pause()
        assert was_expanded and node.is_expanded, "selecting collapsed the owner"


@pytest.mark.asyncio
async def test_selecting_the_owner_scopes_the_whole_screen(session):
    """An owner is a scope, not a heading: the tabs follow it."""
    app = app_for(session)
    async with app.run_test(size=(160, 50)) as pilot:
        await pilot.pause()
        # Start somewhere else: the app opens on the overview, so asserting it
        # is active afterwards would pass whether or not selecting did anything.
        app._activate_tab("tab-languages")
        await pilot.pause()
        assert app.query_one("#project-tabs").active == "tab-languages"

        tree = app.query_one("#project-tree", Tree)
        node = org_node(app)
        tree.focus()
        tree.cursor_line = node.line
        await pilot.press("enter")
        await pilot.pause()
        assert app._scope_owner == "org"
        assert app._current_project is None, "the org replaced the project selection"
        assert app.query_one(OverviewPanel).owner == "org"
        assert app.query_one("#project-tabs").active == "tab-overview"


@pytest.mark.asyncio
async def test_a_facet_tab_reads_the_org_when_the_org_is_selected(session):
    """The same tab, the same facet, a wider scope."""
    app = app_for(session)
    async with app.run_test(size=(160, 50)) as pilot:
        await pilot.pause()
        tree = app.query_one("#project-tree", Tree)
        node = org_node(app)
        tree.focus()
        tree.cursor_line = node.line
        await pilot.press("enter")
        await pilot.pause()
        app._load_tab_data("tab-languages")
        await pilot.pause()
        table = app.query_one("#languages-table", DataTable)
        assert table.row_count == 2, "both repositories' languages, not one's"


# --- one definition, two scopes ----------------------------------------------


def test_every_facet_names_the_same_columns_at_both_scopes(session):
    """Where a column means the same thing it is called the same thing. This
    is the property that made the two axes reconcilable at all."""
    for facet in FACETS:
        org = facet.at(session, ids=None)
        project = facet.at(session, project=session.get(Project, 1))
        shared = set(org.headers) & set(project.headers)
        assert shared, f"{facet.key}: the two scopes share no column name"


def test_every_facet_tab_exists_in_the_app():
    """A facet pointing at a tab nothing renders is a dead link."""
    from dossier.tui.app import DossierApp

    source = __import__("pathlib").Path("src/dossier/tui/app.py").read_text(
        encoding="utf-8")
    for facet in FACETS:
        assert f'id="{facet.tab}"' in source, f"{facet.key} names a tab that is not composed"
        assert f'id="{facet.table}"' in source, f"{facet.key} names a table that is not composed"
    assert set(BY_TAB) <= {f.tab for f in FACETS}
    assert DossierApp is not None


# --- the link between the axes ------------------------------------------------


@pytest.mark.asyncio
async def test_selecting_an_overview_row_opens_the_tab_holding_its_detail(session):
    """The route between the two axes. Without it the overview and the tabs are
    two readings a person reconciles by hand."""
    app = app_for(session)
    async with app.run_test(size=(160, 60)) as pilot:
        await pilot.pause()
        panel = app.query_one(OverviewPanel)
        index = next(i for i, s in enumerate(panel.overview.sections)
                     if s.title == "Open pull requests")
        table = app.query_one(f"#overview-section-{index}", DataTable)
        table.focus()
        table.cursor_coordinate = (0, 0)
        await pilot.pause()
        # The widget's own select action -- what Enter is bound to. Pressing the
        # key here reaches the focused table only when the overview tab is the
        # visible one, which makes the test about tab visibility rather than
        # about the link.
        table.action_select_cursor()
        await pilot.pause()
        await pilot.pause()
        assert app.query_one("#project-tabs").active == "tab-prs"
        assert app.selected_project.full_name == "org/one", (
            "the row named a repository, so that repository is now selected")


def test_a_row_names_the_repository_it_belongs_to(session):
    """The link needs the repo from the row itself; parsing it back out of a
    rendered label would be a second encoding of the same fact."""
    from dossier.overview import build

    overview = build(session, owner="org")
    prs = next(s for s in overview.sections if s.title == "Open pull requests")
    assert prs.headers[0] == "repo"
    assert prs.rows[0][0] == "org/one"


def test_an_org_only_section_links_nowhere(session):
    """There is no per-repository tab holding a phase board, and sending a
    reader to one that does not answer their question is worse than no link."""
    from dossier.overview import build

    overview = build(session, owner="org")
    panel_sections = {s.title for s in overview.sections}
    assert "Deltas by phase" in panel_sections
    from dossier.facets import BY_TITLE

    assert "Deltas by phase" not in BY_TITLE
    assert "Governance posture" not in BY_TITLE
    assert "Wants attention" not in BY_TITLE
