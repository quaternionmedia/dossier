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
