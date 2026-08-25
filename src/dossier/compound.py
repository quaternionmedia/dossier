"""Deltas that are one piece of work, and acting on them as one.

**A SWEEP IS ONE DELTA WITH MANY PARTS**, and `dossier.sweep` says so about a
dependency: bumping one package across twenty-four repositories is not
twenty-four pieces of work that look alike. `governance/qm/records/
DRAFT-deltas-compose.md` says the same thing about deltas, and `part-of` is the
relation that carries it.

What was missing is the acting. `dossier.composition` can already answer which
deltas make up a whole — `parts_of` walks `part-of`, `strands` walks `same-as` —
and every act was still one delta at a time. So advancing a whole meant finding
its parts by eye, advancing each, and remembering how many there had been.

**THE CLOSURE IS BOTH RELATIONS, AND THEY MEAN DIFFERENT THINGS.** `part-of`
composes: closing the whole requires closing this. `same-as` denotes: two
addresses are one strand, so advancing one and not the other would leave the
same work in two phases. Both belong in one act and the reasons are not the
same, which is why they are gathered separately and reported separately.

WHAT THIS CANNOT DO. Decide that acting on all of them is right. A compound is a
reading of the relations somebody stated; whether the whole should move is a
judgement about the work, and the panel asks rather than assumes.

AND IT DOES NOT WALK `blocks`. A delta that blocks another is not part of it —
that is the distinction `RELATIONS` exists to make possible, and following it
here would quietly turn "this must close first" into "these close together".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

from dossier.composition import Edge, parts_of, strands

def closed_phases() -> frozenset[str]:
    """Phase names a delta cannot be advanced out of, as strings.

    **THIS IS A CLARITY CHOICE AND NOT A REPAIR, WHICH I HAD IT BACKWARDS.**
    `CLOSED_PHASES` holds `DeltaPhase` members and `Member.phase` is a string,
    which looked like a comparison that could never be true. It always was:
    `DeltaPhase` is a `str` subclass, so a member equals its own value and
    `"complete" in CLOSED_PHASES` is True. No mutation of the two forms can be
    told apart, because they behave identically.

    Kept because it makes the type explicit at the boundary, and because it is
    the form that still works if `DeltaPhase` ever stops subclassing `str` --
    which `test_the_two_forms_agree_only_because_the_enum_is_a_string` pins,
    so the day that changes is a failure and not a silence.

    Read from the enum rather than listed, so a phase added there is not
    quietly advanceable here.
    """
    try:
        from dossier.facets import CLOSED_PHASES
    except Exception:                             # noqa: BLE001
        return frozenset()
    return frozenset(getattr(phase, "value", str(phase))
                     for phase in CLOSED_PHASES)


@dataclass(frozen=True)
class Member:
    """One delta in a compound, and why it is in it."""

    address: str
    because: str
    """`part-of`, `same-as`, or `chosen` for the one somebody named."""

    title: str = ""
    phase: str = ""
    found: bool = True
    """False for an address no row matches.

    **KEPT, NOT DROPPED.** A relation may name a delta this database has never
    seen -- an address denotes without existing, and the row may arrive later.
    Dropping it would report a compound smaller than the one somebody stated.
    """


@dataclass
class Compound:
    """One piece of work and every delta making it up."""

    chosen: str
    members: list[Member] = field(default_factory=list)

    truncated: bool = False
    """Whether the walk stopped at its depth limit rather than at the end.

    **`parts_of` RETURNS THIS AND ITS DOCSTRING SAYS THE CALLER MUST SAY IT OUT
    LOUD** -- "a truncated answer presented as complete is the shape of finding
    this corpus keeps recording". A compound that says five when the real
    number is deeper is exactly that, and a compound act on it would move five
    of an unknown many.
    """

    @property
    def size(self) -> int:
        return len(self.members)

    @property
    def unknown(self) -> list[Member]:
        return [one for one in self.members if not one.found]

    @property
    def is_alone(self) -> bool:
        """Whether the chosen delta is the whole of it.

        The common case, and the one where a compound act would be a
        confirmation dialog over a single row.
        """
        return self.size <= 1


def edges_from(rows: Iterable[Any]) -> list[Edge]:
    """`DeltaRelation` rows as composition edges."""
    return [
        Edge(row.source_address, row.relation, row.target_address,
             getattr(row, "stated_by", None))
        for row in rows
    ]


def compound_of(address: str, edges: Sequence[Edge],
                rows: Iterable[Any] = ()) -> Compound:
    """The deltas that move together with `address`.

    `rows` are `ProjectDelta`s, used only to fill in a title and a phase. An
    address with no row is still a member: see `Member.found`.
    """
    known = {}
    for row in rows:
        stated = getattr(row, "address", None) or _address_of(row)
        if stated:
            known[stated] = row

    listed = list(edges)
    members = [Member(address, "chosen")]
    seen = {address}

    found_parts, truncated = parts_of(address, listed)
    for part in found_parts:
        if part not in seen:
            seen.add(part)
            members.append(Member(part, "part-of"))
    for strand in strands(address, listed):
        if strand not in seen:
            seen.add(strand)
            members.append(Member(strand, "same-as"))

    filled = []
    for one in members:
        row = known.get(one.address)
        if row is None:
            filled.append(Member(one.address, one.because, found=False))
            continue
        filled.append(Member(
            one.address, one.because,
            title=getattr(row, "title", "") or "",
            phase=_phase_of(row),
        ))
    return Compound(chosen=address, members=filled, truncated=truncated)


def _address_of(row: Any) -> str:
    """A delta's address, when the row does not carry one directly."""
    project = getattr(row, "project_address", None)
    number = getattr(row, "id", None)
    if project and number is not None:
        return f"{project}/delta/{number}"
    return ""


def _phase_of(row: Any) -> str:
    phase = getattr(row, "phase", None)
    return getattr(phase, "value", str(phase)) if phase is not None else ""


def can_advance(one: Member) -> str:
    """Empty when this member can be advanced, or why it cannot.

    A reason rather than a boolean: a compound where three of five will not
    move is a thing a person needs the shape of, and "two of five refused" with
    no reasons is a number they cannot act on.
    """
    if not one.found:
        return "no row here names it"
    if one.phase and one.phase in closed_phases():
        return f"already {one.phase}"
    return ""


def search(rows: Iterable[Any], text: str) -> list[Any]:
    """Deltas whose name, title or branch contains `text`, case-insensitively.

    **ACROSS REPOSITORIES, WHICH IS THE POINT.** Every other way of finding a
    delta here starts by choosing a repository, and a compound crosses them by
    construction -- `governance/qm/records/DRAFT-deltas-compose.md` is explicit
    that a relation joins two addresses and an address carries its own owner.
    """
    wanted = (text or "").strip().lower()
    if not wanted:
        return []
    found = []
    for row in rows:
        haystack = " ".join(str(getattr(row, field, "") or "")
                            for field in ("name", "title", "branch_name"))
        if wanted in haystack.lower():
            found.append(row)
    return found
