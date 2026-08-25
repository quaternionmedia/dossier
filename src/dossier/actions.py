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



    only: str = ""
    """Why this action has one route rather than two. Empty means it has both.

    **AN ACTION WITH ONE ROUTE IS A DECISION, NOT AN OVERSIGHT** -- and the
    difference has to be written down, because the two look identical from
    every other angle."""

    @property
    def rad(self) -> str | None:
        """The dotted numpad route, e.g. `6.2`, or None if the ring cannot
        reach this.

        **READ FROM THE RING RATHER THAN RECORDED BESIDE IT.** This was a
        declared field with a test comparing it against the ring, which is a
        safe way to keep a copy right up to the moment the copy has to change:
        the ring grew a group level and every view's number moved at once.

        The number was never read by anything either -- only its presence, to
        answer whether an action has a second route -- so recording it bought
        a maintenance cost and no reader. What the test now asserts is the
        invariant that is not vacuous: the ring and this registry name the
        same acts, in both directions.
        """
        from dossier.rad.index import by_action

        found = by_action().get(self.id)
        return found.number if found else None

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
    "?": "open help",
}


# The buttons every dialog has, and what each means. **A CONVENTION, EXACTLY AS
# `escape` IS.** `cancel-btn` appears in eight dialogs and `add-btn` in five;
# they are not eight cancellations and five additions, they are one of each,
# performed on whatever is open.
#
# **SO THEY ARE NOT ACTIONS AND GET NO RING ROUTE.** Confirming a dialog you
# opened is the completion of the act that opened it, not a second act. Giving
# each a number would put eight cells in the ring that mean "yes" and can only
# be pressed while a dialog is already in front of you.
#
# What this buys is the thing the four universes lacked: a dialog that invents
# `ok-btn` is now visible, because the standard ids are written down and a test
# compares them.
MODAL_CONVENTIONS: dict[str, str] = {
    "cancel-btn": "abandon the dialog, changing nothing",
    "add-btn": "commit what the dialog collected",
    "create-btn": "commit what the dialog collected",
    "close-btn": "dismiss a dialog that only showed something",
    "delete-btn": "commit a deletion the dialog described",
    "remove-btn": "commit a removal the dialog described",
    "reset-btn": "put the dialog's fields back as they were",
}


# The button a dialog's text fields commit to, in the order a dialog would be
# read. **ENTER IN A FIELD IS A CONVENTION, EXACTLY AS `escape` IS**, and it is
# here for the same reason `cancel-btn` is: five dialogs collecting text are not
# five different meanings of Enter.
#
# It is written down because the app kept getting it wrong one field at a time.
# `#thread-export-path` was fixed once, `#topology-subject` a second time, each
# with a comment calling it "the same one-key-short failure this app already
# fixed once" -- and nine fields were still mouse-only when they were counted.
# A field that only a mouse can submit is worse than no field, because it looks
# finished.
#
# Ordered, not a set: a dialog offering two of these would otherwise commit to
# whichever the query happened to return first.
COMMIT_BUTTONS: tuple[str, ...] = (
    "create-btn", "add-btn", "delete-btn", "remove-btn",
)


# Text fields whose Enter means something other than "commit this dialog", each
# with what it does instead. These are not dialogs; they are fields on a panel,
# and the panel decides. Listed so that `every field can be submitted` is
# checkable without the check having to understand any of them.
FIELDS_WITH_THEIR_OWN_MEANING: dict[str, str] = {
    "search-input": "runs the search, or the `:command` typed into it",
    "topology-subject": "draws the topology for that subject",
    "sweep-package": "reviews a sweep of that package",
    "thread-export-path": "writes the export to that path",
    # Settings, not a form. Both carry `@on(Input.Changed)` handlers that
    # validate and `_auto_save()` on every keystroke, so the value is already
    # persisted by the time Enter could do anything. Declared rather than
    # silently skipped: "Enter does nothing here, and that is correct" is a
    # different fact from "nobody wired Enter", and only one of them is fine.
    "sync-batch-size": "nothing; the value is saved as it is typed",
    "sync-delay": "nothing; the value is saved as it is typed",
}


# One reason, carried in full by each action that has it. **Not "as above"** --
# a reader landing on `view.disk` in a failure message gets the reason, not a
# pointer to a line they cannot see. The variable is what keeps the wording
# single; the repetition in the output is the point of the field.
from dossier.views import VIEWS

VIEWS_USE_THE_RING = (
    "the ring is how a view is chosen; a key for each would be six bindings "
    "competing with the search field, and the ring already costs two "
    "keystrokes to reach any of them"
)


REGISTRY: tuple[Action, ...] = (
    # --- Go: what to look at ---------------------------------------------
    #
    # **ONE ROW PER VIEW, FROM `dossier.views`.** Six of the eighteen views
    # were declared here by hand and the other twelve were not declared at
    # all, which is the same drift the settings list and the ring dispatch
    # both had. A view added to that registry gets its row here, its wedge in
    # the palette and its line in the index together.
    *(Action(view.action, view.title, only=VIEWS_USE_THE_RING)
      for view in VIEWS),

    # --- Do: what to change ----------------------------------------------
    Action("delta.advance", "Advance phase", button="btn-advance-phase",),
    Action("delta.note", "Add note", button="btn-add-note"),
    Action("project.sync", "Sync project", key="s", button="btn-sync",),
    Action("sweep.review", "Sweep a dependency", only="a sweep is proposed from the Dependencies selection and has "
                "no button of its own; the ring is where it is asked for"),

    # --- Show: what to include -------------------------------------------
    Action("filter.all", "All", key="f", button="btn-filter-all"),
    Action("filter.synced", "Synced only", button="btn-filter-synced",),
    Action("filter.drifting", "Drifting", button="btn-filter-unsynced",),

    # --- Reach: across the seam ------------------------------------------
    Action("reach.qmcp", "Open in qmcp", only="not applied yet; the ring says so rather than hiding it"),
    Action("reach.clone", "Clone what is absent",
           only="a clone writes directories onto somebody's disk and pulls "
                "them over the network, so it is asked for deliberately; a "
                "button sitting on a panel is one misclick from eighty-two "
                "of them"),
    Action("reach.ingest", "Ingest deltas", button="btn-ingest-threads",),
    # No key. The direct route is selecting the row -- `DataTable.RowSelected`
    # fires on a click and on Enter alike -- and a tab-local act does not earn a
    # global letter. `r` is Refresh, and taking it would be the fourth-universe
    # problem this file exists to end.
    Action("reach.read", "Read conversation", button="btn-read-thread",),
    Action("reach.reconcile", "Reconcile", only="not applied yet outside the ring"),

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
