"""What a view is waiting for, and whether the thing it names would fix it.

**FOUR BLIND READINGS FOUND FOUR DEFECTS, AND EACH IS A TEST BELOW.** The
readiness model was read from four positions before it was trusted -- a
newcomer on a bare machine, an operator whose harness had died, a maintainer
adding a view, and a reader checking the claims against what is measured. None
of the four is hypothetical; each found something the others did not:

  * *the newcomer* met nine near-identical entries for one fact -- nothing is
    selected -- and learned to stop reading rather than that nine things were
    wrong;
  * *the operator* was told to run `dossier harness queue` when the harness was
    down, which reported the same problem and then named the real fix. A remedy
    has to be the fix, not a hop toward it;
  * *the maintainer* found `dossier governance refresh` offered as a remedy for
    a missing corpus. **That command has never existed**, and nothing checked;
  * *the reader* found `Branches` reporting ready while its clone need had
    never been looked for, because an unchecked need answered `unknown` and
    `unknown` deliberately does not block.

THE MUTATIONS, per P16, quoted as they printed:

`satisfied_by` on the corpus need set back to `dossier governance refresh`:

    AssertionError: tab-governance offers 'dossier governance refresh' as the
    way to satisfy 'corpus', and `governance` has no `refresh`

the clone branch returning UNKNOWN when no repository is named:

    AssertionError: Branches reported ready while nothing had looked for a
    clone
"""

from __future__ import annotations

import click
import pytest

from dossier import readiness, views
from dossier.cli import cli


def names() -> set[str]:
    return {view.name for view in views.VIEWS}


# --- what every declaration has to satisfy --------------------------------------


def test_every_need_names_one_of_the_declared_keys():
    """A key outside `NEEDS` is one no resolver has a branch for, and it would
    answer `unknown` -- which does not block, so the view would read ready."""
    for view in views.VIEWS:
        for need in view.needs:
            assert need.key in views.NEEDS, (
                f"{view.tab} needs {need.key!r}, which is not one of "
                f"{views.NEEDS}")


def test_every_need_says_why_in_a_persons_words():
    """A precondition with no reason is a refusal a reader cannot argue with."""
    for view in views.VIEWS:
        for need in view.needs:
            assert len(need.because.split()) >= 6, (
                f"{view.tab}'s {need.key} need does not say why")


def test_every_remedy_resolves_to_a_view_or_a_runnable_command():
    """**THE ONE THAT CAUGHT A DEAD REMEDY THE DAY IT WAS WRITTEN.**

    `dossier governance refresh` was offered as the way to satisfy a missing
    corpus and has never been a command. A remedy nobody can run leaves a
    reader exactly where the blank panel did, which is the whole thing this
    model exists to stop.

    A remedy is either a view in this registry or a command this CLI has.
    `uv run qmcp serve` is neither and is exempt below, for a stated reason.
    """
    ctx = click.Context(cli)
    known = names()
    broken = []
    for view in views.VIEWS:
        for need in view.needs:
            by = need.satisfied_by
            if by in known or by in OTHER_PROGRAMS:
                continue
            parts = by.replace("dossier ", "").split()
            group = cli.get_command(ctx, parts[0])
            if group is None:
                broken.append(f"{view.tab} offers {by!r} as the way to satisfy "
                              f"{need.key!r}, and `{parts[0]}` is not a command")
                continue
            if len(parts) > 1 and isinstance(group, click.Group):
                if group.get_command(ctx, parts[1]) is None:
                    broken.append(
                        f"{view.tab} offers {by!r} as the way to satisfy "
                        f"{need.key!r}, and `{parts[0]}` has no `{parts[1]}`")
    assert not broken, "\n".join(broken)


# Remedies that are another program's command, not this CLI's. **Named rather
# than pattern-matched**: `uv run ...` would let any string through, and the
# point of the check above is that a remedy is something somebody can run.
OTHER_PROGRAMS = {
    # The harness is a separate process on a separate port. dossier can read it
    # and cannot start it -- telling a reader to run a dossier command here is
    # what the operator's reading found wrong.
    "uv run qmcp serve",
}


