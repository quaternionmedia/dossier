"""A row belongs to a repository, and the row is what says which.

**THE HANDLERS ASKED THE SCREEN INSTEAD OF THE ROW.** Every one of these read
`self.selected_project` — what is selected — when the question is what the row
being clicked belongs to. At one repository the two agree, so the difference
never showed. Across an organisation the table draws every repository's rows and
the answer was whichever repository happened to be chosen, so clicking a release
of `alpha` while `beta` was selected built a link to `beta`.

Then `show_org_overview` was fixed to clear the selection, and the same handlers
stopped doing anything at all rather than doing the wrong thing. Both symptoms,
one cause: the row was never asked.

**ONE OF THE SIX STILL CANNOT BE ASKED.** Issues key on `issue-{number}`, that
repository's own numbering — issue 5 exists in many of them — so the row genuinely
does not say which repository it belongs to, and that one still refuses and says
why. The other five key on database ids.
"""

from __future__ import annotations

import pytest
from sqlmodel import Session, SQLModel, create_engine, select
from textual.widgets import DataTable
from textual.widgets._data_table import RowKey

from dossier.models.schemas import (Project, ProjectBranch, ProjectLanguage,
                                    ProjectRelease)
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


def a_repository(engine, repo, owner="org"):
    with Session(engine) as session:
        project = Project(name=f"{owner}/{repo}", full_name=f"{owner}/{repo}",
                          github_owner=owner, github_repo=repo)
        session.add(project)
        session.commit()
        session.refresh(project)
        return project.id


def select_row(app, table_id, key):
    table = app.query_one(table_id, DataTable)
    table.post_message(DataTable.RowSelected(table, 0, RowKey(key)))


async def at_org_scope(app, pilot):
    app.show_org_overview("org")
    await pilot.pause()
    assert app.selected_project is None


@pytest.mark.asyncio
async def test_a_release_row_names_its_own_repository(engine):
    """THE ONE THIS EXISTS FOR.

    Two repositories, and the release belongs to the second. Nothing is
    selected, so the only place the answer can come from is the row.

    Mutation: read `self.selected_project` in the handler again and this
    fails — with nothing selected it returns, and with the wrong repository
    selected it builds the wrong link.
    """
    a_repository(engine, "alpha")
    beta = a_repository(engine, "beta")
    with Session(engine) as session:
        release = ProjectRelease(project_id=beta, tag_name="v1.0",
                                 name="v1.0", is_prerelease=False)
        session.add(release)
        session.commit()
        session.refresh(release)
        release_id = release.id

    linked: list[dict] = []
    app = DossierApp(session_factory=Factory(engine))
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app._link_version_project = lambda payload: linked.append(payload)
        await at_org_scope(app, pilot)

        select_row(app, "#releases-table", f"release-{release_id}")
        await pilot.pause()

    assert linked, "the row was clicked and nothing happened"
    assert linked[0]["project_id"] == beta, linked[0]
    assert linked[0]["repo"] == "beta", linked[0]


@pytest.mark.asyncio
async def test_a_language_row_names_its_own_repository(engine):
    """Mutation: read the selection instead of `lang.project_id` and this
    fails."""
    a_repository(engine, "alpha")
    beta = a_repository(engine, "beta")
    with Session(engine) as session:
        lang = ProjectLanguage(project_id=beta, language="Python",
                               bytes_count=10, percentage=100.0)
        session.add(lang)
        session.commit()
        session.refresh(lang)
        lang_id = lang.id

    linked: list[dict] = []
    app = DossierApp(session_factory=Factory(engine))
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app._link_language_project = lambda payload: linked.append(payload)
        await at_org_scope(app, pilot)

        select_row(app, "#languages-table", f"lang-{lang_id}")
        await pilot.pause()

    assert linked, "the row was clicked and nothing happened"
    assert linked[0]["project_id"] == beta, linked[0]


@pytest.mark.asyncio
async def test_a_branch_row_names_its_own_repository(engine):
    """Mutation: read the selection instead of `branch.project_id` and this
    fails."""
    a_repository(engine, "alpha")
    beta = a_repository(engine, "beta")
    with Session(engine) as session:
        branch = ProjectBranch(project_id=beta, name="main",
                               commit_sha="abc1234")
        session.add(branch)
        session.commit()
        session.refresh(branch)
        branch_id = branch.id

    linked: list[dict] = []
    app = DossierApp(session_factory=Factory(engine))
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app._link_branch_project = lambda payload: linked.append(payload)
        await at_org_scope(app, pilot)

        select_row(app, "#branches-table", f"branch-{branch_id}")
        await pilot.pause()

    assert linked, "the row was clicked and nothing happened"
    assert linked[0]["project_id"] == beta, linked[0]


@pytest.mark.asyncio
async def test_the_issues_row_still_refuses_and_says_why(engine):
    """THE ONE THAT GENUINELY CANNOT.

    `issue-{number}` is that repository's numbering. Wiring it the same way
    would mean guessing, and guessing opens somebody else's issue.

    Mutation: resolve issues from the row like the others and this fails.
    """
    a_repository(engine, "alpha")

    said: list[str] = []
    app = DossierApp(session_factory=Factory(engine))
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.notify = lambda message, **kwargs: said.append(str(message))
        await at_org_scope(app, pilot)

        select_row(app, "#issues-table", "issue-5")
        await pilot.pause()

    assert said, "it went quiet again"
    assert "numbering" in said[0], said


def test_only_the_ambiguous_table_refuses():
    """A refusal left on a table that can answer is a control that looks
    designed and is a to-do.

    Mutation: refuse in any other row handler and this fails.
    """
    import re
    from pathlib import Path

    source = Path("src/dossier/tui/app.py").read_text(encoding="utf-8")
    calls = re.findall(r"_cannot_without_a_repository\('([^']+)'\)", source)
    assert calls == ["an issue"], calls


def test_the_selection_is_no_longer_read_by_the_wired_handlers():
    """The scan that would have found this in the first place.

    Mutation: put `self.selected_project` back in any of the five bodies and
    this fails.
    """
    import re
    from pathlib import Path

    source = Path("src/dossier/tui/app.py").read_text(encoding="utf-8")
    for table in ("releases", "languages", "branches", "deltas", "components"):
        at = source.index(f'def on_{table}_table_row_selected')
        nxt = re.search(r"\n    (?:@on\(|def )", source[at:])
        body = source[at:at + nxt.start()]
        # **WITHOUT THE COMMENTS, WHICH NAME THE THING THEY REPLACED.** The
        # first run of this failed on the comment explaining why the handler
        # no longer reads the selection -- a scan matching the prose that
        # forbids the thing, which this corpus has caught twice before.
        code = "\n".join(line for line in body.splitlines()
                          if not line.strip().startswith("#"))
        assert "self.selected_project" not in code, (
            f"{table} still asks the screen instead of the row")
