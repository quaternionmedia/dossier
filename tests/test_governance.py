"""Tests for the governance read model.

The corpus's own standard for this class of work: *every signal needs a
fixture in which it reports bad.* A dashboard that is green because its query
returned empty is worse than no dashboard, because it discourages the manual
check that would have caught the problem.

So the cases below are weighted towards the failures. Each of the four red
paths -- document absent, document stale, a project reporting unknown, a
project with drift -- has a fixture that produces it, and asserts the view
does not render it as healthy.
"""

import json
import pathlib
from datetime import datetime, timedelta, timezone

import pytest
import yaml
from sqlmodel import Session, SQLModel, create_engine, select

from dossier import governance as gov
from dossier.models import GovernanceRepository, GovernanceThread
from dossier.parsers.governance import (
    DocumentUnavailable,
    age_hours,
    field,
    load_governance,
    parse_timestamp,
)


@pytest.fixture
def session():
    """In-memory database, per this project's convention of avoiding file creep."""
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as active:
        yield active


def write_governance(tmp_path, projects, generated_at="2026-08-09T20:00:00Z"):
    path = tmp_path / "governance-status.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "schema": 1,
                "generated_at": generated_at,
                "corpus": {"commit": "b94d910"},
                "projects": projects,
            }
        ),
        encoding="utf-8",
    )
    return path


def write_harness(tmp_path, repositories, generated_at="2026-08-09T22:00:00Z", budget=24):
    path = tmp_path / "harness-status.json"
    path.write_text(
        json.dumps(
            {
                "schema": 1,
                "generated_at": generated_at,
                "reading": {"staleness_budget_hours": budget},
                "repositories": repositories,
            }
        ),
        encoding="utf-8",
    )
    return path


# --- The unknown convention ------------------------------------------------


def test_unknown_mapping_is_a_value_with_a_reason():
    node = {"open_prs": {"unknown": "unexpected response shape"}}
    result = field(node, "open_prs")
    assert result.is_unknown
    assert result.unknown == "unexpected response shape"
    assert result.or_none() is None


def test_unknown_replacing_a_whole_subtree_propagates_to_its_children():
    """`adoption` itself can be unknown, not only its leaves."""
    node = {"adoption": {"unknown": "gh: Not Found"}}
    result = field(node, "adoption", "submodule", "branch")
    assert result.is_unknown
    assert result.unknown == "gh: Not Found"


def test_absent_is_not_unknown():
    """Only the document may declare unknown. A missing key is just missing."""
    result = field({"branch": {}}, "branch", "behind_corpus")
    assert not result.is_unknown
    assert result.is_null


def test_null_is_not_unknown():
    """`last_propagation: null` means never propagated, which is established."""
    result = field({"branch": {"last_propagation": None}}, "branch", "last_propagation")
    assert not result.is_unknown
    assert result.is_null


def test_an_object_that_merely_has_an_unknown_key_is_data():
    """The test is a single-key mapping, not the presence of the word."""
    node = {"slots": {"unknown": "x", "contributor": "someone"}}
    assert not field(node, "slots").is_unknown


# --- Red path: the document is absent, unreadable, or the wrong shape ------


def test_absent_document_raises_rather_than_returning_empty(tmp_path):
    with pytest.raises(DocumentUnavailable) as caught:
        load_governance(tmp_path / "nope.yaml")
    assert "not at this path" in caught.value.reason


def test_empty_document_is_unavailable_not_a_document_with_no_projects(tmp_path):
    path = tmp_path / "governance-status.yaml"
    path.write_text("", encoding="utf-8")
    with pytest.raises(DocumentUnavailable):
        load_governance(path)


def test_document_of_the_wrong_shape_is_unavailable(tmp_path):
    path = tmp_path / "governance-status.yaml"
    path.write_text(yaml.safe_dump({"schema": 1, "generated_at": "x"}), encoding="utf-8")
    with pytest.raises(DocumentUnavailable) as caught:
        load_governance(path)
    assert "projects" in caught.value.reason


