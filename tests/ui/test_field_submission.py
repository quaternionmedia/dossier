"""Every text field can be submitted from the keyboard.

**THIS WAS FIXED TWICE, ONE FIELD AT A TIME, AND WAS STILL BROKEN.**
`#thread-export-path` got a handler. Then `#topology-subject` got one, with a
comment in the source calling it "the same one-key-short failure this app
already fixed once". At that point nine of thirteen fields were still mouse-only.

Fixing an instance does not fix a class, and nothing here could see the class:
the fields are in thirteen places, the handlers in three, and no reading of
either tells you the other is short. Only a list does — which is what this is,
and what `dossier/actions.py` exists for.

A field only a mouse can submit is worse than no field, because it looks
finished.
"""

from __future__ import annotations

import re
from pathlib import Path

from dossier import actions

APP = Path(__file__).resolve().parents[2] / "src" / "dossier" / "tui" / "app.py"

# An `Input(...)` call, including one wrapped over several lines.
INPUT_CALL = re.compile(r"Input\((?:[^()]|\([^()]*\))*\)", re.S)


def fields() -> list[tuple[int, str]]:
    """(line, id) for every text field the app composes."""
    source = APP.read_text(encoding="utf-8")
    found = []
    for match in INPUT_CALL.finditer(source):
        ident = re.search(r'id="([^"]+)"', match.group(0))
        line = source[: match.start()].count("\n") + 1
        found.append((line, ident.group(1) if ident else ""))
    return found


def test_there_are_fields_to_check():
    """A regex that matched nothing would make every check below vacuous, and a
    vacuous check reports green.

    Mutation: point `INPUT_CALL` at something absent and this fails.
    """
    assert len(fields()) > 8, fields()


def test_every_field_has_an_id():
    """A field with no id cannot be named by a handler, by a test, or in a bug
    report. It also cannot be exempted, which is the point: the only way to opt
    out is to say so.
    """
    anonymous = [line for line, ident in fields() if not ident]
    assert not anonymous, (
        f"Input() with no id= at line(s) {anonymous}. Give it one: an "
        f"unnamed field cannot be submitted, tested, or excused.")


def test_every_field_can_be_submitted_from_the_keyboard():
    """**THE ONE THIS EXISTS FOR.**

    Two ways to satisfy it, and both are declarations rather than code a reader
    has to find: the field means something of its own and says so in
    `FIELDS_WITH_THEIR_OWN_MEANING`, or it sits in a dialog and Enter commits
    that dialog through `COMMIT_BUTTONS`.

    The second needs nothing per field, which is the whole point — a new dialog
    gets Enter for free, and a new *panel* field fails here until somebody
    decides what Enter means on it.

    Mutation: add an `Input(id="whatever")` to a panel and this fails, naming it.
    """
    source = APP.read_text(encoding="utf-8")
    # A dialog is recognised by the commit button it offers, which is the same
    # thing the runtime handler looks for -- so this cannot pass on a dialog the
    # handler would not act on.
    dialog_buttons = {
        button for button in actions.COMMIT_BUTTONS
        if f'id="{button}"' in source
    }
    assert dialog_buttons, (
        "no commit button appears in the app at all, so the convention this "
        "checks is not implemented and every dialog field is unreachable")

    orphans = []
    for line, ident in fields():
        if ident in actions.FIELDS_WITH_THEIR_OWN_MEANING:
            continue
        if in_a_dialog(source, line, dialog_buttons):
            continue
        orphans.append(f"{ident} (line {line})")

    assert not orphans, (
        "these fields cannot be submitted with Enter:\n  "
        + "\n  ".join(orphans)
        + "\n\nEither the field means something of its own -- add it to "
          "actions.FIELDS_WITH_THEIR_OWN_MEANING with what Enter does -- or it "
          "belongs to a dialog, in which case give that dialog one of "
          f"{list(actions.COMMIT_BUTTONS)}.")


def in_a_dialog(source: str, line: int, dialog_buttons: set[str]) -> bool:
    """Whether a commit button is composed near this field.

    Proximity rather than parsing: these dialogs are composed inline in one
    very long method, so there is no enclosing class or function to ask. The
    window is generous in both directions because a field can precede or follow
    its buttons.
    """
    lines = source.splitlines()
    window = "\n".join(lines[max(0, line - 40): line + 40])
    return any(f'id="{button}"' in window for button in dialog_buttons)


