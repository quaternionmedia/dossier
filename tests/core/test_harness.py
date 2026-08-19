"""Reading a harness's own report, and what it declines to infer."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from dossier import harness
from dossier.models.harness import HarnessInvocation, HarnessSnapshot


def payload(**overrides) -> dict:
    document = {
        "schema": 1,
        "project": "quaternionmedia/qmcp",
        "database": "/somewhere/qmcp.db",
        "totals": {"invocations": 55, "failures": 0,
                   "human_requests": 19, "human_responses": 6, "tables": 18},
        "by_tool": {"echo": 26},
        "by_status": {"SUCCESS": 55},
        "recent": [
            {"address": "quaternionmedia/qmcp/invocation/aaa", "tool_name": "echo",
             "status": "SUCCESS", "duration_ms": 3, "created_at": "2026-02-15 17:57:10",
             "error": None},
        ],
    }
    document.update(overrides)
    return document


@pytest.fixture()
def session():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def lookup_for(session):
    def lookup(address):
        return session.exec(
            select(HarnessInvocation).where(HarnessInvocation.address == address)
        ).first()
    return lookup


# --- reading -----------------------------------------------------------------


def test_a_payload_of_the_wrong_schema_is_refused(session):
    verdicts = harness.plan(payload(schema=99), lookup_for(session))
    assert [v.state for v in verdicts] == ["refused"]
    assert "schema 99" in verdicts[0].reason


def test_a_payload_missing_its_totals_is_refused(session):
    document = payload()
    del document["totals"]
    verdicts = harness.plan(document, lookup_for(session))
    assert verdicts[0].state == "refused"
    assert "totals" in verdicts[0].reason


def test_a_row_without_an_address_is_not_stored(session):
    """An invented identity is one that will not match the same row next time."""
    document = payload(recent=[{"tool_name": "echo"}, 
                               {"address": "a/b/invocation/x", "tool_name": "echo"}])
    assert [row["address"] for row in harness.invocations_of(document)] == \
        ["a/b/invocation/x"]


def test_totals_are_read_verbatim(session):
    assert harness.totals_of(payload()) == {
        "invocations": 55, "failures": 0, "human_requests": 19, "human_responses": 6}


def test_the_excerpt_does_not_become_the_totals(session):
    """The payload carries one recent row and reports fifty-five invocations.
    Recomputing from the rows would report the size of the excerpt."""
    document = payload()
    assert len(harness.invocations_of(document)) == 1
    assert harness.totals_of(document)["invocations"] == 55


# --- ingesting ---------------------------------------------------------------


def test_a_first_read_is_all_new(session):
    verdicts = harness.plan(payload(), lookup_for(session))
    assert [v.state for v in verdicts] == ["new", "new"]


def test_a_changed_status_is_a_disagreement_not_a_correction(session):
    session.add(HarnessInvocation(address="quaternionmedia/qmcp/invocation/aaa",
                                  project="quaternionmedia/qmcp",
                                  tool_name="echo", status="FAILURE"))
    session.commit()
    verdicts = harness.plan(payload(), lookup_for(session))
    differing = [v for v in verdicts if v.state == "differs"]
    assert differing
    assert "status" in differing[0].differences[0]


def test_an_unchanged_row_reads_as_matching(session):
    session.add(HarnessInvocation(address="quaternionmedia/qmcp/invocation/aaa",
                                  project="quaternionmedia/qmcp",
                                  tool_name="echo", status="SUCCESS"))
    session.commit()
    states = [v.state for v in harness.plan(payload(), lookup_for(session))]
    assert "same" in states


def test_the_report_says_nothing_was_written(session):
    text = harness.render(harness.plan(payload(), lookup_for(session)), written=False)
    assert "Nothing was written" in text
    assert "--write" in text


def test_the_report_states_that_nothing_is_deleted(session):
    """The payload is an excerpt by construction, so absence means nothing."""
    text = harness.render(harness.plan(payload(), lookup_for(session)), written=True)
    assert "not one that was removed" in text


def test_loading_a_list_is_refused(tmp_path: Path):
    path = tmp_path / "wrong.json"
    path.write_text(json.dumps([{"schema": 1}]), encoding="utf-8")
    with pytest.raises(ValueError):
        harness.load(path)
