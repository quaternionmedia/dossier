"""This panel's window onto a topology. One of at least two.

**THE SHAPE IS THE HARNESS'S; THE DRAWING IS THIS PANEL'S.** `qmcp` describes a
topology as boxes and arrows with no coordinates, no glyphs and no colours.
This turns that into lines of text. `codecarto` will turn the same description
into a graph in a page. Neither window sees the other's drawing, and neither
description knows a terminal exists.

**THE SAME PIPELINE, AT THIS WINDOW'S RESOLUTION.** Both windows draw the flow
the harness described -- the same boxes, the same arrows, the same order. What
differs is how much of it each medium can resolve. A terminal has one dimension
of position and a handful of border styles, so a `note` becomes a line under the
shape and a `count` becomes a number inside it. A page has room for both at
once, and for layout that carries meaning.

**LOWER RESOLUTION, NOT A DIFFERENT PICTURE.** Somebody reading the terminal and
somebody reading the page are looking at one pipeline and should be able to talk
to each other about it without translating. So this window may render the
description coarsely; it may not render a *different* description, and it may
not add a dimension the harness did not send -- a renderer that ordered boxes by
importance would be drawing a judgement nobody recorded.

**A REFUSED SHAPE IS DRAWN REFUSED.** `council` is in the gallery with its
refusal on the arrow that carries it, because a gallery is where somebody
chooses and a chooser needs to see the one they must not use. Dropping it would
make this organisation's rule invisible at the moment it applies.

WHAT THIS CANNOT DO. Show a topology running. These are shapes, not traces --
`dossier.harness` and `qmcp.audit` are where a run is, and drawing a live flow
on top of a shape is the next thing rather than this thing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Border styles carry the kind, in characters, because a terminal may have no
# colour and a reader may not see it. The same reasoning as the rad menu's
# doubled and dotted rules.
EDGES = {
    "input": ("(", ")"),
    "output": ("(", ")"),
    "gate": ("<", ">"),
    "worker": ("[", "]"),
    "store": ("{", "}"),
}

ARROWS = {
    "flow": "-->",
    "feedback": "<->",
    "refusal": "--x",
}


@dataclass(frozen=True)
class Drawn:
    """One rendering, and what it had to leave out.

    `dropped` is carried rather than discarded: a window that silently showed
    less would leave a reader thinking they had seen the whole description.
    """

    lines: tuple[str, ...]
    dropped: tuple[str, ...] = ()

    def text(self) -> str:
        return "\n".join(self.lines)


def draw(payload: dict[str, Any], width: int = 76) -> Drawn:
    """One topology view, as lines.

    Takes the payload rather than the harness's classes: the two repositories
    do not import each other, and a renderer that needed `qmcp` installed would
    be a window that only opens when the thing it looks at is in the room.
    """
    boxes = {b["id"]: b for b in payload.get("boxes") or []}
    arrows = payload.get("arrows") or []
    lines: list[str] = []
    dropped: list[str] = []

    status = payload.get("status", "")
    marks = payload.get("marks") or []
    # ASCII SEPARATORS, FOR THE REASON `rad/ring.py` GIVES: box-drawing and
    # typographic characters are not encodable in cp1252, which is still what a
    # Windows console hands you. A middle dot rendered as a replacement
    # character in the first run of this.
    head = f"{payload.get('topology', '?')}  |  level {payload.get('level', '?')}"
    if status and status != "runs":
        head += f"  |  {status.upper()}"
    if marks:
        head += f"  |  {', '.join(marks)}"
    lines.append(head)

    caption = payload.get("caption") or ""
    if caption:
        lines.append(f"  {caption}")
    lines.append("")

    if not arrows:
        # Level 1: the parts, and deliberately nothing about order.
        for box in boxes.values():
            lines.append("  " + _box(box))
            if box.get("note"):
                lines.append(f"      {box['note']}")
        return Drawn(tuple(lines), tuple(dropped))

    for arrow in arrows:
        left = boxes.get(arrow.get("from"), {"label": arrow.get("from"),
                                             "kind": "worker"})
        right = boxes.get(arrow.get("to"), {"label": arrow.get("to"),
                                            "kind": "worker"})
        glyph = ARROWS.get(arrow.get("kind", "flow"), "-->")
        label = arrow.get("label") or ""
        line = f"  {_box(left)} {glyph} {_box(right)}"
        if label:
            line += f"   {label}"
        if len(line) > width:
            # Trimmed, and said. A silently cut line is a description a reader
            # believes they have read.
            dropped.append(f"a line was trimmed at {width} columns")
            line = line[:width - 3] + "..."
        lines.append(line)

    notes = [b for b in boxes.values() if b.get("note")]
    if notes:
        lines.append("")
        for box in notes:
            lines.append(f"  {box['label']}: {box['note']}")

    # The count is already inside the box as `label xN`; a second line saying
    # it would be the same fact twice, and two places for it to disagree.

    return Drawn(tuple(lines), tuple(dropped))


def _box(box: dict[str, Any]) -> str:
    left, right = EDGES.get(box.get("kind", "worker"), ("[", "]"))
    label = box.get("label", "?")
    if box.get("count"):
        label = f"{label} x{box['count']}"
    return f"{left}{label}{right}"


def draw_gallery(payloads: list[dict[str, Any]], width: int = 76) -> Drawn:
    """Every shape, one after another, in one view.

    One view rather than one per screen: the question a gallery answers is
    "which of these", and that is not answerable while looking at one of them.
    """
    lines: list[str] = []
    dropped: list[str] = []
    for index, payload in enumerate(payloads):
        if index:
            lines.append("")
            lines.append("  " + "-" * 30)
            lines.append("")
        drawn = draw(payload, width=width)
        lines.extend(drawn.lines)
        dropped.extend(drawn.dropped)
    return Drawn(tuple(lines), tuple(dict.fromkeys(dropped)))
