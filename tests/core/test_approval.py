"""One approval for everything identical, and a queue for everything else.

THE TEST WORTH READING IS THE UNIFORMITY ONE. A batch approval is one person
saying yes to one thing. If the items differ it is one person saying yes to
several things having read one of them, which is worse than twenty-four prompts
because it looks like diligence.
"""

from __future__ import annotations

from dataclasses import dataclass

from dossier.approval import (
    APPROVE,
    BLOCKED,
    DECIDE,
    Batch,
    Item,
    approval_note,
    batch_is_uniform,
    review,
)


@dataclass
class FakeOutcome:
    """Shaped like the harness's, built here because nothing imports across."""

    project: str
    state: str
    detail: str = ""
    edit: str | None = None


def prepared(project, edit=">=0.116.0"):
    return FakeOutcome(project, "done", f"->{edit}", edit)


# --- what may be approved together --------------------------------------------


def test_a_batch_is_only_a_batch_when_every_edit_is_identical():
    """THE ONE THAT MATTERS.

    Not similar -- identical. One keystroke is honest only if the thing being
    said yes to is one thing.

    Mutation: compare the edits loosely, or skip the check, and this fails.
    """
    same = Batch("fastapi to 0.116.0", [prepared_item("a"), prepared_item("b")])
    assert batch_is_uniform(same) is True

    different = Batch("fastapi to 0.116.0",
                      [prepared_item("a"), prepared_item("b", "~=0.116.0")])
    assert batch_is_uniform(different) is False


def prepared_item(name, edit=">=0.116.0"):
    return Item(f"org/{name}", APPROVE, f"->{edit}", edit)


def test_an_empty_batch_is_not_uniform():
    """Reporting "all of them agree" about nothing is the more misleading of
    the two answers available.

    Mutation: return True for an empty batch and this fails.
    """
    assert batch_is_uniform(Batch("nothing", [])) is False


def test_only_prepared_work_reaches_the_batch():
    """A repository nothing prepared cannot be in a batch that approves a
    prepared change."""
    found = review("sweep/x", "fastapi to 0.116.0", [
        prepared("org/a"),
        FakeOutcome("org/b", "needs a worker", "no version declared"),
    ])
    assert [i.repo for i in found.batch.items] == ["a"]
    assert [i.repo for i in found.queue] == ["b"]


def test_a_refusal_is_its_own_decision_rather_than_a_blockage():
    """Two different things to do next: a refusal needs somebody to decide, a
    blockage needs something to change first.

    Mutation: collapse the two and this fails.
    """
    found = review("sweep/x", "c", [
        FakeOutcome("org/r", "refused", "already ahead"),
        FakeOutcome("org/b", "needs a worker", "nothing looked"),
    ])
    asking = {i.repo: i.asking for i in found.queue}
    assert asking["r"] == DECIDE
    assert asking["b"] == BLOCKED


def test_a_done_outcome_with_no_edit_does_not_join_the_batch():
    """"Done" with nothing prepared is not something to apply. Approving it
    would approve an empty change in a repository nobody touched."""
    found = review("sweep/x", "c", [FakeOutcome("org/a", "done", "looked", None)])
    assert found.approvable == 0
    assert found.batches == []
    assert found.queue and found.queue[0].asking == BLOCKED


# --- the queue is not hidden --------------------------------------------------


def test_the_summary_counts_the_queue_first():
    """A summary leading with nine approvals reads as done. The twenty-four is
    the number that matters.

    Mutation: put the batch first and this fails.
    """
    found = review("sweep/fastapi", "fastapi to 0.116.0",
                   [prepared("org/a"), prepared("org/b"),
                    FakeOutcome("org/c", "needs a worker", "no version")])
    summary = found.summary()
    assert summary.index("waiting") < summary.index("ready in")
    assert "3 in the sweep" in summary


def test_a_sweep_with_anything_waiting_is_not_complete():
    """A batch alone is not a sweep. Nine of twenty-four approved is nine of
    twenty-four.

    Mutation: make completeness depend only on the batch and this fails.
    """
    found = review("sweep/x", "c", [prepared("org/a"),
                                    FakeOutcome("org/b", "needs a worker", "")])
    assert found.is_complete is False


