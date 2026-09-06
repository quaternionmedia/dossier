"""Whether this installation is set up, and what to press where it is not.

**AN EMPTY PANEL IS SIX DIFFERENT PROBLEMS WEARING ONE FACE** — no database, an
unmigrated one, no rows in it, no GitHub token, no harness, no clones. Every
pane in the dashboard renders all six as the same empty table, so a first run
showed somebody an empty screen and no reason to prefer any explanation.

**AND EVERY REMEDY IS READ FROM THE MENU.** A checklist is the worst possible
place to type a route: it is read exactly by the people who cannot tell a wrong
keystroke from a broken program. `keystroke()` computes it from the palette.

Nothing here reaches the network except the harness step, which is exercised
against a double.
"""

from __future__ import annotations

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from dossier import onboarding
from dossier.models.schemas import Project
from dossier.onboarding import DONE, SKIPPED, TODO, UNKNOWN, Checklist, Step


@pytest.fixture()
def session():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as made:
        yield made


@pytest.fixture()
def no_token(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)


# --- a step names the route that completes it ---------------------------------


def test_a_remedy_reads_its_keys_from_the_ring():
    """THE ONE THIS EXISTS FOR.

    The action id is stored; the keystrokes are computed. A palette that moves
    moves this with it.

    Mutation: store `"m 4 3"` on the step instead of `reach.download` and
    `test_no_route_is_typed_into_text_a_person_reads` fails.
    """
    from dossier.rad.index import keystroke

    step = Step("Repositories indexed", TODO, "nothing yet",
                action="reach.download")

    assert step.keys() == keystroke("reach.download")
    assert step.keys(), "the ring cannot reach it, so this asserts nothing"
    assert step.remedy() == f"press {step.keys()}"


def test_a_step_the_ring_cannot_reach_names_its_command():
    step = Step("A GitHub token", TODO, "unset",
                command="export GITHUB_TOKEN=...")
    assert step.remedy() == "run `export GITHUB_TOKEN=...`"


def test_a_step_with_both_offers_both():
    step = Step("x", TODO, "y", action="reach.download", command="dossier z")
    said = step.remedy()
    assert said.startswith("press ") and "or run `dossier z`" in said


def test_a_step_with_neither_says_that_is_the_finding():
    """An act nothing reaches is worse than one that is merely undone, and the
    checklist has to say which it is looking at."""
    assert "no route" in Step("x", TODO, "y").remedy()


def test_a_done_step_offers_no_remedy():
    """A checklist that told somebody how to do what they have done is one they
    stop reading.

    Mutation: return the remedy regardless of state and this fails.
    """
    assert Step("x", DONE, "y", action="reach.download").remedy() == ""
    assert Step("x", SKIPPED, "y", command="a").remedy() == ""


def test_every_step_that_names_an_action_names_one_the_ring_has(session,
                                                                no_token):
    """**A CHECKLIST NAMING A DEAD ACTION IS THE FAILURE THIS FILE GUARDS.**
    `keystroke` returns the empty string for an action the ring cannot reach,
    and the remedy would then quietly become "run ..." or nothing at all.

    Mutation: point a step at `reach.nothing` and this fails.
    """
    from dossier.rad.index import by_action

    known = set(by_action())
    found = onboarding.run(session)
    named = [s for s in found.steps if s.action]

    assert named, "no step names a ring action, so this checks nothing"
    for step in named:
        assert step.action in known, (
            f"{step.name} points at `{step.action}`, which the ring cannot "
            f"reach, so its remedy would be silent")


# --- the checklist ------------------------------------------------------------


def test_the_checklist_runs_every_step(session, no_token):
    found = onboarding.run(session)
    assert len(found.steps) == len(onboarding.STEPS)
    assert all(s.name for s in found.steps)


def test_a_step_that_raises_does_not_take_the_checklist_with_it():
    """The remaining five are exactly what somebody needs when one is broken.

    Mutation: let the exception out of `run` and this fails.
    """
    def explodes(**_):
        raise RuntimeError("nope")

    found = onboarding.run(None, steps=(explodes, onboarding.a_github_token))

    assert len(found.steps) == 2
    assert found.steps[0].state == UNKNOWN
    assert "nope" in found.steps[0].detail


def test_a_raised_step_does_not_paste_a_whole_traceback_into_a_cell():
    """A SQLAlchemy error carries the entire statement, and pasting it into a
    table cell makes the one row reporting a problem the one nobody can read.

    Mutation: keep the full message and this fails.
    """
    def explodes(**_):
        raise RuntimeError("first line\nSELECT " + "col, " * 200)

    found = onboarding.run(None, steps=(explodes,))
    assert "\n" not in found.steps[0].detail
    assert len(found.steps[0].detail) < 220, found.steps[0].detail


def test_an_unknown_is_not_a_pass():
    """`diagnostics.Report` makes the same argument: a checklist that went
    quiet because something moved would report a working installation while
    checking nothing.

    Mutation: ignore unknowns in `is_ready` and this fails.
    """
    found = Checklist(steps=[Step("a", DONE, "x"), Step("b", UNKNOWN, "y")])
    assert not found.is_ready
    assert "could not be established" in found.summary()