def test_load_with_neither_document_writes_nothing_and_keeps_what_is_stored(
    session, tmp_path
):
    """An unreadable document must not empty the table it could not read."""
    session.add(GovernanceRepository(name="alfred", behind_corpus=62))
    session.add(GovernanceThread(repository_name="alfred", name="config"))
    session.commit()

    report = gov.load_documents(session, corpus_dir=tmp_path)

    assert not report.anything_loaded
    assert not report.governance.loaded and report.governance.reason
    assert not report.harness.loaded and report.harness.reason
    assert len(session.exec(select(GovernanceRepository)).all()) == 1
    assert len(session.exec(select(GovernanceThread)).all()) == 1


def test_harness_absent_does_not_wipe_threads(session, tmp_path):
    """The failure that would render 'nobody could measure' as 'nothing in flight'."""
    write_governance(tmp_path, [{"name": "alfred", "branch": {"behind_corpus": 62}}])
    session.add(GovernanceThread(repository_name="alfred", name="config", stage="ready"))
    session.commit()

    report = gov.load_documents(session, corpus_dir=tmp_path)

    assert report.governance.loaded
    assert not report.harness.loaded
    assert len(session.exec(select(GovernanceThread)).all()) == 1


def test_a_row_survives_when_only_one_document_names_it(session, tmp_path):
    """Deleting on a half-load would report a repository as having left the org."""
    write_governance(tmp_path, [{"name": "alfred", "branch": {"behind_corpus": 1}}])
    gov.load_documents(session, corpus_dir=tmp_path)
    write_harness(tmp_path, [{"name": "qmcp", "phase": "v0.0.1"}])
    gov.load_documents(session, corpus_dir=tmp_path)

    names = {r.name for r in session.exec(select(GovernanceRepository)).all()}
    assert names == {"alfred", "qmcp"}


# --- Red path: staleness ---------------------------------------------------


def test_age_is_reported_from_the_documents_own_stamp():
    generated = datetime(2026, 8, 9, 12, 0, tzinfo=timezone.utc)
    now = generated + timedelta(hours=30)
    assert age_hours(generated, now) == pytest.approx(30.0)


def test_age_handles_the_naive_timestamps_sqlite_returns():
    """Stored timestamps come back without a timezone; both sides normalise."""
    naive = datetime(2026, 8, 9, 12, 0)
    now = datetime(2026, 8, 9, 18, 0)
    assert age_hours(naive, now) == pytest.approx(6.0)


def test_a_stale_document_is_still_loaded_but_its_age_is_available(session, tmp_path):
    old = (datetime.now(timezone.utc) - timedelta(days=9)).strftime("%Y-%m-%dT%H:%M:%SZ")
    write_governance(tmp_path, [{"name": "alfred"}], generated_at=old)
    gov.load_documents(session, corpus_dir=tmp_path)

    ages = gov.document_age(session)
    assert ages["governance"] > 200
    assert ages["harness"] is None  # never read is distinct from zero


# --- Red path: a project reporting unknown ---------------------------------


def test_unknown_is_stored_with_its_reason_and_renders_as_unknown(session, tmp_path):
    write_governance(
        tmp_path,
        [
            {
                "name": "rad",
                "branch": {"behind_corpus": {"unknown": "no project branch"}},
                "open_prs": {"unknown": "unexpected response shape"},
            }
        ],
    )
    gov.load_documents(session, corpus_dir=tmp_path)

    row = session.exec(
        select(GovernanceRepository).where(GovernanceRepository.name == "rad")
    ).one()
    assert row.behind_corpus is None
    assert row.behind_corpus_unknown == "no project branch"
    assert row.open_prs_unknown == "unexpected response shape"

    assert gov.health(row) == "unknown"
    assert gov.drift_text(row) == "unknown"
    assert gov.show_pair(row.behind_corpus, row.behind_corpus_unknown) == "unknown"


def test_unknown_never_renders_as_blank_or_as_the_healthy_value(session, tmp_path):
    """The failure the corpus names: blank reads as fine."""
    write_governance(tmp_path, [{"name": "rad", "branch": {"behind_corpus": {"unknown": "x"}}}])
    gov.load_documents(session, corpus_dir=tmp_path)
    row = session.exec(select(GovernanceRepository)).one()

    rendered = gov.drift_text(row)
    assert rendered not in ("", "-", "current", "0")
    assert rendered == "unknown"