def test_a_sweep_with_nothing_waiting_is_complete():
    found = review("sweep/x", "c", [prepared("org/a"), prepared("org/b")])
    assert found.is_complete is True


def test_a_sweep_with_nothing_in_it_is_not_complete():
    """Nothing to approve is not everything approved."""
    found = review("sweep/x", "c", [])
    assert found.is_complete is False
    assert "nothing to review" in found.summary()


def test_the_total_counts_both_halves():
    found = review("sweep/x", "c", [prepared("org/a"),
                                    FakeOutcome("org/b", "refused", "ahead"),
                                    FakeOutcome("org/c", "needs a worker", "")])
    assert found.total == 3
    assert found.approvable == 1 and len(found.queue) == 2


# --- what gets written down ---------------------------------------------------


def test_the_note_names_every_repository_the_approval_reached():
    """The point of approving twenty-four things at once is that somebody can
    later see it was twenty-four, and which.

    Mutation: write "batch approved" without the names and this fails.
    """
    batch = Batch("fastapi to 0.116.0",
                  [prepared_item("qmcp"), prepared_item("leo")])
    note = approval_note(batch, by="Peter Kagstrom")

    assert "Peter Kagstrom" in note
    assert "fastapi to 0.116.0" in note
    assert "qmcp" in note and "leo" in note
    assert "2 repositories" in note


def test_the_note_reads_correctly_for_one_repository():
    note = approval_note(Batch("c", [prepared_item("only")]), by="Someone")
    assert "1 repository" in note


# --- rows ---------------------------------------------------------------------


def test_rows_carry_what_a_person_reads_before_saying_yes():
    """The repository, the change, and what is being asked. A row without the
    change is a row somebody approves on trust."""
    found = review("sweep/x", "c", [prepared("org/a", ">=0.116.0")])
    row = found.batch.rows()[0]
    assert row[0] == "a"
    assert ">=0.116.0" in row[1]
    assert row[2] == APPROVE


def test_the_batch_is_ordered_so_two_readings_agree():
    """An approval screen that reordered itself between renders is one nobody
    can check against a note written a moment earlier."""
    found = review("sweep/x", "c",
                   [prepared("org/c"), prepared("org/a"), prepared("org/b")])
    assert [i.repo for i in found.batch.items] == ["a", "b", "c"]


# --- one batch per distinct edit ----------------------------------------------


def test_different_edits_become_different_batches():
    """THE ONE THE REAL ARCHIVE FOUND.

    Against twenty-four repositories, seven declare `>=` and two declare `~=`.
    Both rewrite correctly and they are not the same edit, so they are not one
    approval -- putting them together would be a person approving nine things
    having read seven.

    Mutation: put everything prepared in one batch and this fails, because that
    batch is not uniform.
    """
    found = review("sweep/x", "fastapi to 0.116.0", [
        prepared("org/a", ">=0.116.0"),
        prepared("org/b", ">=0.116.0"),
        prepared("org/c", "~=0.116.0"),
    ])
    assert len(found.batches) == 2
    assert all(batch_is_uniform(batch) for batch in found.batches)
    assert found.approvable == 3


def test_the_biggest_batch_comes_first():
    """The common case is what somebody is most likely here for; the smaller
    ones are the exceptions worth noticing after it."""
    found = review("sweep/x", "c", [
        prepared("org/a", "~=1.0"),
        prepared("org/b", ">=1.0"), prepared("org/c", ">=1.0"),
    ])
    assert found.batches[0].size == 2
    assert found.batch.size == 2, "`batch` is the largest one"


def test_a_batch_names_the_edit_it_applies():
    """Two batches described identically would leave a person approving the
    second one unable to see which it is."""
    found = review("sweep/x", "fastapi to 0.116.0", [
        prepared("org/a", ">=0.116.0"), prepared("org/c", "~=0.116.0")])
    names = {batch.change for batch in found.batches}
    assert any(">=0.116.0" in name for name in names)
    assert any("~=0.116.0" in name for name in names)


def test_no_batches_means_no_main_batch():
    """`None` rather than an empty one: there is nothing to approve, and an
    empty batch would read as a batch that approves nothing."""
    assert review("sweep/x", "c", []).batch is None
