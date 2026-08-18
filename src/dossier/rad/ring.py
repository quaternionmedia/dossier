"""The ring, drawn in a terminal. One, centered, pop-over.

WHAT THIS OWNS AND WHAT IT DOES NOT. Rendering only. Geometry comes from
`RingView.angle_of`, the state machine from `RadSession` -- a widget that
computed its own angles would be a second geometry, and the two would drift the
first time one was fixed. This file holds no menu content either: content is the
host's, supplied through `resolve`.

WHY A MODAL SCREEN. rad's terminal form is one centered pop-over rather than a
menu per node: a terminal has no pointer to open a ring *under*, and several
rings at once would need a focus model the platform does not give us. A modal
screen is also what makes the key handling honest -- the ring has focus while it
is open, so a keystroke is unambiguously an input to the menu.

WHAT IT CANNOT DO. Look like the web ring. Cells are not pixels and a character
is about twice as tall as it is wide, so the circle is drawn on a corrected
aspect and still reads as an oval at small sizes. That is cosmetic and stated
rather than hidden; the interaction is the contract, not the shape.
"""

from __future__ import annotations

import math
from typing import Any

from textual.app import ComposeResult
from textual.containers import Center, Middle
from textual.screen import ModalScreen
from textual.widgets import Static

from dossier.rad.session import RadSession, RingView

# A character cell is roughly twice as tall as it is wide, so horizontal steps
# are doubled to keep the ring from reading as a vertical slit.
ASPECT = 2.0
RADIUS_ROWS = 4
GRID_ROWS = RADIUS_ROWS * 2 + 3
GRID_COLS = int(RADIUS_ROWS * ASPECT * 2) + 22


class Ring(Static):
    """The ring itself: labels placed at their angles, one highlighted.

    `last_render` keeps the text this widget most recently drew. Textual's
    accessor for a `Static`'s content has changed across versions, and a test
    that reached for the wrong one failed in a way that read like the menu
    never opening. The widget knowing what it drew is cheaper than guessing
    which attribute the framework calls it this month.
    """

    last_render: str = ""

    def render_view(self, view: RingView) -> str:
        grid = [[" "] * GRID_COLS for _ in range(GRID_ROWS)]
        centre_row, centre_col = GRID_ROWS // 2, GRID_COLS // 2

        for index, wedge in enumerate(view.wedges):
            angle = view.angle_of(index)
            row = centre_row + round(RADIUS_ROWS * math.sin(angle))
            col = centre_col + round(RADIUS_ROWS * ASPECT * math.cos(angle))

            selected = index == view.highlighted % len(view.wedges)
            label = f"[{wedge.label}]" if selected else f" {wedge.label} "
            if wedge.is_submenu:
                label = label.rstrip() + ">" if selected else label.rstrip() + ">"

            start = max(0, min(col - len(label) // 2, GRID_COLS - len(label)))
            for offset, char in enumerate(label):
                if 0 <= row < GRID_ROWS:
                    grid[row][start + offset] = char

        # The centre says where you are, because a ring one level down looks
        # exactly like the top level otherwise.
        here = " / ".join(view.path) if view.path else "rad"
        centre = f"({here})"
        start = max(0, centre_col - len(centre) // 2)
        for offset, char in enumerate(centre):
            if start + offset < GRID_COLS:
                grid[centre_row][start + offset] = char

        return "\n".join("".join(row).rstrip() for row in grid)


class RingScreen(ModalScreen):
    """The pop-over. Arrows rotate, Enter commits, Escape backs out.

    Every key is routed through the session so that it is metered exactly once.
    A widget that handled a key itself would be an input rad never charged for,
    and the IPA figure would then be quietly too low.
    """

    BINDINGS = []  # keys are handled in on_key so the session meters every one

    def __init__(self, session: RadSession, context: Any = None) -> None:
        super().__init__()
        self._session = session
        self._open_context = context
        self._ring = Ring(id="rad-ring")
        self._status = Static("", id="rad-status")

    def compose(self) -> ComposeResult:
        with Middle():
            with Center():
                yield self._ring
            with Center():
                yield self._status

    def on_mount(self) -> None:
        view = self._session.open_at(self._open_context)
        if view is None:
            # A resolver with nothing to offer must not leave an empty ring for
            # somebody to escape from.
            self.dismiss(None)
            return
        self._redraw(view)

    def _redraw(self, view: RingView) -> None:
        drawn = self._ring.render_view(view)
        self._ring.last_render = drawn
        self._ring.update(drawn)
        current = view.current
        hint = "Enter opens" if current and current.is_submenu else "Enter commits"
        self._status.update(
            f"{current.label if current else '-'}   |   "
            f"arrows rotate  ·  {hint}  ·  Esc backs out   |   "
            f"inputs this action: {self._session.meter.inputs_since_open}"
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
            # Unrecognised: charged at L0 and not at L1, which is what keeps the
            # abstraction ledger honest about keys the menu ignored.
            self._session.meter.raw(recognized=False)
            return

        if view is None:
            self.dismiss(None)
            return
        self._redraw(view)
