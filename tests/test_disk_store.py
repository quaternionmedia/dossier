"""The disk read model: snapshots, the delta, and the arithmetic it refuses.

A disk dashboard fails the way every dashboard here fails -- not by reporting
the wrong answer but by drawing a reassuring picture of one. The delta adds a
second way, specific to it: **a subtraction can invent a fact.** Taking a
measured 40GB from a target nobody could read yields -40GB, which is not a
missing number but a confident, specific claim that 40GB was reclaimed, and
nobody reading a dashboard would doubt it.

So most of what follows asserts that a number is *absent* where it would have
been a lie, and that the reason is present in its place. Per this project's
standard, every signal has a fixture in which it reports bad, and each was
confirmed to go red against the code it names.
"""

from __future__ import annotations

import ast
import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from sqlmodel import Session, SQLModel, create_engine

from dossier import disk_store
from dossier.models import DiskSnapshot, DiskTarget, DiskVolume


@pytest.fixture
def session():
    """In-memory database, per this project's convention of avoiding file creep."""
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as active:
        yield active


def document(
    tmp_path: Path,
    generated_at: str = "2026-08-11T00:00:00Z",
    volumes=None,
    targets=None,
    name: str = "disk-status.json",
) -> Path:
    """A disk status document, in the shape ci/disk_status.py writes."""
    payload = {
        "schema": 1,
        "generated_at": generated_at,
        "generator": {"tool": "ci/disk_status.py", "policy": "ci/disk-policy.yaml"},
        "reading": {"staleness_budget_hours": 6},
        "totals": {
            "volumes_critical": 1,
            "volumes_warn": 0,
            "volumes_unknown": 0,
            "targets_measured": 1,
            "targets_unknown": 0,
            "reclaimable_bytes": {
                "refetched": 100, "rebuilt": 0, "destructive": 0
            },
        },
        "volumes": volumes if volumes is not None else [
            {
                "path": "C:\\", "total_bytes": 1000, "used_bytes": 900,
                "free_bytes": 100, "free_ratio": 0.1, "state": "warn",
                "severity": "critical", "thresholds_fired": ["under the floor"],
            }
        ],
        "targets": targets if targets is not None else [
            {
                "name": "cache", "title": "A cache", "kind": "directory_contents",
                "safety": "refetched", "owner": "something",
                "measured": {
                    "bytes": 500, "files": 5, "units_total": 1, "unreadable": 0,
                    "units": [{"path": "C:/cache/big", "bytes": 500}],
                },
            }
        ],
    }
    path = tmp_path / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def unknown_target(name: str = "cache", reason: str = "daemon not running") -> dict:
    return {
        "name": name, "title": "A cache", "kind": "command",
        "safety": "rebuilt", "owner": "something",
        "measured": {"unknown": reason},
    }


def measured_target(name: str = "cache", size: int = 500) -> dict:
    return {
        "name": name, "title": "A cache", "kind": "directory_contents",
        "safety": "refetched", "owner": "something",
        "measured": {
            "bytes": size, "files": 1, "units_total": 1, "unreadable": 0,
            "units": [{"path": f"C:/{name}", "bytes": size}],
        },
    }


# --- loading ----------------------------------------------------------------


def test_a_document_is_stored_as_a_snapshot(session, tmp_path: Path) -> None:
    outcome = disk_store.load_document(session, document(tmp_path), machine="box")
    assert outcome.loaded
    assert outcome.volumes == 1 and outcome.targets == 1
    assert outcome.generated_at == datetime(2026, 8, 11, 0, 0, 0)


def test_an_absent_document_leaves_the_store_untouched(session, tmp_path: Path) -> None:
    """An empty snapshot would enter the next delta as "everything vanished",
    which is the most alarming way to report a file that was not there."""
    disk_store.load_document(session, document(tmp_path), machine="box")
    outcome = disk_store.load_document(session, tmp_path / "nothing.json", machine="box")
    assert not outcome.loaded
    assert "measure first" in outcome.reason
    assert len(disk_store.snapshots(session, machine="box")) == 1


def test_a_file_that_is_not_a_disk_document_is_refused(session, tmp_path: Path) -> None:
    path = tmp_path / "other.json"
    path.write_text(json.dumps({"hello": "world"}), encoding="utf-8")
    outcome = disk_store.load_document(session, path, machine="box")
    assert not outcome.loaded
    assert "not a disk status document" in outcome.reason


