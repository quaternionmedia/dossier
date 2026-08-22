"""The topology as mermaid, and as a flow with links.

**A THIRD RENDERING OF ONE DOCUMENT, NOT A THIRD DESCRIPTION.** The terminal
flow, the web graph and this mermaid source all come from the same payload. The
test that matters is that the one distinction the harness takes care to send —
an edge nobody measured, as `null` rather than `0` — survives every format it is
translated into. It is the distinction easiest to lose in a translation and the
only one that cannot be recovered afterwards.
"""

from __future__ import annotations

import pytest

from dossier.topology import UNMEASURED, as_mermaid, draw_flow


def payload(**over) -> dict:
    found = {
        "topology": "delegation", "level": 2,
        "caption": "one agent per repository", "status": "runs", "marks": [],
        "boxes": [
            {"id": "subject", "label": "work", "kind": "input",
             "note": "", "count": None},
            {"id": "g", "label": "route", "kind": "gate",
             "note": "", "count": None},
            {"id": "r0", "label": "worker", "kind": "worker",
             "note": "qm/dossier", "count": None},
            {"id": "r1", "label": "worker", "kind": "worker",
             "note": "qm/qmcp", "count": None},
        ],
        "arrows": [
            {"from": "subject", "to": "g", "label": "part-of", "kind": "flow",
             "weight": 0.9, "basis": "mentions"},
            {"from": "g", "to": "r0", "label": "crosses", "kind": "flow",
             "weight": 0.34, "basis": "mentions"},
            {"from": "g", "to": "r1", "label": "crosses", "kind": "flow",
             "weight": None, "basis": ""},
        ],
    }
    found.update(over)
    return found


# --- the distinction that must survive every format ---------------------------


def test_an_unmeasured_edge_is_dotted_and_says_so(payload_=None):
    """THE ONE THAT MATTERS.

    A dotted line is mermaid's idiom for "not a normal flow", and the word is
    there as well because a line style alone does not say *why*. A measured
    edge and an unmeasured one must never render the same.

    Mutation: draw a null weight with the measured arrow and this fails.
    """
    source = as_mermaid(payload())
    dotted = [line for line in source.splitlines() if "-.->" in line]

    assert len(dotted) == 1, source
    assert "unmeasured" in dotted[0]
    # And it is not merely a weak percentage.
    assert "0%" not in dotted[0]


def test_a_measured_edge_carries_its_figure():
    """A band is coarse; the figure is what makes two windows comparable."""
    source = as_mermaid(payload())
    assert "|part-of 90%|" in source
    assert "|crosses 34%|" in source


def test_a_measured_zero_is_not_drawn_as_unmeasured():
    """Somebody looked and found nothing. That is a finding, and the classic
    falsiness bug files it with the unlooked-at.

    Mutation: test `if not weight` instead of `is None` and this fails.
    """
    source = as_mermaid(payload(arrows=[
        {"from": "subject", "to": "g", "label": "crosses", "kind": "flow",
         "weight": 0.0, "basis": "mentions"}]))
    assert "-.->" not in source
    assert "0%" in source


# --- it is mermaid, not something that looks like it --------------------------


def test_it_is_a_flowchart_with_one_node_per_box():
    source = as_mermaid(payload())
    assert source.splitlines()[0].startswith("flowchart ")
    for box_id in ("subject", "g", "r0", "r1"):
        assert any(line.strip().startswith(box_id) for line in source.splitlines())


def test_each_kind_gets_its_own_node_shape():
    """A gate is a gate at any size, in every window.

    Mutation: render every box as a rectangle and this fails.
    """
    source = as_mermaid(payload())
    assert '([("work"' not in source          # not a mangled shape
    assert 'subject(["work"])' in source      # input
    assert 'g{{"route"}}' in source           # gate
    assert 'r0["worker"]' in source           # worker


def test_a_refusal_is_drawn_refused():
    """`--x` however heavily travelled the path it forbids."""
    source = as_mermaid(payload(arrows=[
        {"from": "g", "to": "r0", "label": "no worker", "kind": "refusal",
         "weight": 0.95, "basis": "m"}]))
    assert "--x" in source


def test_an_address_becomes_a_click_target():
    """A reader following the diagram elsewhere gets the same address the
    panel shows, rather than a name they must resolve themselves."""
    source = as_mermaid(payload())
    assert 'click r0 "qm/dossier"' in source


def test_a_label_cannot_close_its_own_node():
    """**A BRACKET IN A LABEL RENDERS AS GARBAGE RATHER THAN FAILING.** Mermaid
    ends a node at the first closing bracket, so a repository called `a]b`
    would produce a diagram nobody could read and no error anywhere.

    Mutation: stop replacing the closing characters and this fails.
    """
    source = as_mermaid(payload(boxes=[
        {"id": "x", "label": 'we"ird]{name}', "kind": "worker",
         "note": "", "count": None}]))
    body = [line for line in source.splitlines() if line.strip().startswith("x")][0]
    assert body.count("]") == 1, body
    assert '"' not in body.split('"', 1)[1].rsplit('"', 1)[0]


def test_an_empty_payload_is_still_valid_source():
    """A diagram with nothing in it is a diagram, and better than a traceback."""
    assert as_mermaid({}).strip() == "flowchart LR"


# --- the flow, and its links --------------------------------------------------


def test_the_flow_draws_connectors_rather_than_a_list_of_arrows():
    """`draw` renders one arrow per line, which reads as a table. This is the
    same information laid out as a flow.

    Mutation: emit one line per arrow and this fails.
    """
    text = draw_flow(payload(), link=False).text()
    assert "'--" in text or "|--" in text


def test_every_box_carries_its_address_as_a_link():
    """The address is what the harness sent; nothing here derives a URL.

    Mutation: drop the click markup and this fails.
    """
    text = draw_flow(payload(), link=True).text()
    assert "@click=app.open_address('qm/dossier')" in text
    # And the address is visible as well as clickable, for a reader who cannot.
    assert "qm/dossier" in text.replace(
        "@click=app.open_address('qm/dossier')", "")


def test_the_unlinked_drawing_carries_no_markup():
    """For a file, a pull request body, or a terminal with no click handler."""
    text = draw_flow(payload(), link=False).text()
    assert "@click" not in text
    assert "qm/dossier" in text


def test_the_flow_keeps_the_unmeasured_glyph():
    text = draw_flow(payload(), link=False).text()
    assert UNMEASURED in text
    assert "[unmeasured]" in text


def test_a_box_nothing_points_at_is_still_drawn():
    """A renderer that dropped it would be quietly deciding it does not count.

    Mutation: skip unconnected boxes and this fails.
    """
    text = draw_flow(payload(boxes=[
        {"id": "lonely", "label": "nobody", "kind": "worker",
         "note": "", "count": None}], arrows=[]), link=False).text()
    assert "nobody" in text
    assert "not connected" in text


def test_the_flow_names_the_channel_it_cannot_carry():
    """A reader comparing this with the web view needs to know which axes are
    missing here, not to discover it by the two disagreeing."""
    assert "line_colour" in draw_flow(payload()).channels_dropped
