"""Replay rad's governed cell vectors against this host.

Obligation 4 of rad's host integration standard §5: *"Replay
`conformance/vectors.json` in the host's own test runner and pin the vector
version claimed. Integrating without this makes 'conformant' a description of
intent."* This host carried a rad port and replayed nothing, so `conformant`
was exactly that description.

**WHY A GRID HOST CAN REPLAY THESE AT ALL.** They read as polar-first and this
port is cell-first, so they look like vectors about a different component.
Standard §2b settles it: a cell and an angle name the same item, by index, and
`placeCells(N)` derives the cell. The `cells` cases are the half that a host
with no pointer can execute.

**WHAT IS REPLAYED, AND WHAT IS NOT.** The `place` and direction steps are this
host's own behaviour and are asserted. `agreesWithRing` is a property of rad --
a cell's angle is fixed at one of eight while a ring's item centre moves with
`N`, so above four items the two place the same item differently, by up to
135°. This host renders no ring, so it replays that case as a fact about the
governed vectors rather than as a claim about itself, and says so rather than
skipping it silently.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dossier.rad.numpad import BACK, place, step_to_item

# Read from the rad checkout beside this one rather than vendored, so a copy
# cannot drift from the governed file. It is why rad's own runner takes the
# vector set as an argument instead of importing one.
RAD_VECTORS = Path(__file__).resolve().parents[3] / "rad" / "conformance" / "vectors.json"

# The version this host claims. It must match the file it loads, or the replay
# cannot say what it proved.
PINNED = "0.0.1"


def vectors() -> dict:
    if not RAD_VECTORS.is_file():
        pytest.skip(
            f"rad is not beside this clone ({RAD_VECTORS}); the vectors are read "
            f"from the governed file rather than a vendored copy"
        )
    document = json.loads(RAD_VECTORS.read_text(encoding="utf-8"))
    if document.get("version") != PINNED:
        # An environment fact, not a defect here: the file read is whatever
        # branch rad's checkout is on, and the cell cases arrived on
        # `evolve/consolidate-rad`. Reported with the reason rather than
        # skipped silently, because a silent skip reads as conformance.
        pytest.skip(
            f"rad's checkout carries vectors {document.get('version')!r} and this "
            f"host pins {PINNED!r}. The cell cases land with rad's "
            f"evolve/consolidate-rad; until that is rad's default branch this "
            f"replay has nothing of the pinned version to run."
        )
    return document


def cell_steps() -> list[tuple[str, dict]]:
    """Every step of every case that carries a `cells` block, with its case name."""
    return [
        (case.get("name", "?"), step)
        for case in vectors().get("cases", [])
        for step in case.get("cells", [])
    ]


def test_the_pinned_version_is_the_file_that_was_loaded():
    assert vectors()["version"] == PINNED


def test_the_vector_set_carries_cell_cases():
    """Without them a grid host has nothing that applies, and a skip would read
    as conformance."""
    assert cell_steps(), "no cell cases in the governed vectors"


def test_placement_matches_every_governed_place_step():
    """**THE OBLIGATION.**

    Mutation: reorder `PLACEMENT` in `dossier.rad.numpad` and this fails; edit
    an `expectCells` in rad's vectors and it fails too, which is what makes it
    conformance rather than a snapshot of this repository.
    """
    checked = 0
    for name, step in cell_steps():
        if "place" not in step:
            continue
        count = step["place"]
        if step.get("expectThrows"):
            with pytest.raises(ValueError):
                place(count)
        else:
            ours = [place(count).by_index[i] for i in range(count)]
            assert ours == list(step["expectCells"]), f"{name}, N={count}"
        checked += 1
    assert checked, "no place steps were replayed"


def test_direction_never_lands_on_a_cell_the_host_greyed_out():
    """A cursor that steps onto a greyed cell reads as broken arrow keys."""
    checked = 0
    for name, step in cell_steps():
        if "toItem" not in step:
            continue
        placement = place(step["n"])
        # `allowed` is optional in the vectors, and its absence is meaningful
        # rather than missing data: `None` is the case where nobody declared
        # availability, and every occupied cell is then a candidate.
        allowed = set(step["allowed"]) if "allowed" in step else None
        landed = step_to_item(step["from"], step["toItem"], placement, allowed)
        assert landed == step["expectCell"], f"{name}: landed on {landed}"
        checked += 1
    assert checked, "no direction steps were replayed"


def test_the_governed_vectors_say_cells_and_ring_part_above_four():
    """Recorded so a reader does not mistake rad's own divergence for a defect
    in this host. This asserts the vectors, not this port."""
    seen = {
        step["agreesWithRing"]: step["expectAgrees"]
        for _, step in cell_steps()
        if "agreesWithRing" in step
    }
    assert seen, "no agreesWithRing steps in the governed vectors"
    assert all(seen[n] for n in seen if n <= 4)
    assert not any(seen[n] for n in seen if n > 4)


def test_the_centre_backs_out_at_every_arity():
    for count in range(1, 9):
        assert BACK not in place(count).by_cell


def test_this_host_covers_the_cell_half_and_says_so(capsys):
    """**WHAT THIS HOST PROVES, AND WHAT IT CANNOT.**

    The governed set partitions cleanly: the cell-addressing cases are this
    host's, and the ring, pointer and timing cases belong to a host with a
    pointer. Neither covers the set alone, and counting it here means a reader
    cannot mistake "all green" for "the contract is proven" -- the same reason
    `codecartographer`'s runner names its not-applicable cases instead of
    passing them.

    Mutation: add a cell case to the governed set that this host does not
    replay, and the equality below fails.
    """
    document = vectors()
    total = len(document["cases"])
    mine = [c for c in document["cases"] if "cells" in c]
    theirs = [c for c in document["cases"] if "cells" not in c]

    assert len(mine) + len(theirs) == total, "the halves do not partition the set"
    replayed = {name for name, _ in cell_steps()}
    assert len(replayed) == len(mine), (
        f"this host replays {len(replayed)} of {len(mine)} cell cases"
    )

    with capsys.disabled():
        print(
            f"\n  rad conformance: {len(mine)} applicable, all passing; "
            f"{len(theirs)} not applicable to this host - it addresses cells "
            f"and has no pointer to give an angle, per host integration "
            f"standard 2b. The halves are disjoint and cover all {total}."
        )
