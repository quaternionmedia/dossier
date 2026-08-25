"""What the dashboard notices carries what would settle it.

**A ROUTE SAYS WHERE TO GO; A REMEDY SAYS WHAT TO RUN.** The dashboard had only
the first. A repository listed as never synced told a person it wanted attention
and left them to work out that syncing was the answer, and where syncing lives —
for every row, every time.

And the three things wanting a person lived on three screens, each phrased as an
observation: harness questions on Waiting, stale repositories on the overview,
failed invocations on Harness. One reading now, with the source named, so a
person can tell what put a row in front of them.

**EMPTY IS A REAL REMEDY AND THE COMMON ONE.** A question a harness put to a
person has none by construction: the answer *is* the act, and it goes back
across the seam the way it came. A harness error has none either — re-running
somebody else's tool is not this application's to decide, and what an error
suggests depends entirely on what it says.
"""

from __future__ import annotations

import pytest

from dossier import interaction, naming


class Row:
    def __init__(self, **kw):
        for key, value in kw.items():
            setattr(self, key, value)


# --- which rows are repositories ---------------------------------------------


def test_a_delta_address_is_not_a_repository():
    """THE ONE THIS EXISTS FOR.

    Four rows in `project` are addresses inside a repository, carrying the
    owner and repo of the repository they belong to — so those fields alone
    cannot tell the two apart.

    Mutation: return True whenever `github_repo` is set and this fails.
    """
    delta = Row(name="quaternionmedia/qm/delta/pr-57",
                full_name="quaternionmedia/qm/delta/pr-57",
                github_owner="quaternionmedia", github_repo="qm")
    repo = Row(name="quaternionmedia/qm", full_name="quaternionmedia/qm",
               github_owner="quaternionmedia", github_repo="qm")

    assert naming.is_a_repository(repo)
    assert not naming.is_a_repository(delta)
    # Both still name the repository they belong to.
    assert naming.repository_of(delta) == ("quaternionmedia/qm", "qm")


def test_a_plain_owner_slash_name_is_a_repository():
    plain = Row(name="org/one", full_name="org/one",
                github_owner=None, github_repo=None)
    assert naming.is_a_repository(plain)


def test_a_row_naming_nothing_is_not_one():
    assert not naming.is_a_repository(Row(name="", full_name=""))
    assert not naming.is_a_repository(Row(name="a/b/c/d", full_name="a/b/c/d"))


def test_the_clone_command_asks_the_same_question():
    """It had its own copy, and the two disagreed: a delta address was skipped
    by one and recommended for syncing by the other, from the same four rows.

    Mutation: give `clone.py` its own `repository_of` again and this fails.
    """
    from dossier import clone

    assert clone.repository_of is naming.repository_of


# --- the remedy --------------------------------------------------------------


def test_an_attention_row_carries_the_act_that_settles_it():
    """THE OTHER ONE THIS EXISTS FOR.

    Mutation: drop `remedy` from `from_attention` and this fails.
    """
    rows = [("org/one", "never", "never synced, no description")]
    found = interaction.from_attention(rows)

    assert len(found) == 1
    assert found[0].remedy == "project.sync"
    assert found[0].can_be_run


def test_every_reason_the_attention_list_gives_is_one_sync():
    """A repository with no description and no language is not three problems.
    It is one repository nobody has read from GitHub lately, and a table
    mapping each reason to its own remedy would imply otherwise.

    Mutation: give any reason a different remedy and this fails.
    """
    for reason in interaction.WANTS_A_SYNC:
        found = interaction.from_attention([("org/one", "never", reason)])
        assert found[0].remedy == "project.sync", reason


def test_a_reason_nothing_settles_carries_no_remedy():
    """Filling this in with something plausible would be the panel deciding
    what somebody meant.

    Mutation: default the remedy to `project.sync` and this fails.
    """
    found = interaction.from_attention([("org/one", "never", "is on fire")])
    assert found[0].remedy == ""
    assert not found[0].can_be_run


