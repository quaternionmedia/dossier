"""The two disk views: the REST surface and the TUI tab.

Both render the same stored facts, and both have the same job at the edges --
never let an unmeasured thing read as a measured zero, and never let "nothing
to compare with" read as "nothing changed".

Every test below is a state that must not render as a machine with room on it.
Each was confirmed to go red against the code it names before being kept, per
this project's standard that a passing test is not evidence until it has been
seen to fail.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from dossier import disk_store
from dossier.api import main as api_main
from dossier.api.main import app

from tests.disk_documents import document, measured_target, unknown_target


@pytest.fixture
def engine():
    built = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(built)
    yield built
    SQLModel.metadata.drop_all(built)
    built.dispose()


@pytest.fixture
def client(engine):
    """A test client whose endpoints read the in-memory database.

    The endpoints look `get_session` up on the module at request time, which
    is what makes this swap work -- the same reason the existing API fixture
    does it this way.
    """
    original_engine = api_main.engine
    original_get_session = api_main.get_session
    api_main.engine = engine
    api_main.get_session = lambda: Session(engine)
    with TestClient(app) as ready:
        yield ready
    api_main.engine = original_engine
    api_main.get_session = original_get_session


def load_two(engine, tmp_path: Path, before, after, machine="box") -> None:
    with Session(engine) as session:
        disk_store.load_document(
            session,
            document(tmp_path, "2026-08-10T00:00:00Z", targets=before, name="a.json"),
            machine=machine,
        )
        disk_store.load_document(
            session,
            document(tmp_path, "2026-08-11T00:00:00Z", targets=after, name="b.json"),
            machine=machine,
        )


# --- the REST surface -------------------------------------------------------


def test_snapshots_are_listed_newest_first(client, engine, tmp_path: Path) -> None:
    load_two(engine, tmp_path, [measured_target("c", 1)], [measured_target("c", 2)])
    body = client.get("/disk/snapshots").json()
    assert len(body) == 2
    assert body[0]["generated_at"] > body[1]["generated_at"]
    assert body[0]["machine"] == "box"


def test_an_empty_store_lists_nothing_rather_than_failing(client) -> None:
    response = client.get("/disk/snapshots")
    assert response.status_code == 200
    assert response.json() == []


def test_a_snapshot_that_does_not_exist_is_a_404(client) -> None:
    assert client.get("/disk/snapshots/9999").status_code == 404


def test_an_unmeasured_target_is_served_as_null_with_its_reason(
    client, engine, tmp_path: Path
) -> None:
    """A client reading only `bytes` gets null and has to decide what to do.
    A zero would have let it decide nothing."""
    load_two(engine, tmp_path, [unknown_target("docker")], [unknown_target("docker")])
    newest = client.get("/disk/snapshots").json()[0]["id"]
    detail = client.get(f"/disk/snapshots/{newest}").json()
    target = next(t for t in detail["targets"] if t["name"] == "docker")
    assert target["bytes"] is None
    assert target["bytes_unknown"] == "daemon not running"


def test_the_delta_reports_growth(client, engine, tmp_path: Path) -> None:
    load_two(engine, tmp_path, [measured_target("c", 100)], [measured_target("c", 400)])
    body = client.get("/disk/delta?machine=box").json()
    assert body["available"] is True
    change = next(t for t in body["targets"] if t["name"] == "c")
    assert change["change"] == 300
    assert change["status"] == "grew"


def test_the_delta_serves_null_where_subtracting_would_invent_a_fact(
    client, engine, tmp_path: Path
) -> None:
    """unknown -> measured is not growth, however plausible the number looks."""
    load_two(engine, tmp_path, [unknown_target("docker")], [measured_target("docker", 23_600)])
    body = client.get("/disk/delta?machine=box").json()
    change = next(t for t in body["targets"] if t["name"] == "docker")
    assert change["change"] is None
    assert change["status"] == "unknown"
    assert change["unknown"]


def test_a_delta_for_an_unmeasured_machine_names_the_machine(client) -> None:
    """"No snapshots" without saying which host was looked for sends the reader
    hunting for a bug in the loader rather than passing --machine."""
    body = client.get("/disk/delta?machine=some-other-box").json()
    assert body["available"] is False
    assert "some-other-box" in body["reason"]


def test_one_snapshot_is_200_with_a_reason_not_an_error(
    client, engine, tmp_path: Path
) -> None:
    """A machine measured once is a normal machine. A 404 would let a client
    render it as broken instead of as "not yet"."""
    with Session(engine) as session:
        disk_store.load_document(session, document(tmp_path), machine="box")
    response = client.get("/disk/delta?machine=box")
    assert response.status_code == 200
    body = response.json()
    assert body["available"] is False
    assert "only one snapshot" in body["reason"]
    assert body["targets"] == []


def test_an_empty_store_delta_is_200_with_a_reason(client) -> None:
    body = client.get("/disk/delta?machine=nobody").json()
    assert body["available"] is False
    assert "no snapshots" in body["reason"]


def test_asking_for_one_end_of_a_delta_is_a_400(client) -> None:
    assert client.get("/disk/delta?older=1").status_code == 400
    assert client.get("/disk/delta?newer=1").status_code == 400


def test_an_explicit_pair_that_does_not_exist_is_a_404(client) -> None:
    assert client.get("/disk/delta?older=900&newer=901").status_code == 404


def test_two_machines_are_refused_rather_than_averaged(
    client, engine, tmp_path: Path
) -> None:
    with Session(engine) as session:
        disk_store.load_document(
            session, document(tmp_path, "2026-08-10T00:00:00Z", name="a.json"),
            machine="laptop",
        )
        disk_store.load_document(
            session, document(tmp_path, "2026-08-11T00:00:00Z", name="b.json"),
            machine="tower",
        )
    ids = [row["id"] for row in client.get("/disk/snapshots").json()]
    body = client.get(f"/disk/delta?older={ids[1]}&newer={ids[0]}").json()
    assert body["available"] is False
    assert "different machines" in body["reason"]


def test_the_volume_change_is_free_space_so_negative_is_filling_up(
    client, engine, tmp_path: Path
) -> None:
    fuller = [{
        "path": "C:\\", "total_bytes": 1000, "used_bytes": 950, "free_bytes": 50,
        "free_ratio": 0.05, "state": "warn", "severity": "critical",
        "thresholds_fired": [],
    }]
    with Session(engine) as session:
        disk_store.load_document(
            session, document(tmp_path, "2026-08-10T00:00:00Z", name="a.json"),
            machine="box",
        )
        disk_store.load_document(
            session,
            document(tmp_path, "2026-08-11T00:00:00Z", volumes=fuller, name="b.json"),
            machine="box",
        )
    body = client.get("/disk/delta?machine=box").json()
    assert body["volumes"][0]["change"] == -50


# --- the TUI tab ------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_disk_tab_says_so_when_nothing_has_been_stored(engine) -> None:
    """The absent case must not render as an empty, healthy-looking table."""
    from dossier.tui import DossierApp

    app_under_test = DossierApp(session_factory=lambda: Session(engine))
    async with app_under_test.run_test(size=(200, 50)) as pilot:
        await pilot.pause()
        app_under_test.query_one("#project-tabs").active = "tab-disk"
        await pilot.pause()

        message = str(app_under_test.query_one("#disk-age").content)
        assert "No disk reading has been stored" in message
        assert "absence of any measurement" in message
        assert app_under_test.query_one("#disk-volumes-table").row_count == 0


@pytest.mark.asyncio
async def test_the_disk_tab_renders_with_no_project_selected(
    engine, tmp_path: Path
) -> None:
    """Disk is machine-wide. Hanging it off the per-project guard would leave
    it permanently blank, and blank reads as a machine with nothing on it."""
    from dossier.tui import DossierApp

    load_two(engine, tmp_path, [measured_target("c", 100)], [measured_target("c", 400)])

    app_under_test = DossierApp(session_factory=lambda: Session(engine))
    async with app_under_test.run_test(size=(200, 50)) as pilot:
        await pilot.pause()
        assert not hasattr(app_under_test, "_current_project_id")
        app_under_test.query_one("#project-tabs").active = "tab-disk"
        await pilot.pause()
        assert app_under_test.query_one("#disk-targets-table").row_count == 1


@pytest.mark.asyncio
async def test_the_dashboard_can_open_directly_on_the_disk_tab(
    engine, tmp_path: Path
) -> None:
    """What `dossier disk dashboard` relies on: an initial tab that wins."""
    from dossier.tui import DossierApp

    load_two(engine, tmp_path, [measured_target("c", 100)], [measured_target("c", 400)])

    app_under_test = DossierApp(
        session_factory=lambda: Session(engine), initial_tab="tab-disk"
    )
    async with app_under_test.run_test(size=(200, 50)) as pilot:
        await pilot.pause()
        assert app_under_test.query_one("#project-tabs").active == "tab-disk"
        assert app_under_test.query_one("#disk-volumes-table").row_count == 1


@pytest.mark.asyncio
async def test_only_one_reading_says_there_is_nothing_to_compare(
    engine, tmp_path: Path
) -> None:
    """Not an empty change column, which reads as "nothing changed"."""
    from dossier.tui import DossierApp

    with Session(engine) as session:
        disk_store.load_document(session, document(tmp_path), machine="box")

    app_under_test = DossierApp(
        session_factory=lambda: Session(engine), initial_tab="tab-disk"
    )
    async with app_under_test.run_test(size=(200, 50)) as pilot:
        await pilot.pause()
        message = str(app_under_test.query_one("#disk-delta-age").content)
        assert "No comparison available" in message
        assert "absence of a second measurement" in message


@pytest.mark.asyncio
async def test_the_tab_always_states_the_reading_age(engine, tmp_path: Path) -> None:
    """A dashboard that looks live and is three days old is worse than one
    that admits its age, because the first stops people checking."""
    from dossier.tui import DossierApp

    load_two(engine, tmp_path, [measured_target("c", 100)], [measured_target("c", 400)])

    app_under_test = DossierApp(
        session_factory=lambda: Session(engine), initial_tab="tab-disk"
    )
    async with app_under_test.run_test(size=(200, 50)) as pilot:
        await pilot.pause()
        message = str(app_under_test.query_one("#disk-age").content)
        assert "disk-status.json" in message
        assert "ago" in message
        assert "budget" in message
        assert "box" in message  # and which machine it describes


@pytest.mark.asyncio
async def test_a_reading_past_its_budget_says_so_rather_than_looking_current(
    engine, tmp_path: Path
) -> None:
    """The stale path needs its own fixture. A test whose document happens to
    be fresh asserts nothing about the branch that matters."""
    from dossier.tui import DossierApp

    with Session(engine) as session:
        disk_store.load_document(
            session,
            document(tmp_path, "2026-01-01T00:00:00Z", name="old.json"),
            machine="box",
        )
        disk_store.load_document(
            session,
            document(tmp_path, "2026-01-02T00:00:00Z", name="older.json"),
            machine="box",
        )

    app_under_test = DossierApp(
        session_factory=lambda: Session(engine), initial_tab="tab-disk"
    )
    async with app_under_test.run_test(size=(200, 50)) as pilot:
        await pilot.pause()
        message = str(app_under_test.query_one("#disk-age").content)
        assert "PAST its" in message
        assert "stale" in message


def test_growth_is_coloured_apart_from_shrinkage() -> None:
    """On a full disk the cache that grew is the problem and the one that
    shrank is the relief, so the two must not read alike."""
    from dossier.tui.app import DossierApp

    assert "red" in DossierApp._disk_change_cell(500, "grew")
    assert "green" in DossierApp._disk_change_cell(-500, "shrank")
    assert "no change" in DossierApp._disk_change_cell(0, "same")


def test_a_change_that_could_not_be_established_shows_the_word_not_a_number() -> None:
    for status in ("unknown", "new", "gone"):
        cell = DossierAppCell(None, status)
        assert status in cell
        assert "0" not in cell


def DossierAppCell(change, status: str) -> str:
    from dossier.tui.app import DossierApp

    return DossierApp._disk_change_cell(change, status)


def test_a_small_size_is_never_rounded_to_zero() -> None:
    """`0.0GB` on a 40MB cache reads as empty, which is the same lie as a blank."""
    from dossier.tui.app import DossierApp

    assert DossierApp._disk_size(40_000_000) == "40MB"
    assert DossierApp._disk_size(4_000) == "4KB"
    assert DossierApp._disk_size(7) == "7B"
    assert DossierApp._disk_size(None) == "unknown"
    assert DossierApp._disk_size(-4_000) == "-4KB"
