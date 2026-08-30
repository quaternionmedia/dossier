"""The families are reachable here, as data rather than as an import.

`records/DRAFT-a-family-is-bordered-by-what-it-drives.md` states which
repositories are one working system, and this host has to be able to show them.
It reaches them the way it reaches rad's vectors: a file at a stable path in the
governance corpus beside this clone, read as JSON.

**NOT AN IMPORT.** Importing the corpus to draw a picture would make this
project depend on a governance tool at runtime, which is the coupling
`records/DRAFT-seams-on-standard-protocols.md` exists to prevent. The seam is a
schema and a path.

What it cannot tell this host: whether anybody is working on a family. That is
`attention`, a different claim, and the artifact says so in its own `reading`
block rather than leaving it to be assumed.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

FAMILIES = Path(__file__).resolve().parents[3] / "qm" / "families.json"


def families() -> dict:
    if not FAMILIES.is_file():
        pytest.skip(
            f"the governance corpus is not beside this clone ({FAMILIES}); the "
            f"families are read from the generated file rather than a copy"
        )
    return json.loads(FAMILIES.read_text(encoding="utf-8"))


def test_the_artifact_is_shaped_the_way_this_host_reads_it():
    document = families()
    assert document["schema"] == 1
    for family in document["families"]:
        assert family["name"] and isinstance(family["members"], list)
        assert family["drives"], f"{family['name']} says what it drives"


def test_this_host_is_in_the_core_family():
    """A consumer that could not find itself would be reading someone else's
    estate."""
    core = next(f for f in families()["families"] if f["name"] == "core")
    assert "dossier" in core["members"]
    assert "codecartographer" in core["members"]


def test_unstated_is_carried_rather_than_folded_into_a_family():
    """A host rendering this must be able to show `unstated` as its own thing.
    Folding it into "no family" is the substitution the roster refuses."""
    document = families()
    assert "unstated" in document
    placed = {m for f in document["families"] for m in f["members"]}
    assert not (placed & set(document["unstated"])), "a repository is both placed and unstated"


def test_the_artifact_states_what_it_must_not_be_read_as():
    reading = families()["reading"]
    assert "attention" in reading["do_not"]
