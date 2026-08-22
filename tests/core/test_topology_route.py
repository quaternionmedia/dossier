"""The route to this window's own renderer.

**`dossier.topology` COULD DRAW AND NOTHING REACHED IT.** The renderer existed,
was tested, and was named by no command and no tab — so this front end had a
finished-looking feature nobody could run. The same shape was found in the other
front end on the same day, which is why it is worth a test rather than a fix.

THE TEST WORTH READING IS THE FIRST: a harness that is not answering must
produce a sentence and a non-zero exit, not a traceback and not an empty
drawing.
"""

from __future__ import annotations

import pytest
from click.testing import CliRunner

from dossier import threads
from dossier.cli import cli


def _payload():
    return {
        "topology": "delegation", "level": 2, "caption": "one per repository",
        "status": "runs", "marks": [],
        "boxes": [
            {"id": "subject", "label": "sweep", "kind": "input",
             "note": "", "count": None},
            {"id": "r0", "label": "dossier", "kind": "worker",
             "note": "qm/dossier", "count": None},
        ],
        "arrows": [
            {"from": "subject", "to": "r0", "label": "part-of", "kind": "flow",
             "weight": 0.9, "basis": "mentions"},
            {"from": "subject", "to": "r0", "label": "crosses", "kind": "flow",
             "weight": None, "basis": ""},
        ],
    }


def test_a_harness_that_is_not_answering_says_so_and_exits_non_zero(monkeypatch):
    """THE ONE THAT MATTERS.

    A front end whose backend is down is the ordinary case. It must name the
    problem, name the command that fixes it, and exit non-zero so a script can
    tell — and it must not draw anything, because an empty drawing states that
    this topology is empty.

    Mutation: exit 0 when the harness is unreachable and this fails.
    """
    monkeypatch.setattr(threads, "topology", lambda **kw: threads.Topology(
        False, "http://127.0.0.1:3141/v1/topology/shape/delegation",
        problem="nothing is answering at http://127.0.0.1:3141",
        remedy="`uv run qm dashboard --start harness`"))

    done = CliRunner().invoke(cli, ["topology"])
    assert done.exit_code == 1
    assert "nothing is answering" in done.output
    assert "qm dashboard --start harness" in done.output
    assert "-?>" not in done.output and "-->" not in done.output


def test_an_unmeasured_edge_is_drawn_as_unmeasured_and_counted(monkeypatch):
    """The one thing every window here is tested for.

    Mutation: draw a null weight as a thin line and this fails.
    """
    monkeypatch.setattr(threads, "topology", lambda **kw: threads.Topology(
        True, "fixture", payload=_payload(), source="topology"))

    done = CliRunner().invoke(cli, ["topology"])
    assert done.exit_code == 0
    assert "-?>" in done.output, "the unmeasured glyph never reached the screen"
    assert "1 of 2 edge(s) measured" in done.output


def test_a_fully_measured_topology_says_so_plainly(monkeypatch):
    payload = _payload()
    payload["arrows"][1]["weight"] = 0.2
    monkeypatch.setattr(threads, "topology", lambda **kw: threads.Topology(
        True, "fixture", payload=payload, source="thread archive", surveyed=128))

    done = CliRunner().invoke(cli, ["topology", "--subject", "dossier"])
    assert "every one of 2 edge(s) is measured" in done.output
    assert "thread archive" in done.output
    assert "128 thread(s) read" in done.output


def test_the_window_names_the_channels_it_cannot_carry(monkeypatch):
    """A reader comparing this with the web view needs to know which axes are
    missing here, not to discover it by the two disagreeing."""
    monkeypatch.setattr(threads, "topology", lambda **kw: threads.Topology(
        True, "fixture", payload=_payload()))

    done = CliRunner().invoke(cli, ["topology"])
    assert "cannot carry" in done.output


def test_listing_asks_the_harness_rather_than_hard_coding(monkeypatch):
    """A list written down here would drift from what the harness serves.

    Mutation: return a literal list and this fails.
    """
    monkeypatch.setattr(threads, "topologies", lambda **kw: ["alpha", "beta"])
    done = CliRunner().invoke(cli, ["topology", "--list"])
    assert done.exit_code == 0
    assert "alpha" in done.output and "beta" in done.output


def test_listing_with_no_harness_refuses_rather_than_printing_nothing(monkeypatch):
    """An empty list and an unreachable harness are opposite facts, and a
    silent empty listing states the first while meaning the second."""
    monkeypatch.setattr(threads, "topologies", lambda **kw: [])
    done = CliRunner().invoke(cli, ["topology", "--list"])
    assert done.exit_code == 1
    assert "not answering" in done.output


def test_a_subject_wins_over_a_kind():
    """Asking what the archive says about one project is the more specific
    request; sending both would leave the harness to guess."""
    import inspect

    source = inspect.getsource(threads.topology)
    assert 'if subject' in source and 'relations/' in source