def test_a_harness_question_has_no_remedy():
    """The answer *is* the act, and it goes back across the seam the way it
    came."""
    asks = [Row(id=1, project="org/one", address="org/one/ask/1",
                prompt="which one?", options="a\\nb", answered_with=None,
                asked_at="2026-01-01")]
    found = interaction.from_harness_asks(asks)
    assert found and all(not one.can_be_run for one in found)


# --- harness errors ----------------------------------------------------------


def test_an_error_is_carried_and_not_classified():
    """The harness wrote what went wrong. Reading that into a category here
    would be this panel guessing at another system's failure, and the guess is
    what a person would then debug.

    Mutation: replace `detail` with a category and this fails.
    """
    rows = [Row(id=7, harness="qmcp", tool="search",
                error="ConnectionRefusedError: [Errno 61] port 3141\\nstack...")]
    found = interaction.from_harness_errors(rows)

    assert len(found) == 1
    assert "ConnectionRefused" in found[0].detail
    assert found[0].source == interaction.FROM_HARNESS
    assert not found[0].can_be_run


def test_an_invocation_with_no_error_is_not_in_the_queue():
    rows = [Row(id=1, harness="qmcp", tool="search", error=None)]
    assert interaction.from_harness_errors(rows) == []


# --- the reading -------------------------------------------------------------


def test_the_waiting_reading_names_what_would_settle_each_row():
    """Mutation: drop the remedy column and this fails."""
    from dossier import facets

    assert facets.WAITING_COLUMNS[-1] == "what would settle it"
    assert "from" in facets.WAITING_COLUMNS


def test_a_source_that_raises_takes_out_its_own_rows_and_not_the_reading():
    """An unreachable harness used to be an empty queue, which reads as nothing
    outstanding.

    Mutation: query the sources inline instead of through `gather` and one
    failure empties the reading.
    """
    def fine():
        return [interaction.Interaction(id="a", kind=interaction.DECIDE,
                                        prompt="p", source="ok")]

    def broken():
        raise ConnectionError("no harness here")

    queue = interaction.gather({"ok": fine, "harness": broken})

    assert [one.id for one in queue.items] == ["a"]
    assert "harness" in queue.unreachable


# --- running it --------------------------------------------------------------


@pytest.mark.asyncio
async def test_choosing_a_row_runs_its_remedy():
    """THE POINT OF THE COLUMN.

    The dashboard has always been able to say a repository had not been read in
    seven months. Acting on it meant knowing syncing was the answer, finding
    where syncing lives, and doing it — per row.

    Mutation: drop the `#waiting-table` handler and this fails.
    """
    from sqlalchemy.pool import StaticPool
    from sqlmodel import Session, SQLModel, create_engine
    from textual.widgets import DataTable
    from textual.widgets._data_table import RowKey

    from dossier import facets
    from dossier.tui.app import DossierApp

    engine = create_engine("sqlite://", poolclass=StaticPool,
                           connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)

    ran: list[str] = []
    app = DossierApp(session_factory=lambda: Session(engine))
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app._apply_rad_intent = lambda intent: ran.append(intent.action)

        table = app.query_one("#waiting-table", DataTable)
        table.clear(columns=True)
        table.add_columns(*facets.WAITING_COLUMNS)
        table.add_row("overview", "org/one: never synced", "never",
                      "project.sync", key="row-0")
        facets.remedies_shown(("project.sync",))

        table.post_message(DataTable.RowSelected(table, 0, RowKey("row-0")))
        await pilot.pause()

    assert ran == ["project.sync"], ran


