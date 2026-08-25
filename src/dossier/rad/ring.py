"""The ring, drawn in a terminal. One, centered, pop-over.

WHAT THIS OWNS AND WHAT IT DOES NOT. Rendering only. Geometry comes from
`RingView.angle_of`, the state machine from `RadSession`, and colour from
`tokens.roles` — a widget that computed its own angles would be a second
geometry, and one that named a colour would paint outside the token layer that
`rad/adr/DRAFT-rad-theme-tokens.md` §1 says nothing paints outside. Content is
the host's, supplied through `resolve`.

WHY A MODAL SCREEN. rad's terminal form is one centered pop-over rather than a
menu per node: a terminal has no pointer to open a ring *under*, and several
rings at once would need a focus model the platform does not give us. A modal
screen also makes the key handling honest — the ring holds focus while open, so
a keystroke is unambiguously an input to the menu.

LAYOUT, AND THE TWO THINGS A TERMINAL FORCES.

  * A cell is about twice as tall as it is wide, so a ring drawn on equal steps
    reads as a vertical slit. Horizontal distance is doubled.
  * A label centred on its own point runs back through the hub at the 3 and 9
    o'clock positions — exactly where the label is widest and the ring is
    narrowest. So labels are pushed *outward* from their angle: right-hand
    labels start at the point, left-hand labels end at it, and only the top and
    bottom are centred on it.

The hub carries where you are, with a rule under it, so the middle reads as a
hub rather than as another label that happens to be central.

WHAT IT CANNOT DO. Look like the web ring. There are no arcs, no fills and no
sub-cell positions, so wedge *shape* is not expressible — position, weight and
colour carry the meaning instead. Stated rather than hidden: the interaction and
the token layer are the contract; the shape is not.
"""

from __future__ import annotations

import time

import math
from typing import Any

from textual.app import ComposeResult
from textual.containers import Center, Middle
from textual.screen import ModalScreen
from textual.widgets import Static

from dossier.rad import numpad
from dossier.rad.session import RadSession, RingView
from dossier.rad.tokens import DEFAULT_THEME, Roles, roles

# A cell is roughly twice as tall as it is wide.
ASPECT = 2.6
RADIUS_ROWS = 4
GRID_ROWS = RADIUS_ROWS * 2 + 5
GRID_COLS = 58

# A node is a bordered box, three rows tall, drawn in ASCII because box-drawing
# characters are not encodable in cp1252 -- the same constraint that governs
# every other glyph here.
BOX_H, BOX_CORNER, BOX_V = "-", "+", "|"


def _box(label: str, selected: bool = False,
         available: bool = True) -> tuple[str, str, str]:
    """One node: its top, middle and bottom rows.

    A selected node is drawn with a doubled rule rather than only a colour.
    rad treats accessibility as foundation, and a selection carried by colour
    alone is invisible to a reader who cannot see it -- so the border says it
    too, in the plain text.

    **An unavailable node is drawn with a dotted rule, for the same reason.**
    Greying out is a colour, and the `contrast` theme deliberately has no dimmer
    ink to grey with; a reader on that theme, or on a sixteen-colour terminal,
    would see a wedge that looks ordinary and refuses to be chosen. Dotted says
    it in characters that survive both.

    Unavailable wins over selected. The highlight never rests on an unavailable
    cell -- every route that moves it skips them -- so the combination means a
    caller drew something the state machine would refuse, and it should look
    refused rather than look chosen.
    """
    inner = f" {label} "
    if not available:
        horizontal = "."
    elif selected:
        horizontal = "="
    else:
        horizontal = BOX_H
    edge = BOX_CORNER + horizontal * len(inner) + BOX_CORNER
    return edge, f"{BOX_V}{inner}{BOX_V}", edge


def _depth_marks(depth: int, width: int) -> list[str]:
    """One rule per level, so the palette's depth is readable at a glance.

    Three lines means three deep. It sits under the hub -- the one part of the
    ring that never moves -- so depth is read from the same place as what is on
    deck, rather than by counting breadcrumbs.
    """
    del width  # a fixed short mark: a rule as wide as the hub collides with
    # the side nodes, which sit on the hub's own rows.
    return [BOX_H * 3 for _ in range(max(depth, 1))]

# A submenu is marked with a glyph rather than a word, so a label's length says
# something about the label and not about its arity.
#
# EVERY GLYPH HERE IS ENCODABLE IN CP1252, and that is a constraint rather than
# a preference: this repository has already lost a demo to a folder emoji a
# Windows console could not encode, and a ring that raises
# UnicodeEncodeError is not a prettier ring. U+203A and U+00B7 are in cp1252;
# U+276F and the arrow glyphs are not.
SUBMENU = "›"
SELECT_L, SELECT_R = "[", "]"