def test_a_field_with_its_own_meaning_says_what_that_meaning_is():
    """An exemption with no reason is an excuse, and this list is the only place
    a reader learns what Enter does on those fields."""
    for ident, meaning in actions.FIELDS_WITH_THEIR_OWN_MEANING.items():
        assert len(meaning.strip()) > 15, f"{ident}: the reason is a label"


def test_no_exemption_names_a_field_that_is_gone():
    """A list that outlives its subjects stops being read.

    Mutation: leave a removed field in the mapping and this fails.
    """
    present = {ident for _, ident in fields()}
    stale = [f for f in actions.FIELDS_WITH_THEIR_OWN_MEANING if f not in present]
    assert not stale, f"these fields no longer exist: {stale}"


def test_the_commit_buttons_are_all_conventions():
    """`COMMIT_BUTTONS` and `MODAL_CONVENTIONS` must not drift: a button Enter
    commits to, that no dialog convention describes, is a fourth universe
    starting.
    """
    undeclared = [b for b in actions.COMMIT_BUTTONS
                  if b not in actions.MODAL_CONVENTIONS]
    assert not undeclared, (
        f"Enter commits to {undeclared}, which MODAL_CONVENTIONS does not "
        f"describe. Say what they mean, or stop committing to them.")


# --- and it actually happens, not just declared --------------------------------
#
# The checks above read the source. They prove every field is *declared*
# submittable, which is a different claim from Enter doing anything — and this
# corpus's own repeated finding is that a check on the arrangement is not a
# check on the behaviour. These drive the real app.

import pytest
from textual.widgets import Input



@pytest.mark.asyncio
async def test_enter_in_a_dialog_field_commits_the_dialog(test_session, monkeypatch, no_close):
    """THE ONE THAT MATTERS.

    Type a project name, press Enter, and the dialog does what Add does. Before
    this, that keystroke did nothing at all and the field looked finished.

    Mutation: remove the `@on(Input.Submitted)` handler and this fails.
    """
    from dossier.tui.app import DossierApp

    added: list[str] = []
    monkeypatch.setattr(DossierApp, "add_project",
                        lambda self, name: added.append(name))

    app = DossierApp(session_factory=lambda: no_close(test_session))
    async with app.run_test(size=(160, 50)) as pilot:
        await pilot.pause()
        app.action_add()
        await pilot.pause()

        field = app.screen.query_one("#project-input", Input)
        field.value = "a-new-project"
        field.focus()
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()

    assert added == ["a-new-project"], added


@pytest.mark.asyncio
async def test_enter_respects_what_the_dialog_refuses(test_session, monkeypatch, no_close):
    """Enter presses the dialog's button; it does not bypass its judgement.

    The Add handler refuses an empty name and says so. Pressing Enter must get
    that same refusal rather than dismissing — which also demonstrates the
    button being pressed is the dialog's own, since only its handler refuses.

    Mutation: dismiss directly from the Enter handler instead of pressing the
    button and this fails.
    """
    from dossier.tui.app import DossierApp

    added: list[str] = []
    monkeypatch.setattr(DossierApp, "add_project",
                        lambda self, name: added.append(name))

    app = DossierApp(session_factory=lambda: no_close(test_session))
    async with app.run_test(size=(160, 50)) as pilot:
        await pilot.pause()
        app.action_add()
        await pilot.pause()

        field = app.screen.query_one("#project-input", Input)
        field.value = ""
        field.focus()
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        still_open = bool(app.screen.query("#project-input"))

    assert added == [], added
    assert still_open, "the dialog dismissed on a name it says it requires"


@pytest.mark.asyncio
async def test_enter_on_a_panel_field_does_that_fields_own_thing(
        test_session, monkeypatch, no_close):
    """A field in `FIELDS_WITH_THEIR_OWN_MEANING` must not be swallowed by the
    dialog convention. The topology subject draws a topology; it commits
    nothing.

    Observed by what the draw *asks for* rather than by patching the method that
    starts it: replacing `_load_topology_tab` leaves the tab's loading lifecycle
    half-run and the test hangs, which is the harness measuring itself rather
    than the behaviour.

    Mutation: remove the specific `@on(Input.Submitted, "#topology-subject")`
    handler and this fails. Removing the *early return* does not fail here, and
    the guard-on-the-guard tests at the end of this file say why and cover it.
    """
    from dossier import threads
    from dossier.tui.app import DossierApp

    asked: list[str] = []

    def record(**kw):
        asked.append(kw.get("subject") or kw.get("kind") or "")
        return threads.Topology(
            False, "http://127.0.0.1:3141/v1/topology",
            problem="nothing is answering", remedy="start the harness")

    monkeypatch.setattr(threads, "topology", record)

    app = DossierApp(session_factory=lambda: no_close(test_session),
                     initial_tab="tab-topology")
    async with app.run_test(size=(160, 50)) as pilot:
        await pilot.pause()
        for _ in range(30):
            if asked:
                break
            await pilot.pause(0.05)
        asked.clear()

        field = app.screen.query_one("#topology-subject", Input)
        field.value = "dossier"
        field.focus()
        await pilot.pause()
        await pilot.press("enter")
        for _ in range(30):
            if asked:
                break
            await pilot.pause(0.05)

    assert asked == ["dossier"], asked


