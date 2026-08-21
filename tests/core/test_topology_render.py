"""The panel's window onto a shape the harness described.

THE TEST WORTH READING IS THE SECOND ONE. This window may show less than the
description carries. What it must never do is show more -- an invented
dimension is a judgement nobody recorded, drawn as though somebody had.
"""

from __future__ import annotations

from dossier.topology import ARROWS, EDGES, draw, draw_gallery


def payload(**over):
    base = {
        "topology": "delegation", "level": 2, "caption": "route by shape",
        "status": "runs", "marks": [],
        "boxes": [
            {"id": "in", "label": "work", "kind": "input", "note": "", "count": None},
            {"id": "r", "label": "route", "kind": "gate", "note": "", "count": None},
            {"id": "w", "label": "worker", "kind": "worker",
             "note": "one per shape", "count": None},
            {"id": "none", "label": "no worker", "kind": "output",
             "note": "named, never dropped", "count": None},
        ],
        "arrows": [
            {"from": "in", "to": "r", "label": "", "kind": "flow"},
            {"from": "r", "to": "w", "label": "shape a", "kind": "flow"},
            {"from": "r", "to": "none", "label": "unregistered", "kind": "refusal"},
        ],
    }
    base.update(over)
    return base


# --- it reads the description, not the harness --------------------------------


def test_it_draws_from_a_payload_and_imports_nothing_from_the_harness():
    """A window that needed `qmcp` installed would only open when the thing it
    looks at is in the room.

    Mutation: import `qmcp.topology_view` here and this fails wherever the
    harness is absent.
    """
    import pathlib

    import dossier.topology as module

    source = pathlib.Path(module.__file__).read_text(encoding="utf-8")
    assert "import qmcp" not in source
    assert "from qmcp" not in source


def test_a_refusal_is_never_drawn_as_a_flow():
    """THE ONE THAT MATTERS.

    Three arrow kinds, three glyphs. Merging refusal into flow would draw a
    path that nothing takes, which is worse than drawing no path.

    Mutation: map every kind to `-->` and this fails.
    """
    assert len({ARROWS["flow"], ARROWS["feedback"], ARROWS["refusal"]}) == 3
    text = draw(payload()).text()
    assert ARROWS["refusal"] in text


def test_the_kind_of_a_box_is_carried_in_characters_not_colour():
    """A terminal may have no colour and a reader may not see it -- the same
    reasoning the rad menu uses for its doubled and dotted borders."""
    text = draw(payload()).text()
    assert "(work)" in text, "an input"
    assert "<route>" in text, "a gate"
    assert "[worker]" in text, "a worker"


def test_every_declared_kind_has_a_border():
    for kind in ("input", "output", "gate", "worker", "store"):
        assert kind in EDGES


# --- what it says about itself ------------------------------------------------


def test_a_refused_shape_says_so_in_its_heading():
    text = draw(payload(status="refused", marks=["spends", "decides"])).text()
    assert "REFUSED" in text
    assert "spends" in text and "decides" in text


def test_a_running_shape_does_not_shout():
    """`runs` is the ordinary case and does not need a badge on every row."""
    assert "RUNS" not in draw(payload()).text()


def test_the_caption_is_shown_because_a_shape_without_one_is_a_diagram():
    assert "route by shape" in draw(payload()).text()


# --- what it had to leave out -------------------------------------------------


def test_a_trimmed_line_is_reported_rather_than_silently_cut():
    """A silently cut line is a description a reader believes they have read.

    Mutation: trim without recording and this fails.
    """
    wide = payload(arrows=[{"from": "in", "to": "r",
                            "label": "x" * 200, "kind": "flow"}])
    drawn = draw(wide, width=40)
    assert drawn.dropped, "nothing was reported as trimmed"
    assert all(len(line) <= 40 for line in drawn.lines)


def test_nothing_is_reported_as_dropped_when_nothing_was():
    assert draw(payload(), width=200).dropped == ()


