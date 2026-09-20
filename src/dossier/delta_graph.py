"""A repository's deltas and their links, as a boxes-and-arrows document.

**A THREAD IS A DELTA AND DELTAS COMPOSE DELTAS** --
`governance/qm/records/DRAFT-deltas-compose.md` -- so a repository's in-flight
work is a graph: the deltas are the nodes, their `DeltaLink` rows are the edges,
and a delta that links another delta *nests* it. This builds that graph as the
same `{boxes, arrows}` document `dossier.topology` already draws, so the delta
graph and the harness topology read in one vocabulary when they sit side by side
on the Dossier tab.

**dossier's OWN data, no seam crossed.** Unlike the harness topology this needs
no `qmcp` process running: every fact in it is a row this database already
holds. The two panes answer the same question -- how does this repository's work
connect -- from the two sides that can, and either can be read with the other
down.

**WHAT draw() DOES NOT DRAW, NAMED RATHER THAN DROPPED.** `dossier.topology.draw`
emits one line per arrow, so a delta with no recorded link is not in the drawing
at all -- it would be silently absent. `standalone` carries those names back so
the caller can say "these appear only in the table", which is true: the deltas
table above the graph lists every delta, linked or not. The graph is the
connections; the table is the census.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# A link's kind, in the box brackets `dossier.topology` draws by `kind`, plus
# the word that says which bracketed thing it is when a bracket is shared: a
# store `{...}` holds both a branch and a doc, so the label carries the noun.
_TARGET: dict[str, tuple[str, str]] = {
    "pr": ("gate", "pr"),
    "issue": ("input", "issue"),
    "branch": ("store", "branch"),
    "doc": ("store", "doc"),
}


def _phase(delta: Any) -> str:
    phase = getattr(delta, "phase", None)
    return getattr(phase, "value", None) or str(phase or "--")


@dataclass(frozen=True)
class Graph:
    """The drawable document, and what it could not carry into the drawing.

    `payload` goes to `dossier.topology.draw` unchanged. `standalone` is the
    names of the deltas that no arrow touches -- present in the repository, and
    in the deltas table, but not in a drawing that is one line per edge.
    """

    payload: dict[str, Any]
    standalone: tuple[str, ...]


def build(deltas: Any, links: Any, *, name: str) -> Graph:
    """Turn a project's deltas and links into a topology document.

    `deltas`: the `ProjectDelta` rows that are the nodes.
    `links`: `(delta_id, DeltaLink)` pairs -- every link hanging off those
    deltas. Pure over rows already read, so it draws without a database and a
    test can hand it plain objects.
    """
    by_id = {d.id: d for d in deltas}
    boxes: dict[str, dict[str, Any]] = {}
    arrows: list[dict[str, Any]] = []
    connected: set[str] = set()

    for delta in deltas:
        box_id = f"delta-{delta.id}"
        boxes[box_id] = {
            "id": box_id,
            "label": delta.name,
            "kind": "worker",
            "note": _phase(delta),
        }

    for delta_id, link in links:
        src = f"delta-{delta_id}"
        if src not in boxes:
            # A link off a delta outside this reading; its own repository draws
            # it, not this one.
            continue
        if link.link_type == "delta":
            target = f"delta-{link.target_id}"
            if target not in boxes:
                known = by_id.get(link.target_id)
                boxes[target] = {
                    "id": target,
                    "label": known.name if known else f"delta #{link.target_id}",
                    "kind": "worker",
                }
        else:
            kind, noun = _TARGET.get(link.link_type, ("worker", link.link_type))
            handle = link.target_name or (
                f"#{link.target_id}" if link.target_id is not None else "?")
            target = f"{link.link_type}-{handle}"
            if target not in boxes:
                boxes[target] = {"id": target, "label": f"{noun} {handle}",
                                 "kind": kind}
        # No weight: a recorded link is a fact, not a measured strength, and
        # `draw` renders a weightless flow as a solid `-->`. Drawing it faint
        # would assert a slightness nobody established -- the same distinction
        # the topology's `-?>` guards.
        arrows.append({"from": src, "to": target, "kind": "flow",
                       "label": link.link_type})
        connected.add(src)
        connected.add(target)

    standalone = tuple(
        boxes[f"delta-{d.id}"]["label"]
        for d in deltas
        if f"delta-{d.id}" not in connected
    )
    payload = {
        "topology": name,
        "level": "deltas",
        "caption": "recorded links, not measured edges: a delta that links a "
                   "delta nests it",
        "boxes": list(boxes.values()),
        "arrows": arrows,
    }
    return Graph(payload, standalone)
