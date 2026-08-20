"""rad's session contract, in Python, for a terminal host.

    session = RadSession(resolve=my_resolver, on_intent=my_handler)
    session.open_at(context)      # 1 input
    session.rotate(+1)            # 1 input
    session.enter()               # 1 input -- opens a submenu, or commits

WHAT THIS IS AND IS NOT. This is the host-facing half of
`rad/adr/DRAFT-rad-host-integration-standard.md`, which draws the line:

    rad owns   geometry, the state machine, the committing band, hit resolution
    the host   menu content for a context, and applying an intent

So this module holds the state machine and the metering, and takes `resolve` and
`on_intent` from the caller. **It imports nothing from Textual.** That is what
makes the eventual extraction to a shared package a move rather than a rewrite,
and it is the mitigation for building here rather than in `rad` itself.

THE FOUR VERBS ARE FIXED. `Go`, `Do`, `Show`, `Reach` -- the durable palette,
identical in every host, so the menu is learned once rather than per
application. The *children* are the host's, returned by `resolve`. A fifth
top-level verb is a change to the contract.

IPA IS RAD'S METRIC, NOT ONE INVENTED HERE.
`rad/adr/DRAFT-interaction-efficiency-metrics.md`: one input is "one pointer
down...up envelope" **or** "one keystroke", and IPA is measured at **L3 --
committed intents** -- precisely so it is "comparable across platforms by
construction". A terminal meters it natively. All five levels are counted and
reconciled at L3, because a number that cannot sit beside the web
implementation's is a number nobody can act on.

THE KEYBOARD BUDGET IS `1 + ceil(N/2) + 1`. rad calls a verb over budget a
*resolver design error* -- restructure the menu, do not relax the number. This
reports it and does not fail on it, which is a deliberate choice while the
palette is still settling.

WHAT THIS CANNOT DO.

  * Commit by crossing an outer rim. That is the pointer path, and a terminal
    has no finger. The keyboard path is the whole of what is implemented.
  * Schedule against a clock. `Intent.clock` exists and is always None: the
    fields are here so quantized commit is a later implementation rather than a
    schema version, and nothing pretends to quantize.
  * Tell you whether a menu is a good menu. It reports the cost of reaching a
    verb; whether that verb should have been there is the resolver's business.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Callable

from dossier.rad import numpad

SCHEMA = 1

# The durable palette. Fixed, and identical in every host.
GO, DO, SHOW, REACH = "go", "do", "show", "reach"
DURABLE_VERBS: tuple[tuple[str, str], ...] = (
    (GO, "Go"),
    (DO, "Do"),
    (SHOW, "Show"),
    (REACH, "Reach"),
)

# rad's abstraction ledger. Every implementation meters all five and reconciles
# at L3; the names are rad's, not ours.
L0, L1, L2, L3 = "l0_raw", "l1_recognized", "l2_transitions", "l3_intents"


@dataclass(frozen=True)
class Wedge:
    """One item in the ring. `children` makes it a submenu, `action` a commit."""

    id: str
    label: str
    children: tuple[Wedge, ...] = ()
    action: str | None = None
    address: str | None = None

    @property
    def is_submenu(self) -> bool:
        return bool(self.children)


@dataclass(frozen=True)
class RingView:
    """Read-only: exactly what a renderer needs, and nothing about a renderer.

    A renderer that had to ask the session anything else would be a second place
    the state lives.
    """

    wedges: tuple[Wedge, ...]
    highlighted: int
    path: tuple[str, ...]
    context: Any = None

    available: tuple[bool, ...] | None = None
    """Which wedges this host can act on, parallel to `wedges`.

    `None` means the host never said, and everything is available -- so a host
    that does not know about availability is unchanged. It is deliberately not
    an empty tuple: that is a real answer about a menu with no wedges in it.
    """

    @property
    def placement(self) -> numpad.Placement:
        """Which numpad cell holds which wedge."""
        return numpad.place(len(self.wedges))

    @property
    def cursor_cell(self) -> int:
        """The cell the highlight is on."""
        return self.placement.by_index.get(self.highlighted, numpad.BACK)

    def is_available(self, index: int) -> bool:
        """Whether the wedge at `index` can be chosen."""
        if self.available is None:
            return True
        return bool(self.available[index])

    def available_cells(self) -> tuple[int, ...]:
        """The cells a highlight is allowed to land on."""
        return tuple(cell for cell, index in self.placement.by_cell.items()
                     if self.is_available(index))

    def wedge_at(self, cell: int) -> Wedge | None:
        """The wedge in a cell, or None for the centre and empty cells."""
        index = self.placement.by_cell.get(cell)
        return None if index is None else self.wedges[index]

    @property
    def current(self) -> Wedge | None:
        if not self.wedges:
            return None
        return self.wedges[self.highlighted % len(self.wedges)]

    def angle_of(self, index: int) -> float:
        """Where a wedge sits on the ring, in radians, 12 o'clock first.

        Geometry is rad's to own, so it lives here rather than in the widget --
        a renderer that computed its own angles would be a second geometry.
        """
        count = max(len(self.wedges), 1)
        return -math.pi / 2 + (2 * math.pi * index / count)


@dataclass(frozen=True)
class Intent:
    """A committed intent: the message this whole thing exists to produce."""

    schema: int
    verb: str
    action: str
    path: tuple[str, ...]
    address: str | None
    ipa: int
    levels: dict[str, int]
    clock: None = None  # stubbed: see the module docstring

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "verb": self.verb,
            "action": self.action,
            "path": list(self.path),
            "address": self.address,
            "cost": {"ipa": self.ipa, "levels": dict(self.levels)},
            "clock": self.clock,
        }


@dataclass
class Meter:
    """rad's five levels, counted and reconciled at L3."""

    counts: dict[str, int] = field(default_factory=lambda: {L0: 0, L1: 0, L2: 0, L3: 0})
    inputs_since_open: int = 0

    def raw(self, recognized: bool) -> None:
        """A key arrived. L0 always; L1 only if the state machine knows it."""
        self.counts[L0] += 1
        if recognized:
            self.counts[L1] += 1
            self.inputs_since_open += 1

    def transition(self) -> None:
        self.counts[L2] += 1

    def commit(self) -> int:
        """Close out one action. Returns its IPA and resets the input tally."""
        self.counts[L3] += 1
        cost = self.inputs_since_open
        self.inputs_since_open = 0
        return cost

    def reconciles(self) -> bool:
        """L1 must account for every input charged, and L3 never exceed L2.

        The reconciliation rad asks for. It is cheap and it is the only thing
        that makes the IPA figure trustworthy rather than merely present.
        """
        return self.counts[L1] <= self.counts[L0] and self.counts[L3] <= self.counts[L2]