# --- levels -------------------------------------------------------------------


def test_the_parts_level_draws_no_arrows():
    drawn = draw(payload(level=1, arrows=[]))
    for glyph in ARROWS.values():
        assert glyph not in drawn.text()


def test_a_note_is_shown_where_there_is_room_for_it():
    assert "one per shape" in draw(payload()).text()


def test_a_count_appears_once_and_only_inside_its_box():
    """The box already reads `label xN`. A second line saying it would be the
    same fact twice, and two places for it to disagree.

    Mutation: add a count line back and this fails.
    """
    counted = payload(boxes=[{"id": "m", "label": "members", "kind": "worker",
                              "note": "", "count": 9}],
                      arrows=[{"from": "m", "to": "m", "label": "",
                               "kind": "feedback"}])
    text = draw(counted).text()
    # Twice on the arrow line, because a self-loop draws its box at both ends
    # -- that is the drawing being correct, not the count being repeated. What
    # must not come back is a separate line restating it.
    assert "9 of them" not in text
    assert "members x9" in text


# --- the gallery is one view --------------------------------------------------


def test_the_gallery_is_one_view_rather_than_one_per_shape():
    """The question a gallery answers is "which of these", and that is not
    answerable while looking at one of them."""
    drawn = draw_gallery([payload(topology="a"), payload(topology="b")])
    text = drawn.text()
    assert "a  |" in text and "b  |" in text
    assert "-" * 30 in text, "no separator between shapes"


def test_an_empty_gallery_draws_nothing_rather_than_raising():
    assert draw_gallery([]).lines == ()


def test_the_gallery_reports_a_trim_once_rather_than_per_shape():
    wide = payload(arrows=[{"from": "in", "to": "r", "label": "x" * 200,
                            "kind": "flow"}])
    drawn = draw_gallery([wide, wide, wide], width=40)
    assert len(drawn.dropped) == 1


# --- the same pipeline, at a lower resolution ---------------------------------


def test_every_box_and_arrow_in_the_description_is_drawn():
    """THE GUARANTEE THE TWO WINDOWS REST ON.

    Somebody reading this terminal and somebody reading the page are looking at
    one pipeline, and must be able to talk about it without translating. That
    holds only if this window renders the whole flow -- coarsely is fine,
    partially is not.

    Resolution is how much detail a medium can carry. It is not licence to omit
    a step: a flow missing a stage is a different flow, and the two readers
    would be discussing different things while believing otherwise.

    Mutation: draw only the first three arrows and this fails.
    """
    full = payload(
        boxes=[{"id": c, "label": f"stage {c}", "kind": "worker",
                "note": "", "count": None} for c in "abcdef"],
        arrows=[{"from": a, "to": b, "label": "", "kind": "flow"}
                for a, b in zip("abcde", "bcdef")])

    text = draw(full, width=200).text()
    for box in full["boxes"]:
        assert box["label"] in text, f"{box['label']} was not drawn"
    for arrow in full["arrows"]:
        pair = f"[stage {arrow['from']}] --> [stage {arrow['to']}]"
        assert pair in text, f"{pair} was not drawn"


def test_a_narrow_window_trims_presentation_and_never_the_flow():
    """The one place resolution and completeness could conflict. A line too
    long for the terminal loses its label, not its arrow.

    Mutation: drop over-long lines instead of trimming them and this fails.
    """
    full = payload(
        boxes=[{"id": "a", "label": "stage a", "kind": "worker",
                "note": "", "count": None},
               {"id": "b", "label": "stage b", "kind": "worker",
                "note": "", "count": None}],
        arrows=[{"from": "a", "to": "b", "label": "why " * 40, "kind": "flow"}])

    drawn = draw(full, width=44)
    assert "[stage a]" in drawn.text(), "the flow lost a box to the margin"
    assert "-->" in drawn.text(), "the flow lost its arrow to the margin"
    assert drawn.dropped, "the trim was not reported"