@pytest.mark.asyncio
async def test_a_row_with_no_remedy_says_so_rather_than_doing_nothing():
    """A control that refuses and a control that is broken look identical when
    both are silent.

    Mutation: return without notifying and this fails.
    """
    from sqlalchemy.pool import StaticPool
    from sqlmodel import Session, SQLModel, create_engine
    from textual.widgets import DataTable
    from textual.widgets._data_table import RowKey

    from dossier import facets
    from dossier.tui.app import DossierApp

    engine = create_engine("sqlite://", poolclass=StaticPool,
                           connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)

    said: list[str] = []
    app = DossierApp(session_factory=lambda: Session(engine))
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.notify = lambda message, **kwargs: said.append(str(message))

        table = app.query_one("#waiting-table", DataTable)
        table.clear(columns=True)
        table.add_columns(*facets.WAITING_COLUMNS)
        table.add_row("harness", "which one?", "asked 2d", "a person",
                      key="row-0")
        facets.remedies_shown(("",))

        table.post_message(DataTable.RowSelected(table, 0, RowKey("row-0")))
        await pilot.pause()

    assert said, "the row did nothing and said nothing"
    assert "the answer is the act" in said[0], said


def test_the_attention_list_does_not_recommend_what_cannot_be_synced():
    """THE HOLE, FOUND BY MUTATING THE THING RATHER THAN THE HELPER.

    `test_a_delta_address_is_not_a_repository` checks `naming.is_a_repository`,
    and passed happily while the overview called it nowhere. Making the skip a
    no-op left every test green: the helper was right and unused.

    Four rows in the real database are delta addresses, and every one read as
    never synced with no description and no language — three reasons apiece,
    permanently, for something that has no sync to be missing.

    Mutation: make the skip in `_attention` a no-op and this fails.
    """
    from sqlalchemy.pool import StaticPool
    from sqlmodel import Session, SQLModel, create_engine

    from dossier import overview
    from dossier.models.schemas import Project

    engine = create_engine("sqlite://", poolclass=StaticPool,
                           connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    session = Session(engine)
    session.add(Project(name="org/two", full_name="org/two",
                        github_owner="org", github_repo="two"))
    session.add(Project(name="org/one/delta/pr-9",
                        full_name="org/one/delta/pr-9",
                        github_owner="org", github_repo="one"))
    session.commit()

    rows = overview.build(session, owner="org").section("Wants attention").rows
    named = [row[0] for row in rows]
    assert not any("delta" in name for name in named), named


def test_the_heading_says_what_the_rows_are():
    """**THE LABEL HAD TO FOLLOW THE CONTENT.** "Waiting on a person" was exact
    when this read harness questions alone. With the attention list in it,
    thirty-eight of thirty-eight rows were waiting on a *sync* — an act this
    panel can run — and a heading saying otherwise is the panel misdescribing
    its own rows.

    Mutation: put the old title back and this fails.
    """
    from dossier import facets

    facet = facets.BY_KEY["waiting"]
    assert facet.title == "Outstanding"
    assert "waiting on a person" not in facet.title.lower()


def test_the_note_names_all_three_sources():
    """A note describing one source, on a reading that gathers three, is the
    same misdescription one layer down.

    Mutation: leave the old note and this fails.
    """
    from sqlalchemy.pool import StaticPool
    from sqlmodel import Session, SQLModel, create_engine

    from dossier import facets

    engine = create_engine("sqlite://", poolclass=StaticPool,
                           connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        note = facets.BY_KEY["waiting"].at(session, limit=5).note

    for source in ("harness could not answer", "read lately", "failed"):
        assert source in note, (source, note)


def test_the_view_registry_says_the_same_thing_the_facet_does():
    """A fourth description of one reading, and it went stale the moment the
    reading changed — the registry still said "Questions a harness could not
    answer for itself" after two more sources had joined it.

    Mutation: revert either title and this fails.
    """
    from dossier import facets, views

    view = views.BY_TAB["tab-waiting"]
    assert view.title == facets.BY_KEY["waiting"].title
    assert "harness questions" in view.summary
    assert "read lately" in view.summary