def test_a_measured_zero_is_current_not_unknown(session, tmp_path):
    write_governance(tmp_path, [{"name": "datum", "branch": {"behind_corpus": 0}}])
    gov.load_documents(session, corpus_dir=tmp_path)
    row = session.exec(select(GovernanceRepository)).one()
    assert gov.drift_text(row) == "current"
    assert gov.health(row) == "ok"


# --- Red path: drift -------------------------------------------------------


def test_drift_is_distinct_from_both_healthy_and_unknown(session, tmp_path):
    write_governance(
        tmp_path,
        [
            {"name": "alfred", "branch": {"behind_corpus": 62}, "seed": {"adr_template_vs_corpus": "drift"}},
            {"name": "datum", "branch": {"behind_corpus": 0}, "seed": {"adr_template_vs_corpus": "match"}},
            {"name": "rad", "branch": {"behind_corpus": {"unknown": "no branch"}}},
        ],
    )
    gov.load_documents(session, corpus_dir=tmp_path)
    states = {r.name: gov.health(r) for r in gov.repositories(session)}
    assert states == {"alfred": "drift", "datum": "ok", "rad": "unknown"}


# --- The slot layer, which read a key that does not exist ------------------


def test_slot_verdict_comes_from_compliant_not_from_counting(session, tmp_path):
    """Regression: reading a nonexistent key reported every repository as ok.

    The rule has an automation exclusion and a per-base exemption. Counting
    pull requests here would be a second definition of it, so the document's
    own `compliant` boolean is the verdict.
    """
    write_harness(
        tmp_path,
        [
            {
                "name": "apothecary",
                "slots": {
                    "open_prs": [{"number": 8}, {"number": 12}, {"number": 13}],
                    "compliant": False,
                    "violations": [{"author": "someone", "numbers": [8, 12, 13]}],
                },
            },
            {
                "name": "datum",
                "slots": {"open_prs": [{"number": 1}], "compliant": True, "violations": []},
            },
        ],
    )
    gov.load_documents(session, corpus_dir=tmp_path)
    rows = {r.name: r for r in gov.repositories(session)}

    assert rows["apothecary"].slot_state == "over"
    assert rows["apothecary"].slot_violations == "#8, #12, #13"
    assert gov.health(rows["apothecary"]) == "drift"
    assert rows["datum"].slot_state == "ok"


def test_a_missing_compliant_key_is_no_answer_rather_than_ok(session, tmp_path):
    """The exact bug: absence must not resolve to the healthy value."""
    write_harness(tmp_path, [{"name": "mystery", "slots": {"open_prs": []}}])
    gov.load_documents(session, corpus_dir=tmp_path)
    row = session.exec(select(GovernanceRepository)).one()
    assert row.slot_state is None
    assert gov.show_pair(row.slot_state, row.slot_unknown) == "-"


def test_unknown_slots_subtree_is_unknown_not_ok(session, tmp_path):
    write_harness(tmp_path, [{"name": "mystery", "slots": {"unknown": "gh: Not Found"}}])
    gov.load_documents(session, corpus_dir=tmp_path)
    row = session.exec(select(GovernanceRepository)).one()
    assert row.slot_unknown == "gh: Not Found"
    assert gov.health(row) == "unknown"


# --- Threads: the work in flight -------------------------------------------


def test_threads_load_with_their_delta_and_stalled_flag(session, tmp_path):
    write_harness(
        tmp_path,
        [
            {
                "name": "qm",
                "threads": [
                    {
                        "name": "evolve/ci-tooling-fixes",
                        "stage": "draft",
                        "pr": 36,
                        "delta": {"additions": 10490, "deletions": 60, "commits": 17, "changed_files": 60},
                        "idle_hours": 1.0,
                        "stalled": False,
                    },
                    {
                        "name": "config",
                        "stage": "ready",
                        "pr": 113,
                        "idle_hours": 22874.0,
                        "stalled": True,
                    },
                ],
            }
        ],
    )
    report = gov.load_documents(session, corpus_dir=tmp_path)
    assert report.threads == 2

    rows = gov.threads(session)
    assert rows[0].stalled is True  # stalled surfaces first
    assert rows[0].name == "config"
    assert rows[1].additions == 10490
    assert rows[1].pr == 36


