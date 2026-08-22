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

# WEIGHT, AT THIS WINDOW'S RESOLUTION. A page can draw a line 3.7 times thicker
# than another; a terminal has a handful of characters and no half-steps, so a
# continuous weight lands in bands. That is the resolution difference doing its
# job -- both windows draw the same edge, one of them coarsely.
#
# The bands are stated here rather than computed from the data, because a scale
# that rescaled itself per graph would make two readings incomparable: the same
# edge would look strong beside weak company and weak beside strong.
WEIGHT_BANDS = (
    (0.30, "==>", "strong"),
    (0.10, "-->", "moderate"),
    (0.00, "..>", "faint"),
)

UNMEASURED = "-?>"
"""**NOT THE FAINT GLYPH.** An unmeasured edge drawn as faint asserts weakness
nobody established. A reader must be able to tell "we looked and it is slight"
from "nobody looked", because the second is a gap in the evidence and the first
is a finding."""


# WHAT THIS WINDOW CAN ACTUALLY CARRY, DECLARED AGAINST THE HARNESS'S MAPPING.
#
# The harness declares four channels: line weight for strength, line style for
# measured, line colour for relation kind, node shape for box kind. A terminal
# has one glyph per edge, so weight and style land in the *same* three
# characters -- and colour cannot be relied on at all.
#
# **THAT COLLISION IS RESOLVED IN FAVOUR OF THE AXIS THAT MUST NOT BE LOST.**
# `measured` wins the glyph: `-?>` is unmeasured whatever its strength, because
# an unmeasured edge drawn as faint asserts weakness nobody established. Only
# once an edge is known to be measured do the bands encode strength.
#
# Colour is dropped outright and the relation kind moves onto the glyph with
# it -- `--x` for refusal, `<->` for feedback. Nothing is folded silently:
# `Drawn.dropped` names every channel this window could not carry.
CARRIES = {
    "line_weight": "banded into three glyphs; a terminal has no half-steps",
    "line_style": "the same glyph, and it wins when the two collide",
    "node_shape": "the box brackets -- (input) <gate> [worker] {store}",
}

CANNOT_CARRY = {
    "line_colour": "a terminal may have no colour and a reader may not see it; "
                   "relation kind rides the glyph instead",
}


@dataclass(frozen=True)
class Drawn:
    """One rendering, and what it had to leave out.

    `dropped` is carried rather than discarded: a window that silently showed
    less would leave a reader thinking they had seen the whole description.
    """

    lines: tuple[str, ...]
    dropped: tuple[str, ...] = ()
    channels_dropped: tuple[str, ...] = ()
    """Visual channels this window could not carry. Named rather than omitted:
    a reader comparing this with the page needs to know which axes are missing
    here, not to discover it by the two disagreeing."""

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
        return Drawn(tuple(lines), tuple(dropped), tuple(CANNOT_CARRY))

    for arrow in arrows:
        left = boxes.get(arrow.get("from"), {"label": arrow.get("from"),
                                             "kind": "worker"})
        right = boxes.get(arrow.get("to"), {"label": arrow.get("to"),
                                            "kind": "worker"})
        glyph = _glyph(arrow)
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

    weighed = [a for a in arrows if a.get("basis")]
    if weighed:
        lines.append("")
        for arrow in weighed:
            weight = arrow.get("weight")
            shown = "unmeasured" if weight is None else f"{weight:.0%}"
            target = boxes.get(arrow.get("to"), {}).get("label", arrow.get("to"))
            lines.append(f"  {target}: {shown} -- {arrow['basis']}")

    notes = [b for b in boxes.values() if b.get("note")]
    if notes:
        lines.append("")
        for box in notes:
            lines.append(f"  {box['label']}: {box['note']}")

    # The count is already inside the box as `label xN`; a second line saying
    # it would be the same fact twice, and two places for it to disagree.

    return Drawn(tuple(lines), tuple(dropped), tuple(CANNOT_CARRY))


def _glyph(arrow: dict[str, Any]) -> str:
    """The arrow, banded by weight where a weight was measured.

    Kind wins over weight: a refusal is drawn as a refusal however strong it
    is, because "this path is not taken" and "this path is well travelled" are
    not points on one scale.
    """
    kind = arrow.get("kind", "flow")
    if kind != "flow":
        return ARROWS.get(kind, "-->")
    if "weight" not in arrow:
        return ARROWS["flow"]
    weight = arrow.get("weight")
    if weight is None:
        return UNMEASURED
    for floor, glyph, _ in WEIGHT_BANDS:
        if weight >= floor:
            return glyph
    return ARROWS["flow"]