@pytest.mark.parametrize("remedy", sorted(OTHER_PROGRAMS))
def test_nothing_is_exempted_that_this_cli_could_do_itself(remedy: str):
    """An exemption that stopped being true is a hole nobody can see."""
    ctx = click.Context(cli)
    first = remedy.replace("uv run ", "").split()[0]
    assert first != "dossier" or cli.get_command(ctx, first) is None


# --- the four readings ----------------------------------------------------------


def test_one_missing_thing_is_one_entry_however_many_views_it_holds_up():
    """The newcomer's reading. Nine views waiting on a selection is one fact.

    Grouped on what is missing rather than on how each view words it --
    `views._of_one_repository` varies the sentence per view on purpose, and
    keying on that produced nine groups of one, which is the wall again.
    """
    text = readiness.render(readiness.survey(
        harness_base="http://127.0.0.1:9", corpus="/nowhere"))

    assert text.count("-> overview") == 1, (
        "the views waiting on a selection were not gathered into one entry")

    # **THE COUNT IS DERIVED, NOT TYPED.** An earlier version asserted the
    # literal "9 waiting on project", which is a number the registry decides:
    # adding a tenth view that needs a repository would fail this test while
    # nothing was wrong.
    held = sum(1 for v in views.VIEWS
               if v.needs and v.needs[0].key == views.PROJECT)
    assert f"{held} waiting on project" in text


def test_a_remedy_for_a_dead_harness_is_the_thing_that_starts_it():
    """The operator's reading. A remedy that reports the problem is a hop, not
    a fix."""
    for tab in ("tab-topology", "tab-harness"):
        view = views.BY_TAB[tab]
        remedy = view.needs[0].satisfied_by
        assert "serve" in remedy, f"{tab}'s remedy does not start anything"
        assert "harness queue" not in remedy, (
            f"{tab} sends a reader to a command that reads the harness it "
            f"cannot reach")


def test_a_need_nobody_looked_for_does_not_read_as_ready():
    """The reader's reading. `unknown` does not block, so a need that answers
    `unknown` when it simply was not asked makes the view look available."""
    branches = views.BY_TAB["tab-branches"]

    result = readiness.readiness(branches, selection=object())

    assert not result.ready, (
        "Branches reported ready while nothing had looked for a clone")
    assert result.blocking[0].need.key == views.CLONE


def test_a_need_that_cannot_be_measured_is_unknown_and_does_not_block():
    """And the other direction, which is the one worth keeping.

    Whether the overview's reading has been taken is recorded nowhere, so
    `attention` answers `unknown`. Refusing to show Outstanding on the strength
    of a measurement that never happened would be the worse of the two errors.
    """
    outstanding = views.BY_TAB["tab-waiting"]

    result = readiness.readiness(outstanding, selection=object())

    assert result.ready
    assert result.answers[0].state == readiness.UNKNOWN


# --- what the resolver measures -------------------------------------------------


def test_a_harness_that_is_not_answering_is_unmet_rather_than_unknown():
    """Not running is a real answer, and a common one: it is a separate
    process that very often has not been started."""
    answer = readiness.check(views.Need(views.HARNESS, "because", "x"),
                             harness_base="http://127.0.0.1:9")

    assert answer.state == readiness.UNMET
    assert answer.blocks


def test_a_corpus_present_without_its_documents_is_unmet_and_says_which(
        tmp_path):
    """A pin that predates the generated documents is the ordinary case while
    a corpus is new, and it is not the same as no corpus at all."""
    (tmp_path / "ci").mkdir()

    answer = readiness.check(views.Need(views.CORPUS, "because", "x"),
                             corpus=tmp_path)

    assert answer.state == readiness.UNMET
    assert "generated documents" in answer.detail


def test_every_view_with_no_needs_is_ready_on_a_bare_machine():
    """The floor: a view that answers from this database alone always can."""
    for result in readiness.survey(harness_base="http://127.0.0.1:9",
                                   corpus="/nowhere"):
        if not result.view.needs:
            assert result.ready, f"{result.view.tab} declares nothing and is "\
                                 f"not ready"


def test_the_survey_covers_the_whole_registry():
    """A survey that quietly dropped a view would report a tidier estate."""
    assert len(readiness.survey()) == len(views.VIEWS)
