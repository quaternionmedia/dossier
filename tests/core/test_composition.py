"""How deltas compose, and what this refuses to do about a tangle.

`governance/qm/records/DRAFT-deltas-compose.md` is the decision. The tests that
matter here are the ones asserting something is *not* done: no cycle refused, no
address resolved, no phase rolled up. Every one of those is a convenience a
project-management tool normally provides, and each is a place it starts lying.
"""

from __future__ import annotations

import pytest

from dossier.composition import (
    DEPTH,
    INVERSES,
    RELATIONS,
    SYMMETRIC,
    Edge,
    check_address,
    check_relation,
    parts_of,
    render_tangles,
    strands,
    tangles,
)


def addr(name: str, repo: str = "qm") -> str:
    return f"quaternionmedia/{repo}/delta/{name}"


def edge(source: str, relation: str, target: str, repo_a="qm", repo_b="qm") -> Edge:
    return Edge(addr(source, repo_a), relation, addr(target, repo_b))


# --- the vocabulary is closed -----------------------------------------------


def test_every_relation_carries_the_test_that_decides_it():
    """The sentences are what somebody reads when choosing between `blocks` and
    `crosses`. A vocabulary of bare words would not make that choice possible."""
    assert set(RELATIONS) == {"part-of", "same-as", "blocks", "crosses",
                              "derived-from"}
    assert all(RELATIONS.values()), "each relation states when it holds"


def test_a_word_outside_the_vocabulary_is_refused_and_says_where_to_change_it():
    """Mutation: accept any string and a typo becomes a category -- the same
    substitution this corpus refuses for `phase` and for `attention`."""
    problem = check_relation("blockz")
    assert problem is not None
    assert "not a relation" in problem
    assert "DRAFT-deltas-compose" in problem, "it names where a sixth is decided"


def test_the_symmetric_relations_are_their_own_inverse():
    """A property of what they mean, not a convenience."""
    assert SYMMETRIC == {"same-as", "crosses"}
    for relation in SYMMETRIC:
        assert INVERSES[relation] == relation


def test_derived_from_has_no_inverse():
    """The parent is not "the origin of" in any sense it has to carry."""
    assert INVERSES["derived-from"] is None


# --- an address denotes without existing ------------------------------------


def test_a_relation_may_name_a_delta_this_side_has_never_seen():
    """Checked as a shape, never as an existence.

    A relation to a delta in a repository nobody has ingested is the ordinary
    case for cross-project work, and refusing it would make composition
    available only inside one database.
    """
    assert check_address(addr("never-ingested", repo="somewhere-else")) is None


def test_something_that_is_not_a_delta_address_is_refused():
    assert check_address("quaternionmedia/qm") is not None
    assert "delta" in check_address("quaternionmedia/qm/pr/12")
    assert check_address("quaternionmedia/qm/delta/") is not None


# --- a tangle is kept -------------------------------------------------------


def test_a_cycle_is_reported_rather_than_refused():
    """THE LOAD-BEARING TEST.

    Every other tracker rejects `a blocks b blocks a` as invalid input, and what
    happens next is that somebody deletes whichever relation the tool complained
    about -- consistent tool, false record, deletion made by whoever was least
    equipped to judge it.

    Mutation: raise on a cycle instead of returning it and this fails.
    """
    edges = [edge("one", "blocks", "two"),
             edge("two", "blocks", "three"),
             edge("three", "blocks", "one")]
    found = tangles(edges)
    assert len(found) == 1
    assert set(found[0].addresses) == {addr("one"), addr("two"), addr("three")}
    assert found[0].only == "blocks"


def test_a_tangle_crosses_repositories():
    """The case the record exists for: a knot no single repository can see."""
    edges = [edge("ship", "blocks", "skips", "qm", "qmcp"),
             edge("skips", "blocks", "extras", "qmcp", "qm"),
             edge("extras", "blocks", "ship", "qm", "qm")]
    found = tangles(edges)
    assert len(found) == 1
    assert any("/qmcp/" in address for address in found[0].addresses)
    assert any("/qm/" in address for address in found[0].addresses)


