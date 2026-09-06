"""One word per thing, and what each one means.

**"THREAD" MEANT THREE DIFFERENT THINGS AND NOTHING SAID SO**, which is the same
shape of failure `actions.py` and `views.py` were each written against: not one
of the three is wrong from inside its own module, and the collision is only
visible from a list.

The three, measured:

  * a **conversation** the harness archived -- `dossier/threads.py`, the
    `tab-threads` pane, `facets.threads_org`;
  * a **governance thread**, one line of work in flight read out of
    `harness-status.json` -- `models/governance.GovernanceThread`, the second
    table on the Governance pane;
  * a **worker**, Textual's background thread -- 52 `call_from_thread` calls and
    every `@work(thread=True)` in `tui/app.py`.

**AND IT HAD ALREADY COST SOMETHING.** `views.py` described `tab-threads` as
"Every line of work in flight, most idle first" and named `dossier governance
threads` as the command that reaches the same reading. Both belong to the
*second* sense. The pane shows the first: archived conversations, sorted
disagreements-first, from a facet titled "Thread archive". So the registry that
feeds the ring, the settings list, the command sheet and `docs/commands.md` told
a reader the tab showed work in flight and named a command that shows something
else -- and every one of those pages published it.

THE RULE. **Nothing this application says to a person uses the bare word
"thread".** Each sense has a name below and that name is used. The word survives
in exactly two places, and both are somebody else's:

  * `dossier/threads.py` and its `/v1/threads` calls, because that is the
    harness's endpoint and renaming our half of a seam does not rename theirs;
  * `GovernanceThread` and its table, because that is the corpus's word in
    `harness-status.json`, and a reader comparing the two documents needs them
    to match.

Both are qualified everywhere a person sees them.

WHAT THIS IS NOT. A style guide, or a list of every noun. It is the list of
words that were carrying more than one meaning, which is the only kind worth
writing down -- `tests/core/test_vocabulary.py` checks the user-facing surface
against it, and a word with one meaning needs no check.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Term:
    """One word, one meaning, and where it is allowed to appear."""

    word: str
    """The settled word. What a person reads."""

    means: str
    """The one thing it names."""

    lives_in: tuple[str, ...]
    """Modules, tables or panes that carry it."""

    not_the_same_as: tuple[str, ...] = ()
    """The words it was being confused with."""

    borrowed: str = ""
    """Whose word it is, when it is not ours to change.

    **A BORROWED WORD IS A DECISION, NOT AN OVERSIGHT**, and the difference has
    to be written down for the same reason `Action.only` writes it down: from
    every other angle a name we chose badly and a name we did not choose look
    identical.
    """


CONVERSATION = "conversation"
GOVERNANCE_THREAD = "governance thread"
DELTA = "delta"
WORKER = "worker"


TERMS: tuple[Term, ...] = (
    Term(
        word=CONVERSATION,
        means="one archived chat, with its turns, as the harness holds it",
        lives_in=("dossier/threads.py", "tab-threads", "facets.threads_org"),
        not_the_same_as=(GOVERNANCE_THREAD, WORKER),
        borrowed="the harness calls these `/v1/threads`, so the module and the "
                 "endpoint keep that word; what a person reads does not",
    ),
    Term(
        word=GOVERNANCE_THREAD,
        means="one line of work in flight, as `harness-status.json` reports it",
        lives_in=("models/governance.GovernanceThread", "governance_thread",
                  "governance-threads-table"),
        not_the_same_as=(CONVERSATION, WORKER),
        borrowed="the corpus's word, and a reader comparing this pane against "
                 "`harness-status.json` needs the two to match; it is never "
                 "written bare",
    ),
    Term(
        word=DELTA,
        means="the unit of work this database keeps -- what a conversation, a "
              "governance thread and an open pull request all become",
        lives_in=("models.ProjectDelta", "tab-deltas", "dossier deltas"),
    ),
    Term(
        word=WORKER,
        means="a background job, so the panel keeps drawing while it runs",
        lives_in=("tui/app.py",),
        not_the_same_as=(CONVERSATION, GOVERNANCE_THREAD),
        borrowed="Textual spells it `@work(thread=True)` and "
                 "`call_from_thread`; the decorator is theirs, the prose is "
                 "ours and says worker",
    ),
)

BY_WORD: dict[str, Term] = {term.word: term for term in TERMS}


# The word that was carrying all of it, and what to say instead. Read by
# `test_vocabulary.py`, which fails on a bare use in anything a person reads.
AMBIGUOUS = "thread"

INSTEAD: tuple[str, ...] = (CONVERSATION, GOVERNANCE_THREAD, DELTA, WORKER)


# Where a bare `thread` is still correct, each with why. **Nothing is exempted
# without a reason** -- an exemption list with no reasons becomes the place
# every new collision is filed.
BARE_IS_CORRECT: dict[str, str] = {
    "dossier/threads.py":
        "the module is one half of a seam whose other half serves "
        "`/v1/threads`; naming it for our word would hide which endpoint it "
        "calls",
    "models/governance.py":
        "`GovernanceThread` is the corpus's row and its table name; the class "
        "is already qualified by its prefix",
    "parsers/governance.py":
        "reads `harness-status.json`, whose keys are the corpus's",
    "models/harness.py":
        "the harness payload's own field names",
}


def says(word: str) -> Term | None:
    """The term for a settled word, or None."""
    return BY_WORD.get(word)


def qualified(text: str) -> bool:
    """Whether `text` uses the ambiguous word only in a settled phrase.

    Case-insensitive, because a heading capitalises and a sentence does not,
    and a rule that only held in lower case would be a rule about formatting.
    """
    lowered = text.lower()
    if AMBIGUOUS not in lowered:
        return True
    # Every settled phrase that legitimately contains it, longest first so
    # `governance thread` is matched before `thread` inside it.
    allowed = sorted((t.word for t in TERMS if AMBIGUOUS in t.word),
                     key=len, reverse=True)
    for phrase in allowed:
        lowered = lowered.replace(phrase, "")
    return AMBIGUOUS not in lowered
