"""The org overview: what it counts, and what it refuses to say.

These assert on rendered content rather than on the queries, for the reason
recorded in `tests/test_rad.py`: a test that checks the mechanism can pass while
the feature is broken. Every figure here is compared against a fixture whose
rows the test itself created, so a wrong aggregate is a failure and not a
plausible-looking number.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlmodel import Session, SQLModel, create_engine

from dossier import overview as ov
from dossier.models.governance import GovernanceRepository
from dossier.models.schemas import (
    DeltaPhase,
    Project,
    ProjectContributor,
    ProjectDelta,
    ProjectDependency,
    ProjectIssue,
    ProjectLanguage,
    ProjectPullRequest,
)

NOW = datetime(2026, 8, 18, tzinfo=timezone.utc)


@pytest.fixture()
def session():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        fresh = Project(name="qm/alpha", full_name="qm/alpha", github_language="Python",
                        github_stars=10, description="a repo",
                        last_synced_at=NOW - timedelta(days=2))
        stale = Project(name="qm/beta", full_name="qm/beta", github_language="Rust",
                        github_stars=5, description="another",
                        last_synced_at=NOW - timedelta(days=90))
        never = Project(name="qm/gamma", full_name="qm/gamma")
        s.add_all([fresh, stale, never])
        s.commit()
        for p in (fresh, stale, never):
            s.refresh(p)

        s.add_all([
            ProjectPullRequest(project_id=fresh.id, pr_number=1, title="one", state="open"),
            ProjectPullRequest(project_id=fresh.id, pr_number=2, title="two", state="closed"),
            ProjectIssue(project_id=fresh.id, issue_number=3, title="bug", state="open"),
            ProjectLanguage(project_id=fresh.id, language="Python", bytes_count=3_000_000),
            ProjectLanguage(project_id=stale.id, language="Rust", bytes_count=1_000_000),
            ProjectContributor(project_id=fresh.id, username="ada", contributions=40),
            ProjectContributor(project_id=stale.id, username="ada", contributions=2),
            ProjectContributor(project_id=fresh.id, username="grace", contributions=7),
            ProjectDependency(project_id=fresh.id, name="pytest"),
            ProjectDependency(project_id=stale.id, name="pytest"),
            ProjectDelta(project_id=fresh.id, name="d1", title="Open work",
                         phase=DeltaPhase.IMPLEMENTATION, updated_at=NOW),
            ProjectDelta(project_id=fresh.id, name="d2", title="Finished",
                         phase=DeltaPhase.COMPLETE, updated_at=NOW),
            GovernanceRepository(name="alpha", phase="v0.0.1", precondition="met",
                                 release_state="unreleased", seed_drift="drift",
                                 behind_corpus=95, records_total=9, records_ratified=0,
                                 governance_generated_at=NOW - timedelta(days=3)),
        ])
        s.commit()
        yield s


def figures(built) -> dict[str, str]:
    return {c.label: c.value for c in built.masthead}


def test_masthead_counts_what_is_there(session):
    f = figures(ov.build(session, now=NOW))
    assert f["repositories"] == "3"
    assert f["never synced"] == "1"
    assert f["stars"] == "15"
    assert f["open PRs"] == "1", "a closed PR is tracked but not open"
    assert f["open issues"] == "1"
    assert f["contributors"] == "2", "one login on two repos is one contributor"
    assert f["deltas on deck"] == "1", "a complete delta is not on deck"


def test_never_synced_is_a_headline_not_a_footnote(session):
    """A repo nothing is known about must not read as a repo with nothing in it."""
    built = ov.build(session, now=NOW)
    cell = next(c for c in built.masthead if c.label == "never synced")
    assert cell.value == "1"
    assert "absent" in cell.note


def test_governance_values_are_passed_through_verbatim(session):
    """The generator's words, unrenamed. A renderer that re-spells one has
    defined a second governance vocabulary."""
    rows = ov.build(session, now=NOW).section("Governance posture").rows
    assert len(rows) == 1
    row = rows[0]
    assert "drift" in row, "seed_drift is rendered as the generator wrote it"
    assert "met" in row and "unreleased" in row
    assert "95" in row


def test_claim_and_evidence_stay_in_separate_columns(session):
    section = ov.build(session, now=NOW).section("Governance posture")
    assert section.headers.index("phase") < section.headers.index("precondition")
    assert "claim" in section.note and "evidence" in section.note


def test_on_deck_excludes_closed_phases(session):
    rows = ov.build(session, now=NOW).section("On deck").rows
    phases = {r[1]: r[2] for r in rows}
    assert "Open work" in phases
    assert "Closed work" not in phases, "a closed delta is not on deck"


def test_a_pull_request_no_delta_claims_is_still_on_deck(session):
    """THE HALF THE MERGE COULD HAVE DROPPED.

    `On deck` absorbed the pull requests tab because 138 of 156 rows were the
    same item. The 18 that were not are work outside the phase model, and a
    merge that showed only deltas would have deleted them from the reading
    while looking tidier.

    Mutation: list only deltas in `deltas_org` and this fails.
    """
    from dossier.facets import NO_DELTA

    rows = ov.build(session, now=NOW).section("On deck").rows
    unclaimed = [r for r in rows if r[2] == NO_DELTA]
    assert unclaimed, "an open pull request with no delta vanished"
    assert all(r[3].startswith("#") for r in unclaimed), (
        "an unclaimed pull request must carry its number as its evidence")


def test_every_phase_is_listed_even_at_zero(session):
    """A phase with no deltas is a fact about the board, not a row to drop."""
    rows = ov.build(session, now=NOW).section("Deltas by phase").rows
    assert [r[0] for r in rows] == [p.value for p in DeltaPhase]
    assert dict((r[0], r[1]) for r in rows)["implementation"] == "1"


def test_language_share_is_of_the_table_and_says_so(session):
    section = ov.build(session, now=NOW).section("Language mix")
    shares = {r[0]: r[3] for r in section.rows}
    assert shares == {"Python": "75%", "Rust": "25%"}
    assert "not of the org" in section.note


def test_dependency_count_is_repos_not_declarations(session):
    rows = ov.build(session, now=NOW).section("Shared dependencies").rows
    assert rows[0][0] == "pytest" and rows[0][1] == "2"


def test_contributor_reach_counts_repositories(session):
    rows = ov.build(session, now=NOW).section("Contributors by reach").rows
    assert rows[0][:3] == ("ada", "2", "42")


def test_attention_lists_the_unknown_and_dates_it(session):
    section = ov.build(session, now=NOW).section("Wants attention")
    listed = {r[0]: r[2] for r in section.rows}
    assert "never synced" in listed["qm/gamma"]
    assert "no description" in listed["qm/gamma"]
    assert "synced 3mo ago" in listed["qm/beta"]
    assert "qm/alpha" not in listed, "a fresh, described, typed repo is not listed"


def test_attention_states_its_threshold_and_declines_a_verdict(session):
    note = ov.build(session, now=NOW).section("Wants attention").note
    assert str(ov.STALE_AFTER_DAYS) in note
    assert "own convention" in note
    assert "not the same as" in note


def test_ages_are_injectable_so_they_can_be_asserted(session):
    """`now` is a parameter precisely so this test can exist."""
    later = ov.build(session, now=NOW + timedelta(days=365))
    assert "1yr" in later.generated_from or "12mo" in later.generated_from


# Sections an empty database cannot empty. `Deltas by phase` is a fixed board
# with a row per phase and no rows of its own; `Thread archive` belongs to the
# harness and is read over HTTP, so it is populated exactly when the harness is
# running -- which made this test pass or fail depending on whether something
# was listening on another port. That is the suite measuring its own
# surroundings rather than the code.
NOT_THE_DATABASE_S = {"Deltas by phase", "Thread archive"}


def test_an_empty_dossier_says_so_rather_than_showing_zeroes():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as empty:
        built = ov.build(empty, now=NOW)
    assert built.generated_from == "nothing synced yet"
    assert all(section.is_empty or section.title in NOT_THE_DATABASE_S
               for section in built.sections)


def test_the_sections_an_empty_database_cannot_empty_are_still_drawn():
    """Excluding them from the assertion above must not mean excluding them
    from the page. A section that vanished when the database was empty would
    take its explanatory note with it, and the note is the part that says why
    the table is empty.
    """
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as empty:
        built = ov.build(empty, now=NOW)
    titles = {section.title for section in built.sections}
    assert NOT_THE_DATABASE_S <= titles, f"missing: {NOT_THE_DATABASE_S - titles}"


# --- the tab, driven ---------------------------------------------------------


def _drawn(app) -> str:
    """What is actually on the screen.

    Asserting on the widget's state would check that the code ran. This checks
    that a reader can see the result, which is the only claim worth making
    about a view.
    """
    import html
    import re

    # `export_screenshot` returns SVG, and every change of style opens a new
    # `<text>` element -- so a phrase that renders as one string arrives split
    # across several. Joining the text nodes with nothing between them is what
    # reconstitutes the line a reader actually sees.
    # Spaces arrive as `&#160;` entities, so an undecoded scrape finds single
    # words and never a phrase -- which would quietly weaken every assertion
    # below into a substring match on one word.
    svg = app.export_screenshot()
    joined = "".join(re.findall(r"<text[^>]*>([^<]*)</text>", svg))
    return html.unescape(joined).replace(" ", " ")


@pytest.mark.asyncio
async def test_the_overview_tab_draws_the_org_figures(session):
    from dossier.tui.app import DossierApp
    from dossier.tui.overview_panel import OverviewPanel

    app = DossierApp(session_factory=lambda: _NoCloseSession(session),
                     initial_tab="tab-overview")
    async with app.run_test(size=(160, 60)) as pilot:
        await pilot.pause()
        drawn = _drawn(app)
        # Inside the context: `run_test` tears the widget tree down on exit, so
        # a query after it reports NoMatches for a widget that was mounted the
        # whole time -- a failure that reads exactly like a missing widget.
        panel = app.query_one(OverviewPanel)
        titles = [section.title for section in panel.overview.sections]

    # What a reader gets without scrolling: the masthead and the first
    # sections. The later ones are asserted through the panel's own overview
    # rather than the screen, because claiming they are visible at 60 rows
    # would be asserting something untrue of any real terminal.
    for expected in ("repositories", "never synced", "GOVERNANCE POSTURE", "ON DECK"):
        assert expected in drawn, f"{expected!r} is not on the first screen"

    assert titles[0] == "Governance posture"
    assert "Wants attention" in titles


@pytest.mark.asyncio
async def test_the_ring_reaches_the_overview_in_three_inputs(session):
    """Ordering Overview first inside `Go` is what buys this, and it is the
    host's only lever on cost once the child count is fixed."""
    from dossier.rad.palette import resolve
    from dossier.rad.session import RadSession

    committed = []
    rad = RadSession(resolve=resolve, on_intent=committed.append)
    rad.open_at(None)   # 1
    rad.enter()         # 2 -- into Go, highlight lands on Overview
    rad.enter()         # 3 -- commits it
    assert [i.action for i in committed] == ["view.overview"]
    assert committed[0].ipa == 3


