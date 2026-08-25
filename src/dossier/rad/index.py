"""Every rad command, numbered by the cells you press to reach it.

**THE NUMBER IS THE ROUTE, NOT A LABEL.** `6.2` is not an identifier somebody
assigned to sync; it is the two keys that reach it -- `6` for Do, `2` for the
third thing under Do. A reader who has the number has the keystrokes, and a
reader who has the keystrokes can derive the number. Nothing has to be looked
up, which is the whole point of numbering a menu that is already a numpad.

**SO NOTHING HERE IS WRITTEN DOWN.** The index is computed from the same two
things the ring itself uses -- `palette.resolve` for the content and
`numpad.place` for the placement. A hand-maintained table would be a second
copy of the menu, and the failure mode of a second copy of a menu is a
documented number that opens something else. Add a wedge to the palette and its
number appears here; reorder the palette and every number after it moves, which
is true of the menu too and is the honest thing for the index to say.

WHAT `5` IS, AT EVERY LEVEL AND EVERY DEPTH. Back out one level, or close the
ring. It is never an item, so it never carries a number: there is no `6.5`.
`numpad.BACK` is the one cell this module refuses to index, and
`numpad.place`'s own placement order never assigns it.

WHAT THIS CANNOT TELL YOU. Whether an action does anything. A wedge names an
action and the host applies it; one that nothing handles still has a number and
still appears here, because a number missing from the index reads as a menu item
that does not exist. `applied_by` takes the host's dispatch table and marks the
difference, and `dossier.tui.app.DossierApp` is what supplies it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable, Sequence

from dossier.rad import numpad
from dossier.rad.palette import resolve as default_resolve

# The key that opens the ring, from `DossierApp.BINDINGS`. Named here so the
# instructions can state a whole keystroke sequence rather than "open the menu,
# then press 6 2" -- the first press is part of the route.
OPEN_KEY = "m"


@dataclass(frozen=True)
class Command:
    """One reachable menu item, and the keys that reach it."""

    number: str
    """Dotted cell path, e.g. `6.2`. Unique, and it is the route."""

    path: tuple[str, ...]
    """The labels walked through, e.g. `("Do", "Sync project")`."""

    action: str | None
    """What the wedge commits, or None for a submenu that only opens."""

    cells: tuple[int, ...]
    """The numpad cells, e.g. `(6, 2)`."""

    @property
    def label(self) -> str:
        return self.path[-1]

    @property
    def depth(self) -> int:
        return len(self.cells)

    @property
    def is_menu(self) -> bool:
        """A wedge that opens a submenu rather than committing an action."""
        return self.action is None

    @property
    def keys(self) -> tuple[str, ...]:
        """The full keystroke sequence from the dashboard, `m` included."""
        return (OPEN_KEY, *(str(cell) for cell in self.cells))

    @property
    def presses(self) -> int:
        """How many keys it costs from the dashboard.

        This is a keystroke count and deliberately not rad's IPA: IPA meters
        one *input*, and the chorded diagonals in `numpad` make some routes
        cheaper in inputs than in keys. `RadSession` is what meters cost;
        this is what a person reads off a page.
        """
        return len(self.keys)


def index(resolve: Callable[..., Sequence[Any]] = default_resolve,
          context: Any = None) -> tuple[Command, ...]:
    """Every command in the ring, in numeric route order.

    Depth-first, so a submenu is immediately followed by what it holds --
    the order somebody reads a menu in, rather than every top-level item and
    then every second-level one.
    """
    found: list[Command] = []
    _walk(tuple(resolve(context)), (), (), found)
    return tuple(found)


def _walk(wedges: Sequence[Any], cells: tuple[int, ...],
          labels: tuple[str, ...], found: list[Command]) -> None:
    placement = numpad.place(len(wedges))
    # By cell, not by list position: the placement order puts the cardinals
    # first, so the fifth child sits at 9 and reading the list in order would
    # number it 5. Walking cells ascending would put 1 before 2 before 4, which
    # is neither the reading order nor the placement order -- so the list order
    # is kept and the cell is looked up.
    for position, wedge in enumerate(wedges):
        cell = placement.by_index[position]
        assert cell != numpad.BACK, (
            f"{wedge.label!r} was placed on the centre, which always backs out")
        here = (*cells, cell)
        names = (*labels, wedge.label)
        children = tuple(getattr(wedge, "children", ()) or ())
        found.append(Command(
            number=".".join(str(c) for c in here),
            path=names,
            action=getattr(wedge, "action", None),
            cells=here,
        ))
        if children:
            _walk(children, here, names, found)


def by_number(resolve: Callable[..., Sequence[Any]] = default_resolve,
              context: Any = None) -> dict[str, Command]:
    """The index keyed by route, for looking up what `6.2` is."""
    return {command.number: command for command in index(resolve, context)}


def by_action(resolve: Callable[..., Sequence[Any]] = default_resolve,
              context: Any = None) -> dict[str, Command]:
    """The index keyed by action, for looking up where an act sits.

    The other direction of `by_number`, and the one a caller holding an action
    needs. It exists so nothing has to write a route down a second time to
    answer "can the ring reach this" -- a copy that stayed correct until the
    ring grew a level and eighteen numbers moved at once.

    Submenus are not in it: they have no action, and two of them would collide
    on `None`.
    """
    return {command.action: command
            for command in index(resolve, context) if command.action}


def keystroke(action: str,
              resolve: Callable[..., Sequence[Any]] = default_resolve,
              context: Any = None) -> str:
    """The keys that reach `action`, e.g. `m 8 6 6`. Empty if none do.

    **SO NOBODY TYPES A ROUTE INTO PROSE AGAIN.** Five places held `m 6 4` for
    the sweep -- two of them shown to a person -- and every one of them was
    wrong the moment `Go` grew a group level and the sweep moved to `m 8 6 6`.
    They were all correct when written, which is the whole problem with a route
    written down anywhere but the menu.
    """
    found = by_action(resolve, context).get(action)
    return " ".join(found.keys) if found else ""


def applied_by(handled: Iterable[str],
               resolve: Callable[..., Sequence[Any]] = default_resolve,
               context: Any = None) -> tuple[tuple[Command, bool], ...]:
    """Each command paired with whether the host handles its action.

    A submenu is always "handled": opening it is the whole of what it does.
    An action wedge is handled when its action appears in `handled`, which the
    host supplies from its own dispatch. Marking the difference is the point --
    a menu item that reports "not applied yet" is a real state a reader should
    be able to see on the page rather than by pressing it.
    """
    known = set(handled)
    return tuple(
        (command, True if command.is_menu else command.action in known)
        for command in index(resolve, context)
    )


# --- the sheet ----------------------------------------------------------------

# The numpad, drawn once. `numpad.py` carries the same picture in its docstring
# for a reader of the code; this is the one a reader of the sheet sees, and it
# is built from `numpad.POSITION` rather than typed out, so a grid that ever
# changed shape would change here too.
def _grid() -> str:
    rows = []
    for row in range(3):
        cells = [str(numpad.CELL_AT[(column, row)]) for column in range(3)]
        rows.append("    " + "  ".join(cells))
    return "\n".join(rows)


def as_markdown(handled: Iterable[str] = (),
                resolve: Callable[..., Sequence[Any]] = default_resolve,
                context: Any = None) -> str:
    """The command sheet, indexed on the route.

    `handled` is the host's dispatch. Everything not in it is still listed and
    marked, because a number missing from the sheet reads as a menu item that
    does not exist -- and "exists but does nothing yet" is a different thing a
    reader should be able to see without pressing it.
    """
    marked = applied_by(handled, resolve, context)
    lines = [
        "# rad commands",
        "",
        "**Generated. Do not edit.** Every number below is computed from",
        "`dossier.rad.palette.resolve` and `dossier.rad.numpad.place` -- the same",
        "two things the ring itself is built from. Regenerate by running the test",
        "suite.",
        "",
        "## The number is the route",
        "",
        "`6.2` is not a name somebody gave to sync. It is the keys: `6` opens **Do**,",
        "`2` is the third thing under it. Press `m` to open the ring, then the digits.",
        "So sync is **`m` `6` `2`** -- three keys, from anywhere in the application.",
        "",
        "```",
        _grid(),
        "```",
        "",
        f"`{numpad.BACK}` is the centre. It backs out one level, or closes the ring,",
        "at every level and every depth -- so it is never an item and there is no",
        f"`6.{numpad.BACK}`. Arrow keys and `wasd` move the highlight if you would",
        "rather look than type; the digits are the fast path and both arrive at the",
        "same cell.",
        "",
        "## Every command",
        "",
        "| # | keys | what | action | wired |",
        "|---|---|---|---|---|",
    ]
    for command, is_wired in marked:
        indent = "&nbsp;&nbsp;" * (command.depth - 1)
        keys = " ".join(f"`{key}`" for key in command.keys)
        action = f"`{command.action}`" if command.action else "*opens a submenu*"
        mark = "yes" if is_wired else "**not yet**"
        lines.append(
            f"| `{command.number}` | {keys} | {indent}{command.label} | "
            f"{action} | {mark} |")

    lines += _sync_section()
    lines += _ingest_section()

    unwired = [c for c, ok in marked if not ok]
    lines += [
        "",
        "**A command marked not yet is greyed out and cannot be chosen.** Its",
        "cell is still there and still numbered -- dropping it would renumber",
        "every command after it, and these numbers are written down. The digit",
        "is refused, arrows and diagonals step over it, and a verb whose every",
        "child is unavailable is greyed too rather than opening onto a level of",
        "dead cells. It is drawn with a dotted border as well as a dimmer ink,",
        "so the state survives a theme with no dim colour and a terminal that",
        "approximates.",
    ]
    if unwired:
        lines.append("")
        lines.append("Not yet applied: "
                     + ", ".join(f"`{c.number}` {c.label}" for c in unwired)
                     + ".")
    return "\n".join(lines) + "\n"


def _sync_section() -> list[str]:
    """What `6.2` does, stated from the constants that decide it.

    Every figure here is read out of the code rather than typed: the confirm
    threshold from the app, the staleness threshold from `dossier.overview`,
    and the list of views a sync does not feed from `dossier.freshness`. A
    number typed into this page would be a claim with an expiry date and no
    date on it -- `governance/qm/records/DRAFT-few-integers-in-durable-text.md`.
    """
    from dossier.freshness import NOT_FROM_SYNC, STALE_AFTER_DAYS

    try:
        from dossier.tui.app import DossierApp

        threshold = DossierApp.SYNC_WITHOUT_CONFIRMING
    except Exception:  # pragma: no cover - the sheet renders without the app
        threshold = None

    lines = [
        "",
        "## `6.2` -- making the view current",
        "",
        "Press `m` `6` `2`. It refreshes what is on screen, and it always says",
        "what it did.",
        "",
        "**The tab decides what gets refreshed, not the selection.** On the",
        "overview that is every repository the overview is scoped to -- the app",
        "selects a repository on start-up, and scoping the organisation's",
        "refresh to it would refresh one repository nobody chose. On a",
        "repository tab it is that repository.",
        "",
        f"**Stale means older than {STALE_AFTER_DAYS} days**, the same threshold",
        "the overview's attention list already sorts on. Never-synced is not",
        "stale -- it is its own state, it has no age, and it is fetched first.",
        "Repositories that are already current are not refetched.",
        "",
    ]
    if threshold is not None:
        lines += [
            f"**Above {threshold} repositories it asks first.** The first press",
            "states what it would fetch; press `6` `2` again to go ahead. Going",
            "anywhere else in the menu cancels it. Below that it just runs, so",
            "the common case stays three keys.",
            "",
        ]
    lines += [
        "**Some views a sync cannot help**, and it says which rather than",
        "reporting nothing to do:",
        "",
    ]
    for tab, reason in sorted(NOT_FROM_SYNC.items()):
        lines.append(f"- `{tab}` -- {reason}")
    return lines


def _ingest_section() -> list[str]:
    """How to get an export into the archive, from the menu.

    Written because somebody could not. The button existed, its handler was on
    another class, and the button itself sat off the right edge of the screen --
    so the field could be filled in and submitted to nothing. `PRINCIPLES.md`
    P14 is what turns that into a menu route rather than a repair and a shrug.
    """
    return [
        "",
        "## `4.6` -- putting an export into the archive",
        "",
        "Conversations are not fetched. Somebody asks the service for an export,",
        "waits for the mail, and downloads it -- that is a human step by",
        "construction, and this organisation would want it to be one anyway.",
        "What follows is everything after the download.",
        "",
        "1. Press `m` `4` `6`. The archive opens with the cursor already in the",
        "   path field -- you do not have to find it.",
        "2. Type or paste the path to the export. Either the `conversations.json`",
        "   itself or the folder holding it; surrounding double quotes are",
        "   stripped, so Windows' *Copy as path* pastes straight in.",
        "3. Press Enter. The button beside the field does the same thing and is",
        "   there for a mouse -- neither is the real one.",
        "",
        "**The panel does not write the archive.** It asks the harness to unpack",
        "the export, because the harness owns it. If nothing is listening, the",
        "refusal names the address it tried and the command that starts one --",
        "not a silent failure and not a stack trace.",
        "",
        "**The count is refreshed before it is reported**, so the number in the",
        "message and the rows on the screen are one reading rather than two.",
        "",
        "**`m` `6` `2` will not help here.** The archive is one of the views a",
        "sync does not feed: it is the harness's, reached over HTTP, and syncing",
        "GitHub would not change a row of it. Pressing sync on that tab says so",
        "rather than reporting nothing to do.",
    ]