def test_a_symmetric_relation_is_not_reported_as_a_two_node_cycle():
    """`a same-as b` implies `b same-as a`. Reporting the pair as a tangle
    would bury every real one in noise.

    Mutation: walk symmetric relations too and this fails.
    """
    assert tangles([edge("one", "same-as", "two")]) == []
    assert tangles([edge("one", "crosses", "two")]) == []


def test_one_cycle_is_reported_once_however_it_is_entered():
    """Three nodes in a ring can be walked from any of them."""
    edges = [edge("one", "blocks", "two"),
             edge("two", "blocks", "three"),
             edge("three", "blocks", "one")]
    assert len(tangles(edges)) == 1


def test_the_report_says_nothing_was_changed():
    """A reader must not think the tool untangled anything."""
    edges = [edge("one", "blocks", "two"), edge("two", "blocks", "one")]
    text = render_tangles(tangles(edges))
    assert "Nothing here has been changed" in text
    assert "never broken" in text
    assert "person's to say" in text


def test_no_tangle_is_not_a_promise():
    """An empty report describes what was recorded, not the work."""
    text = render_tangles([])
    assert "No tangle" in text
    assert "not a promise" in text


def test_a_containment_cycle_is_named_as_the_different_thing_it_is():
    """A `blocks` ring is a scheduling knot; a `part-of` ring cannot be true at
    all. A reader should not have to work out which they have."""
    edges = [edge("one", "part-of", "two"), edge("two", "part-of", "one")]
    assert "cannot be true of all of them" in render_tangles(tangles(edges))


# --- what a delta is made of ------------------------------------------------


def test_parts_are_walked_inward_through_part_of():
    edges = [edge("leaf", "part-of", "branch"),
             edge("branch", "part-of", "trunk")]
    parts, truncated = parts_of(addr("trunk"), edges)
    assert parts == [addr("branch"), addr("leaf")]
    assert truncated is False


def test_a_deep_chain_stops_at_the_bound_and_says_so():
    """An unbounded walk over a graph allowed to contain cycles is a hang, and
    a hang in a dashboard reads as a broken tool.

    Mutation: drop the bound and this test does not finish.
    """
    edges = [edge(f"n{i}", "part-of", f"n{i - 1}") for i in range(1, DEPTH + 6)]
    parts, truncated = parts_of(addr("n0"), edges)
    assert truncated is True, "a truncated answer must announce itself"
    assert len(parts) < DEPTH + 5


def test_a_cycle_in_part_of_does_not_hang_the_walk():
    edges = [edge("one", "part-of", "two"), edge("two", "part-of", "one")]
    parts, _ = parts_of(addr("one"), edges)
    assert addr("two") in parts


def test_blocks_is_not_walked_as_containment():
    """`blocks` orders strands; it does not make one part of the other.

    Mutation: walk every relation in `parts_of` and this fails, which is the
    board asserting a hierarchy nobody stated.
    """
    assert parts_of(addr("two"), [edge("one", "blocks", "two")])[0] == []


# --- same-as keeps both names -----------------------------------------------


def test_both_addresses_survive_a_same_as():
    """Neither is retired and neither is rewritten. Documents already cite each
    of them, and picking a winner breaks whichever links did not win."""
    edges = [edge("here", "same-as", "there", "qm", "qmcp")]
    assert strands(addr("here"), edges) == [addr("there", "qmcp")]
    assert strands(addr("there", "qmcp"), edges) == [addr("here")]


def test_same_as_is_followed_transitively():
    edges = [edge("a", "same-as", "b"), edge("b", "same-as", "c")]
    assert strands(addr("a"), edges) == [addr("b"), addr("c")]


def test_an_unrelated_delta_has_no_other_names():
    assert strands(addr("alone"), [edge("a", "blocks", "b")]) == []
