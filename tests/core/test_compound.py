"""Deltas that are one piece of work, and finding them across repositories.

**`dossier.composition` COULD ALREADY SAY WHICH DELTAS MAKE UP A WHOLE**, and
every act was still one delta at a time. So advancing a whole meant finding its
parts by eye, advancing each, and remembering how many there had been.

Two relations are walked and they mean different things. `part-of` composes:
closing the whole requires closing this. `same-as` denotes: two addresses are
one strand, so advancing one and not the other leaves the same work in two
phases.

**`blocks` IS NOT WALKED**, and that is the point of having a closed vocabulary.
Following it would quietly turn "this must close before that can start" into
"these close together" — which is the substitution `RELATIONS` exists to make
impossible.
"""

from __future__ import annotations

from dossier import compound
from dossier.composition import Edge


class Row:
    def __init__(self, address, title="", phase=""):
        self.address = address
        self.title = title
        self.phase = phase


A = "org/a/delta/1"
B = "org/b/delta/2"
C = "org/c/delta/3"
D = "org/d/delta/4"


# --- what moves together ------------------------------------------------------


def test_part_of_and_same_as_are_both_in_the_compound():
    """THE ONE THIS EXISTS FOR.

    Mutation: walk only `part-of` and this fails.
    """
    edges = [Edge(A, "part-of", B, None), Edge(C, "same-as", B, None)]
    found = compound.compound_of(B, edges)

    assert found.size == 3
    assert {one.address for one in found.members} == {A, B, C}
    because = {one.address: one.because for one in found.members}
    assert because[B] == "chosen"
    assert because[A] == "part-of"
    assert because[C] == "same-as"


def test_blocks_is_not_walked():
    """THE OTHER ONE.

    "This must close before that can start" is not "these close together", and
    a compound act that moved a blocker would be acting on work somebody said
    was separate.

    Mutation: follow `blocks` too and this fails.
    """
    edges = [Edge(D, "blocks", B, None)]
    found = compound.compound_of(B, edges)

    assert found.is_alone, [one.address for one in found.members]


def test_a_delta_with_nothing_stated_is_the_whole_of_it():
    assert compound.compound_of(B, []).is_alone


def test_an_address_no_row_names_is_kept_and_marked():
    """A relation may name a delta this database has never seen — an address
    denotes without existing, and the row may arrive later. Dropping it would
    report a compound smaller than the one somebody stated.

    Mutation: skip members with no row and this fails.
    """
    edges = [Edge(A, "part-of", B, None)]
    found = compound.compound_of(B, edges, rows=[Row(B, "the whole", "review")])

    assert found.size == 2
    assert [one.address for one in found.unknown] == [A]
    assert not found.unknown[0].found


def test_a_truncated_walk_says_so():
    """`parts_of` returns this and its docstring says the caller must say it
    out loud: a truncated answer presented as complete is the shape of finding
    this corpus keeps recording.

    A compound act on one would move five of an unknown many.

    Mutation: drop `truncated` from the `Compound` and this fails.
    """
    from dossier.composition import DEPTH

    # A chain longer than the walk will follow.
    chain = [Edge(f"org/x/delta/{n + 1}", "part-of", f"org/x/delta/{n}", None)
             for n in range(1, DEPTH + 3)]
    found = compound.compound_of("org/x/delta/1", chain)

    assert found.truncated, found.size


# --- whether each can move ----------------------------------------------------


def test_a_closed_delta_reports_why_it_cannot_advance():
    """A delta already complete cannot be advanced, and says which phase.

    **I CLAIMED THIS COMPARISON HAD BEEN BROKEN. IT HAD NOT.** `DeltaPhase` is
    a `str` subclass, so a member equals its own value and comparing a plain
    string against `CLOSED_PHASES` has always worked. The mutation is what
    found the overclaim: swapping the string form back for the enum form left
    every test green, because there is no behavioural difference to catch.
    """
    closed = compound.closed_phases()
    assert closed, "nothing is closed, so this proves nothing"

    assert "complete" in closed, closed

    stuck = compound.Member(A, "part-of", phase="complete")
    assert compound.can_advance(stuck) == "already complete"


