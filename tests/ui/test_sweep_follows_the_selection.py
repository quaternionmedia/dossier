"""Choosing a dependency is how a person says what a sweep acts on.

**AND IT DID NOTHING AT ORG SCOPE, WHICH IS THE SCOPE A SWEEP IS FOR.**
`on_dependencies_table_row_selected` opened with `if not self.selected_project:
return`. A sweep is one change across many repositories — the reading somebody
opens it from is the organisation's, where no repository is selected — so the
row highlighted, `selected_dependency` kept whatever it held, and the review
took the widest-shared package while a reader was looking at another.

The same gate, on a different table, had already made the org documentation tree
inert. It is the shape to look for: a handler that assumes the per-repository
scope, on a surface that is drawn at both.
"""

from __future__ import annotations

import pytest
from sqlmodel import Session, SQLModel, create_engine
from textual.widgets import DataTable, Static

from dossier.models.schemas import Project, ProjectDependency
from dossier.tui.app import DossierApp


@pytest.fixture()
def engine():
    from sqlalchemy.pool import StaticPool

    made = create_engine("sqlite://", poolclass=StaticPool,
                         connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(made)
    return made


class Factory:
    def __init__(self, engine):
        self._engine = engine

    def __call__(self):
        return Session(self._engine)


def declare(engine, repo, owner, package, spec=">=1.0.0"):
    with Session(engine) as session:
        project = session.exec(
            __import__("sqlmodel").select(Project)
            .where(Project.name == f"{owner}/{repo}")).first()
        if project is None:
            project = Project(name=f"{owner}/{repo}",
                              full_name=f"{owner}/{repo}", github_owner=owner)
            session.add(project)
            session.commit()
            session.refresh(project)
        dep = ProjectDependency(project_id=project.id, name=package,
                                version_spec=spec, source="pyproject.toml",
                                dep_type="runtime")
        session.add(dep)
        session.commit()
        session.refresh(dep)
        return dep.id


async def open_dependencies_at_org(app, pilot, owner="org"):
    app.show_org_overview(owner)
    await pilot.pause()
    app._activate_tab("tab-dependencies")
    app._load_tab_data("tab-dependencies")
    await pilot.pause()


def select_row(app, table_id, key):
    table = app.query_one(table_id, DataTable)
    table.post_message(DataTable.RowSelected(table, 0, key))


@pytest.mark.asyncio
async def test_choosing_a_dependency_at_org_scope_registers(engine):
    """THE ONE THIS EXISTS FOR.

    No repository is selected, and the choice still has to take.

    Mutation: put `if not self.selected_project: return` back at the top of the
    handler and this fails.
    """
    from textual.widgets._data_table import RowKey

    dep_id = declare(engine, "alpha", "org", "httpx")
    declare(engine, "beta", "org", "httpx")

    app = DossierApp(session_factory=Factory(engine))
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await open_dependencies_at_org(app, pilot)

        assert app.selected_project is None, "the test is not at org scope"
        select_row(app, "#dependencies-table", RowKey(f"dep-{dep_id}"))
        await pilot.pause()
        await pilot.pause()

        assert app.selected_dependency == "httpx", (
            "choosing a package at org scope did nothing")


@pytest.mark.asyncio
async def test_the_sweep_tab_says_what_it_would_take(engine):
    """A person who chose a package and opened the tab was shown a keystroke
    and no sign the choice had registered — so the only way to find out what
    the sweep would act on was to run it.

    Mutation: drop the `Chosen:` line from the empty-state summary and this
    fails.
    """
    from textual.widgets._data_table import RowKey

    dep_id = declare(engine, "alpha", "org", "sqlmodel")
    declare(engine, "beta", "org", "sqlmodel")

    app = DossierApp(session_factory=Factory(engine))
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await open_dependencies_at_org(app, pilot)
        select_row(app, "#dependencies-table", RowKey(f"dep-{dep_id}"))
        await pilot.pause()
        await pilot.pause()

        app._activate_tab("tab-sweep")
        app._load_sweep_tab(None)
        await pilot.pause()

        said = str(app.query_one("#sweep-summary", Static).render())
        assert "sqlmodel" in said, said


@pytest.mark.asyncio
async def test_with_nothing_chosen_it_says_what_it_would_fall_back_to(engine):
    """A fallback that reads as a choice is how the panel came to sweep one
    package while somebody watched another.

    Mutation: drop the fallback sentence and this fails.
    """
    app = DossierApp(session_factory=Factory(engine))
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app._activate_tab("tab-sweep")
        app._load_sweep_tab(None)
        await pilot.pause()

        said = str(app.query_one("#sweep-summary", Static).render())
        assert "widest-shared" in said, said


@pytest.mark.asyncio
async def test_the_keys_it_names_are_the_ones_that_run_the_review(engine):
    """The tab told people to press the keys it had typed into itself.

    `m 8 6 6` opens this tab; `m 6 4` runs the review. Reading the route from
    the menu is what keeps those apart.

    Mutation: hardcode any keystroke in the summary and
    `test_no_route_is_typed_into_text_a_person_reads` fails; change it to the
    tab's own route and this one does.
    """
    from dossier.rad.index import keystroke

    app = DossierApp(session_factory=Factory(engine))
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app._activate_tab("tab-sweep")
        app._load_sweep_tab(None)
        await pilot.pause()

        said = str(app.query_one("#sweep-summary", Static).render())
        for key in keystroke("sweep.review").split():
            assert key in said, (said, keystroke("sweep.review"))


def test_the_interaction_layer_is_handed_its_routes(engine=None):
    """rad routes to interactions and does not own them, so the route arrives
    as an argument rather than an import.

    Mutation: import `dossier.rad` in `interaction.py` and
    `test_the_layer_works_with_rad_absent` fails; drop the parameter and this
    one does.
    """
    from dossier.interaction import from_sweep_review

    class Item:
        repo = "org/one"
        detail = "needs a person"

    class Batch:
        change = "httpx to 1.0"
        size = 1
        items = [Item()]

    class Review:
        batches = [Batch()]
        queue = []

    default = from_sweep_review(Review())
    assert default[0].route == "", "a host with no menu was given a route"

    given = from_sweep_review(Review(), route_for=lambda action: f"<{action}>")
    assert given[0].route == "<sweep.review>"


@pytest.mark.asyncio
async def test_the_intersections_panel_is_cleared_with_the_selection(engine):
    """It answers "what does changing this touch?", which has no meaning across
    an organisation -- so left alone it kept one repository's relationships on
    screen under the owner's heading.

    Found by spot-checking the panel after moving it onto the Dossier tab, and
    made visible by clearing `selected_project`: before that the panel was
    stale *and* the rest of the screen agreed with it.

    Mutation: drop the `show_for(None)` from `show_org_overview` and this
    fails.
    """
    from dossier.tui.intersections_panel import IntersectionsPanel

    declare(engine, "alpha", "org", "httpx")

    app = DossierApp(session_factory=Factory(engine))
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        with Session(engine) as session:
            project = session.exec(
                __import__("sqlmodel").select(Project)).first()
            session.expunge(project)
        app.show_project_details(project)
        await pilot.pause()
        assert app.query_one(IntersectionsPanel).project_name is not None

        app.show_org_overview("org")
        await pilot.pause()
        assert app.query_one(IntersectionsPanel).project_name is None, (
            "the panel still names a repository at org scope")


@pytest.mark.asyncio
async def test_a_row_that_cannot_be_opened_at_org_scope_says_so(engine):
    """SIX HANDLERS WENT QUIET AT ONCE, AND THE CHANGE THAT DID IT WAS A FIX.

    Clearing `selected_project` when an owner is selected is what its docstring
    always claimed. Before that these ran against whichever repository was
    chosen last -- opening the wrong repository's issue, or filing a dependency
    under a repository nobody was looking at.

    They cannot act at org scope, because the row key is that repository's own
    numbering: issue 5 exists in many of them. So they say so. A control that
    refuses and a control that is broken look identical when both do nothing.

    Mutation: return without notifying and this fails.
    """
    from textual.widgets._data_table import RowKey

    said: list[str] = []
    app = DossierApp(session_factory=Factory(engine))
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.notify = lambda message, **kwargs: said.append(str(message))
        app.show_org_overview("org")
        await pilot.pause()

        select_row(app, "#issues-table", RowKey("issue-5"))
        await pilot.pause()

    assert said, "clicking the row did nothing and said nothing"
    assert "Select a repository" in said[0], said
    assert "numbered" in said[0], "it does not say why"


@pytest.mark.asyncio
async def test_an_empty_row_still_says_nothing(engine):
    """The placeholder row is not a refusal, and a notification on it would be
    noise on every empty table.

    Mutation: notify before the `empty` check and this fails.
    """
    from textual.widgets._data_table import RowKey

    said: list[str] = []
    app = DossierApp(session_factory=Factory(engine))
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.notify = lambda message, **kwargs: said.append(str(message))
        app.show_org_overview("org")
        await pilot.pause()

        select_row(app, "#issues-table", RowKey("empty"))
        await pilot.pause()

    assert not said, said
