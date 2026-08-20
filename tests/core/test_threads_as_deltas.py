"""The thread archive, read in the delta vocabulary.

A thread is a delta. The tab used to show an inventory -- title, source, turns,
last seen -- which is a true description of a conversation and says nothing
about it as a unit of work. These are the columns that make it a board.
"""

from __future__ import annotations

from dossier.facets import THREADS_COLUMNS, _delta_name, _threads_rows, _thread_state


class FakeArchive:
    def __init__(self, threads, note="as indexed."):
        self.threads = threads
        self.note = note
        self.reachable = True
        self.indexed = True


def row(**kwargs):
    base = {"id": "abc", "title": "A conversation", "turns": 4,
            "address": "quaternionmedia/qmcp/delta/thread-abc",
            "perspective": "claude/thread", "phase": "brainstorm",
            "changes": 1, "diverged": False}
    base.update(kwargs)
    return base


# --- the address is the harness's ---------------------------------------------


def test_the_delta_name_comes_from_the_harness():
    """THE ONE THAT MATTERS.

    The panel does not compute `thread-{id}`. The harness builds the address
    from the same function that builds the delta payload, and this reads the
    tail of it -- so a change to the naming rule moves both, and neither side
    can drift into naming a delta something the other cannot find.

    Mutation: derive the name from `row["id"]` here and this fails, because
    the address below deliberately does not match the id.
    """
    assert _delta_name(row(id="xyz")) == "thread-abc"


def test_a_harness_that_does_not_send_an_address_gets_no_name_invented():
    """An older harness has no `address` field. Unknown is a value: the row
    says `--` rather than showing a name this side made up, which would look
    like something a reader could go and find.

    Mutation: fall back to `f"thread-{row['id']}"` and this fails.
    """
    assert _delta_name(row(address=None)) == "--"
    assert _delta_name({}) == "--"


def test_the_phase_is_shown_and_not_decided_here():
    """`brainstorm` is `to_thread_delta`'s decision, carried across the seam.
    A panel that decided it would be a second opinion about somebody else's
    delta."""
    rendered = _threads_rows(FakeArchive([row(phase="brainstorm")]))
    assert rendered[0][3] == "brainstorm"
    assert _threads_rows(FakeArchive([row(phase=None)]))[0][3] == "--"


# --- what the columns say -----------------------------------------------------


def test_the_columns_are_the_delta_vocabulary():
    """Mutation: put `source` and `last seen` back and this fails. Those are
    inventory columns; they describe the file rather than the work."""
    assert THREADS_COLUMNS == (
        "delta", "title", "speaks as", "phase", "turns", "state")


def test_every_row_has_a_cell_for_every_column():
    rendered = _threads_rows(FakeArchive([row(), row(id="two")]))
    assert all(len(r) == len(THREADS_COLUMNS) for r in rendered)


def test_the_perspective_is_the_level_it_speaks_at():
    """Two assistants discussing one piece of work are two perspectives on one
    strand, not one duplicated. The column is what keeps them apart on screen.
    """
    rendered = _threads_rows(FakeArchive([
        row(perspective="claude/thread"),
        row(id="b", perspective="chatgpt/thread"),
    ]))
    assert {r[2] for r in rendered} == {"claude/thread", "chatgpt/thread"}


# --- state --------------------------------------------------------------------


def test_a_thread_seen_once_is_new_and_one_seen_again_grew():
    assert _thread_state(row(changes=1)) == "new"
    assert _thread_state(row(changes=3)) == "grew"


def test_a_disagreement_outranks_how_many_times_it_changed():
    """It is the only row that is a finding. A conversation that both grew and
    disagreed is reported as disagreeing, because that is the half somebody
    has to act on."""
    assert _thread_state(row(changes=9, diverged=True)) == "disagrees"


def test_disagreements_sort_first():
    """A page that buried a finding under four hundred rows would be an
    inventory with a finding hidden in it.

    Mutation: drop the sort and this fails.
    """
    rendered = _threads_rows(FakeArchive([
        row(id="a", title="Ordinary"),
        row(id="b", title="Contradicts itself", diverged=True),
        row(id="c", title="Also ordinary"),
    ]))
    assert rendered[0][1] == "Contradicts itself"


def test_an_unknown_change_count_is_not_read_as_a_change():
    """A missing `changes` is not zero and not one; it renders as `new` rather
    than claiming the thread grew, because claiming growth from an absent
    figure is inventing evidence."""
    assert _thread_state({"diverged": False}) == "new"