def test_the_overview_action_is_routed_to_a_real_tab():
    """An action no host handles is a dead wedge."""
    from dossier.rad.palette import resolve
    from dossier.tui.app import DossierApp

    actions = {w.action for verb in resolve() for w in verb.children}
    assert "view.overview" in actions
    assert DossierApp.RAD_VIEWS["view.overview"] == "tab-overview"


class _NoCloseSession:
    """Hands the fixture's session to the app without letting it be closed.

    The app opens and closes a session per read; the fixture owns this one for
    the whole test, and a closed session would take the fixture down with it.
    """

    def __init__(self, session):
        self._session = session

    def __enter__(self):
        return self._session

    def __exit__(self, *exc):
        return False


def test_the_sync_horizon_reads_as_english(session):
    """"today ago" is a figure a reader mistrusts for the wrong reason."""
    assert ov.build(session, now=NOW).generated_from == "most recent sync 2d ago"
    same_day = ov.build(session, now=NOW + timedelta(hours=1))
    assert "ago" not in same_day.generated_from or "today ago" not in same_day.generated_from


def test_scoping_to_an_owner_excludes_everything_else(session):
    """Unscoped, this view reported 104,576 stars for an org that has 54."""
    from dossier.models.schemas import Project as P

    session.add(P(name="third/party", github_owner="Textualize", github_stars=50_000,
                  description="a dependency", github_language="Python",
                  last_synced_at=NOW))
    session.commit()

    everything = figures(ov.build(session, now=NOW))
    scoped = figures(ov.build(session, now=NOW, owner="qm"))
    assert everything["stars"] == "50,015"
    assert scoped["stars"] == "15", "a third party's repo is not the org's stars"
    assert scoped["repositories"] == "3", "the fixture repos carry their owner in full_name"
