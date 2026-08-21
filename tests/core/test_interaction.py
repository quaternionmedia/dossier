"""Everything wanting a person, in one list, and rad optional over it.

THE TESTS WORTH READING ARE THE FIRST TWO. A batch must stay one interaction or
the batching is undone two layers above where it was decided; and the layer must
work with rad absent, because rad is a presentation and not the mechanism.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from dossier.interaction import (
    ANSWER,
    APPROVE,
    DECIDE,
    KINDS,
    PROVIDE,
    Interaction,
    Queue,
    from_harness_asks,
    from_sweep_review,
    gather,
    needs_an_export,
)


@dataclass
class FakeBatch:
    change: str
    items: list

    @property
    def size(self):
        return len(self.items)


@dataclass
class FakeItem:
    repo: str
    detail: str = ""


@dataclass
class FakeReview:
    batches: list
    queue: list


# --- batching survives the abstraction ----------------------------------------


def test_a_batch_is_one_interaction_covering_many():
    """THE ONE THAT MATTERS.

    Seven repositories approved together is one answer. Emitting seven
    interactions here would undo the batching two layers above where it was
    decided, and put the person back in front of seven prompts.

    Mutation: emit one per repository and this fails.
    """
    review = FakeReview(
        batches=[FakeBatch("fastapi to 0.116.0 (>=0.116.0)",
                           [FakeItem(f"r{i}") for i in range(7)])],
        queue=[])
    found = from_sweep_review(review)

    assert len(found) == 1
    assert found[0].covers == 7
    assert found[0].is_batched
    assert found[0].kind == APPROVE


def test_the_queue_counts_what_one_pass_would_settle():
    review = FakeReview(
        batches=[FakeBatch("a", [FakeItem("x")] * 7),
                 FakeBatch("b", [FakeItem("y")] * 2)],
        queue=[FakeItem("z", "already ahead")])
    queue = Queue(items=from_sweep_review(review))

    assert len(queue.items) == 3
    assert queue.covered == 10
    assert "10 settled" in queue.summary()


# --- rad is a presentation, not the mechanism ---------------------------------


def test_the_layer_works_with_rad_absent():
    """THE OTHER ONE THAT MATTERS.

    Everything must still fire without the menu. rad routes to interactions; it
    does not own them, and a layer that imported it would make an optional
    mechanism a required one.

    Mutation: import anything from `dossier.rad` in `interaction.py` and this
    fails.
    """
    import pathlib

    import dossier.interaction as module

    source = pathlib.Path(module.__file__).read_text(encoding="utf-8")
    assert "import rad" not in source
    assert "from dossier.rad" not in source


def test_a_route_is_words_rather_than_a_callable():
    """This layer is read by a terminal today and by a page later. A function
    reference crosses neither."""
    review = FakeReview(batches=[FakeBatch("a", [FakeItem("x")])], queue=[])
    assert isinstance(from_sweep_review(review)[0].route, str)


# --- the four kinds are four actions ------------------------------------------


def test_a_question_with_options_is_answered_and_one_without_is_decided():
    """The harness knows which it asked. Turning a free question into a
    multiple choice puts words in somebody's mouth.

    Mutation: default every ask to `answer` and this fails.
    """
    asked = from_harness_asks([
        {"request_id": "a", "prompt": "which?", "options": ["x", "y"],
         "status": "pending"},
        {"request_id": "b", "prompt": "what should happen here?",
         "status": "pending"},
    ])
    kinds = {i.id: i.kind for i in asked}
    assert kinds["a"] == ANSWER and kinds["b"] == DECIDE


def test_a_value_nobody_can_guess_is_provide_rather_than_answer():
    """No list of options contains a path on somebody's disk."""

    class Empty:
        reachable = False
        indexed = False

    found = needs_an_export(Empty())
    assert found and found[0].kind == PROVIDE
    assert found[0].options == ()


def test_an_answered_ask_is_not_still_waiting():
    asked = from_harness_asks([{"request_id": "a", "prompt": "p",
                                "status": "answered"}])
    assert asked == []


def test_a_populated_archive_asks_for_nothing():
    class Full:
        reachable = True
        indexed = True

    assert needs_an_export(Full()) == []


# --- a source that cannot be asked --------------------------------------------


