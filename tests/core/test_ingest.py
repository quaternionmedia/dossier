"""Ingesting delta payloads another system emitted.

Nothing here touches the configured database: `plan` takes its two lookups as
arguments, so the decision layer is testable without a session and the caller
owns the transaction.

THE TESTS THAT MATTER ARE THE REFUSALS. An ingest is easy to write so that it
always writes something -- and a sync that invents a project from a typo in
another system, or silently overwrites a field somebody set here, is worse than
no sync at all. This database holds 141 projects somebody synced by hand.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from dossier.ingest import (
    SCHEMA,
    address_of,
    differences,
    load,
    plan,
    render,
)


@dataclass
class FakeProject:
    id: int = 1
    full_name: str = "quaternionmedia/qmcp"


@dataclass
class FakeDelta:
    name: str = "summarizer"
    title: str = "Summarizer"
    description: str = "a prompt"
    phase: str = "planning"
    delta_type: str = "feature"
    priority: str = "medium"


def payload(**overrides) -> dict:
    row = {
        "name": "summarizer", "title": "Summarizer", "description": "a prompt",
        "phase": "planning", "delta_type": "feature", "priority": "medium",
    }
    row.update(overrides.pop("delta", {}))
    base = {
        "schema": SCHEMA,
        "project": "quaternionmedia/qmcp",
        "delta": row,
        "links": [{"link_type": "address", "target_id": None,
                   "target_name": "quaternionmedia/qmcp/delta/summarizer"}],
    }
    base.update(overrides)
    return base


def run(payloads, project=FakeProject(), existing=None):
    return plan(payloads, lambda name: project, lambda pid, n: existing)


# --- identity is the address -------------------------------------------------


def test_the_address_is_read_from_the_links():
    assert address_of(payload()) == "quaternionmedia/qmcp/delta/summarizer"


def test_an_address_is_derived_when_the_payload_carries_no_link():
    item = payload()
    item["links"] = []
    assert address_of(item) == "quaternionmedia/qmcp/delta/summarizer"


def test_a_payload_with_neither_has_no_address():
    assert address_of({"schema": SCHEMA}) is None


# --- what would happen -------------------------------------------------------


def test_an_unseen_delta_is_a_create():
    assert run([payload()])[0].action == "create"


def test_an_identical_delta_is_unchanged():
    assert run([payload()], existing=FakeDelta())[0].action == "unchanged"


def test_a_differing_delta_is_an_update_naming_the_fields():
    verdict = run([payload(delta={"phase": "review", "priority": "high"})],
                  existing=FakeDelta())[0]
    assert verdict.action == "update"
    assert any("phase" in d for d in verdict.differences)
    assert any("priority" in d for d in verdict.differences)


def test_a_difference_names_both_values():
    """A reader deciding has to see what is being replaced."""
    verdict = run([payload(delta={"phase": "review"})], existing=FakeDelta())[0]
    assert "here 'planning'" in verdict.differences[0]
    assert "payload 'review'" in verdict.differences[0]


def test_a_field_the_payload_omits_is_not_a_difference():
    """Absent is not empty. Treating a missing key as a blank would let a
    partial payload wipe fields somebody set here."""
    item = payload()
    item["delta"] = {"name": "summarizer"}
    assert run([item], existing=FakeDelta())[0].action == "unchanged"


def test_an_enum_phase_on_the_row_compares_against_a_string_payload():
    """The row stores an enum, the payload a string. Compared naively every
    row differs on every run."""
    class EnumLike:
        value = "planning"

    row = FakeDelta()
    row.phase = EnumLike()
    assert differences(row, {"phase": "planning"}) == []


# --- the refusals ------------------------------------------------------------


def test_a_payload_from_another_schema_is_refused():
    item = payload()
    item["schema"] = SCHEMA + 1
    verdict = run([item])[0]
    assert verdict.action == "refused" and "Refusing" in verdict.reason


def test_a_project_this_database_does_not_have_is_refused():
    """Inventing a project from a delta lets a typo elsewhere populate this
    database."""
    verdict = plan([payload()], lambda name: None, lambda pid, n: None)[0]
    assert verdict.action == "refused" and "no project" in verdict.reason


def test_a_payload_naming_no_project_is_refused():
    item = payload()
    del item["project"]
    assert run([item])[0].action == "refused"


def test_a_payload_naming_no_delta_is_refused():
    item = payload()
    item["delta"] = {}
    assert run([item])[0].action == "refused"


def test_a_refusal_never_becomes_a_write():
    """The plan is what the writer applies; a refused entry must not be in it
    as anything actionable."""
    item = payload()
    item["schema"] = 99
    assert all(v.action not in ("create", "update") for v in run([item]))


# --- loading -----------------------------------------------------------------


def test_a_single_payload_or_a_list_both_load(tmp_path):
    one = tmp_path / "one.json"
    one.write_text(json.dumps(payload()), encoding="utf-8")
    many = tmp_path / "many.json"
    many.write_text(json.dumps([payload(), payload()]), encoding="utf-8")
    assert len(load(one)) == 1
    assert len(load(many)) == 2


def test_an_empty_payload_file_is_refused(tmp_path):
    path = tmp_path / "empty.json"
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(SystemExit):
        load(path)


def test_a_missing_payload_file_is_refused(tmp_path):
    with pytest.raises(SystemExit):
        load(tmp_path / "absent.json")


# --- what the report says ----------------------------------------------------


def test_the_report_counts_each_verdict():
    text = render(run([payload()]), written=False)
    assert "1 new" in text


def test_the_report_says_nothing_was_written_by_default():
    assert "Nothing was written" in render(run([payload()]), written=False)


def test_the_report_says_written_when_it_was():
    assert "Written." in render(run([payload()]), written=True)


def test_the_report_states_that_a_difference_is_not_a_correction():
    """Two views disagreeing is a delta to resolve, not a winner to pick."""
    text = render(run([payload()]), written=False)
    assert "disagreement, not a correction" in text


def test_the_report_states_that_nothing_is_deleted():
    """A delta absent from a payload is not one that was removed."""
    assert "not one that was removed" in render(run([payload()]), written=False)


# --- the links, which the write path used to drop ----------------------------
#
# `links` was read for the address and then discarded, so the row naming what a
# delta points at -- the invocation that found it, and the address that joins it
# to the other view -- was never stored. Both sides believed the join existed
# and nothing held it. These run the real CLI against a real database, because
# the defect was in the write path and a test of `plan` alone cannot see it.


def _run_ingest(tmp_path, payloads, monkeypatch):
    """Ingest through the real command, against a database of its own."""
    from click.testing import CliRunner

    database = tmp_path / "links.db"
    monkeypatch.setenv("DOSSIER_DATABASE_URL", f"sqlite:///{database}")

    import importlib

    from dossier import cli as cli_module
    cli_module = importlib.reload(cli_module)

    runner = CliRunner()
    assert runner.invoke(cli_module.cli, ["db", "upgrade"]).exit_code == 0
    assert runner.invoke(
        cli_module.cli, ["projects", "add", "quaternionmedia/qmcp"]).exit_code == 0

    payload_file = tmp_path / "deltas.json"
    payload_file.write_text(json.dumps(payloads), encoding="utf-8")
    result = runner.invoke(
        cli_module.cli, ["deltas", "ingest", str(payload_file), "--write"])
    assert result.exit_code == 0, result.output
    return database, cli_module


def _payload(**delta):
    row = {"name": "tag-claims-does-not-pass", "title": "t", "phase": "brainstorm",
           "delta_type": "chore", "priority": "high"}
    row.update(delta)
    return {
        "schema": SCHEMA,
        "project": "quaternionmedia/qmcp",
        "delta": row,
        "links": [
            {"link_type": "invocation", "target_id": None, "target_name": "abc-123"},
            {"link_type": "address", "target_id": None,
             "target_name": "quaternionmedia/qmcp/delta/tag-claims-does-not-pass"},
        ],
    }


def _links(database):
    import sqlite3

    connection = sqlite3.connect(str(database))
    try:
        return sorted(connection.execute(
            "select link_type, target_name from delta_link"))
    finally:
        connection.close()


def test_a_payloads_links_are_stored(tmp_path, monkeypatch):
    database, _ = _run_ingest(tmp_path, [_payload()], monkeypatch)
    assert _links(database) == [
        ("address", "quaternionmedia/qmcp/delta/tag-claims-does-not-pass"),
        ("invocation", "abc-123"),
    ]


def test_ingesting_the_same_payload_twice_does_not_duplicate_a_link(tmp_path, monkeypatch):
    """A harness emits its state on every run, so re-ingesting is ordinary.

    Mutation: append without checking and this doubles.
    """
    database, cli_module = _run_ingest(tmp_path, [_payload()], monkeypatch)
    from click.testing import CliRunner

    payload_file = tmp_path / "deltas.json"
    again = CliRunner().invoke(
        cli_module.cli, ["deltas", "ingest", str(payload_file), "--write"])
    assert again.exit_code == 0, again.output
    assert len(_links(database)) == 2


def test_a_delta_whose_fields_did_not_change_still_gains_a_new_link(tmp_path, monkeypatch):
    """The case the first fix missed.

    Links were written only on `create` and `update`, so an unchanged delta
    skipped the pass entirely -- and a second run of the same failing check
    produces exactly that: the same delta, a new invocation. The rows that
    accumulate were the rows being dropped.
    """
    database, cli_module = _run_ingest(tmp_path, [_payload()], monkeypatch)
    from click.testing import CliRunner

    second = _payload()
    second["links"] = [
        {"link_type": "invocation", "target_id": None, "target_name": "def-456"}]
    payload_file = tmp_path / "second.json"
    payload_file.write_text(json.dumps([second]), encoding="utf-8")

    result = CliRunner().invoke(
        cli_module.cli, ["deltas", "ingest", str(payload_file), "--write"])
    assert result.exit_code == 0, result.output
    assert "already matching" in result.output, "the delta itself is unchanged"
    assert ("invocation", "def-456") in _links(database)