def band_of(weight: float | None) -> str:
    """The word for a weight, for a legend or a row a reader can sort."""
    if weight is None:
        return "unmeasured"
    for floor, _, name in WEIGHT_BANDS:
        if weight >= floor:
            return name
    return "faint"


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
    return Drawn(tuple(lines), tuple(dict.fromkeys(dropped)),
                 tuple(CANNOT_CARRY))


# --- the same shape, as mermaid -----------------------------------------------
#
# **A DRAWING THAT CAN LEAVE THE TERMINAL.** The text above is this window's
# resolution and nothing else can read it. Mermaid is a format a page, a
# README, a pull request comment and a documentation site all render, so the
# same topology can be looked at by somebody who is not sitting in front of
# this panel -- without either window inventing a second description.
#
# **IT IS A THIRD RENDERING OF THE SAME DOCUMENT, NOT A NEW DESCRIPTION.** Same
# boxes, same arrows, same order, same measured/unmeasured distinction. What
# mermaid adds is that a renderer somewhere else can lay it out; what it must
# not add is a judgement the harness did not send.

MERMAID_SHAPES = {
    # Mermaid's node syntax carries kind the way the terminal's brackets do.
    "input": ("([", "])"),
    "output": ("([", "])"),
    "gate": ("{{", "}}"),
    "worker": ("[", "]"),
    "store": ("[(", ")]"),
}
MERMAID_DEFAULT = ("[", "]")

MERMAID_LINKS = {
    # `-->` measured, `-.->` unmeasured, `--x` refused. The dotted line is
    # mermaid's own idiom for "not a normal flow", which is the closest thing
    # it has to the terminal's `-?>`.
    "measured": "-->",
    "unmeasured": "-.->",
    "refusal": "--x",
    "feedback": "<-->",
}


def _mermaid_id(box_id: str) -> str:
    """A node id mermaid will accept. Non-alphanumerics become underscores."""
    cleaned = "".join(c if c.isalnum() else "_" for c in str(box_id))
    return cleaned or "n"


def _mermaid_text(value: str) -> str:
    """Label text, with the characters that end a mermaid node removed.

    Quotes and brackets in a label close the node early and produce a diagram
    that renders as garbage rather than failing -- so they are replaced rather
    than escaped, because a label is a name and not markup.
    """
    return (str(value or "")
            .replace('"', "'").replace("[", "(").replace("]", ")")
            .replace("{", "(").replace("}", ")").replace("|", "/"))


def as_mermaid(payload: dict[str, Any], direction: str = "LR") -> str:
    """The topology as mermaid `flowchart` source.

    **THE UNMEASURED DISTINCTION SURVIVES THE FORMAT.** An edge nobody measured
    is dotted, never thin -- the same rule every other window here obeys, and
    the reason a `weight` of null is sent instead of a zero. A mermaid diagram
    that drew it as a normal arrow would be the one rendering in which the
    distinction was lost.

    Returns source, not a picture. Nothing here renders mermaid; the point is
    that many things elsewhere do.
    """
    lines = [f"flowchart {direction}"]

    for box in payload.get("boxes") or []:
        opener, closer = MERMAID_SHAPES.get(str(box.get("kind") or ""),
                                            MERMAID_DEFAULT)
        label = _mermaid_text(box.get("label"))
        note = _mermaid_text(box.get("note"))
        count = box.get("count")
        if count:
            label = f"{label} ({count})"
        lines.append(f'    {_mermaid_id(box.get("id"))}{opener}"{label}"{closer}')
        if note and note != label:
            # The address, as a mermaid click target. A reader following the
            # diagram somewhere else gets the same address the panel shows.
            lines.append(f'    click {_mermaid_id(box.get("id"))} "{note}"')

    for arrow in payload.get("arrows") or []:
        kind = str(arrow.get("kind") or "flow")
        weight = arrow.get("weight")
        if kind in ("refusal", "feedback"):
            link = MERMAID_LINKS[kind]
        elif weight is None:
            link = MERMAID_LINKS["unmeasured"]
        else:
            link = MERMAID_LINKS["measured"]

        label = _mermaid_text(arrow.get("label"))
        if weight is None and kind == "flow":
            # Said in words, because a dotted line alone does not say why.
            label = f"{label} (unmeasured)".strip()
        elif weight is not None:
            label = f"{label} {float(weight):.0%}".strip()

        middle = f"|{label}|" if label else ""
        lines.append(f'    {_mermaid_id(arrow.get("from"))} '
                     f'{link}{middle} {_mermaid_id(arrow.get("to"))}')

    return "\n".join(lines)