def test_a_source_that_raises_is_named_rather_than_counted_as_empty():
    """Nothing to say and nobody answering look identical in a total and are
    opposite facts.

    Mutation: swallow the failure and this fails.
    """
    def explodes():
        raise RuntimeError("no harness")

    queue = gather({"harness": explodes,
                    "sweep": lambda: [Interaction("s", APPROVE, "p", "sweep")]})

    assert len(queue.items) == 1
    assert queue.unreachable == ["harness"]
    assert "could not be asked" in queue.summary()


def test_an_empty_queue_with_an_unreachable_source_does_not_read_as_quiet():
    queue = gather({"harness": lambda: (_ for _ in ()).throw(OSError("down"))})
    assert "could not be asked" in queue.summary()
    assert "nothing is waiting" not in queue.summary()


def test_a_genuinely_empty_queue_says_so_plainly():
    assert "nothing is waiting" in gather({"a": list}).summary()


# --- ordering -----------------------------------------------------------------


def test_the_cheapest_answers_come_first():
    """One keystroke settling seven repositories is a better use of the first
    minute than a judgement settling one. That is cost, not importance --
    nothing here knows what is urgent.
    """
    queue = Queue(items=[
        Interaction("one", DECIDE, "think about this", "sweep"),
        Interaction("many", APPROVE, "approve seven", "sweep", covers=7),
    ])
    assert [i.id for i in queue.ordered()] == ["many", "one"]


def test_ordering_is_stable_so_two_readings_agree():
    items = [Interaction(f"i{n}", APPROVE, "p", "sweep") for n in range(5)]
    queue = Queue(items=items)
    assert [i.id for i in queue.ordered()] == [i.id for i in queue.ordered()]


def test_every_kind_is_one_of_the_declared_four():
    review = FakeReview(batches=[FakeBatch("a", [FakeItem("x")])],
                        queue=[FakeItem("y", "why")])
    for item in from_sweep_review(review):
        assert item.kind in KINDS


# --- rad optional in fact, not only in intention ------------------------------


def test_the_application_imports_with_rad_absent():
    """THE CLAIM, MADE CHECKABLE.

    "Everything still fires without rad" was intention rather than fact: three
    panels imported `dossier.rad.tokens` at module level, so the whole
    application failed to import without rad installed. The menu was already
    optional; the palette had accidentally not been, and nobody noticed because
    both live under `rad/`.

    **IN A SUBPROCESS, BECAUSE THE OBVIOUS VERSION IS THE HAZARD THIS SUITE
    ALREADY GUARDS.** Blocking the import in-process means clearing every
    `dossier` module from `sys.modules` and importing again -- which re-registers
    every SQLModel table and raises `InvalidRequestError`, and would leave the
    modules swapped for whatever ran next. A fresh interpreter answers the same
    question and leaves nothing behind.

    Mutation: import `dossier.rad.tokens` directly in any panel and this fails.
    """
    import subprocess
    import sys
    import textwrap

    script = textwrap.dedent("""
        import builtins
        real = builtins.__import__

        def refuse(name, *a, **k):
            if name.startswith('dossier.rad'):
                raise ImportError('rad is not installed')
            return real(name, *a, **k)

        builtins.__import__ = refuse
        from dossier.tui.app import DossierApp
        from dossier.palette import rad_is_present, roles
        assert rad_is_present() is False
        assert roles().wedge_label
        print('ok')
    """)
    done = subprocess.run([sys.executable, "-c", script],
                          capture_output=True, text=True, timeout=180)
    assert done.returncode == 0, (
        "the panel does not import without rad: " + done.stderr[-1500:])
    assert "ok" in done.stdout


def test_the_fallback_palette_answers_every_role_rad_does():
    """A role rad has and the fallback does not is an attribute error on a
    machine without rad -- found at draw time, by somebody who cannot fix it.

    Mutation: drop a role from the fallback and this fails.
    """
    from dossier.palette import _FALLBACK_ROLES, rad_is_present, roles

    if not rad_is_present():
        pytest.skip("rad is not installed, so there is nothing to compare")

    from dossier.rad.tokens import roles as rad_roles

    for name in vars(rad_roles()):
        assert name in _FALLBACK_ROLES, f"the fallback has no {name}"


def test_the_fallback_is_reported_rather_than_silent():
    """An installation running on the fallback should be able to find that out
    without reading a stack trace."""
    from dossier.palette import rad_is_present

    assert isinstance(rad_is_present(), bool)
