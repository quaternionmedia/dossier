"""Every action this panel offers, declared once.

**FOUR UNIVERSES DESCRIBED THE SAME THINGS AND NONE OF THEM AGREED.** Measured
before this file existed: 45 buttons with 43 handlers, 35 key bindings, 37
`action_` methods, and a rad ring of 19 commands of which 9 were wired. Nothing
connected them, so:

- `filter.all`, `filter.synced` and `filter.drifting` were in the ring and
  reported "not applied yet", while three buttons did exactly those things;
- the Topology view arrived with two buttons and no route in the ring at all;
- `escape -> close` was written four times and `q -> close` three, in four
  screens, each unaware of the others.

None of that is visible from any one of the four places. It is only visible from
a list, which is what this is.

**ONE DECLARATION, THREE ROUTES.** An `Action` names what it does once, and says
how it can be reached: a key, a button, a rad route. The host wires them; this
decides nothing about behaviour. What it makes possible is the question nobody
could previously ask — *is every action reachable both ways?*

**THE RULE THIS EXISTS TO ENFORCE.** Every action is completable by direct
interaction — a click or a keystroke — **and** by the numpad protocol. Not
because two routes are twice as good, but because the two serve different
people: a route only rad can reach is invisible to somebody who never opens the
ring, and a route only a button can reach cannot be driven from the keyboard at
all. An action that genuinely has only one route says so, in `only`, with the
reason.

**WHAT IS NOT HERE, ON PURPOSE.** Screen-local conventions. `escape` closing a
modal is not an action of this panel; it is what `escape` means everywhere, and
listing it once per screen in a registry would be the same duplication in a new
place. `CONVENTIONS` below names them so they are stated rather than repeated
without comment.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Action:
    """One thing a person can do, and every way of reaching it."""

    id: str
    """The canonical name, and the one the host dispatches on. Matches the
    rad ring's `action` exactly -- two vocabularies for one act is how the
    ring came to report `filter.all` unhandled while a button did it."""

    label: str
    """What a person sees. One label, so the button, the ring and the command
    sheet cannot drift into three names for one act."""

    key: str | None = None
    """The keystroke that commits it from the dashboard, if any."""

    button: str | None = None
    """The id of the button that commits it, if any."""

    rad: str | None = None
    """The dotted numpad route, e.g. `6.2`. **Derived from the ring, not
    declared twice** -- the ring is where the layout lives, and a number typed
    here as well would be a second copy that goes stale silently. This field
    records what the ring says, and a test compares them."""

    only: str = ""
    """Why this action has one route rather than two. Empty means it has both.

    **AN ACTION WITH ONE ROUTE IS A DECISION, NOT AN OVERSIGHT** -- and the
    difference has to be written down, because the two look identical from
    every other angle."""

    @property
    def direct(self) -> bool:
        """Reachable without opening the ring: a key or a button."""
        return bool(self.key or self.button)

    @property
    def both_ways(self) -> bool:
        return self.direct and bool(self.rad)


# Screen-local conventions. Not actions: `escape` closes whatever is open, in
# every screen, and that is what `escape` means rather than something this panel
# invented. Named here so the repetition in the screens is a convention being
# followed rather than four independent decisions.
CONVENTIONS: dict[str, str] = {
    "escape": "close or cancel whatever is open",
    "q": "close the screen (where it is not a text field)",
    "tab": "move focus forward",
    "shift+tab": "move focus back",
}


# One reason, carried in full by each action that has it. **Not "as above"** --
# a reader landing on `view.disk` in a failure message gets the reason, not a
# pointer to a line they cannot see. The variable is what keeps the wording
# single; the repetition in the output is the point of the field.
VIEWS_USE_THE_RING = (
    "the ring is how a view is chosen; a key for each would be six bindings "
    "competing with the search field, and the ring already costs two "
    "keystrokes to reach any of them"
)


REGISTRY: tuple[Action, ...] = (
    # --- Go: what to look at ---------------------------------------------
    Action("view.overview", "Overview", rad="8.8", only=VIEWS_USE_THE_RING),
    Action("view.deltas", "Deltas", rad="8.6", only=VIEWS_USE_THE_RING),
    Action("view.governance", "Governance", rad="8.2", only=VIEWS_USE_THE_RING),
    Action("view.disk", "Disk", rad="8.4", only=VIEWS_USE_THE_RING),
    Action("view.details", "Details", rad="8.9", only=VIEWS_USE_THE_RING),
    Action("view.topology", "Topology", rad="8.3", only=VIEWS_USE_THE_RING),

    # --- Do: what to change ----------------------------------------------
    Action("delta.advance", "Advance phase", button="btn-advance-phase",
           rad="6.8"),
    Action("delta.note", "Add note", button="btn-add-note", rad="6.6"),
    Action("project.sync", "Sync project", key="s", button="btn-sync",
           rad="6.2"),
    Action("sweep.review", "Sweep a dependency", rad="6.4",
           only="a sweep is proposed from the Dependencies selection and has "
                "no button of its own; the ring is where it is asked for"),

    # --- Show: what to include -------------------------------------------
    Action("filter.all", "All", key="f", button="btn-filter-all", rad="2.8"),
    Action("filter.synced", "Synced only", button="btn-filter-synced",
           rad="2.6"),
    Action("filter.drifting", "Drifting", button="btn-filter-unsynced",
           rad="2.2"),

    # --- Reach: across the seam ------------------------------------------
    Action("reach.qmcp", "Open in qmcp", rad="4.8",
           only="not applied yet; the ring says so rather than hiding it"),
    Action("reach.ingest", "Ingest deltas", button="btn-ingest-threads",
           rad="4.6"),
    Action("reach.reconcile", "Reconcile", rad="4.2",
           only="not applied yet outside the ring"),

    # --- the ring itself --------------------------------------------------
    Action("rad.menu", "Open the menu", key="m",
           only="the route into the ring cannot be inside it"),
)


BY_ID: dict[str, Action] = {action.id: action for action in REGISTRY}


def by_button(button_id: str) -> Action | None:
    """The action a button commits, or None if it commits none."""
    for action in REGISTRY:
        if action.button == button_id:
            return action
    return None


def by_key(key: str) -> Action | None:
    """The action a keystroke commits, or None."""
    for action in REGISTRY:
        if action.key == key:
            return action
    return None


def one_route_only() -> tuple[Action, ...]:
    """Actions reachable one way, which each carry a reason.

    Not a failure list -- a list of decisions somebody made and wrote down.
    A test proves each has a reason; nothing proves the reason is a good one,
    which is a person's judgement.
    """
    return tuple(a for a in REGISTRY if not a.both_ways)
