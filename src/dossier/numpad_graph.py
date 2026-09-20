"""A graph seam drawn as a numpad -- the terminal's resolution for a graph.

**TWO WINDOWS, TWO RESOLUTIONS.** `codecartographer` renders a graph on a canvas
with hundreds of nodes, curved edges, palettes and a radial menu. This is the
other window onto the same artifact, and a terminal is not a canvas. So it
renders a graph seam as the menu this application already draws in the terminal:
rad's numpad, eight cells around a centre.

**THE GEOMETRY IS NOT REINVENTED HERE.** The cells, their positions and the
order they fill are `dossier.rad.numpad` -- the same layout the keystroke menu
uses, so a reader who knows where `7` is on the menu knows where it is here.
This module adds only the choice of *which* nodes and the drawing of the grid;
`rad.numpad.place` decides where they land and enforces the limit.

**THE LIMIT IS THE POINT, AND IT IS EIGHT.** rad's numpad holds eight items
around a centre that is never an item -- `place` raises on a ninth rather than
drop it, because a menu missing an item looks like one that never had it. A
graph is the same: at most eight nodes are drawn, the busiest first, and the
render says how many it stood for. A picture that silently drops the rest is the
private-name leak in another domain -- a reading that looks complete and is not.

**THE CENTRE IS THE ORIGIN, NEVER A NODE.** rad reserves the centre to back out
of a menu; here it holds nothing and marks where the eight are measured from.
Putting the busiest node in the middle would be a different, larger visual
language -- an ego graph -- and this window is deliberately the small one.

**THIS WINDOW ONLY CONSUMES.** It reads the seam a producer emits -- the gjgf
graph `codecartographer` serves, or any `{nodes, edges}` object of that shape --
and computes no layout beyond which eight nodes. The producer decided what the
graph says; this decides only how eight cells show it.
"""

from __future__ import annotations

from typing import Any

from dossier.rad import numpad

# rad's numpad holds this many items around its centre. Named from the geometry
# rather than repeated as a literal, so the two cannot drift.
CELLS = len(numpad.PLACEMENT)

_CELL_W = 12
# The three display rows, top to bottom, read straight off rad's cell positions.
_ROWS = tuple(
    tuple(numpad.CELL_AT[(col, row)] for col in range(3))
    for row in range(3)
)


def _nodes_and_edges(seam: Any) -> tuple[dict[str, dict], list[tuple[str, str]]]:
    """Read the two shapes a graph seam arrives in.

    gjgf keys its nodes by id in a dict; a hand-written seam may hand a list.
    Either way this returns nodes as `{id: attrs}` and edges as `(source,
    target)` pairs, dropping an edge that names a node the seam never declared
    rather than inventing the node -- the rule the two-views comparison follows.
    """
    graph = seam.get("graph", seam) if isinstance(seam, dict) else {}
    raw_nodes = graph.get("nodes", {})
    nodes: dict[str, dict] = {}
    if isinstance(raw_nodes, dict):
        for nid, attrs in raw_nodes.items():
            nodes[str(nid)] = attrs if isinstance(attrs, dict) else {}
    else:  # a list of node objects, each carrying its own id
        for item in raw_nodes:
            if isinstance(item, dict) and item.get("id") is not None:
                nodes[str(item["id"])] = item

    edges: list[tuple[str, str]] = []
    for e in graph.get("edges", []):
        if not isinstance(e, dict):
            continue
        src, tgt = e.get("source"), e.get("target")
        if src is None or tgt is None:
            continue
        src, tgt = str(src), str(tgt)
        if src in nodes and tgt in nodes:
            edges.append((src, tgt))
    return nodes, edges


def _label(nid: str, attrs: dict) -> str:
    """A node's label, however the seam spelled it. gjgf puts attributes under
    `metadata`; a flatter seam puts them at the top. The id is the last resort,
    never a blank cell."""
    meta = attrs.get("metadata", {}) if isinstance(attrs.get("metadata"), dict) else {}
    return str(attrs.get("label") or meta.get("label")
               or attrs.get("filename") or meta.get("filename") or nid)


def _degree(nodes: dict[str, dict], edges: list[tuple[str, str]]) -> dict[str, int]:
    deg = {nid: 0 for nid in nodes}
    for src, tgt in edges:
        deg[src] += 1
        deg[tgt] += 1
    return deg


def _place(nodes: dict[str, dict], deg: dict[str, int]) -> dict[int, str]:
    """Assign up to eight nodes to numpad cells, the busiest first.

    Ties break on id so one graph always lands the same way -- a render that
    moved on re-run would be two pictures of one thing. `rad.numpad.place`
    owns the cell order and the eight-item limit; this only ranks the nodes and
    takes the first eight, because a ninth would make `place` raise.
    """
    ranked = sorted(nodes, key=lambda n: (-deg[n], n))[:CELLS]
    placement = numpad.place(len(ranked))
    return {cell: ranked[index] for cell, index in placement.by_cell.items()}


def _trim(text: str, width: int) -> str:
    return text if len(text) <= width else text[: width - 1] + "…"


def render(seam: Any, title: str = "") -> str:
    """The numpad render of a graph seam, as text a terminal prints."""
    nodes, edges = _nodes_and_edges(seam)
    deg = _degree(nodes, edges)
    placement = _place(nodes, deg)
    cell_of = {nid: cell for cell, nid in placement.items()}

    lines: list[str] = []
    if title:
        lines.append(title)

    bar = "  +" + "+".join(["-" * (_CELL_W + 2)] * 3) + "+"
    for row in _ROWS:
        lines.append(bar)
        cells = []
        for cell in row:
            nid = placement.get(cell)
            if nid:
                body = f"{cell} {_trim(_label(nid, nodes[nid]), _CELL_W - 2)}"
            elif cell == numpad.BACK:
                body = "· origin"  # the centre marks where the eight are measured from
            else:
                body = str(cell)
            cells.append(f" {body:<{_CELL_W}} ")
        lines.append("  |" + "|".join(cells) + "|")
    lines.append(bar)

    # Edges, spoken in numpad addresses -- only those between two placed nodes,
    # so the legend never points at a cell the grid does not show.
    shown = sorted({
        tuple(sorted((cell_of[s], cell_of[t])))
        for s, t in edges if s in cell_of and t in cell_of
    })
    if shown:
        lines.append("  edges:  " + "  ".join(f"{a}-{b}" for a, b in shown))

    placed, total = len(placement), len(nodes)
    if total > CELLS:
        lines.append(f"  nodes:  {placed} of {total} "
                     f"(a numpad holds {CELLS} around a centre)")
    else:
        lines.append(f"  nodes:  {total}")
    return "\n".join(lines)
