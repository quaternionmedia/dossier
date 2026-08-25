"""A route a person is shown comes from the menu, not from a string beside it.

**THE MOTIVATING CLAIM FOR THIS WAS WRONG, AND THAT IS WORTH WRITING DOWN.**
`Go` grew a group level, the Sweep *tab* became `m 8 6 6`, and five hand-typed
`m 6 4`s looked stale. They were not: `sweep.review` still sits at `6.4`,
because `Do` was never reordered — `m 8 6 6` opens the tab and `m 6 4` runs the
review, and they are different acts. Every copy was correct.

So this guard is not a repair. It is the rule the near-miss argued for: had `Do`
been the verb that grew a level instead of `Go`, `interaction.py` would have
handed a person the wrong keys on every queued approval, and nothing would have
said so. A route is a fact about the menu, and the menu is where it should be
read from.

WHAT IT CHECKS, AND WHAT IT DELIBERATELY DOES NOT. Only string literals that are
not docstrings — the text shown at runtime, and the data handed to other
systems. Docstrings and comments explain the scheme and have to be able to name
`6.2` to do it. A stale docstring misleads somebody reading the code; a stale
runtime string misleads somebody pressing keys, and only one of those is a
defect in the product.

It also could not tell `0.116.0` from a route when it read raw text, which is
why it reads the syntax tree instead.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

SRC = Path("src/dossier")

# `m 8 6 6`, `m` `8` `6` `6`, `[b]m 6 4[/b]`.
KEYSTROKE = re.compile(r"\bm(?:\W{0,4}\d\b){2,}")
# A dotted route in backticks. Two digits or more, which is what a cell path is.
DOTTED = re.compile(r"`\d(?:\.\d)+`")
# **AND THE SAME ROUTE WITH NO BACKTICKS ROUND IT.** The first version of this
# required them, and `"Press 6.2 again to fetch {n}."` sat in the sync
# confirmation the whole time -- a route shown to a person, in the exact form a
# person reads, invisible to a guard written for the form a *document* uses.
#
# Anchored on the verb rather than on the digits, because a bare `0.116.0` is a
# version and this has already mistaken one for a route once.
SPOKEN = re.compile(r"[Pp]ress\s+\d(?:[\s.]+\d)+")

# **THE RAD PACKAGE IS THE MENU.** It is where the numbers come from, and its
# own strings draw the sheet that explains them.
ALLOWED_PACKAGES = {"rad"}


def _runtime_strings(path: Path):
    """Every string literal in the file that is not a docstring.

    Read from the syntax tree rather than the text, so a comment explaining the
    scheme and a version number in prose are both invisible here -- the first
    read of this flagged `0.116.0` and a paragraph about generic `1.2.3`
    numbering, neither of which is a route.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))

    # **ANY BARE STRING STATEMENT, NOT ONLY A LEADING ONE.** The first version
    # looked at the first statement of a module, class or function, and this
    # corpus documents dataclass fields with a bare string *after* the
    # assignment. Those are documentation by every measure that matters and
    # were being read as runtime text.
    documentation = {
        id(node.value) for node in ast.walk(tree)
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    }
    for node in ast.walk(tree):
        if (isinstance(node, ast.Constant) and isinstance(node.value, str)
                and id(node) not in documentation):
            yield node.lineno, node.value


def _files():
    for path in sorted(SRC.rglob("*.py")):
        parts = path.relative_to(SRC).parts
        if any(part in ALLOWED_PACKAGES for part in parts):
            continue
        yield path


@pytest.mark.parametrize("path", list(_files()),
                         ids=lambda p: str(p.relative_to(SRC)))
def test_no_route_is_typed_into_text_a_person_reads(path):
    """THE ONE THIS EXISTS FOR.

    Mutation: put `route="m 6 4"` back in `interaction.py`, or
    `"Press m 6 4 to review a sweep."` back in the Sweep tab, or
    `"Press 6.2 again"` back in the sync confirmation, and this fails.
    """
    offenders = []
    for line, value in _runtime_strings(path):
        for pattern in (KEYSTROKE, DOTTED, SPOKEN):
            for hit in pattern.findall(value):
                offenders.append(f"{line}: {hit.strip()}")
    assert not offenders, (
        f"{path} shows a route it typed out; read it from "
        f"`rad.index.keystroke` instead: {offenders}")


def test_the_helper_answers_for_every_act_the_ring_reaches():
    """A guard everything routes through is only as good as what it routes to.

    Mutation: return "" from `keystroke` and this fails.
    """
    from dossier.rad.index import index, keystroke

    for command in index():
        if command.is_menu:
            continue
        found = keystroke(command.action)
        assert found, f"{command.action} has no keystroke"
        assert found.split() == list(command.keys), found


def test_the_helper_is_empty_for_something_the_ring_cannot_reach():
    """Empty is the honest answer, and a caller shows nothing rather than a
    route that goes somewhere else."""
    from dossier.rad.index import keystroke

    assert keystroke("nothing.like.this") == ""


def test_the_tab_and_the_review_are_different_acts():
    """The near-miss, kept as a test because it is the thing that misled me.

    `m 8 6 6` opens the Sweep tab and `m 6 4` runs the review. Reading one
    number and assuming the other is what made five correct strings look
    stale.

    Mutation: point `view.sweep` and `sweep.review` at one wedge and this
    fails.
    """
    from dossier.rad.index import keystroke

    tab = keystroke("view.sweep")
    review = keystroke("sweep.review")
    assert tab and review and tab != review, (tab, review)