# --- the guard on the guard ----------------------------------------------------
#
# **THIS ONE IS HONEST ABOUT BEING DEFENSIVE.** Removing the early return for
# `FIELDS_WITH_THEIR_OWN_MEANING` kills no test that drives the real app, and it
# is worth saying why rather than claiming a mutation that does not fire: no
# screen in the app today puts a commit button on the same screen as a panel
# field, so the loop finds nothing and falls through harmlessly.
#
# That is a property of the current layout, not of the rule. `#search-input`
# lives on the main screen, and the day anything composes an `add-btn` there,
# Enter in the search box would run the search *and* commit a dialog. So the
# case is built here directly instead of waiting for the layout to produce it.


class _Pressed:
    """A button that records being pressed instead of doing anything."""

    def __init__(self):
        self.presses = 0

    def press(self):
        self.presses += 1


class _Found(list):
    """What `screen.query(...)` returns: falsy when empty, `.first()` when not."""

    def first(self, _type=None):
        return self[0]


class _Screen:
    def __init__(self, buttons: dict):
        self._buttons = buttons
        self.asked: list[str] = []

    def query(self, selector: str):
        self.asked.append(selector)
        found = self._buttons.get(selector.lstrip("#"))
        return _Found([found] if found else [])


class _Field:
    def __init__(self, ident: str, screen):
        self.id = ident
        self.screen = screen


class _Event:
    def __init__(self, field):
        self.input = field
        self.stopped = False

    def stop(self):
        self.stopped = True


def _handle(field_id: str, buttons: dict):
    """Run the app's real handler against a constructed screen."""
    from dossier.tui.app import DossierApp

    screen = _Screen(buttons)
    event = _Event(_Field(field_id, screen))
    DossierApp.on_any_field_submitted(object.__new__(DossierApp), event)
    return screen, event


def test_a_panel_field_is_not_committed_even_beside_a_commit_button():
    """THE ONE THE EARLY RETURN EXISTS FOR.

    A field that means something of its own, on a screen that also holds a
    commit button. Without the early return, Enter would do the field's own
    thing *and* commit the dialog — two acts from one keystroke, and the second
    one invisible.

    Mutation: delete the `FIELDS_WITH_THEIR_OWN_MEANING` early return and this
    fails.
    """
    button = _Pressed()
    screen, event = _handle("search-input", {"add-btn": button})

    assert button.presses == 0, "Enter in the search field committed a dialog"
    assert screen.asked == [], "it should not even look for a commit button"
    assert not event.stopped, (
        "stopping the event would also rob the field's own handler of it")


def test_a_dialog_field_beside_a_commit_button_commits_it():
    """The control. Without it, the case above is satisfiable by never pressing
    anything at all."""
    button = _Pressed()
    _, event = _handle("project-input", {"add-btn": button})

    assert button.presses == 1
    assert event.stopped, "the event must be stopped once it has been acted on"


def test_the_first_commit_button_in_order_wins():
    """`COMMIT_BUTTONS` is ordered, not a set: a dialog offering two would
    otherwise commit to whichever the query happened to return first, and which
    one that is would depend on the DOM.

    Mutation: iterate a set instead of the tuple and this becomes flaky rather
    than failing outright, which is worse — so the order is asserted directly.
    """
    from dossier import actions

    first, second = actions.COMMIT_BUTTONS[0], actions.COMMIT_BUTTONS[1]
    winner, loser = _Pressed(), _Pressed()
    _handle("project-input", {first: winner, second: loser})

    assert (winner.presses, loser.presses) == (1, 0)


def test_a_dialog_with_no_commit_button_does_nothing_and_says_nothing():
    """A dialog that invents its own button id gets no Enter. That is a real
    gap, and it is the structural test above that names it — this one only
    pins that the runtime fails quietly rather than raising into the app.
    """
    _, event = _handle("project-input", {})
    assert not event.stopped