def _place_in(grid: list[list[str]], row: int, col: int, text: str,
              width: int) -> None:
    """Write `text` into a grid of a given width, clipped to it."""
    if not 0 <= row < len(grid):
        return
    start = max(0, min(col, width - len(text)))
    for offset, character in enumerate(text):
        if 0 <= start + offset < width:
            grid[row][start + offset] = character


def _place(grid: list[list[str]], row: int, col: int, text: str) -> None:
    """Write text into the grid, clipped rather than wrapped or raising."""
    if not 0 <= row < len(grid):
        return
    start = max(0, min(col, GRID_COLS - len(text)))
    for offset, char in enumerate(text):
        if 0 <= start + offset < GRID_COLS:
            grid[row][start + offset] = char


class Ring(Static):
    """The ring: labels at their angles, one selected, colour by role token.

    `last_render` keeps the plain text most recently drawn. Textual's accessor
    for a `Static`'s content has changed across versions, and a test reaching
    for the wrong one failed in a way that read like the menu never opening.
    """

    last_render: str = ""

    # Where the cells landed the last time this was drawn: `(width, columns,
    # rows)`, in the widget's own coordinates.
    #
    # **KEPT RATHER THAN RECOMPUTED.** The box width depends on the longest
    # label at that level, so a second derivation would have to know the view
    # as well as the geometry -- and a pointer that lands one cell over from
    # where a person clicked is worse than a ring with no pointer at all.
    last_geometry: tuple[int, list[int], list[int]] | None = None

    # How tall one cell's box is. `_box` draws three lines and the layout steps
    # four, so the fourth is the gap between rows.
    CELL_ROWS = 3

    def __init__(self, theme: str = DEFAULT_THEME, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.roles: Roles = roles(theme)

    def cell_at(self, x: int, y: int) -> int | None:
        """The numpad cell containing a point, or None for the gaps.

        None is a real answer: the gaps between the boxes belong to no cell,
        and a click that landed in one has to do nothing rather than pick the
        nearest. Snapping would make the ring act on a cell the person did not
        press, which is exactly what a menu must never do.
        """
        if self.last_geometry is None:
            return None
        width, column_at, row_at = self.last_geometry

        column = next((index for index, left in enumerate(column_at)
                       if left <= x < left + width), None)
        row = next((index for index, top in enumerate(row_at)
                    if top <= y < top + self.CELL_ROWS), None)
        if column is None or row is None:
            return None
        return numpad.CELL_AT.get((column, row))

    def render_view(self, view: RingView) -> str:
        """Rich markup for the nine cells. Every colour is a role token.

        Laid out as a numeric keypad, so a direction and a digit name the same
        place and a reader who knows where `7` is on a keyboard knows where it
        is on the screen.

            7 8 9
            4 5 6      5 always backs out
            1 2 3

        The centre never holds an item. It shows what backing out would do, in
        the same place at every depth, so "what am I about to leave" costs no
        eye movement -- and a menu whose centre sometimes cancels and sometimes
        chooses cannot be used without looking.
        """
        placement = view.placement
        cursor = view.cursor_cell

        labelled: dict[int, tuple[str, bool, bool]] = {}
        for cell, index in placement.by_cell.items():
            wedge = view.wedges[index]
            text = f"{cell} {wedge.label}" + (SUBMENU if wedge.is_submenu else "")
            labelled[cell] = (text, cell == cursor, view.is_available(index))

        depth = len(view.path)
        centre_text = f"{numpad.BACK} back" if depth else f"{numpad.BACK} close"
        # The centre is always available: backing out is the one thing that
        # works at every level, including a level where nothing else does.
        labelled[numpad.BACK] = (centre_text, False, True)

        width = max(len(text) for text, _, _ in labelled.values()) + 4
        gap = 2
        column_at = [column * (width + gap) for column in range(3)]
        row_at = [row * 4 for row in range(3)]
        self.last_geometry = (width, column_at, row_at)

        cols = column_at[-1] + width
        rows = row_at[-1] + 3 + 2  # room for the depth marks underneath
        grid = [[" "] * cols for _ in range(rows)]

        painted: list[tuple[int, str, bool, bool, bool]] = []
        for cell, (text, selected, available) in labelled.items():
            column, row = numpad.POSITION[cell]
            box = _box(text.ljust(width - 4), selected, available)
            for offset, line in enumerate(box):
                _place_in(grid, row_at[row] + offset, column_at[column], line, cols)
            is_submenu = text.endswith(SUBMENU)
            painted.append((row_at[row] + 1, text, selected, is_submenu, available))

        # Depth, under the centre: one rule per level, so how deep you are is
        # readable without counting the path.
        for offset, mark in enumerate(_depth_marks(depth + 1, width - 4)):
            _place_in(grid, row_at[-1] + 3 + offset,
                      column_at[1] + (width - len(mark)) // 2, mark, cols)

        plain = chr(10).join("".join(line).rstrip() for line in grid)
        self.last_render = plain
        return self._colourise(plain, painted, row_at[1] + 1)

    def _colourise(self, plain: str, painted, centre_row: int) -> str:
        """Wrap each placed label in its role token, leaving the grid alone.

        Per line rather than per cell: markup around every cell would multiply
        the string for no visible gain, and a terminal renders it identically.
        """
        lines = plain.split("\n")
        out: list[str] = []
        for row_index, line in enumerate(lines):
            marks = [m for m in painted if m[0] == row_index]
            text = line

            for _, body, selected, is_submenu, available in marks:
                if not body or body not in text:
                    continue
                if not available:
                    # Ahead of selected and of submenu: an unavailable wedge is
                    # not a chooseable one wearing a different colour, and the
                    # submenu mark on a greyed verb should be greyed too.
                    token = self.roles.wedge_label_unavailable
                    weight = ""
                else:
                    token = (self.roles.focus_ring if selected
                             else (self.roles.submenu_mark if is_submenu
                                   else self.roles.wedge_label))
                    weight = "bold " if selected else ""
                text = text.replace(body, f"[{weight}{token}]{body}[/]", 1)

            if not marks:
                stripped = line.strip()
                if stripped.startswith("-"):
                    text = line.replace(stripped, f"[{self.roles.hub_stroke}]{stripped}[/]", 1)
                elif stripped:
                    text = line.replace(stripped, f"[{self.roles.hub_label}]{stripped}[/]", 1)
            elif row_index == centre_row:
                # The hub shares its row with the 3 and 9 o'clock labels, so it
                # is painted after them and only where it actually sits.
                pass

            out.append(text)
        return "\n".join(out)


class RingScreen(ModalScreen):
    """The pop-over. Arrows rotate, Enter commits, Escape backs out.

    Every key is routed through the session so it is metered exactly once. A
    widget that handled a key itself would be an input rad never charged for,
    and the IPA figure would then be quietly too low.
    """

    BINDINGS = []  # handled in on_key, so the session meters every key

    # THE SCREEN PAINTS NOTHING. A `ModalScreen` covers the app by default,
    # which hides the data the menu is about to act on -- and a menu whose
    # options refer to a selection you can no longer see is worse than a menu
    # that costs an extra keystroke. Transparent here, so the dashboard renders
    # behind; only the panel below has a ground of its own.
    #
    # It stays a modal rather than becoming an overlay widget, because the
    # modal is what makes the key handling honest: the ring holds focus while
    # open, so every keystroke is unambiguously an input to the menu and the
    # IPA figure is not quietly wrong.
    DEFAULT_CSS = """
    RingScreen {
        align: center middle;
        background: transparent;
    }
    /* The layout containers fill the screen. Transparent on the screen alone
       is not enough -- `Middle` and `Center` inherit an opaque ground and
       paint it edge to edge, which hides the dashboard just as completely as
       an opaque screen did. The panel below re-opts into a ground. */
    RingScreen Middle, RingScreen Center {
        background: transparent;
        height: auto;
        width: auto;
    }
    #rad-ring {
        width: auto;
        height: auto;
        padding: 1 3 0 3;
    }
    #rad-status {
        width: auto;
        padding: 0 3;
    }
    """

    def __init__(self, session: RadSession, context: Any = None,
                 theme: str = DEFAULT_THEME, opening_on: int | None = None
                 ) -> None:
        # NOT `self._context`. `MessagePump`, which every Textual screen
        # inherits, already has a `_context`; assigning over it replaces a
        # method with a value and the app then dies inside the message pump
        # with "'NoneType' object is not callable" -- nowhere near this line.
        super().__init__()
        self._session = session
        self._open_context = context
        self._roles = roles(theme)
        self._ring = Ring(theme=theme, id="rad-ring")
        self._status = Static("", id="rad-status")
        # A cell to press as though the person had, right after opening.
        #
        # **PRESSED, NOT JUMPED TO.** The caller is the row of buttons on the
        # keypad's middle rank, and clicking one is two inputs -- open, then
        # choose -- exactly as `m` then `6` is. Seeding the session's state
        # directly would put the same menu on screen for one charged input and
        # make the cost ledger disagree with the keyboard.
        self._opening_on = opening_on

    def compose(self) -> ComposeResult:
        with Middle():
            with Center():
                yield self._ring
            with Center():
                yield self._status

    def on_mount(self) -> None:
        # Colours are set here rather than in the CSS above, because the CSS is
        # a class attribute and the tokens are a theme chosen per instance --
        # a literal in that stylesheet would paint outside the token layer.
        for widget in (self._ring, self._status):
            widget.styles.background = self._roles.panel_bg
        self._ring.styles.border = ("round", self._roles.panel_border)

        view = self._session.open_at(self._open_context)
        if view is None:
            # A resolver with nothing to offer must not leave an empty ring for
            # somebody to escape from.
            self.dismiss(None)
            return

        if self._opening_on is not None:
            intent = self._session.press_cell(self._opening_on)
            if intent is not None:
                # A cell that commits on the way in. Nothing on the middle rank
                # does today, and refusing to handle it would be a menu that
                # opened and did nothing.
                self.dismiss(intent)
                return
            view = self._session.view
            if view is None:
                self.dismiss(None)
                return

        self._redraw(view)

    def _redraw(self, view: RingView) -> None:
        self._ring.update(self._ring.render_view(view))
        current = view.current
        act = "open" if current and current.is_submenu else "commit"
        label = current.label if current else "-"
        cost = self._session.meter.inputs_since_open
        self._status.update(
            f"[bold {self._roles.wedge_label_selected}]{label}[/]"
            f"[{self._roles.hint}]  ·  arrows rotate  ·  "
            f"enter {act}  ·  esc back  ·  [/]"
            f"[{self._roles.cost}]{cost} in[/]"
        )

    def on_click(self, event) -> None:
        """A click on a cell is the same input as pressing its digit.

        **ROUTED THROUGH `press_cell`, WHICH IS THE POINT.** This module's rule
        is that every input goes through the session so it is metered exactly
        once; a click handled here would be an input rad never charged for, and
        the IPA figure would be quietly too low for anybody using a mouse.

        Before this the ring had no pointer support at all -- no click handler
        anywhere in the file -- so a person who reached for the menu with a
        mouse could open it and then not use it.
        """
        event.stop()
        cell = self._cell_under(event)
        if cell is None:
            return
        if cell == numpad.BACK:
            # The centre backs out, at every depth, exactly as the key does.
            view = self._session.back()
            if view is None:
                self.dismiss(None)
                return
            self._redraw(view)
            return

        intent = self._session.press_cell(cell)
        if intent is not None:
            self.dismiss(intent)
            return
        view = self._session.view
        if view is None:
            self.dismiss(None)
            return
        self._redraw(view)

    def _cell_under(self, event) -> int | None:
        """The cell a click landed on, in the ring widget's coordinates.

        The event arrives in screen coordinates and the geometry is the
        widget's, so the offset between them has to come off. Reading the
        widget's region rather than assuming it sits at the origin: it is
        centred, so those differ by half the terminal.
        """
        try:
            region = self._ring.region
        except Exception:                          # noqa: BLE001
            return None
        x = event.screen_x - region.x
        y = event.screen_y - region.y
        if x < 0 or y < 0:
            return None
        return self._ring.cell_at(x, y)

    def on_key(self, event) -> None:
        key = event.key
        event.stop()

        digit = numpad.digit_of(key)
        direction = numpad.direction_of(key)

        if digit is not None:
            # One keystroke to any item. This is the whole point of a keypad
            # layout: the fastest path does not depend on where the highlight
            # happens to be.
            intent = self._session.press_cell(digit)
            if intent is not None:
                self.dismiss(intent)
                return
            view = self._session.view
            if view is None:
                self.dismiss(None)
                return
        elif direction is not None:
            # `time.monotonic` rather than the wall clock: the chord window is
            # a duration, and a clock that can step backwards would read two
            # deliberate presses as one.
            view = self._session.move(direction, now=time.monotonic())
        elif key == "tab":
            view = self._session.rotate(+1)
        elif key == "shift+tab":
            view = self._session.rotate(-1)
        elif key in ("enter", "space"):
            intent = self._session.enter()
            if intent is not None:
                self.dismiss(intent)
                return
            view = self._session.view
        elif key == "escape":
            view = self._session.back()
            if view is None:
                self.dismiss(None)
                return
        else:
            # Unrecognised: charged at L0 and not at L1, which keeps the
            # abstraction ledger honest about keys the menu ignored.
            self._session.meter.raw(recognized=False)
            return

        if view is None:
            self.dismiss(None)
            return
        self._redraw(view)
