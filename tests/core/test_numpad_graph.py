"""The terminal renders a graph as rad's numpad: eight cells around a centre.

`codecartographer` draws the same seam on a canvas with no such limit; this is
the other window, and its resolution is rad's numpad. The tests that matter are
the ones that keep the limit honest and keep the geometry rad's, not a second
copy: eight nodes maximum, the centre never a node, the count told straight, and
the same seam drawn the same way twice.
"""

from __future__ import annotations

from dossier import numpad_graph
from dossier.rad import numpad


def _grid(seam: dict, **kw) -> str:
    return numpad_graph.render(seam, **kw)


def _gjgf(node_ids, edges):
    return {"graph": {
        "nodes": {str(n): {"metadata": {"label": f"repo-{n}"}} for n in node_ids},
        "edges": [{"source": str(s), "target": str(t)} for s, t in edges],
    }}


def test_a_graph_larger_than_eight_nodes_is_capped_and_says_so():
    """**THE HARD LIMIT, AND IT IS rad's.** rad's numpad holds eight items around
    a centre; a ninth would make `rad.numpad.place` raise. So the render places
    at most eight and reports the total, because a picture that silently drops
    the rest reads as a complete graph missing most of itself.

    Mutation: drop the `[:CELLS]` bound in `numpad_graph._place` and `place`
    raises on the ninth node -- the render breaks rather than lying, which is the
    limit doing its job one layer down.
    """
    edges = [(0, n) for n in range(1, 20)]  # node 0 is the hub
    seam = _gjgf(range(20), edges)
    nodes, e = numpad_graph._nodes_and_edges(seam)
    placement = numpad_graph._place(nodes, numpad_graph._degree(nodes, e))
    assert len(placement) == numpad_graph.CELLS == 8, "a numpad placed more than eight nodes"

    text = _grid(seam)
    assert "8 of 20" in text, "the render did not say how many nodes it stood for"


def test_the_centre_holds_no_node():
    """rad reserves the centre to back out of a menu; here it holds no node and
    marks the origin. The busiest node goes to a cell around it, never the
    middle."""
    seam = _gjgf(range(9), [(0, 1), (0, 2), (0, 3), (0, 4), (0, 5), (1, 2)])
    nodes, e = numpad_graph._nodes_and_edges(seam)
    placement = numpad_graph._place(nodes, numpad_graph._degree(nodes, e))
    assert numpad.BACK not in placement, "a node was placed in the reserved centre"
    assert "· origin" in _grid(seam), "the centre did not render as the origin"


def test_the_geometry_is_rads_not_a_second_copy():
    """The cells and their fill order come from `dossier.rad.numpad`, so the
    graph lands where the keystroke menu would put the same count of items."""
    seam = _gjgf(range(4), [(0, 1), (0, 2), (0, 3)])
    nodes, e = numpad_graph._nodes_and_edges(seam)
    placement = numpad_graph._place(nodes, numpad_graph._degree(nodes, e))
    # rad places four items at the cardinals: cells 8, 6, 2, 4.
    assert set(placement) == {8, 6, 2, 4}, "placement did not follow rad's PLACEMENT"


def test_an_edge_to_an_undeclared_node_is_dropped_not_invented():
    """A seam whose edge names a node it never declared is missing a node, not
    hiding one: the edge is dropped rather than conjuring the node."""
    seam = {"graph": {
        "nodes": {"a": {"label": "a"}, "b": {"label": "b"}},
        "edges": [{"source": "a", "target": "b"}, {"source": "a", "target": "ghost"}],
    }}
    nodes, edges = numpad_graph._nodes_and_edges(seam)
    assert set(nodes) == {"a", "b"}
    assert edges == [("a", "b")], "an edge to an undeclared node survived"


def test_a_flat_seam_without_the_gjgf_wrapper_still_reads():
    """The producer may hand the graph object itself, not wrapped in `graph`."""
    seam = {"nodes": {"x": {"label": "x"}}, "edges": []}
    nodes, _ = numpad_graph._nodes_and_edges(seam)
    assert set(nodes) == {"x"}
    assert "nodes:  1" in _grid(seam)


def test_the_same_seam_renders_the_same_way_twice():
    """A render that moved on re-run would be two pictures of one graph. Ties
    break on id, so placement is stable."""
    seam = _gjgf(range(8), [(0, 1), (2, 3), (4, 5)])
    assert _grid(seam) == _grid(seam)


def test_a_label_is_never_a_blank_cell():
    """A node with no label falls back to its id, not an empty cell."""
    seam = {"nodes": {"only-an-id": {}}, "edges": []}
    assert "only-an-id" in _grid(seam)