def budget_for(count: int) -> int:
    """rad's keyboard budget: 1 + ceil(N/2) + 1."""
    return 1 + math.ceil(count / 2) + 1


class RadSession:
    """The state machine. Idle, open, or one level into a submenu."""

    def __init__(self, resolve: Callable[[Any], tuple[Wedge, ...]],
                 on_intent: Callable[[Intent], None] | None = None,
                 available: Callable[[Wedge], bool] | None = None) -> None:
        self._resolve = resolve
        self._on_intent = on_intent
        # AVAILABILITY IS THE HOST'S KNOWLEDGE, NOT THE PALETTE'S. The palette
        # is content and says what the menu offers; whether this application
        # can act on a given wedge is a fact about its dispatch, and putting it
        # in the palette would make one host's gaps another host's menu. `None`
        # means nobody said, and everything is available.
        self._available = available
        self._stack: list[tuple[Wedge, ...]] = []
        self._highlight: list[int] = []
        self._path: list[str] = []
        self._context: Any = None
        # The last direction pressed, for reading two of them as a diagonal.
        self._last_direction: str | None = None
        self._last_direction_at: float = 0.0
        self.meter = Meter()
        self.intents: list[Intent] = []

    # -- state ------------------------------------------------------------

    @property
    def is_open(self) -> bool:
        return bool(self._stack)

    @property
    def view(self) -> RingView | None:
        if not self.is_open:
            return None
        wedges = self._stack[-1]
        return RingView(
            wedges=wedges,
            highlighted=self._highlight[-1],
            path=tuple(self._path),
            context=self._context,
            available=(None if self._available is None
                       else tuple(self.is_available(w) for w in wedges)),
        )

    def _first_available(self, wedges: tuple[Wedge, ...]) -> int:
        """Where the highlight starts. Falls back to 0.

        Opening onto a cell that Enter refuses is the same failure as walking
        onto one, and it is the first thing a person sees. The fallback matters
        only when nothing at this level is available, which cannot happen
        through a submenu -- `is_available` refuses to open one with no
        available descendant -- but can at the top level of a host that wires
        nothing.
        """
        for index, wedge in enumerate(wedges):
            if self.is_available(wedge):
                return index
        return 0

    def is_available(self, wedge: Wedge) -> bool:
        """Whether this host can act on `wedge`.

        A SUBMENU IS AVAILABLE IF ANYTHING UNDER IT IS. Greying the leaves and
        leaving the verb bright walks a reader into a level where every cell is
        dead, which is worse than not opening: they have spent two keystrokes
        to be told nothing is there. Recursive rather than one level deep, so a
        deeper palette than this one behaves the same way.
        """
        if self._available is None:
            return True
        if wedge.is_submenu:
            return any(self.is_available(child) for child in wedge.children)
        return bool(self._available(wedge))

    # -- inbound API ------------------------------------------------------

    def open_at(self, context: Any = None) -> RingView | None:
        """Open the ring. One input.

        A resolver returning nothing leaves the ring closed rather than opening
        an empty one -- an empty ring is a dead end a user has to escape from,
        and it reads as a broken menu rather than an absent one.
        """
        self.meter.raw(recognized=True)
        wedges = tuple(self._resolve(context))
        if not wedges:
            return None
        self._context = context
        self._stack = [wedges]
        self._highlight = [self._first_available(wedges)]
        self._path = []
        self.meter.transition()
        return self.view

    def move(self, direction: str, now: float | None = None) -> RingView | None:
        """Move the highlight one direction. One input.

        Two presses arriving within `numpad.CHORD_WINDOW` are read as the
        diagonal between them, which is what pressing both at once means to a
        person and what a terminal cannot report. The chord is a shortcut, never
        the only route: the same two presses spaced further apart walk to the
        same corner one cell at a time.
        """
        if not self.is_open:
            self.meter.raw(recognized=False)
            return None
        self.meter.raw(recognized=True)

        view = self.view
        placement = view.placement
        # `None` when nobody declared availability, which `step_to_item` reads
        # as "every occupied cell". Building a set of all of them instead would
        # work and would hide the difference between "all of these" and "nobody
        # said", which is a distinction the rest of this module keeps.
        allowed = (None if view.available is None
                   else set(view.available_cells()))
        target = None

        if (now is not None and self._last_direction is not None
                and now - self._last_direction_at <= numpad.CHORD_WINDOW):
            corner = numpad.chord(self._last_direction, direction)
            if (corner is not None and corner in placement.by_cell
                    and (allowed is None or corner in allowed)):
                target = corner

        if target is None:
            target = numpad.step_to_item(view.cursor_cell, direction, placement,
                                         allowed=allowed)

        self._last_direction = direction
        self._last_direction_at = now if now is not None else 0.0

        index = placement.by_cell.get(target)
        if index is not None:
            self._highlight[-1] = index
        self.meter.transition()
        return self.view

    def press_cell(self, cell: int) -> Intent | None:
        """Choose the item in a numpad cell directly. One input.

        The centre backs out at every depth, which is why it holds no item: a
        menu whose centre sometimes cancels and sometimes chooses the fifth
        thing cannot be used without looking.
        """
        if not self.is_open:
            self.meter.raw(recognized=False)
            return None
        if cell == numpad.BACK:
            self.back()
            return None

        view = self.view
        index = view.placement.by_cell.get(cell)
        if index is None:
            # An empty cell is not a mistake worth punishing, and it is not a
            # transition either: nothing moved and nothing was chosen.
            self.meter.raw(recognized=False)
            return None
        if not view.is_available(index):
            # RECOGNIZED, AND REFUSED. The key is charged because it cost the
            # person a keystroke, and rad's IPA should say so -- a menu with
            # dead cells in it ought to show up as a worse number rather than
            # as a free mistake. Nothing transitions and the highlight does not
            # move: landing the cursor on a cell that cannot be chosen is the
            # state this whole change exists to prevent.
            self.meter.raw(recognized=True)
            return None
        self._highlight[-1] = index
        return self.enter()

    def rotate(self, delta: int) -> RingView | None:
        """Move the highlight. One input. Wraps, because a ring has no ends."""
        if not self.is_open:
            self.meter.raw(recognized=False)
            return None
        self.meter.raw(recognized=True)
        count = len(self._stack[-1])
        # Walk in `delta`'s direction until an available wedge, at most one lap.
        # Stopping on an unavailable one would put the cursor somewhere Enter
        # refuses, which reads as the key being broken.
        step = 1 if delta >= 0 else -1
        position = self._highlight[-1]
        for _ in range(count):
            position = (position + (delta if _ == 0 else step)) % count
            if self.is_available(self._stack[-1][position]):
                self._highlight[-1] = position
                break
        self.meter.transition()
        return self.view

    def enter(self) -> Intent | None:
        """Commit the highlighted wedge, or open it if it has children.

        One input either way. Returns the intent when one was committed.
        """
        if not self.is_open:
            self.meter.raw(recognized=False)
            return None
        self.meter.raw(recognized=True)
        wedge = self.view.current
        self.meter.transition()

        if wedge is None:
            return None
        if not self.is_available(wedge):
            # Reachable only if a highlight ended up here anyway -- every route
            # that moves it skips unavailable cells. Refused rather than
            # trusted: a guard that only holds while its callers behave is one
            # nobody can rely on.
            return None
        if wedge.is_submenu:
            self._stack.append(wedge.children)
            self._highlight.append(self._first_available(wedge.children))
            self._path.append(wedge.id)
            return None

        verb = self._path[0] if self._path else wedge.id
        intent = Intent(
            schema=SCHEMA,
            verb=verb,
            action=wedge.action or wedge.id,
            path=tuple(self._path + [wedge.id]),
            address=wedge.address,
            ipa=self.meter.commit(),
            levels=dict(self.meter.counts),
        )
        self.intents.append(intent)
        self.close(charge=False)
        if self._on_intent is not None:
            self._on_intent(intent)
        return intent

    def back(self) -> RingView | None:
        """Up one level, or closed if already at the top. One input."""
        if not self.is_open:
            self.meter.raw(recognized=False)
            return None
        self.meter.raw(recognized=True)
        self.meter.transition()
        if len(self._stack) == 1:
            self.close(charge=False)
            return None
        self._stack.pop()
        self._highlight.pop()
        self._path.pop()
        return self.view

    def close(self, charge: bool = True) -> None:
        """Abandon the menu. `charge=False` when a commit already paid for it."""
        if charge and self.is_open:
            self.meter.raw(recognized=True)
            self.meter.transition()
        self._stack = []
        self._highlight = []
        self._path = []
        self._context = None
        self.meter.inputs_since_open = 0

    # -- reporting --------------------------------------------------------

    def cost_report(self) -> dict[str, Any]:
        """IPA and its inverse, with the budget for the top level.

        Reported, never enforced: rad calls an over-budget verb a resolver
        design error, and while the palette is settling that is pressure rather
        than a gate.
        """
        committed = [i.ipa for i in self.intents]
        total = sum(committed)
        top = len(self._resolve(None) or ())
        return {
            "actions": len(committed),
            "inputs": total,
            "ipa": (total / len(committed)) if committed else None,
            "apc": (len(committed) / total) if total else None,
            "budget_top_level": budget_for(top),
            "over_budget": [i.action for i in self.intents
                            if i.ipa > budget_for(top)],
            "levels": dict(self.meter.counts),
            "reconciles": self.meter.reconciles(),
        }