def test_reloading_replaces_threads_rather_than_appending(session, tmp_path):
    write_harness(tmp_path, [{"name": "qm", "threads": [{"name": "a"}, {"name": "b"}]}])
    gov.load_documents(session, corpus_dir=tmp_path)
    write_harness(tmp_path, [{"name": "qm", "threads": [{"name": "a"}]}])
    gov.load_documents(session, corpus_dir=tmp_path)
    assert len(gov.threads(session)) == 1


def test_a_document_reporting_no_threads_is_not_the_same_as_never_read(
    session, tmp_path
):
    write_harness(tmp_path, [{"name": "qm", "threads": []}])
    gov.load_documents(session, corpus_dir=tmp_path)

    assert gov.threads(session) == []
    # ...but the document WAS read, and the age proves it. The view uses this
    # to tell "quiet" apart from "unmeasured".
    assert gov.document_age(session)["harness"] is not None


# --- Timestamps ------------------------------------------------------------


def test_trailing_z_timestamps_parse():
    parsed = parse_timestamp("2026-08-09T20:19:41Z")
    assert parsed == datetime(2026, 8, 9, 20, 19, 41, tzinfo=timezone.utc)


def test_an_unparseable_timestamp_degrades_one_column_rather_than_the_document():
    assert parse_timestamp("not a date") is None
    assert parse_timestamp(None) is None


# --- The tab actually activates --------------------------------------------
#
# Worth its own test rather than trusting the wiring: this ref's TUI hangs tab
# loading off a guard that returns early when no project is selected, and the
# governance tab is org-wide. Code written against the other ref's topology
# fails silently here -- it renders an empty table, which reads as fine.


@pytest.mark.asyncio
async def test_governance_tab_populates_with_no_project_selected(tmp_path):
    from dossier.tui import DossierApp

    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)

    def session_factory():
        return Session(engine)

    write_governance(
        tmp_path,
        [
            {"name": "alfred", "branch": {"behind_corpus": 62}, "seed": {"adr_template_vs_corpus": "drift"}},
            {"name": "rad", "branch": {"behind_corpus": {"unknown": "no project branch"}}},
        ],
    )
    write_harness(
        tmp_path,
        [{"name": "qm", "threads": [{"name": "evolve/x", "stage": "draft", "pr": 36, "idle_hours": 1.0}]}],
    )
    with session_factory() as active:
        gov.load_documents(active, corpus_dir=tmp_path)

    app = DossierApp(session_factory=session_factory)
    async with app.run_test(size=(160, 50)) as pilot:
        await pilot.pause()
        tabs = app.query_one("#project-tabs")
        tabs.active = "tab-governance"
        await pilot.pause()

        table = app.query_one("#governance-table")
        threads = app.query_one("#governance-threads-table")
        # Three repositories: two from the governance document, one the
        # harness document alone knows about.
        assert table.row_count == 3
        assert threads.row_count == 1
        assert "generated" in str(app.query_one("#governance-age").content)


@pytest.mark.asyncio
async def test_governance_tab_says_so_when_nothing_has_been_loaded():
    """The absent case must not render as an empty, healthy-looking table."""
    from dossier.tui import DossierApp

    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)

    app = DossierApp(session_factory=lambda: Session(engine))
    async with app.run_test(size=(160, 50)) as pilot:
        await pilot.pause()
        app.query_one("#project-tabs").active = "tab-governance"
        await pilot.pause()

        message = str(app.query_one("#governance-age").content)
        assert "No governance document has been read" in message
        assert app.query_one("#governance-table").row_count == 0


# --- Joining governance rows to projects, at read time ---------------------


def make_project(**kwargs):
    from dossier.models import Project

    return Project(**kwargs)


