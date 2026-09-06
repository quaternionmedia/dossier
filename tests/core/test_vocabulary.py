"""Every word this application says to a person means one thing.

**"THREAD" MEANT THREE**, and the collision was invisible from inside each of
the three modules that used it — a conversation the harness archived, a
governance thread out of `harness-status.json`, and Textual's background worker.

**IT HAD ALREADY COST SOMETHING.** `views.py` described the `tab-threads` pane
as "Every line of work in flight, most idle first" and named `dossier governance
threads` as the equivalent command. Both belong to the *second* sense. The pane
shows the first. The registry feeds the ring, the settings list, the command
sheet and `docs/commands.md`, so four surfaces published a description of a pane
that does not exist — and the command it named exists and shows something else,
which is the worst of the three possible wrongs.

Nothing in any one module could tell you that. A list can, which is what
`dossier/vocabulary.py` is and what this checks.
"""

from __future__ import annotations

import pytest

from dossier import vocabulary
from dossier.vocabulary import AMBIGUOUS, BY_WORD, TERMS, qualified


# --- the list itself ----------------------------------------------------------


def test_there_are_terms_to_check():
    """A list that emptied would make every check below vacuous, and a vacuous
    check reports green."""
    assert len(TERMS) >= 4, TERMS


@pytest.mark.parametrize("term", TERMS, ids=lambda t: t.word)
def test_every_term_says_what_it_means_and_where_it_lives(term):
    """A word with no meaning written down is a word somebody will reuse.

    Mutation: empty any `means` and this fails.
    """
    assert len(term.means) > 20, f"{term.word}: the meaning is a label"
    assert term.lives_in, f"{term.word} names no module, table or pane"


@pytest.mark.parametrize("term", TERMS, ids=lambda t: t.word)
def test_a_borrowed_word_says_whose_it_is(term):
    """**A BORROWED WORD IS A DECISION, NOT AN OVERSIGHT**, and from every
    other angle a name we chose badly and a name we did not choose look
    identical — the same argument `Action.only` makes about a one-route action.

    Three of these are borrowed: the harness's `/v1/threads`, the corpus's
    `harness-status.json`, and Textual's `@work(thread=True)`. None of them is
    ours to rename, and all three had to be said out loud.
    """
    if AMBIGUOUS not in term.word and term.word != vocabulary.WORKER:
        return
    assert len(term.borrowed) > 25, (
        f"{term.word} keeps a word this repository does not own and does not "
        f"say whose it is")


def test_no_two_terms_claim_one_word():
    assert len(BY_WORD) == len(TERMS)


# --- the rule -----------------------------------------------------------------


def test_the_qualifier_lets_a_settled_phrase_through():
    """`governance thread` contains the ambiguous word and is a settled phrase,
    so it must pass; a bare use must not.

    Mutation: match the shorter phrase first and `governance thread` fails.
    """
    assert qualified("Every governance thread, most idle first.")
    assert qualified("Every conversation the harness has archived.")
    assert not qualified("Every thread, most idle first.")
    assert not qualified("THREADS in flight")


def test_the_qualifier_ignores_case():
    """A rule that only held in lower case would be a rule about formatting."""
    assert not qualified("Thread archive")
    assert qualified("Governance Thread stages")


# --- the user-facing surface --------------------------------------------------


def test_no_view_says_the_ambiguous_word_bare():
    """**THE ONE THIS EXISTS FOR.**

    `views.py` is read by the ring, the settings list, the command sheet and
    `docs/commands.md`. A word that means three things there means three things
    on four pages.

    Mutation: retitle the pane "Threads" again and this fails.
    """
    from dossier.views import VIEWS

    unqualified = [(v.tab, v.title, v.summary) for v in VIEWS
                   if not qualified(v.title) or not qualified(v.summary)]
    assert not unqualified, (
        f"these say {AMBIGUOUS!r} without saying which one: {unqualified}. "
        f"Use one of {vocabulary.INSTEAD}.")


def test_no_ring_wedge_says_the_ambiguous_word_bare():
    """The menu is the other place a person reads these words, and it is built
    from `views.py` plus the hand-written verbs in `rad/palette.py`.

    Mutation: label a wedge "Ingest threads" and this fails.
    """
    from dossier.rad.index import index

    unqualified = [c.number + " " + c.label for c in index()
                   if not qualified(c.label)]
    assert not unqualified, unqualified


def test_no_action_label_says_the_ambiguous_word_bare():
    from dossier.actions import REGISTRY

    unqualified = [a.id for a in REGISTRY if not qualified(a.label)]
    assert not unqualified, unqualified


# --- the defect that proved it ------------------------------------------------


def test_the_conversation_pane_describes_the_conversation_pane():
    """**THE REGRESSION THIS FILE WAS WRITTEN FOR.**

    The registry entry and the facet that fills the pane have to be about the
    same entity. They were not: the entry described governance threads and the
    facet renders the harness's conversation archive.

    Mutation: put the old summary back and this fails.
    """
    from dossier.facets import BY_TAB as FACETS
    from dossier.views import BY_TAB as VIEWS

    view = VIEWS["tab-threads"]
    facet = FACETS["tab-threads"][0]

    assert "conversation" in view.summary.lower(), view.summary
    assert "conversation" in facet.title.lower(), facet.title
    assert "in flight" not in view.summary.lower(), (
        "that is the governance-thread pane's reading, not this one's")


def test_that_pane_does_not_name_a_command_for_a_different_entity():
    """It named `dossier governance threads`, which exists and reads
    `GovernanceThread` rows — a command that works and answers a question the
    reader did not ask is worse than no command at all.

    `View.cli` is for named routes only; the derived `dossier show threads`
    reaches this one, so empty is the correct value.

    Mutation: name any `governance` command here and this fails.
    """
    from dossier.views import BY_TAB as VIEWS

    cli = VIEWS["tab-threads"].cli
    assert "governance" not in cli, (
        f"{cli!r} reads governance threads, not conversations")


def test_the_governance_pane_is_the_one_about_work_in_flight():
    """The other half of the same assertion: the reading the conversation pane
    was wrongly given still has to exist somewhere.

    Mutation: delete the governance-thread table and this fails.
    """
    from dossier.tui.app import DossierApp
    import inspect

    source = inspect.getsource(DossierApp)
    assert "governance-threads-table" in source, (
        "nothing shows governance threads any more")


# --- the exemptions are reasoned ----------------------------------------------


def test_every_place_that_keeps_the_bare_word_says_why():
    """An exemption list with no reasons becomes the place every new collision
    is filed.

    Mutation: add a path with an empty reason and this fails.
    """
    for where, why in vocabulary.BARE_IS_CORRECT.items():
        assert len(why) > 30, f"{where}: the reason is a label"


def test_those_places_exist():
    """A reason attached to a path that moved is a reason nobody can check."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[2] / "src" / "dossier"
    missing = [where for where in vocabulary.BARE_IS_CORRECT
               if where.endswith(".py")
               and not (root / where.split("dossier/")[-1]).exists()]
    assert not missing, missing
