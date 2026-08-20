"""How deltas compose, and why a tangle is kept rather than refused.

    dossier deltas relate <from> <relation> <to>
    dossier deltas tangles

`governance/qm/records/DRAFT-deltas-compose.md` is the decision. This module is
the mechanism, and the three things worth knowing before reading it:

**A relation joins two addresses, not two rows.** Both sides are
`<owner>/<repo>/delta/<id>`, so a relation crosses repositories and threads by
construction. A relation naming a delta this database has never seen is kept:
an address denotes without existing, and the row it names may arrive later.

**The vocabulary is closed.** Five relations. A free string would let a typo
become a category, which is the substitution this corpus refuses for `phase`,
for `attention`, and now here.

**A CYCLE IS REPORTED AND NEVER BROKEN.** Every tracker refuses `a blocks b
blocks a` as invalid input. What happens next is that somebody deletes whichever
relation the tool complained about -- so the tool is consistent and the record
is false, and the deletion was made by whoever was least equipped to judge it.
A tangle is a fact about the work. Refusing to store it does not untangle
anything; it destroys the only evidence that the work is knotted, which is
usually the most useful thing anybody knew.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# The five, with the test that decides each one. Keep the sentences: they are
# what somebody reads when choosing between `blocks` and `crosses`, which is the
# choice this vocabulary exists to make possible.
RELATIONS: dict[str, str] = {
    "part-of": "closing the whole requires closing this",
    "same-as": "two addresses denote one strand",
    "blocks": "this must close before that can start",
    "crosses": ("both must happen, they interact at one point, and neither "
                "contains the other"),
    "derived-from": "this strand came out of that one and both continue",
}

# Reading a relation backwards. `same-as` and `crosses` are their own inverse --
# they are symmetric, and that is a property of what they mean rather than a
# convenience. `derived-from` has none: the parent is not "the origin of" in any
# sense the parent has to carry.
INVERSES: dict[str, str | None] = {
    "part-of": "contains",
    "same-as": "same-as",
    "blocks": "blocked-by",
    "crosses": "crosses",
    "derived-from": None,
}

SYMMETRIC = frozenset({"same-as", "crosses"})

# How far `part-of` is walked before the answer says it stopped. An unbounded
# walk over a graph that is allowed to contain cycles is a hang, and a hang in a
# dashboard reads as a broken tool rather than as deep work.
DEPTH = 12


def check_relation(relation: str) -> str | None:
    """Why this is not a relation, or None."""
    if relation in RELATIONS:
        return None
    return (f"{relation!r} is not a relation. The five are: "
            f"{', '.join(sorted(RELATIONS))}. Adding a sixth is a change to "
            f"governance/qm/records/DRAFT-deltas-compose.md, not to a string.")


def check_address(address: str) -> str | None:
    """Why this is not a delta address, or None.

    Checked as a shape and not as an existence. The grammar is explicit that an
    address denotes without existing, and a relation to a delta that has not
    been ingested yet is ordinary rather than wrong.
    """
    parts = address.split("/", 3)
    if len(parts) != 4:
        return (f"{address!r} is not <owner>/<repo>/delta/<id>")
    if parts[2] != "delta":
        return (f"{address!r} addresses a {parts[2]!r}, and a relation joins "
                f"two deltas")
    if not parts[3]:
        return f"{address!r} has no id"
    return None


@dataclass(frozen=True)
class Edge:
    """One relation, as stored."""

    source: str
    relation: str
    target: str
    stated_by: str | None = None

    def reversed(self) -> "Edge":
        return Edge(self.target, INVERSES.get(self.relation) or self.relation,
                    self.source, self.stated_by)


@dataclass
class Tangle:
    """A cycle, and the relations that make it.

    Reported and never broken. `kinds` is carried because a cycle of `blocks` is
    a scheduling knot and a cycle of `same-as` is three names for one strand --
    different findings that a reader should not have to reconstruct.
    """

    addresses: list[str] = field(default_factory=list)
    kinds: list[str] = field(default_factory=list)

    @property
    def only(self) -> str | None:
        """The single relation this tangle is made of, if it is made of one."""
        unique = set(self.kinds)
        return unique.pop() if len(unique) == 1 else None


def _outgoing(edges: list[Edge]) -> dict[str, list[Edge]]:
    out: dict[str, list[Edge]] = {}
    for edge in edges:
        out.setdefault(edge.source, []).append(edge)
    return out


def parts_of(address: str, edges: list[Edge],
             depth: int = DEPTH) -> tuple[list[str], bool]:
    """What this delta is made of, and whether the walk stopped early.

    Walks `part-of` inward: everything whose closing the whole requires. The
    second value is True when `depth` was reached, which the caller must say out
    loud -- a truncated answer presented as complete is the shape of finding
    this corpus keeps recording.
    """
    incoming: dict[str, list[str]] = {}
    for edge in edges:
        if edge.relation == "part-of":
            incoming.setdefault(edge.target, []).append(edge.source)

    seen, frontier, truncated = [], [address], False
    visited = {address}
    for _ in range(depth):
        following = []
        for node in frontier:
            for child in incoming.get(node, []):
                if child in visited:
                    continue
                visited.add(child)
                seen.append(child)
                following.append(child)
        if not following:
            return seen, False
        frontier = following
    else:
        truncated = bool(frontier)
    return seen, truncated


def strands(address: str, edges: list[Edge]) -> list[str]:
    """Every address `same-as` says denotes this same strand.

    Both names are returned and neither is retired. Two systems each named one
    strand, both names are already in documents, and picking a winner breaks
    whichever links did not win. Resolution is the reader's.
    """
    same: dict[str, set[str]] = {}
    for edge in edges:
        if edge.relation == "same-as":
            same.setdefault(edge.source, set()).add(edge.target)
            same.setdefault(edge.target, set()).add(edge.source)

    seen, frontier = {address}, [address]
    while frontier:
        node = frontier.pop()
        for other in same.get(node, ()):
            if other not in seen:
                seen.add(other)
                frontier.append(other)
    return sorted(seen - {address})


def tangles(edges: list[Edge]) -> list[Tangle]:
    """Every cycle these relations form.

    Symmetric relations are walked one way only. `a same-as b` and its implied
    `b same-as a` are one statement, and reporting the pair as a two-node cycle
    would bury every real tangle in noise.
    """
    directed = [edge for edge in edges if edge.relation not in SYMMETRIC]
    out = _outgoing(directed)

    found: list[Tangle] = []
    seen_signatures: set[tuple[str, ...]] = set()
    on_stack: dict[str, int] = {}
    path: list[Edge] = []

    def walk(node: str) -> None:
        on_stack[node] = len(path)
        for edge in out.get(node, []):
            if edge.target in on_stack:
                start = on_stack[edge.target]
                ring = path[start:] + [edge]
                addresses = [step.source for step in ring]
                signature = tuple(sorted(set(addresses)))
                if signature not in seen_signatures:
                    seen_signatures.add(signature)
                    found.append(Tangle(addresses,
                                        [step.relation for step in ring]))
                continue
            path.append(edge)
            walk(edge.target)
            path.pop()
        del on_stack[node]

    for node in list(out):
        if node not in on_stack:
            walk(node)
    return found


def render_tangles(found: list[Tangle]) -> str:
    """What the cycles are, and that nothing was changed because of them."""
    if not found:
        return ("No tangle. Every relation these deltas carry runs one way.\n"
                "That is a fact about what has been recorded, not a promise "
                "about the work.")

    lines = [f"{len(found)} tangle(s). Nothing here has been changed.", ""]
    for tangle in found:
        only = tangle.only
        lines.append(f"  {' -> '.join(tangle.addresses)} -> {tangle.addresses[0]}")
        lines.append(f"      {' / '.join(tangle.kinds)}")
        if only == "blocks":
            lines.append("      A blocking cycle: nothing in it can start "
                         "first, so somebody has to decide what does.")
        elif only == "part-of":
            lines.append("      A containment cycle: each of these is part of "
                         "the next, which cannot be true of all of them.")
        lines.append("")

    lines += [
        "A tangle is a fact about the work rather than an error in the record.",
        "It is reported and never broken: deleting a relation to satisfy a",
        "checker makes the tool consistent and the record false. Whether this",
        "one is a mistake or a real knot is a person's to say.",
    ]
    return "\n".join(lines)