def test_a_document_with_no_timestamp_is_refused(session, tmp_path: Path) -> None:
    """Stamping it with the load time would sort it as the newest reading
    regardless of what it describes, so one undated document poisons every
    later delta."""
    path = document(tmp_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["generated_at"] = "not a date"
    path.write_text(json.dumps(payload), encoding="utf-8")

    outcome = disk_store.load_document(session, path, machine="box")
    assert not outcome.loaded
    assert "generated_at" in outcome.reason


def test_loading_appends_rather_than_replaces(session, tmp_path: Path) -> None:
    """The difference from governance load, and the reason a delta is possible."""
    disk_store.load_document(session, document(tmp_path, "2026-08-10T00:00:00Z"), machine="box")
    disk_store.load_document(session, document(tmp_path, "2026-08-11T00:00:00Z"), machine="box")
    assert len(disk_store.snapshots(session, machine="box")) == 2


def test_an_unmeasured_target_is_stored_as_a_reason_not_a_zero(
    session, tmp_path: Path
) -> None:
    """The pair the whole module turns on."""
    path = document(tmp_path, targets=[unknown_target()])
    outcome = disk_store.load_document(session, path, machine="box")
    stored = disk_store.targets_of(session, outcome.snapshot_id)[0]
    assert stored.bytes is None
    assert stored.bytes_unknown == "daemon not running"


def test_an_unreadable_volume_is_stored_as_a_reason_not_a_zero(
    session, tmp_path: Path
) -> None:
    path = document(tmp_path, volumes=[{"path": "E:\\", "usage": {"unknown": "not ready"}}])
    outcome = disk_store.load_document(session, path, machine="box")
    stored = disk_store.volumes_of(session, outcome.snapshot_id)[0]
    assert stored.free_bytes is None
    assert stored.usage_unknown == "not ready"
    assert stored.severity == "unknown"


def test_snapshots_are_pruned_per_machine(session, tmp_path: Path) -> None:
    """A chatty host must not evict a quiet one's history."""
    for day in range(1, 6):
        disk_store.load_document(
            session, document(tmp_path, f"2026-08-0{day}T00:00:00Z"), machine="loud", keep=3
        )
    disk_store.load_document(
        session, document(tmp_path, "2026-08-01T00:00:00Z"), machine="quiet", keep=3
    )
    assert len(disk_store.snapshots(session, machine="loud")) == 3
    assert len(disk_store.snapshots(session, machine="quiet")) == 1


def test_pruning_removes_the_child_rows_too(session, tmp_path: Path) -> None:
    """Orphaned volumes and targets would accumulate invisibly."""
    for day in range(1, 4):
        disk_store.load_document(
            session, document(tmp_path, f"2026-08-0{day}T00:00:00Z"), machine="box", keep=1
        )
    kept = disk_store.snapshots(session, machine="box")
    assert len(kept) == 1
    from sqlmodel import select

    assert len(session.exec(select(DiskVolume)).all()) == 1
    assert len(session.exec(select(DiskTarget)).all()) == 1


# --- the delta, and the four subtractions it refuses ------------------------


def two_snapshots(session, tmp_path: Path, before, after, machine="box"):
    disk_store.load_document(
        session, document(tmp_path, "2026-08-10T00:00:00Z", targets=before, name="a.json"),
        machine=machine,
    )
    disk_store.load_document(
        session, document(tmp_path, "2026-08-11T00:00:00Z", targets=after, name="b.json"),
        machine=machine,
    )
    return disk_store.latest_delta(session, machine=machine)


def change_for(delta, name: str):
    return next(t for t in delta.targets if t.name == name)


def test_a_target_that_grew_reports_the_gain(session, tmp_path: Path) -> None:
    delta = two_snapshots(
        session, tmp_path, [measured_target("cache", 100)], [measured_target("cache", 400)]
    )
    change = change_for(delta, "cache")
    assert change.status == "grew"
    assert change.change == 300


def test_a_target_that_shrank_reports_the_loss(session, tmp_path: Path) -> None:
    delta = two_snapshots(
        session, tmp_path, [measured_target("cache", 400)], [measured_target("cache", 100)]
    )
    assert change_for(delta, "cache").change == -300
    assert change_for(delta, "cache").status == "shrank"


def test_an_unmeasured_end_produces_no_number(session, tmp_path: Path) -> None:
    """The subtraction that would claim a reclaim nobody performed.

    This is not hypothetical: docker's target went from unknown to 23.6GB
    between two real readings taken 70 seconds apart, and a naive delta would
    have reported the cache growing by 23.6GB in that time.
    """
    delta = two_snapshots(
        session, tmp_path, [unknown_target("docker")], [measured_target("docker", 23_600)]
    )
    change = change_for(delta, "docker")
    assert change.change is None
    assert change.status == "unknown"
    assert "daemon not running" in change.unknown


def test_an_unmeasured_later_end_also_produces_no_number(session, tmp_path: Path) -> None:
    delta = two_snapshots(
        session, tmp_path, [measured_target("docker", 100)], [unknown_target("docker")]
    )
    assert change_for(delta, "docker").change is None


def test_a_target_only_in_the_later_snapshot_is_new_not_growth(
    session, tmp_path: Path
) -> None:
    """It may have been that size all along and simply not in the policy."""
    delta = two_snapshots(session, tmp_path, [], [measured_target("fresh", 900)])
    change = change_for(delta, "fresh")
    assert change.status == "new"
    assert change.change is None
    assert change.after == 900
    assert "not in the earlier snapshot" in change.unknown


def test_a_target_only_in_the_earlier_snapshot_is_gone_not_reclaimed(
    session, tmp_path: Path
) -> None:
    """Being dropped from the policy is not the same as being reclaimed."""
    delta = two_snapshots(session, tmp_path, [measured_target("dropped", 900)], [])
    change = change_for(delta, "dropped")
    assert change.status == "gone"
    assert change.change is None
    assert "not the same as being reclaimed" in change.unknown


def test_two_machines_are_never_compared(session, tmp_path: Path) -> None:
    """A laptop's cache growth against a workstation's volume is a trend that
    happened on neither, and every number in it would look plausible."""
    disk_store.load_document(
        session, document(tmp_path, "2026-08-10T00:00:00Z", name="a.json"), machine="laptop"
    )
    disk_store.load_document(
        session, document(tmp_path, "2026-08-11T00:00:00Z", name="b.json"), machine="tower"
    )
    rows = disk_store.snapshots(session)
    delta = disk_store.delta_between(session, rows[1], rows[0])
    assert not delta.available
    assert "different machines" in delta.reason


def test_one_snapshot_is_not_an_empty_delta(session, tmp_path: Path) -> None:
    """A machine measured once is a normal machine. "Nothing to compare with"
    must not render as "nothing changed"."""
    disk_store.load_document(session, document(tmp_path), machine="box")
    delta = disk_store.latest_delta(session, machine="box")
    assert not delta.available
    assert "only one snapshot" in delta.reason
    assert delta.targets == []


def test_no_snapshots_says_so_rather_than_reporting_calm(session) -> None:
    delta = disk_store.latest_delta(session, machine="box")
    assert not delta.available
    assert "no snapshots" in delta.reason


def test_the_volume_change_is_free_space_and_signed(session, tmp_path: Path) -> None:
    """Free rather than used, because free is the number that runs out.
    Negative is the disk filling up."""
    fuller = [{
        "path": "C:\\", "total_bytes": 1000, "used_bytes": 950, "free_bytes": 50,
        "free_ratio": 0.05, "state": "warn", "severity": "critical",
        "thresholds_fired": [],
    }]
    disk_store.load_document(
        session, document(tmp_path, "2026-08-10T00:00:00Z", name="a.json"), machine="box"
    )
    disk_store.load_document(
        session,
        document(tmp_path, "2026-08-11T00:00:00Z", volumes=fuller, name="b.json"),
        machine="box",
    )
    delta = disk_store.latest_delta(session, machine="box")
    assert delta.volumes[0].change == -50


def test_snapshots_out_of_order_are_still_compared_oldest_first(
    session, tmp_path: Path
) -> None:
    """Loading yesterday's document after today's must not invert every sign."""
    disk_store.load_document(
        session,
        document(tmp_path, "2026-08-11T00:00:00Z", targets=[measured_target("c", 400)], name="b.json"),
        machine="box",
    )
    disk_store.load_document(
        session,
        document(tmp_path, "2026-08-10T00:00:00Z", targets=[measured_target("c", 100)], name="a.json"),
        machine="box",
    )
    rows = disk_store.snapshots(session, machine="box")
    delta = disk_store.delta_between(session, rows[0], rows[1])
    assert change_for(delta, "c").change == 300


def test_grew_is_sorted_largest_gain_first(session, tmp_path: Path) -> None:
    """The answer to "what is doing this to me" belongs at the top."""
    delta = two_snapshots(
        session, tmp_path,
        [measured_target("small", 10), measured_target("big", 10)],
        [measured_target("small", 20), measured_target("big", 5000)],
    )
    assert [t.name for t in delta.grew] == ["big", "small"]


def test_everything_without_a_number_is_reachable_as_a_group(
    session, tmp_path: Path
) -> None:
    """So a view can list them apart rather than as dashes among real numbers."""
    delta = two_snapshots(
        session, tmp_path,
        [measured_target("fine", 10), unknown_target("murky")],
        [measured_target("fine", 20), unknown_target("murky")],
    )
    assert [t.name for t in delta.unreadable] == ["murky"]


# --- the read model runs no commands ----------------------------------------


def test_the_store_never_shells_out() -> None:
    """The corpus's rule: a renderer may not run a command. disk.py is the
    actor; this module is the read model, and the line between them is the
    same one corpus.py and governance.py sit either side of."""
    tree = ast.parse(Path(disk_store.__file__).read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert "subprocess" not in imported


def test_the_models_never_shell_out() -> None:
    import dossier.models.disk as model_module

    source = Path(model_module.__file__).read_text(encoding="utf-8")
    assert "subprocess" not in source


# --- the migration is executable, not merely stamped over -------------------


def test_the_disk_tables_are_created_by_the_migration_chain(tmp_path: Path) -> None:
    """`create_all` builds these tables on any dossier command, so `db upgrade`
    aborts and the documented fix is `db stamp head`. That makes it entirely
    possible to ship a migration nobody has ever run. This runs it.
    """
    import shutil
    import sqlite3
    import subprocess
    import sys

    root = Path(__file__).resolve().parent.parent
    if not (root / "alembic.ini").exists():
        pytest.skip("no alembic.ini")

    # Copied rather than run in place. `script_location` and `sqlalchemy.url`
    # in alembic.ini are both relative, so running here builds the database in
    # this temp directory and leaves the operator's own store alone -- which
    # matters, because their store is already at head and would prove nothing.
    shutil.copy(root / "alembic.ini", tmp_path / "alembic.ini")
    shutil.copytree(root / "alembic", tmp_path / "alembic")

    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        capture_output=True, text=True, cwd=str(tmp_path),
        encoding="utf-8", errors="replace",
    )
    assert result.returncode == 0, (result.stderr or result.stdout)[-2000:]
    assert "006_disk" in (result.stderr + result.stdout)
    assert "007_reclaim" in (result.stderr + result.stdout)

    built = sqlite3.connect(tmp_path / "dossier.db")
    tables = {
        row[0]
        for row in built.execute("select name from sqlite_master where type='table'")
    }
    built.close()
    assert {"disk_snapshot", "disk_volume", "disk_target", "disk_reclaim"} <= tables


def test_the_migration_can_be_undone(tmp_path: Path) -> None:
    """A downgrade nobody has run is a rollback plan nobody has."""
    import shutil
    import sqlite3
    import subprocess
    import sys

    root = Path(__file__).resolve().parent.parent
    if not (root / "alembic.ini").exists():
        pytest.skip("no alembic.ini")
    shutil.copy(root / "alembic.ini", tmp_path / "alembic.ini")
    shutil.copytree(root / "alembic", tmp_path / "alembic")

    def alembic(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, "-m", "alembic", *args],
            capture_output=True, text=True, cwd=str(tmp_path),
            encoding="utf-8", errors="replace",
        )

    def disk_tables() -> set[str]:
        built = sqlite3.connect(tmp_path / "dossier.db")
        found = {
            row[0]
            for row in built.execute(
                "select name from sqlite_master where type='table' "
                "and name like 'disk%'"
            )
        }
        built.close()
        return found

    assert alembic("upgrade", "head").returncode == 0
    assert {"disk_snapshot", "disk_volume", "disk_target", "disk_reclaim"} <= disk_tables()

    # Down to the revision before the disk domain existed, so both 006 and 007
    # are exercised rather than only whichever happens to be head today.
    down = alembic("downgrade", "005_governance")
    assert down.returncode == 0, (down.stderr or down.stdout)[-2000:]
    assert disk_tables() == set()

    # And back up, so the rollback is not one-way.
    assert alembic("upgrade", "head").returncode == 0
    assert {"disk_snapshot", "disk_reclaim"} <= disk_tables()


def test_every_table_model_is_imported_by_alembic_env() -> None:
    """A model missing from env.py is not a missing feature -- it is a
    destructive autogenerate.

    `target_metadata` is populated by import side-effect, so a table that is
    absent from the metadata but present in the database reads to autogenerate
    as one to drop. The governance tables were missing from that list, which
    means an autogenerate run would have emitted a drop against the org's
    governance history.
    """
    root = Path(__file__).resolve().parent.parent
    env = root / "alembic" / "env.py"
    source = env.read_text(encoding="utf-8")
    for name in ("DiskSnapshot", "DiskVolume", "DiskTarget",
                 "GovernanceRepository", "GovernanceThread"):
        assert name in source, f"{name} is missing from alembic/env.py"