def test_the_slug_is_the_strong_key(session):
    row = GovernanceRepository(name="alfred", slug="quaternionmedia/alfred")
    project = make_project(name="alfred-thing", full_name="quaternionmedia/alfred")
    assert gov.match_strength(row, project) == "slug"


def test_matching_falls_back_through_weaker_keys(session):
    row = GovernanceRepository(name="alfred", slug="quaternionmedia/alfred")
    assert gov.match_strength(row, make_project(name="x", github_repo="alfred")) == "repo name"
    assert gov.match_strength(row, make_project(name="alfred")) == "name"
    assert gov.match_strength(row, make_project(name="someone/alfred")) == "trailing name"


def test_an_unrelated_project_does_not_match():
    row = GovernanceRepository(name="alfred", slug="quaternionmedia/alfred")
    assert gov.match_strength(row, make_project(name="rad")) is None


def test_the_strongest_match_wins_when_several_could(session):
    """A weak name collision must not beat an exact slug."""
    session.add(GovernanceRepository(name="alfred", slug="quaternionmedia/alfred"))
    session.add(make_project(name="alfred"))  # matches by bare name
    session.add(make_project(name="elsewhere/alfred", full_name="quaternionmedia/alfred"))
    session.commit()

    row = session.exec(select(GovernanceRepository)).one()
    project, how = gov.project_for_repository(session, row)
    assert how == "slug"
    assert project.name == "elsewhere/alfred"


def test_governance_for_project_reports_how_it_matched(session):
    session.add(GovernanceRepository(name="alfred", slug="quaternionmedia/alfred", phase="v0.0.1"))
    session.commit()
    row, how = gov.governance_for_project(session, make_project(name="alfred"))
    assert row.phase == "v0.0.1"
    assert how == "name"


def test_a_project_the_corpus_does_not_govern_has_no_row(session):
    session.add(GovernanceRepository(name="alfred"))
    session.commit()
    row, how = gov.governance_for_project(session, make_project(name="unrelated"))
    assert row is None and how is None


def test_coverage_says_synced_and_flags_a_weak_match():
    project = make_project(name="alfred")
    assert gov.coverage_text(None, None) == "not synced"
    assert gov.coverage_text(project, "slug") == "synced"
    assert gov.coverage_text(project, "name") == "synced (name)"


def test_summary_lines_distinguish_never_propagated_from_unknown():
    never = GovernanceRepository(name="a")
    unknown = GovernanceRepository(name="b", last_propagation_unknown="no branch")
    assert any("never propagated" in line for line in gov.summary_lines(never))
    assert any("unknown" in line for line in gov.summary_lines(unknown))


def test_summary_lines_say_so_when_there_is_no_row():
    lines = gov.summary_lines(None)
    assert any("not in the corpus" in line for line in lines)


def test_summary_lines_flag_a_match_made_on_a_weak_key():
    row = GovernanceRepository(name="alfred")
    assert any("not by slug" in line for line in gov.summary_lines(row, "name"))
    assert not any("not by slug" in line for line in gov.summary_lines(row, "slug"))


def test_threads_for_a_project_come_from_its_governance_row(session):
    session.add(GovernanceRepository(name="alfred", slug="quaternionmedia/alfred"))
    session.add(GovernanceThread(repository_name="alfred", name="config", idle_hours=5.0))
    session.add(GovernanceThread(repository_name="rad", name="other", idle_hours=9.0))
    session.commit()

    found = gov.threads_for_project(session, make_project(name="alfred"))
    assert [t.name for t in found] == ["config"]


# --- Finding the corpus ----------------------------------------------------


def test_an_explicit_corpus_dir_always_wins(tmp_path):
    path, why = gov.resolve_corpus_dir(tmp_path)
    assert path == tmp_path
    assert "--corpus-dir" in why


def test_a_directory_holding_the_documents_is_chosen(tmp_path, monkeypatch):
    write_governance(tmp_path, [{"name": "alfred"}])
    monkeypatch.chdir(tmp_path)
    path, why = gov.resolve_corpus_dir(None)
    assert path == pathlib.Path(".")
    assert "current directory" in why


