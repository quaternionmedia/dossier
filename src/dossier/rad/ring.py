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

import math
from typing import Any

from textual.app import ComposeResult
from textual.containers import Center, Middle
from textual.screen import ModalScreen
from textual.widgets import Static

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


def _box(label: str, selected: bool = False) -> tuple[str, str, str]:
    """One node: its top, middle and bottom rows.

    A selected node is drawn with a doubled rule rather than only a colour.
    rad treats accessibility as foundation, and a selection carried by colour
    alone is invisible to a reader who cannot see it -- so the border says it
    too, in the plain text.
    """
    inner = f" {label} "
    horizontal = "=" if selected else BOX_H
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

    def __init__(self, theme: str = DEFAULT_THEME, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.roles: Roles = roles(theme)

    def render_view(self, view: RingView) -> str:
        """Rich markup for the ring. Every colour is a role token."""
        grid = [[" "] * GRID_COLS for _ in range(GRID_ROWS)]
        centre_row, centre_col = GRID_ROWS // 2, GRID_COLS // 2
        count = max(len(view.wedges), 1)
        selected_index = view.highlighted % count
        current = view.current

        # THE HUB IS THE ON-DECK SLOT. It always holds the wedge that Enter
        # would take, in the same place, so reading "what am I about to do"
        # costs no eye movement and does not depend on spotting a highlight
        # somewhere on the rim. It is the only part of the ring that never
        # moves, which is what makes it worth reading.
        on_deck = current.label if current else "-"
        if current is not None and current.is_submenu:
            on_deck += SUBMENU
        hub = _box(on_deck)
        for offset, line in enumerate(hub):
            _place(grid, centre_row - 1 + offset, centre_col - len(line) // 2, line)

        # Depth, directly under the hub: one rule per level.
        depth = len(view.path) + 1
        for offset, mark in enumerate(_depth_marks(depth, len(hub[0]) - 4)):
            _place(grid, centre_row + 2 + offset, centre_col - len(mark) // 2, mark)

        painted: list[tuple[int, str, bool, bool]] = []
        for index, wedge in enumerate(view.wedges):
            angle = view.angle_of(index)
            dx, dy = math.cos(angle), math.sin(angle)
            selected = index == selected_index
            label = wedge.label + (SUBMENU if wedge.is_submenu else "")
            rows = _box(label, selected)
            width = len(rows[0])

            row = centre_row + round(RADIUS_ROWS * dy)
            # The hub occupies three rows, and a node overlapping them would
            # sit inside the box that is meant to be the one stable thing here.
            # Only the top and bottom positions can collide: the east and west
            # nodes share the hub's rows and are far clear of it horizontally,
            # so pushing them down would open a gap for no reason.
            if abs(row - centre_row) <= 1 and abs(dx) < 0.3:
                row = centre_row + (3 if dy >= 0 else -3)

            reach = round(RADIUS_ROWS * ASPECT * dx)
            if dx > 0.3:
                col = centre_col + reach
            elif dx < -0.3:
                col = centre_col + reach - width
            else:
                col = centre_col + reach - width // 2

            for offset, line in enumerate(rows):
                _place(grid, row - 1 + offset, col, line)
            painted.append((row, label, selected, wedge.is_submenu))

        plain = chr(10).join("".join(row).rstrip() for row in grid)
        self.last_render = plain
        return self._colourise(plain, painted, centre_row)

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

            for _, body, selected, is_submenu in marks:
                if not body or body not in text:
                    continue
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
                 theme: str = DEFAULT_THEME) -> None:
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

    def on_key(self, event) -> None:
        key = event.key
        event.stop()

        if key in ("right", "down", "tab"):
            view = self._session.rotate(+1)
        elif key in ("left", "up", "shift+tab"):
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