def test_the_two_forms_agree_only_because_the_enum_is_a_string():
    """The assumption underneath, pinned so the day it changes is a failure.

    `closed_phases()` returns strings and `CLOSED_PHASES` holds enum members,
    and the two behave identically *because* `DeltaPhase` subclasses `str`.
    That is the only reason, and nothing else in this module says so.

    Mutation: drop `str` from `DeltaPhase`'s bases and this fails -- which is
    the point, because at that moment the string form becomes the one that
    still works and the enum form silently stops matching.
    """
    from dossier.facets import CLOSED_PHASES
    from dossier.models.schemas import DeltaPhase

    assert issubclass(DeltaPhase, str)
    assert "complete" in CLOSED_PHASES
    assert compound.closed_phases() == frozenset(
        getattr(phase, "value", phase) for phase in CLOSED_PHASES)


def test_an_open_delta_can_advance():
    assert compound.can_advance(compound.Member(A, "chosen", phase="review")) == ""


def test_a_member_with_no_row_says_that_rather_than_a_phase():
    """A reason rather than a boolean: "two of five refused" with no reasons is
    a number a person cannot act on."""
    missing = compound.Member(A, "part-of", found=False)
    assert "no row" in compound.can_advance(missing)


# --- finding one --------------------------------------------------------------


def test_search_looks_at_name_title_and_branch():
    rows = [Row("x", title="bump bokeh"), Row("y", title="unrelated")]
    rows[0].name = ""
    rows[0].branch_name = ""
    rows[1].name = "chore/bump-me"
    rows[1].branch_name = ""

    assert len(compound.search(rows, "bump")) == 2


def test_search_is_case_insensitive_and_ignores_blank():
    row = Row("x", title="Bump Bokeh")
    row.name = ""
    row.branch_name = ""

    assert compound.search([row], "bump") == [row]
    assert compound.search([row], "   ") == []


def test_both_commands_exist():
    """Mutation: remove either from `cli.py` and this fails."""
    import click

    from dossier.cli import cli

    group = cli.get_command(None, "deltas")
    assert isinstance(group, click.Group)
    assert "search" in group.list_commands(None)
    assert "compound" in group.list_commands(None)


def test_the_compound_command_reads_and_does_not_advance():
    """Reads and prints. A command that swept a compound as a side effect of
    describing it would be the panel deciding the whole should move.

    Mutation: advance anything in `deltas_compound` and this fails.
    """
    import inspect

    from dossier.cli import cli

    group = cli.get_command(None, "deltas")
    source = inspect.getsource(group.get_command(None, "compound").callback)
    # **THE FIRST VERSION MATCHED `can_advance(`**, which is the function that
    # *reports* whether a member could move -- a scan hitting the name of the
    # thing it forbids, which this corpus has now caught four times. What makes
    # a command write is a commit or an assignment, so those are what is
    # checked.
    for writing in ("session.add", "session.commit", ".phase =", "advance_"):
        assert writing not in source, writing


# --- advancing one that is part of something ----------------------------------


def test_advancing_a_compound_member_asks_before_moving_it_alone():
    """THE COMPOUND ACT, AND IT IS A QUESTION RATHER THAN A SWEEP.

    `part-of` says closing the whole requires closing this; `same-as` says two
    addresses denote one strand. Advancing one alone can leave a compound
    half-moved, or the same work in two phases.

    Whether a whole should move is a judgement about the work, and the
    relations are somebody's statement about it rather than a licence to act on
    their behalf — so the first press says what it noticed and the second says
    "yes, this one alone", the same shape the sync confirmation uses.

    Mutation: drop the `_compound_beside` check from `action_advance_delta_phase`
    and this fails.
    """
    import inspect

    from dossier.tui.app import DossierApp

    source = inspect.getsource(DossierApp.action_advance_delta_phase)
    assert "_compound_beside" in source
    assert "_compound_pending" in source
    # The second press is what advances.
    assert source.index("_compound_pending = True") < source.index(
        "delta.advance_phase()")


def test_a_compound_reading_that_fails_does_not_block_an_advance():
    """An exception reading the relations would stop a plain delta moving
    because two *other* deltas were related to each other.

    Mutation: let `_compound_beside` raise and this fails.
    """
    import inspect

    from dossier.tui.app import DossierApp

    source = inspect.getsource(DossierApp._compound_beside)
    assert "except Exception" in source
    assert "return None" in source