def test_the_documents_beat_a_directory_that_only_looks_like_a_corpus(
    tmp_path, monkeypatch
):
    """A vendored corpus with no documents must not win over one that has them."""
    project = tmp_path / "project"
    (project / "governance" / "qm" / "records").mkdir(parents=True)
    (project / "governance" / "qm" / "PRINCIPLES.md").write_text("x", encoding="utf-8")
    corpus = tmp_path / "qm"
    corpus.mkdir()
    write_governance(corpus, [{"name": "alfred"}])

    monkeypatch.chdir(project)
    path, why = gov.resolve_corpus_dir(None)
    assert path == pathlib.Path("..") / "qm"
    assert "beside" in why


def test_a_corpus_without_documents_is_still_named_with_the_caveat(
    tmp_path, monkeypatch
):
    """Reporting a concrete path beats reporting nothing."""
    (tmp_path / "records").mkdir()
    (tmp_path / "PRINCIPLES.md").write_text("x", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    path, why = gov.resolve_corpus_dir(None)
    assert path == pathlib.Path(".")
    assert "neither document is there yet" in why


def test_finding_nothing_still_returns_a_path_and_says_so(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    path, why = gov.resolve_corpus_dir(None)
    assert path == pathlib.Path(".")
    assert "nothing looked like a corpus" in why


# --- Refreshing, and the boundary that keeps it out of the renderer --------


def test_the_read_and_render_path_runs_no_commands():
    """The corpus's rule, enforced here the way the corpus enforces it.

    A renderer that can shell out is a second place a governance rule gets
    defined, and two definitions drift. Refreshing is a different act and
    lives in `dossier.corpus`; these three modules must stay clean.
    """
    import dossier.governance
    import dossier.models.governance
    import dossier.parsers.governance

    for module in (
        dossier.parsers.governance,
        dossier.models.governance,
        dossier.governance,
    ):
        source = pathlib.Path(module.__file__).read_text(encoding="utf-8")
        assert "subprocess" not in source, f"{module.__name__} must not run commands"


def test_refresh_reports_a_checkout_without_the_generators(tmp_path):
    """A project's vendored corpus has no ci/ -- absent, not broken."""
    from dossier import corpus

    (tmp_path / ".git").mkdir()
    reason = corpus.can_refresh(tmp_path)
    assert reason is not None
    assert "ci/governance_status.py" in reason

    outcomes = corpus.refresh(tmp_path)
    assert len(outcomes) == 2
    assert all(not o.ran for o in outcomes)
    assert all("nothing here to run" in o.summary for o in outcomes)


def test_refresh_reports_a_missing_directory_rather_than_raising(tmp_path):
    from dossier import corpus

    outcomes = corpus.refresh(tmp_path / "absent")
    assert all(not o.ran and "does not exist" in o.reason for o in outcomes)


def test_refresh_runs_the_generators_in_order_and_reports_failure(tmp_path):
    """Governance first: the harness generator can read the governance document.

    Stand-in generators, so this exercises the ordering and the failure path
    without the network. One exits non-zero to prove a failure is reported
    rather than swallowed.
    """
    from dossier import corpus

    (tmp_path / ".git").mkdir()
    (tmp_path / "ci").mkdir()
    (tmp_path / "ci" / "governance_status.py").write_text(
        "import pathlib\n"
        "pathlib.Path('order.log').write_text('governance\\n')\n",
        encoding="utf-8",
    )
    (tmp_path / "ci" / "harness_status.py").write_text(
        "import pathlib, sys\n"
        "p = pathlib.Path('order.log')\n"
        "p.write_text(p.read_text() + 'harness\\n')\n"
        "sys.stderr.write('deliberate failure\\n')\n"
        "sys.exit(3)\n",
        encoding="utf-8",
    )

    outcomes = corpus.refresh(tmp_path)

    assert (tmp_path / "order.log").read_text().split() == ["governance", "harness"]
    assert outcomes[0].ok is True
    assert outcomes[1].ok is False
    assert "deliberate failure" in outcomes[1].reason
    assert "failed" in outcomes[1].summary


@pytest.mark.asyncio
async def test_the_dashboard_can_open_directly_on_the_governance_tab(tmp_path):
    """What `governance dashboard` relies on: an initial tab that wins."""
    from dossier.tui import DossierApp

    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    write_governance(tmp_path, [{"name": "alfred", "branch": {"behind_corpus": 62}}])
    with Session(engine) as active:
        gov.load_documents(active, corpus_dir=tmp_path)

    app = DossierApp(session_factory=lambda: Session(engine), initial_tab="tab-governance")
    async with app.run_test(size=(160, 50)) as pilot:
        await pilot.pause()
        assert app.query_one("#project-tabs").active == "tab-governance"
        assert app.query_one("#governance-table").row_count == 1


@pytest.mark.asyncio
async def test_selecting_a_project_shows_its_governance_in_the_details_tab(tmp_path):
    """The project->org link, driven through the real app.

    Worth an app-level test rather than a helper test: the panel has no session,
    so if the app stops handing the row over the block silently renders empty --
    and empty reads as fine.
    """
    from dossier.models import Project
    from dossier.tui import DossierApp

    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    write_governance(
        tmp_path,
        [{"name": "alfred", "branch": {"behind_corpus": 62}, "seed": {"adr_template_vs_corpus": "drift"}}],
    )
    with Session(engine) as active:
        gov.load_documents(active, corpus_dir=tmp_path)
        active.add(Project(name="alfred", full_name="quaternionmedia/alfred"))
        active.commit()

    app = DossierApp(session_factory=lambda: Session(engine))
    async with app.run_test(size=(160, 50)) as pilot:
        await pilot.pause()
        with Session(engine) as active:
            project = active.exec(select(Project)).one()
        app.show_project_details(project)
        await pilot.pause()

        block = str(app.query_one("#project-governance").content)
        assert "Governance" in block
        assert "62 behind" in block
        assert "drift" in block


@pytest.mark.asyncio
async def test_a_project_the_corpus_does_not_govern_says_so_rather_than_nothing(tmp_path):
    from dossier.models import Project
    from dossier.tui import DossierApp

    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as active:
        active.add(Project(name="unrelated"))
        active.commit()

    app = DossierApp(session_factory=lambda: Session(engine))
    async with app.run_test(size=(160, 50)) as pilot:
        await pilot.pause()
        with Session(engine) as active:
            project = active.exec(select(Project)).one()
        app.show_project_details(project)
        await pilot.pause()
        block = str(app.query_one("#project-governance").content)
        assert "not in the corpus" in block


@pytest.mark.asyncio
async def test_the_governance_table_shows_which_repositories_are_synced(tmp_path):
    """The org->project link: coverage, in the org-wide table."""
    from dossier.models import Project
    from dossier.tui import DossierApp

    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    write_governance(tmp_path, [{"name": "alfred"}, {"name": "rad"}])
    with Session(engine) as active:
        gov.load_documents(active, corpus_dir=tmp_path)
        active.add(Project(name="alfred", full_name="quaternionmedia/alfred"))
        active.commit()

    app = DossierApp(session_factory=lambda: Session(engine), initial_tab="tab-governance")
    async with app.run_test(size=(180, 50)) as pilot:
        await pilot.pause()
        table = app.query_one("#governance-table")
        rendered = {
            str(table.get_row_at(i)[0]): str(table.get_row_at(i)[-1])
            for i in range(table.row_count)
        }
        assert any("alfred" in name and "synced" in cell and "not" not in cell
                   for name, cell in rendered.items())
        assert any("rad" in name and "not synced" in cell for name, cell in rendered.items())


# --- The real documents, if this checkout has them -------------------------


def test_against_the_vendored_corpus_if_present(session):
    """Reads the real documents when the pin carries them; skips when it does not.

    The pin currently predates both, so this skips. It is here so that the
    first pin bump that carries them exercises the parser against the real
    thing rather than only against fixtures written by the same author.
    """
    governance_path, harness_path = gov.default_paths()
    if not governance_path.exists() and not harness_path.exists():
        pytest.skip("the vendored corpus does not carry the documents at this pin")

    report = gov.load_documents(session)
    assert report.anything_loaded
    for row in gov.repositories(session):
        assert gov.health(row) in {"ok", "drift", "unknown"}
