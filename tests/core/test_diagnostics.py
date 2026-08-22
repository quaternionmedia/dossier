"""The self-check, checked.

**NOTHING IMPORTED `dossier.diagnostics` FROM A TEST UNTIL THIS FILE.** The
module whose job is to notice that the rest of the application has drifted was
the one thing nothing verified, which is the shape this corpus keeps naming: the
scaffolding you measure with is part of the measurement.

THE TESTS WORTH READING ARE THE FIRST THREE. They are about `live-database`,
which is the only check here that reads runtime state rather than source, and
whose first version was wrong in exactly the way it existed to catch.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from dossier import diagnostics
from dossier.diagnostics import (
    CHECKS,
    FAIL,
    PASS,
    UNKNOWN,
    Result,
    run,
    the_database_being_read_is_the_one_with_the_data,
)


def _database(path: Path, projects: int) -> Path:
    """A database with `projects` rows, made the way the real one is."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as db:
        db.execute("create table if not exists project (id integer primary key)")
        db.executemany("insert into project (id) values (?)",
                       [(n,) for n in range(projects)])
    return path


# --- the check that reads runtime state ---------------------------------------


def test_reading_an_empty_database_beside_a_full_one_fails(tmp_path, monkeypatch):
    """THE ONE THAT MATTERS.

    Two databases, one migrated and one not, and nothing on screen saying which
    is in use -- the failure `health.candidate_databases` was written for. The
    panel reports the counts of whichever it opened, truthfully and uselessly.

    Mutation: return PASS whenever the live database exists and this fails.
    """
    live = tmp_path / "dossier.db"
    _database(live, 0)
    full = _database(tmp_path / "elsewhere" / "dossier.db", 112)

    monkeypatch.setattr("dossier.sources.open_database", lambda: live)
    monkeypatch.setattr("dossier.health.candidate_databases",
                        lambda cwd=None: [live, full])

    found = the_database_being_read_is_the_one_with_the_data()
    assert found.state == FAIL
    assert str(full) in found.detail


def test_an_empty_installation_is_unknown_rather_than_a_failure(tmp_path, monkeypatch):
    """Nothing ingested yet is not a defect. A fresh clone must not open onto a
    red diagnostic that no action clears."""
    live = _database(tmp_path / "dossier.db", 0)
    monkeypatch.setattr("dossier.sources.open_database", lambda: live)
    monkeypatch.setattr("dossier.health.candidate_databases",
                        lambda cwd=None: [live])

    assert the_database_being_read_is_the_one_with_the_data().state == UNKNOWN


def test_the_empty_verdict_refuses_to_claim_nothing_is_ingested(tmp_path, monkeypatch):
    """THE HOLE THIS CHECK HAD, KEPT SHUT.

    The first version said "nothing has been ingested yet". Run from any
    directory other than the one holding the data -- which is the whole
    situation this check exists for -- that sentence is false, because
    `candidate_databases` searches the working directory and the home directory
    and cannot see anything else. An empty result was being reported as an empty
    archive, which is this check committing the error it was written to catch.

    Mutation: restore the old wording and this fails.
    """
    live = _database(tmp_path / "dossier.db", 0)
    monkeypatch.setattr("dossier.sources.open_database", lambda: live)
    monkeypatch.setattr("dossier.health.candidate_databases",
                        lambda cwd=None: [live])

    detail = the_database_being_read_is_the_one_with_the_data().detail
    assert "nothing has been ingested" not in detail
    assert "would not be seen from here" in detail
    assert str(live) in detail, "a bounded search names what it searched"


def test_the_check_does_not_create_the_database_it_looks_for(tmp_path, monkeypatch):
    """**THE CHECK MUST NOT CAUSE THE DEFECT.**

    `sqlite3.connect` creates a missing file. A check that opened each candidate
    read-write would leave an empty database at every path it considered, then
    report them all present and all empty -- manufacturing its own evidence.

    Mutation: drop `mode=ro` from `_rows_in` and this fails.
    """
    # **THE PARENT DIRECTORY MUST EXIST.** The first version of this test used
    # `tmp_path / "not-there" / "dossier.db"`, where `connect` fails on the
    # missing directory before it can create anything -- so the test passed with
    # `mode=ro` removed and was asserting nothing. Found by mutating.
    absent = tmp_path / "absent.db"
    live = _database(tmp_path / "dossier.db", 3)
    monkeypatch.setattr("dossier.sources.open_database", lambda: live)
    monkeypatch.setattr("dossier.health.candidate_databases",
                        lambda cwd=None: [live, absent])

    the_database_being_read_is_the_one_with_the_data()
    assert not absent.exists(), "the check created a database while looking"


def test_a_populated_live_database_passes(tmp_path, monkeypatch):
    live = _database(tmp_path / "dossier.db", 112)
    monkeypatch.setattr("dossier.sources.open_database", lambda: live)
    monkeypatch.setattr("dossier.health.candidate_databases",
                        lambda cwd=None: [live])

    found = the_database_being_read_is_the_one_with_the_data()
    assert found.state == PASS and "112" in found.detail


def test_a_database_that_cannot_be_read_counts_as_empty_rather_than_raising(tmp_path):
    """A file that is not a database at all. The check reports; it does not
    take the diagnostic down with it."""
    broken = tmp_path / "dossier.db"
    broken.write_text("this is not sqlite", encoding="utf-8")
    assert diagnostics._rows_in(broken) == 0


def test_a_read_only_open_is_what_stops_the_creation(tmp_path, monkeypatch):
    """The second defence, on its own.

    `_rows_in` returns early for a path that is not a file, so the read-only
    URI never gets exercised in normal use and a mutation removing it goes
    unnoticed. This bypasses the first guard to test the second, because two
    defences where only one is checked is one defence.

    Mutation: drop `mode=ro` from `_rows_in` and this fails.
    """
    absent = tmp_path / "absent.db"
    monkeypatch.setattr(Path, "is_file", lambda self: True)

    assert diagnostics._rows_in(absent) == 0
    assert not absent.exists(), "a read-write open created the database"


# --- properties every check has to have ---------------------------------------


def test_every_check_names_the_failure_it_exists_because_of():
    """`found_because` is the field that lets somebody judge whether a check is
    still worth running. A check whose origin nobody can name is one nobody can
    retire.

    Mutation: add a check with an empty `found_because` and this fails.
    """
    for result in run().results:
        assert result.found_because.strip(), f"{result.name} says why it exists"
        assert len(result.found_because) > 40, (
            f"{result.name}: `found_because` is a sentence about a real "
            f"failure, not a label")


def test_one_check_raising_does_not_take_the_report_with_it():
    """Mutation: let `run` propagate and this fails."""
    def explodes() -> Result:
        raise RuntimeError("boom")

    report = run(checks=CHECKS + (explodes,))
    assert len(report.results) == len(CHECKS) + 1
    assert any(r.state == UNKNOWN and "boom" in r.detail for r in report.results)


def test_every_check_reports_one_of_the_three_states():
    assert {r.state for r in run().results} <= {PASS, FAIL, UNKNOWN}


def test_check_names_are_unique_so_a_reader_can_cite_one():
    names = [r.name for r in run().results]
    assert len(names) == len(set(names))
