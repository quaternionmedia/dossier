"""One declaration per action, and the four universes reconciled against it.

**THE MEASUREMENT THAT PROMPTED THIS.** 45 buttons, 43 handlers, 35 bindings, 37
`action_` methods and a 19-command ring of which 9 were wired — four descriptions
of one set of things, none of which could see the others. What that hid:
`filter.*` reported "not applied yet" in the ring while three buttons did exactly
those things, and the Topology view shipped with two buttons and no ring route.

Neither is visible from inside any one universe. Both are obvious from a list.

THE TESTS WORTH READING ARE THE FIRST TWO: every action is reachable both ways
or says why, and the registry agrees with the ring about the numbers.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from dossier import actions
from dossier.actions import BY_ID, CONVENTIONS, REGISTRY
from dossier.rad.index import index

APP = Path(__file__).resolve().parents[2] / "src" / "dossier" / "tui" / "app.py"


# --- the rule this registry exists to enforce ---------------------------------


@pytest.mark.parametrize("action", REGISTRY, ids=lambda a: a.id)
def test_every_action_is_reachable_both_ways_or_says_why(action):
    """THE ONE THAT MATTERS.

    Every action is completable by a click or a keystroke **and** by the numpad
    protocol. Not because two routes are twice as good — because they serve
    different people. A route only rad reaches is invisible to somebody who
    never opens the ring; a route only a button reaches cannot be driven from
    the keyboard.

    An action with one route is allowed and must say why. **A reason is what
    separates a decision from an oversight**, and from every other angle the
    two look identical.

    Mutation: remove a reason from a one-route action and this fails.
    """
    if action.both_ways:
        return
    assert action.only.strip(), (
        f"{action.id} is reachable only "
        f"{'by the ring' if action.rad else 'directly'}, and says nothing "
        f"about why. Either give it the other route or write the reason down."
    )
    assert len(action.only) > 25, f"{action.id}: the reason is a label"


def test_most_actions_have_both_routes():
    """A registry where everything carried an excuse would satisfy the test
    above and none of its purpose.

    Mutation: strip the key and button from every action and this fails.
    """
    both = [a for a in REGISTRY if a.both_ways]
    assert len(both) >= 5, (
        f"only {len(both)} of {len(REGISTRY)} actions have both routes; the "
        f"reasons have become a way around the rule")


# --- the registry and the ring agree ------------------------------------------


def test_every_ring_action_is_declared():
    """The ring is where the layout lives; this is where the wiring lives. An
    action in one and not the other is how `filter.*` came to be routable and
    unhandled at the same time.

    Mutation: add a wedge with a new action and this fails until it is declared.
    """
    ring = {c.action for c in index() if not c.is_menu}
    missing = sorted(ring - set(BY_ID))
    assert not missing, f"in the ring, declared nowhere: {missing}"


def test_every_declared_rad_route_is_the_route_the_ring_gives():
    """**THE NUMBER IS THE RING'S, AND THIS RECORDS IT.** Two places holding one
    number is how the number goes stale; the test is what makes the copy safe.

    Mutation: renumber a wedge without updating the registry and this fails.
    """
    ring = {c.action: c.number for c in index() if not c.is_menu}
    wrong = {
        action.id: (action.rad, ring.get(action.id))
        for action in REGISTRY
        if action.rad and ring.get(action.id) != action.rad
    }
    assert not wrong, f"declared route != the ring's route: {wrong}"


def test_no_two_actions_claim_one_route():
    """A duplicated key, button or number is a route whose destination depends
    on which declaration is read first."""
    for field in ("key", "button", "rad"):
        seen: dict[str, str] = {}
        for action in REGISTRY:
            value = getattr(action, field)
            if not value:
                continue
            assert value not in seen, (
                f"{field} {value!r} is claimed by both {seen[value]} and "
                f"{action.id}")
            seen[value] = action.id


# --- the host agrees with the registry ----------------------------------------


def test_every_declared_button_exists_in_the_panel():
    """A declaration naming a button nothing yields is a route that does not
    exist, and it reads as one that does.

    Mutation: rename a button without updating the registry and this fails.
    """
    source = APP.read_text(encoding="utf-8")
    yielded = set(re.findall(r'Button\([^)]*id="([\w-]+)"', source, re.S))
    missing = sorted(a.button for a in REGISTRY
                     if a.button and a.button not in yielded)
    assert not missing, f"declared buttons the panel does not yield: {missing}"


def test_every_declared_key_is_bound_in_the_panel():
    """A declared key nothing binds is a keystroke that does nothing.

    Mutation: remove a binding without updating the registry and this fails.
    """
    source = APP.read_text(encoding="utf-8")
    bound = set(re.findall(r'Binding\(\s*"([^"]+)"', source))
    missing = sorted(a.key for a in REGISTRY if a.key and a.key not in bound)
    assert not missing, f"declared keys the panel does not bind: {missing}"


def test_the_host_handles_every_action_it_claims_to():
    """`RAD_HANDLED` is what the panel tells the ring it can do. An action in
    the registry with a route and no handler is the ring offering something
    that does nothing."""
    from dossier.tui.app import DossierApp

    handled = set(DossierApp.RAD_HANDLED)
    claimed = {a.id for a in REGISTRY if a.rad and not a.only}
    unhandled = sorted(claimed - handled)
    assert not unhandled, (
        f"declared as fully wired and not in RAD_HANDLED: {unhandled}")


# --- conventions are stated, not repeated by accident -------------------------


def test_screen_local_conventions_are_named():
    """`escape` closing a modal is not an action of this panel; it is what
    `escape` means. It appeared four times in four screens, and listing it once
    per screen in the registry would be the same duplication in a new place.

    Mutation: put a convention key in the registry and this fails.
    """
    conventional = set(CONVENTIONS)
    declared = {a.key for a in REGISTRY if a.key}
    overlap = sorted(conventional & declared)
    assert not overlap, (
        f"these are conventions and actions at once: {overlap}. A key cannot "
        f"mean one thing everywhere and something else here.")


def test_every_convention_says_what_it_means():
    for key, meaning in CONVENTIONS.items():
        assert meaning.strip(), f"{key} is listed with no meaning"


# --- the lookups --------------------------------------------------------------


def test_a_button_resolves_to_its_action():
    assert actions.by_button("btn-sync").id == "project.sync"
    assert actions.by_button("btn-nothing") is None


def test_a_key_resolves_to_its_action():
    assert actions.by_key("s").id == "project.sync"
    assert actions.by_key("~") is None


def test_the_one_route_list_is_the_actions_with_reasons():
    """Not a failure list — a list of decisions somebody wrote down."""
    for action in actions.one_route_only():
        assert action.only, f"{action.id} is in the list with no reason"


# --- dialogs follow a convention rather than each inventing one ---------------


def test_every_dialog_button_is_one_of_the_conventional_ids():
    """**A DIALOG THAT INVENTS `ok-btn` IS THE PROBLEM THIS CATCHES.**

    `cancel-btn` appears in eight dialogs and `add-btn` in five. They are not
    eight cancellations and five additions -- they are one of each, performed
    on whatever is open, which is why they are conventions and not actions.

    The value of writing them down is that a ninth dialog using a different id
    becomes visible. Nothing else in this codebase could have told you.

    Mutation: rename one dialog's cancel button and this fails.
    """
    from dossier.actions import MODAL_CONVENTIONS

    source = APP.read_text(encoding="utf-8")
    # Buttons whose ids look generic -- no feature prefix -- are dialog
    # buttons. A feature button is `btn-<something>`; a dialog button is
    # `<verb>-btn`, which is the convention this checks.
    dialog_like = set(re.findall(r'id="([a-z]+-btn)"', source))
    unknown = sorted(dialog_like - set(MODAL_CONVENTIONS))
    assert not unknown, (
        f"dialog buttons outside the convention: {unknown}. Either use one of "
        f"{sorted(MODAL_CONVENTIONS)} or add it with what it means.")


def test_a_dialog_button_is_never_also_an_action():
    """A button cannot mean "confirm this dialog" and "do this thing to the
    dossier" at once.

    Mutation: register a dialog button as an action and this fails.
    """
    from dossier.actions import MODAL_CONVENTIONS

    declared = {a.button for a in REGISTRY if a.button}
    overlap = sorted(declared & set(MODAL_CONVENTIONS))
    assert not overlap, f"declared as both a convention and an action: {overlap}"


def test_every_modal_convention_says_what_it_means():
    from dossier.actions import MODAL_CONVENTIONS

    for button, meaning in MODAL_CONVENTIONS.items():
        assert len(meaning.strip()) > 15, f"{button}: the meaning is a label"
