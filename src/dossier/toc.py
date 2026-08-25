"""One index of everything this application can be asked to do.

**THE NUMBER IS THE KEYSTROKE, WHICH IS WHY THERE IS ONLY ONE NUMBERING.** A
table of contents usually invents its own `1.2.3`, and then the document has a
number and the application has a route and neither knows about the other. Here
`8.6.6` *is* the route: `m` opens the ring, `8` is Go, `6` is Work, `6` is
Sweep. A reader who has the number has the keystrokes and a reader who has the
keystrokes can derive the number, so nothing has to be looked up.

Which also means nothing here is written down. The tree comes from
`dossier.rad.index`, which computes it from the palette and the numpad; what a
view *is* and what command reaches it come from `dossier.views`. Reordering a
group moves every number after it, on this page and in the menu together, and
that is the honest behaviour of an index computed from the menu rather than
typed beside it.

WHAT THIS IS NOT. A list of every command. `dossier --help` has around seventy
leaf commands and the ring reaches a fraction of them on purpose -- the ring is
for what a person does repeatedly, and a keystroke spent on a once-a-quarter
migration is a keystroke taken from something else. The commands outside the
ring are named where the view they belong to is named, and counted at the end
so their absence is a stated fact rather than an omission.

WHAT THIS CANNOT DO. Say whether a view has anything in it, or whether an action
works. `applied_by` marks what the host dispatches, which is a different claim
from "this does what it says".
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from dossier import views
from dossier.rad import index as rad_index


@dataclass(frozen=True)
class Entry:
    """One line of the index."""

    number: str
    """The rad route, e.g. `8.6.6`. Unique, and it is the address."""

    keys: tuple[str, ...]
    """The whole keystroke, `m` included."""

    title: str
    depth: int
    is_menu: bool
    wired: bool

    action: str = ""
    summary: str = ""
    cli: str = ""
    """A command that reaches the same thing, derived or named."""


# What the ring can do that is not opening a view, and the command that does
# the same thing outside the application.
#
# **THE EMPTY ONES ARE DECLARED, NOT OMITTED.** "There is no command for this,
# and that is correct" is a different fact from "nobody wrote one", and only
# one of them is fine. Advancing a phase and filtering the list act on what is
# on screen; a command that did them would be acting on a screen that is not
# there. A new act with no entry here fails
# `test_every_act_says_whether_it_has_a_command`, which is the point.
ACT_ROUTES: dict[str, str] = {
    "project.sync": "dossier github sync",
    "sweep.review": "dossier sweep",
    "reach.ingest": "dossier deltas ingest",
    "delta.advance": "",
    "delta.note": "",
    "filter.all": "",
    "filter.synced": "",
    "filter.drifting": "",
    "reach.reconcile": "",
    "reach.read": "",
    "reach.qmcp": "",
}


def _cli_for(view: views.View) -> str:
    """The command that reaches a view.

    A named one wins: somebody who knows `dossier disk status` should not be
    told to type the generic form. Everything backed by a facet gets
    `dossier show <name>` for free, which is what stops this index from having
    to say "no command" eight times.
    """
    if view.cli:
        return view.cli
    from dossier.facets import BY_TAB

    if BY_TAB.get(view.tab):
        return f"dossier show {view.name}"
    return ""


def entries(handled: Iterable[str] = ()) -> tuple[Entry, ...]:
    """Every command in the ring, in route order, with how else to reach it."""
    found = []
    for command, wired in rad_index.applied_by(handled):
        action = command.action or ""
        view = views.BY_ACTION.get(action)
        found.append(Entry(
            number=command.number,
            keys=command.keys,
            title=command.label,
            depth=command.depth,
            is_menu=command.is_menu,
            wired=wired,
            action=command.action or "",
            summary=view.summary if view else "",
            cli=_cli_for(view) if view else ACT_ROUTES.get(action, ""),
        ))
    return tuple(found)


def unreachable_views() -> tuple[views.View, ...]:
    """Views the registry holds that the ring does not reach.

    Should be empty, and is asserted to be. It exists because "the ring reaches
    every view" is the property this page is for, and a property nothing can
    report on is a property nobody notices losing.
    """
    reached = {e.action for e in entries() if e.action}
    return tuple(v for v in views.VIEWS if v.action not in reached)


def as_markdown(handled: Iterable[str] = ()) -> str:
    """The index, numbered on the route."""
    found = entries(handled)
    lines = [
        "# What dossier can be asked to do",
        "",
        "**Generated. Do not edit.** Every number is computed from the menu --",
        "`dossier.rad.palette`, `dossier.rad.numpad` and `dossier.views` -- and",
        "regenerating rides the ordinary test command.",
        "",
        "## The number is the keystroke",
        "",
        "`8.6.6` is not a name somebody gave to the sweep. It is the keys: `8`",
        "opens **Go**, `6` is **Work**, `6` is **Sweep**. Press `m` to open the",
        "ring, then the digits -- so the sweep is **`m` `8` `6` `6`**, from",
        "anywhere in the application.",
        "",
        "`5` is the centre. It backs out one level, or closes the ring, at every",
        "depth -- so it is never an item and no number contains it. Arrows and",
        "`wasd` move the highlight if you would rather look than type.",
        "",
        "## Contents",
        "",
    ]
    for entry in found:
        indent = "  " * (entry.depth - 1)
        if entry.is_menu:
            lines.append(f"{indent}- **`{entry.number}`  {entry.title}**")
            continue
        keys = " ".join(f"`{k}`" for k in entry.keys)
        mark = "" if entry.wired else "  *(not applied yet)*"
        lines.append(f"{indent}- `{entry.number}`  {entry.title} -- {keys}{mark}")
        if entry.summary:
            lines.append(f"{indent}  {entry.summary}")
        if entry.cli:
            lines.append(f"{indent}  `{entry.cli}`")
        elif entry.action and not entry.action.startswith("view."):
            # Stated rather than left blank: an act with no command is an act
            # on what is on screen, and a reader should not have to wonder
            # whether one was forgotten.
            lines.append(f"{indent}  *in the application only*")
    lines += _outside_the_ring()
    return "\n".join(lines) + "\n"


def _outside_the_ring() -> list[str]:
    """What the ring does not reach, counted rather than listed.

    **THE COUNT IS THE POINT AND IT IS READ, NOT TYPED.** A page that showed
    the ring and stopped would read as the whole application. Saying how much
    sits outside it, from `cli.list_commands` at the moment of writing, turns
    an omission into a stated fact -- and this section is one run at one
    commit, which is the one place a bare figure belongs.
    """
    import click

    from dossier.cli import cli as group

    leaves: list[str] = []

    def walk(node, prefix=()):
        for name in node.list_commands(None):
            found = node.get_command(None, name)
            here = (*prefix, name)
            if isinstance(found, click.Group):
                walk(found, here)
            else:
                leaves.append(" ".join(here))

    walk(group)
    named = {e.cli.replace("dossier ", "") for e in entries() if e.cli}
    rest = sorted(set(leaves) - named)
    return [
        "",
        "## Outside the ring",
        "",
        f"`dossier --help` reaches **{len(leaves)}** leaf commands; **{len(named)}**",
        "of them are named above beside the view they belong to. The rest are",
        "not menu items and are not meant to be: the ring is for what somebody",
        "does repeatedly, and a cell spent on a once-a-quarter migration is a",
        "cell taken from something else.",
        "",
        "```",
        *(f"  dossier {name}" for name in rest),
        "```",
    ]