def test_an_empty_checklist_is_not_ready():
    assert not Checklist().is_ready
    assert "no steps ran at all" in Checklist().summary()


def test_an_optional_step_left_undone_does_not_block_readiness():
    """The harness and the corpus are ordinary things not to have. A checklist
    showing six red rows to somebody correctly set up is one nobody reads
    twice.

    Mutation: count optional steps in `outstanding` and this fails.
    """
    found = Checklist(steps=[Step("a", DONE, "x"),
                             Step("b", TODO, "y", required=False)])
    assert found.is_ready
    assert found.next_step() is None


def test_the_next_step_is_the_first_outstanding_required_one():
    """Order is the order they have to happen in — a token before a download,
    a download before a clone — so this is genuinely next rather than the
    first red row.

    Mutation: reorder `STEPS` and the guidance stops being a sequence.
    """
    names = [s.__name__ for s in onboarding.STEPS]
    assert names.index("a_github_token") < names.index("something_in_it")
    assert names.index("something_in_it") < names.index("clones_on_this_disk")


# --- the individual steps -----------------------------------------------------


def test_an_empty_dossier_says_every_pane_is_empty(session, no_token):
    step = onboarding.something_in_it(session=session)
    assert step.state == TODO
    assert step.action == "reach.download"


def test_a_filled_dossier_counts_what_is_in_it(session):
    session.add(Project(name="qm/a", full_name="qm/a"))
    session.commit()
    step = onboarding.something_in_it(session=session)
    assert step.state == DONE and "1 project" in step.detail


def test_the_token_step_never_renders_the_token(monkeypatch):
    """**A CHECKLIST THAT PRINTED SOMEBODY'S TOKEN WOULD PUT IT IN THE FIRST
    SCREENSHOT THEY SENT ASKING FOR HELP.**

    Mutation: interpolate the value and this fails.
    """
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_supersecretvalue")
    step = onboarding.a_github_token()

    assert step.state == DONE
    assert "ghp_supersecretvalue" not in step.detail
    assert "ghp_supersecretvalue" not in step.remedy()


def test_a_missing_token_says_what_it_costs(no_token):
    step = onboarding.a_github_token()
    assert step.state == TODO
    assert "60 requests" in step.detail, "it does not say why this matters"


def test_an_in_memory_database_is_not_reported_as_a_file(session):
    """**THE TWO-DATABASES FAILURE WITH A TICK BESIDE IT.** A panel open on an
    in-memory database is not reading `dossier.db`, and naming that file would
    say it was.

    Mutation: fall through to `health.check()` and this reports a path.
    """
    step = onboarding.a_database(session=session)
    assert step.state == DONE
    assert "in memory" in step.detail
    assert ".db" not in step.detail


def test_nothing_indexed_means_nothing_can_be_absent(session):
    """A clone step that reported "0 of 0 absent" on a fresh install would be
    a red row for a state that is correct."""
    step = onboarding.clones_on_this_disk(session=session)
    assert step.state == SKIPPED and not step.required


def test_an_unreachable_harness_is_skipped_and_not_failed(monkeypatch):
    """Most installations never want one. A missing optional dependency is not
    a fault.

    Mutation: return TODO and a correctly set-up install shows a red row.
    """
    class Absent:
        reachable = False

    monkeypatch.setattr("dossier.threads.fetch", lambda *a, **k: Absent())
    step = onboarding.the_harness()

    assert step.state == SKIPPED and not step.required


def test_a_harness_that_cannot_be_asked_is_unknown(monkeypatch):
    """Not the same as one that answered "no". `threads.py` makes exactly this
    distinction about the same service."""
    def refuses(*a, **k):
        raise OSError("connection refused")

    monkeypatch.setattr("dossier.threads.fetch", refuses)
    step = onboarding.the_harness()

    assert step.state == UNKNOWN
    assert "connection refused" in step.detail


# --- rendering ----------------------------------------------------------------


def test_the_rows_carry_the_remedy(session, no_token):
    """The table a person reads has the "what to do" column filled for exactly
    the rows that need it.

    Mutation: drop the remedy column and the pane becomes a list of problems
    with no answers.
    """
    found = onboarding.run(session)
    rows = onboarding.rows(found)

    assert len(rows) == len(found.steps)
    assert len(onboarding.COLUMNS) == len(rows[0])
    todo = [r for r in rows if r[1] == TODO]
    assert todo, "nothing is outstanding, so this checks nothing"
    assert all(r[3] for r in todo), "an outstanding step with no remedy"


def test_the_rendering_is_ascii_so_a_cp1252_console_can_print_it(session,
                                                                 no_token):
    """This repository has already lost a demo to a glyph a Windows console
    could not encode."""
    drawn = onboarding.render(onboarding.run(session))
    drawn.encode("cp1252")
    assert drawn.strip()


def test_the_rendering_names_the_next_step(session, no_token):
    drawn = onboarding.render(onboarding.run(session))
    assert "Next:" in drawn
