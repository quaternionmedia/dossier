"""Replay rad's conformance vectors against this host's placement.

Obligation 4 of rad's host integration standard: *"Replay
`conformance/vectors.json` in the host's own test runner and pin the vector
version claimed. Integrating without this makes 'conformant' a description of
intent."* This host had 1791 lines of rad port and replayed nothing, so
`conformant` was exactly that description.

**WHY A GRID HOST CAN REPLAY POLAR VECTORS AT ALL.** It looked as though it
could not: the vectors are written polar-first and this port is numpad-first,
so they read as being about a different component. They are not. A numpad is
the polar model evaluated at a constant set of angles -- eight cells 45 degrees
apart around a dead zone -- and the arithmetic is boring precisely because the
angles never move. rad's `adr/DRAFT-one-addressing-many-renderers.md` is the
decision, and `vectors.json`'s `numpad` block is the projection it obliges.

**WHAT THIS TEST ASSERTS TODAY, AND WHY IT IS NOT `agree everywhere`.** The two
disagree, on six of eight arities. Which side is wrong is that record's §4 and
is a person's decision, not this file's. So the test pins the disagreement
exactly: it passes on today's reality and fails the moment either side moves,
which is the difference between a divergence that is known and one that is
merely present. When §4 is answered, this file asserts full agreement and the
`EXPECTED_AGREEMENT` set goes away.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dossier.rad.numpad import BACK, place

# The vector set is read from the rad checkout beside this one rather than
# vendored, so a copy of the vectors cannot drift from the governed file --
# which is the same reason rad's own runner takes the set as an argument.
RAD_VECTORS = Path(__file__).resolve().parents[3] / "rad" / "conformance" / "vectors.json"

# Arities where this host's placement already matches the derived order.
# Everything else is rad's §4, open.
EXPECTED_AGREEMENT = {1, 4}


def vectors() -> dict:
    if not RAD_VECTORS.is_file():
        pytest.skip(
            f"rad is not beside this clone ({RAD_VECTORS}); the vectors are "
            f"read from the governed file rather than a vendored copy"
        )
    return json.loads(RAD_VECTORS.read_text(encoding="utf-8"))


def numpad_cases(document: dict) -> list[dict]:
    return [c for c in document.get("cases", []) if "numpadOrder" in c]


def test_the_vector_set_carries_a_numpad_projection():
    """Without it, a grid host has nothing that applies to it and `skip`
    would read as `conformant`."""
    document = vectors()
    assert document.get("numpad"), "vectors.json carries no numpad block"
    assert numpad_cases(document), "no numpad cases to replay"


def test_the_pinned_vector_version_is_the_one_replayed():
    """A host claims a version. An unpinned replay cannot say what it proved."""
    assert vectors()["version"] == "0.4.0"


def test_the_centre_is_back_and_never_holds_an_item():
    """The one rule both models already agreed on, at every arity."""
    document = vectors()
    assert document["numpad"]["back"] == BACK
    for count in range(1, 9):
        assert BACK not in place(count).by_cell


def test_placement_matches_the_derived_order_exactly_where_it_is_known_to():
    """**THE DIVERGENCE, PINNED RATHER THAN DISCOVERED AGAIN.**

    Mutation: change `PLACEMENT` in `dossier.rad.numpad` and this fails. Change
    `startDeg` or `clockwise` in rad's vectors and it fails too, which is the
    property that makes it a conformance test rather than a snapshot of this
    repository.
    """
    document = vectors()
    agreed, differed = set(), {}
    for case in numpad_cases(document):
        count = case["n"]
        derived = list(case["numpadOrder"])
        ours = [place(count).by_index[i] for i in range(count)]
        if ours == derived:
            agreed.add(count)
        else:
            differed[count] = {"derived": derived, "ours": ours}

    assert agreed == EXPECTED_AGREEMENT, (
        f"agreement moved: {sorted(agreed)} rather than "
        f"{sorted(EXPECTED_AGREEMENT)}. If this host or rad changed on purpose, "
        f"rad's adr/DRAFT-one-addressing-many-renderers.md §4 is the decision "
        f"and this expectation moves with it. Differences: {differed}"
    )


def test_an_arity_the_grid_cannot_hold_is_refused_rather_than_truncated():
    """Both models agree the ring ceiling is eight."""
    with pytest.raises(ValueError):
        place(9)
