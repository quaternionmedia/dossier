"""The delta-link graph: a repository's deltas and links as a drawable document.

Pure over rows, so these hand `build` plain objects rather than a database --
the same freedom the function was written for, and the reason a test can assert
the nesting without seeding SQL.
"""

from __future__ import annotations

from types import SimpleNamespace

from dossier import delta_graph, topology


def _delta(id, name, phase="implementation"):
    return SimpleNamespace(id=id, name=name, phase=phase)


def _link(delta_id, link_type, target_id=None, target_name=None):
    return SimpleNamespace(delta_id=delta_id, link_type=link_type,
                           target_id=target_id, target_name=target_name)


def test_every_delta_is_a_box_labelled_by_name():
    graph = delta_graph.build(
        [_delta(1, "add-dark-mode"), _delta(2, "fix-auth")], [], name="app")
    labels = {b["label"] for b in graph.payload["boxes"]}
    assert labels == {"add-dark-mode", "fix-auth"}


def test_a_link_becomes_an_arrow_to_a_target_box():
    graph = delta_graph.build(
        [_delta(1, "add-dark-mode")],
        [(1, _link(1, "pr", target_id=42))],
        name="app")
    assert graph.payload["arrows"], "the link drew no arrow"
    arrow = graph.payload["arrows"][0]
    assert arrow["from"] == "delta-1"
    target = {b["id"]: b for b in graph.payload["boxes"]}[arrow["to"]]
    assert "pr" in target["label"] and "42" in target["label"]


def test_a_delta_that_links_a_delta_nests_it():
    """The self-nesting the abstraction is built on: a delta-to-delta link is
    an arrow between two delta boxes, not an edge to a foreign node."""
    graph = delta_graph.build(
        [_delta(1, "epic"), _delta(2, "sub-task")],
        [(1, _link(1, "delta", target_id=2))],
        name="app")
    arrow = graph.payload["arrows"][0]
    assert arrow["from"] == "delta-1" and arrow["to"] == "delta-2"
    # Both ends are among the repository's own deltas, so no extra box was made.
    assert len([b for b in graph.payload["boxes"]
                if b["id"].startswith("delta-")]) == 2


def test_an_unlinked_delta_is_standalone_not_dropped():
    """`draw` is one line per edge, so a delta no arrow touches is not in the
    drawing. It must be reported, because the pane beside it claims to show the
    repository's deltas."""
    graph = delta_graph.build(
        [_delta(1, "linked"), _delta(2, "lonely")],
        [(1, _link(1, "branch", target_name="feat/x"))],
        name="app")
    assert graph.standalone == ("lonely",)


def test_the_payload_draws_without_error():
    """The whole point of matching the topology document: `draw` renders it
    with no special-casing, so the two panes read in one notation."""
    graph = delta_graph.build(
        [_delta(1, "epic"), _delta(2, "sub")],
        [(1, _link(1, "delta", target_id=2)),
         (2, _link(2, "pr", target_id=7))],
        name="app")
    drawn = topology.draw(graph.payload, width=48)
    text = drawn.text()
    assert "epic" in text and "sub" in text and "pr #7" in text


def test_a_link_to_a_delta_outside_the_reading_still_draws():
    """A delta may link one this repository's reading does not hold; it becomes
    a box named by its id rather than crashing on a missing node."""
    graph = delta_graph.build(
        [_delta(1, "here")],
        [(1, _link(1, "delta", target_id=99))],
        name="app")
    labels = {b["label"] for b in graph.payload["boxes"]}
    assert "delta #99" in labels