# --- the same shape, as a flow with links -------------------------------------


def draw_flow(payload: dict[str, Any], width: int = 76,
              link: bool = True) -> Drawn:
    """The topology as a flow of boxes, with each box a link to its address.

    **A LIST OF ARROWS IS NOT A FLOWCHART.** `draw` renders one arrow per line,
    which is exact and reads as a table. This lays the boxes out in the order
    the harness sent them, draws the connectors between them, and hangs each
    box's address off it as something a reader can follow.

    `link=False` produces the same drawing without markup, for anywhere that is
    not a Textual widget -- a file, a pull request body, a terminal that has no
    handler for a click.

    **THE LINK IS THE ADDRESS, NOT A GUESS AT ONE.** A box's `note` is the
    address the harness sent; nothing here derives a URL, because a window that
    invented a destination would send readers somewhere the harness never named.
    """
    boxes = payload.get("boxes") or []
    arrows = payload.get("arrows") or []
    by_id = {b["id"]: b for b in boxes}
    lines: list[str] = []
    dropped: list[str] = []

    head = f"{payload.get('topology', '?')}  |  level {payload.get('level', '?')}"
    status = payload.get("status", "")
    if status and status != "runs":
        head += f"  |  {status.upper()}"
    lines.append(head)
    caption = payload.get("caption", "")
    if caption:
        lines.append(f"  {caption}")
    lines.append("")

    # Outgoing arrows per box, in the order they arrived. Order is the
    # harness's; sorting here would be this window imposing a reading.
    out: dict[str, list[dict]] = {}
    for arrow in arrows:
        out.setdefault(str(arrow.get("from")), []).append(arrow)

    for box in boxes:
        box_id = str(box.get("id"))
        lines.append(f"  {_linked(box, link)}")
        going = out.get(box_id, [])
        for index, arrow in enumerate(going):
            last = index == len(going) - 1
            elbow = "'--" if last else "|--"
            target = by_id.get(str(arrow.get("to")), {})
            glyph = _glyph(arrow)
            label = str(arrow.get("label") or "")
            weight = arrow.get("weight")
            # The number in words beside the glyph, because a band is coarse
            # and a reader comparing two windows needs the figure.
            measure = ("unmeasured" if weight is None
                       else f"{float(weight):.0%}")
            lines.append(
                f"  {elbow} {glyph} {_linked(target, link)}"
                f"   {label}  [{measure}]".rstrip())
        if going:
            lines.append("")

    # Boxes nothing points at and that point at nothing are still boxes. A
    # renderer that dropped them would be quietly deciding they do not count.
    reached = {str(a.get("to")) for a in arrows} | set(out)
    lonely = [b for b in boxes if str(b.get("id")) not in reached]
    if lonely:
        lines.append("  not connected to anything the harness sent:")
        for box in lonely:
            lines.append(f"    {_linked(box, link)}")
        lines.append("")

    # Named rather than omitted, as `draw` does: a reader comparing this with
    # the web view needs to know which axes this window cannot carry.
    dropped.append("line_colour")
    return Drawn(lines=tuple(lines), channels_dropped=tuple(dropped))


def _linked(box: dict[str, Any], link: bool) -> str:
    """One box, drawn as its kind, linked to its address when there is one."""
    left, right = EDGES.get(str(box.get("kind") or "worker"), ("[", "]"))
    label = str(box.get("label") or "?")
    count = box.get("count")
    if count:
        label = f"{label} {count}"
    drawn = f"{left}{label}{right}"

    note = str(box.get("note") or "")
    if not link or not note:
        return drawn if not note else f"{drawn}   {note}"
    # Textual console markup. The address is both the label of the link and
    # what it opens, so a reader who cannot click still sees where it goes.
    return f"[@click=app.open_address('{note}')]{drawn}[/]   {note}"
