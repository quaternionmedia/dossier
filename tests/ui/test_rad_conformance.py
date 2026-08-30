"""Replay rad's conformance vectors against this host's cell placement.

Obligation 4 of rad's host integration standard: *"Replay
`conformance/vectors.json` in the host's own test runner and pin the vector
version claimed. Integrating without this makes 'conformant' a description of
intent."* This host carried a rad port of some size and replayed nothing, so
`conformant` was exactly that description. This file is that obligation.

**WHY A GRID HOST CAN REPLAY THESE VECTORS AT ALL.** They read as polar-first
and this port is cell-first, so they look like vectors about a different
component. They are not: standard §2b says a cell and an angle name the same
item, by index. The `cells` block is the projection that makes the shared
addressing checkable from a terminal.

**WHAT `cellAgreesWithRing` IS, AND WHAT IT IS NOT.** It is false for most
arities, and that is a property of rad rather than a defect in any host. A
cell's angle is fixed at one of eight; a ring's item centre moves with `N`. So
above four items the two place the same item differently, by up to 135° --
standard §2b constraint 3, priced in the nine-cells record clause 4. A host is
conformant when it matches `placeCells`, not when it makes that predicate true.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dossier.rad.numpad import BACK, PLACEMENT, place

# Read from the rad checkout beside this one rather than vendored, so a copy
# cannot drift from the governed file. This is why rad's own runner takes the
# vector set as an argument instead of importing one.
RAD_VECTORS = Path(__file__).resolve().parents[3] / "rad" / "conformance" / "vectors.json"


def vectors() -> dict:
    if not RAD_VECTORS.is_file():
        pytest.skip(
            f"rad is not beside this clone ({RAD_VECTORS}); the vectors are read "
            f"from the governed file rather than a vendored copy"
        )
    return json.loads(RAD_VECTORS.read_text(encoding="utf-8"))


def cell_cases(document: dict) -> list[dict]:
    return [c for c in document.get("cases", []) if "expectCells" in c]


def test_the_vector_set_carries_a_cells_projection():
    """Without it a grid host has nothing that applies, and `skip` reads as
    `conformant`."""
    document = vectors()
    assert document.get("cells"), "vectors.json carries no cells block"
    assert cell_cases(document), "no cells cases to replay"


def test_the_pinned_vector_version_is_the_one_replayed():
    """A host claims a version. An unpinned replay cannot say what it proved."""
    assert vectors()["version"] == "0.6.0"


def test_this_host_places_cells_exactly_as_the_vectors_do():
    """**THE OBLIGATION, AND IT PASSES.**

    Mutation: reorder `PLACEMENT` in `dossier.rad.numpad` and this fails.
    Change `cells.placement` in rad's vectors and it fails too, which is what
    makes it conformance rather than a snapshot of this repository.
    """
    document = vectors()
    for case in cell_cases(document):
        count = case["n"]
        ours = [place(count).by_index[i] for i in range(count)]
        assert ours == list(case["expectCells"]), (
            f"N={count}: this host places {ours}, the vectors say "
            f"{case['expectCells']}"
        )


def test_the_placement_table_itself_matches_the_governed_one():
    """The table is the whole of the addressing, so it is compared directly
    rather than only through its slices."""
    assert list(PLACEMENT) == list(vectors()["cells"]["placement"])


def test_the_centre_is_back_and_never_holds_an_item():
    document = vectors()
    assert document["cells"]["back"] == BACK
    for count in range(1, 9):
        assert BACK not in place(count).by_cell


def test_cells_and_ring_coincide_only_where_the_vectors_say_they_do():
    """Recorded so a reader does not mistake the divergence for a host defect.

    This asserts rad's own predicate, not this host's behaviour.
    """
    document = vectors()
    case = next(c for c in document["cases"] if c.get("name") == "cellAgreesWithRing")
    assert case["expectAgrees"] == [1, 4]


def test_an_arity_the_grid_cannot_hold_is_refused_rather_than_truncated():
    """Both the ring ceiling and the grid ceiling are eight."""
    with pytest.raises(ValueError):
        place(9)
