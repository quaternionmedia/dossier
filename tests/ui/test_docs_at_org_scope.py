"""Selecting an owner shows the owner's documentation, not one repository's.

**THE DOCS TAB HAS NO FACET, AND THAT IS WHY NOTHING ROUTED IT.** A facet is a
table with an org reading and a project reading, and the tab routing is built
around that; documentation is a tree, so it was never registered as one. At org
scope the tab therefore fell through to the per-project gate and returned -- and
kept whichever repository happened to be selected last.

Which is the failure worth a test: the tab was not blank. It showed one
repository's documentation under a heading that said the organisation, and there
is no way for a reader to tell that apart from the organisation having one
documented repository.
"""

from __future__ import annotations

import pytest
from sqlmodel import Session, SQLModel, create_engine
from textual.widgets import Tree

from dossier.models.schemas import DocumentSection, Project
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


def documented(engine, repo, owner, titles):
    with Session(engine) as session:
        project = Project(name=f"{owner}/{repo}", full_name=f"{owner}/{repo}",
                          github_owner=owner)
        session.add(project)
        session.commit()
        session.refresh(project)
        for order, title in enumerate(titles):
            session.add(DocumentSection(
                project_id=project.id, title=title, content=title,
                source_file="README.md", order=order,
                section_type="readme"))
        session.commit()
        return project.id


def labels(app):
    tree = app.query_one("#docs-tree", Tree)
    return [str(node.label) for node in tree.root.children]


@pytest.mark.asyncio
async def test_selecting_an_owner_shows_every_repository_that_has_docs(engine):
    """THE ONE THIS EXISTS FOR.

    Three documented repositories under one owner. The tab must name all three,
    not the one that happened to be selected.

    Mutation: drop the `tab-docs` branch from the org routing and this fails.
    """
    documented(engine, "alpha", "org", ["A one", "A two"])
    documented(engine, "beta", "org", ["B one"])
    documented(engine, "gamma", "org", ["C one", "C two", "C three"])

    app = DossierApp(session_factory=Factory(engine))
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.show_org_overview("org")
        await pilot.pause()
        app._activate_tab("tab-docs")
        app._load_tab_data("tab-docs")
        await pilot.pause()

        drawn = " ".join(labels(app))
        for repo in ("alpha", "beta", "gamma"):
            assert repo in drawn, f"{repo} is missing: {drawn}"


@pytest.mark.asyncio
async def test_each_repository_says_how_much_it_has(engine):
    """The count is what lets a reader find the documentation without opening
    a hundred nodes.

    Mutation: drop the count from the label and this fails.
    """
    documented(engine, "alpha", "org", ["one", "two", "three"])

    app = DossierApp(session_factory=Factory(engine))
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.show_org_overview("org")
        await pilot.pause()
        app._activate_tab("tab-docs")
        app._load_tab_data("tab-docs")
        await pilot.pause()

        assert any("(3)" in label for label in labels(app)), labels(app)


@pytest.mark.asyncio
async def test_the_owners_own_repository_comes_first(engine):
    """An organisation that documents itself keeps that in a repository named
    after it, and it is the page somebody scoped to the owner came for -- even
    when another repository has more sections.

    Mutation: sort by count alone and this fails.
    """
    documented(engine, "big", "org", ["a", "b", "c", "d"])
    documented(engine, "org", "org", ["the charter"])

    app = DossierApp(session_factory=Factory(engine))
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.show_org_overview("org")
        await pilot.pause()
        app._activate_tab("tab-docs")
        app._load_tab_data("tab-docs")
        await pilot.pause()

        first = labels(app)[0]
        assert "org" in first and "big" not in first, labels(app)


@pytest.mark.asyncio
async def test_an_owner_with_nothing_parsed_is_told_so(engine):
    """An empty tree is a claim that there is no documentation. Saying nothing
    has been parsed yet, and naming the command that parses, is a different
    claim and the true one.

    Mutation: return early without adding the line and this fails.
    """
    with Session(engine) as session:
        session.add(Project(name="org/bare", full_name="org/bare",
                            github_owner="org"))
        session.commit()

    app = DossierApp(session_factory=Factory(engine))
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.show_org_overview("org")
        await pilot.pause()
        app._activate_tab("tab-docs")
        app._load_tab_data("tab-docs")
        await pilot.pause()

        drawn = " ".join(labels(app))
        assert "nothing parsed" in drawn, drawn
        assert "dossier parse" in drawn, "it does not say what would fix it"


@pytest.mark.asyncio
async def test_selecting_a_repository_there_selects_it_everywhere(engine):
    """Clicking a repository in the org tree means the same thing as clicking
    it in the sidebar. A tree whose rows only expand is a dead end.

    **THROUGH THE HANDLER, NOT THE HELPER.** Calling `_select_project_by_id`
    directly passed while the feature was broken: the branch was on the project
    tree's handler and these rows are in `#docs-tree`, whose handler returned
    early whenever no project was selected -- the only state the org reading is
    ever drawn in. The rows expanded and did nothing, and the test said fine.

    Mutation: drop the `project_id` branch from the docs tree handler, or put
    it back after the selection gate, and this fails.
    """
    documented(engine, "alpha", "org", ["one"])
    project_id = documented(engine, "beta", "org", ["two", "three"])

    app = DossierApp(session_factory=Factory(engine))
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.show_org_overview("org")
        await pilot.pause()
        app._activate_tab("tab-docs")
        app._load_tab_data("tab-docs")
        await pilot.pause()

        tree = app.query_one("#docs-tree", Tree)
        row = next(node for node in tree.root.children
                   if (node.data or {}).get("project_id") == project_id)
        tree.select_node(row)
        tree.post_message(Tree.NodeSelected(row))
        await pilot.pause()
        await pilot.pause()

        assert app.selected_project is not None
        assert app.selected_project.id == project_id
        assert app._scope_owner is None, (
            "the scope stayed on the owner while a repository was selected")


def test_the_drawing_limit_is_a_drawing_limit():
    """`DOC_REPOS_DRAWN` bounds what is rendered, and the tree says when it
    stopped. A board quietly showing forty of sixty reads as sixty."""
    import re
    from pathlib import Path

    source = Path("src/dossier/tui/app.py").read_text(encoding="utf-8")
    body = source[source.index("def _load_docs_at_org"):
                  source.index("def _load_docs_tab")]
    assert "DOC_REPOS_DRAWN" in body
    assert re.search(r"more repository\(ies\)", body), (
        "nothing tells a reader the tree stopped early")
