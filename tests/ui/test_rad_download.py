"""`4.3` -- downloading a whole owner from the menu.

**THE PANEL COULD ADD ONE REPOSITORY AT A TIME AND NO MORE.** Everything an
organisation has was `dossier github sync-user` or `dossier github sync-org`,
on the command line, and which of the two was right was something you had to
already know -- picking wrong does not fail, it returns an empty list, so an
organisation asked for as a user reports "no repositories" and reads as a fact
about the org.

**THE RING CANNOT ASK FOR FREE TEXT**, and an owner is free text: rad commits
and closes, which is what makes a keystroke count mean anything. So the wedge
opens a dialog, exactly as `4.6` does for an export path, and the dialog is
where the name is typed.

**AND IT LISTS BEFORE IT ACTS.** The first commit looks the owner up -- one
call, which says whether they are a person or an organisation and how much of
what they have is already here. The second fetches. A download that started on
the keystroke that named it would spend hundreds of API calls on a typo.

No test here reaches GitHub.
"""

from __future__ import annotations

import pytest
from sqlmodel import Session, SQLModel, create_engine
from textual.widgets import Button, Input, Static

from dossier.rad.index import applied_by, by_number, keystroke
from dossier.tui import DossierApp


def app_for():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    return DossierApp(session_factory=lambda: Session(engine))


# --- the number ---------------------------------------------------------------


def test_four_three_is_the_download_command():
    """Pinned, because it is written into the command sheet and this file. A
    palette reorder that moved it must be loud rather than silent.

    Mutation: reorder `Reach` and this fails.
    """
    found = by_number()["4.3"]
    assert found.action == "reach.download"
    assert found.path == ("Reach", "Download an owner")
    assert found.keys == ("m", "4", "3")


def test_it_sits_beside_the_clone_because_they_are_two_halves_of_one_act():
    """The clone brings the *code* for what this database already indexes; the
    download brings the *index* for what GitHub has and nobody here has asked
    about. Neighbours in the menu because they are neighbours in meaning.
    """
    reach = [c for c in by_number().values()
             if c.number.startswith("4.") and not c.is_menu]
    actions = [c.action for c in reach]
    assert {"reach.clone", "reach.download"} <= set(actions)


def test_the_download_command_is_wired():
    """A wedge the host does not handle is greyed out and refuses the digit.

    Mutation: drop it from `RAD_ACTIONS` and this fails.
    """
    wired = {c.action: ok for c, ok in applied_by(DossierApp.RAD_HANDLED)}
    assert wired["reach.download"], "4.3 is in the ring and does nothing"


def test_the_sixth_child_of_reach_cost_no_keystrokes():
    """rad's budget is `1 + ceil(N/2) + 1`: five children cost 5 and six cost
    5. This one was free, which is why it went here rather than under `Do`,
    where a seventh child would have cost a step.

    Mutation: put it under `Do` and this fails.
    """
    from dossier.rad.palette import resolve
    from dossier.rad.session import budget_for

    reach = next(w for w in resolve() if w.id == "reach")
    assert len(reach.children) == 6
    assert budget_for(6) == budget_for(5)


def test_nobody_has_to_type_the_route_into_prose():
    """`keystroke` is how a route reaches a page. Five places once held `m 6 4`
    for the sweep and every one went stale at once.
    """
    assert keystroke("reach.download") == "m 4 3"


# --- the act is declared, and reachable outside the app too -------------------


def test_the_act_says_why_it_has_one_route_in_the_app():
    """An action with one route is a decision, and the difference between a
    decision and an oversight has to be written down.

    Mutation: remove the reason and `test_every_action_is_reachable_both_ways_
    or_says_why` fails.
    """
    from dossier import actions

    found = actions.BY_ID["reach.download"]
    assert found.button is None and found.key is None
    assert len(found.only) > 25 and "API calls" in found.only


def test_it_has_a_command_outside_the_application():
    """**AND IT IS ONE COMMAND, NOT TWO.** The ring works out user-or-org, and
    a command line that still made you choose would be the two surfaces
    describing one act differently.

    Mutation: point it at `sync-user` and the route no longer matches what the
    ring does.
    """
    from dossier.toc import ACT_ROUTES

    assert ACT_ROUTES["reach.download"] == "dossier github download"


def test_that_command_exists_and_takes_an_owner():
    from click.testing import CliRunner

    from dossier.cli import cli

    result = CliRunner().invoke(cli, ["github", "download", "--help"])
    assert result.exit_code == 0, result.output
    assert "OWNER" in result.output
    assert "--dry-run" in result.output, "it cannot say what it would do"


# --- the dialog ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_route_opens_a_dialog_with_the_cursor_in_the_field():
    """THE ONE THIS EXISTS FOR.

    The ring hands off to a surface that can hold free text, and it lands with
    the cursor already where the name goes -- `4.6` states the same rule about
    the same thing.

    Mutation: drop the `focus()` in `on_mount` and this fails.
    """
    app = app_for()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app._begin_owner_download()
        await pilot.pause()

        field = app.screen.query_one("#download-owner", Input)
        assert app.screen.focused is field, (
            f"the cursor is on {app.screen.focused}, not the owner field")


@pytest.mark.asyncio
async def test_the_dialog_commits_with_a_conventional_button():
    """`add-btn` is in `COMMIT_BUTTONS`, which is what gives Enter in the field
    its meaning for free. A dialog inventing `lookup-btn` would need Enter
    wired by hand and would fail the convention guard.

    Mutation: rename the button and `test_every_dialog_button_is_one_of_the_
    conventional_ids` fails.
    """
    app = app_for()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app._begin_owner_download()
        await pilot.pause()

        ids = {b.id for b in app.screen.query(Button)}

    assert ids == {"add-btn", "cancel-btn"}, ids


@pytest.mark.asyncio
async def test_an_empty_owner_is_refused_rather_than_looked_up():
    """A look-up with nothing in the field is a call spent on nothing.

    Mutation: drop the guard and this reaches the network.
    """
    app = app_for()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app._begin_owner_download()
        await pilot.pause()

        screen = app.screen
        screen.query_one("#download-owner", Input).value = "   "
        screen.query_one("#add-btn", Button).press()
        await pilot.pause()

        assert screen._looked_up is None
        assert app.screen is screen, "it committed with nothing named"


@pytest.mark.asyncio
async def test_the_first_commit_reads_and_the_second_fetches(monkeypatch):
    """**LIST FIRST, ACT SECOND.** The first press says what is there and
    relabels the button with the number; only the second dismisses the dialog
    and starts the work.

    Mutation: dismiss on the first press and this fails on the first assert.
    """
    from dossier import download as fetching

    class Found:
        repos = ("a", "b", "c")
        held = frozenset()

        def summary(self):
            return "qm (organization): 3 repository(ies), none of them held here yet"

    monkeypatch.setattr(fetching, "inventory",
                        lambda session, client, login: Found())
    monkeypatch.setattr("dossier.parsers.GitHubClient",
                        lambda *a, **k: _NoClient())

    app = app_for()
    started = []
    monkeypatch.setattr(DossierApp, "_run_owner_download",
                        lambda self, login: started.append(login))

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app._begin_owner_download()
        await pilot.pause()

        screen = app.screen
        screen.query_one("#download-owner", Input).value = "qm"
        screen.query_one("#add-btn", Button).press()
        await pilot.pause()
        await pilot.pause()

        assert app.screen is screen, "the first press committed"
        assert started == [], "the first press started a download"
        said = str(screen.query_one("#download-found", Static).render())
        assert "3 repository(ies)" in said, said
        assert "Download 3" in str(screen.query_one("#add-btn", Button).label)

        screen.query_one("#add-btn", Button).press()
        await pilot.pause()
        await pilot.pause()

    assert started == ["qm"], started


@pytest.mark.asyncio
async def test_editing_the_name_after_a_look_up_looks_it_up_again(monkeypatch):
    """**OTHERWISE THE COUNT ON THE BUTTON IS ABOUT SOMEBODY ELSE.** Two
    presses with an edit between them would fetch the second owner on the
    strength of the first one's reading.

    Mutation: keep `_looked_up` across an edit and this fails.
    """
    from dossier import download as fetching

    class Found:
        repos = ("a",)
        held = frozenset()

        def summary(self):
            return "one"

    seen = []

    def looked(session, client, login):
        seen.append(login)
        return Found()

    monkeypatch.setattr(fetching, "inventory", looked)
    monkeypatch.setattr("dossier.parsers.GitHubClient",
                        lambda *a, **k: _NoClient())

    app = app_for()
    started = []
    monkeypatch.setattr(DossierApp, "_run_owner_download",
                        lambda self, login: started.append(login))

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app._begin_owner_download()
        await pilot.pause()

        screen = app.screen
        field = screen.query_one("#download-owner", Input)
        button = screen.query_one("#add-btn", Button)

        field.value = "first"
        button.press()
        await pilot.pause()
        await pilot.pause()

        field.value = "second"
        button.press()
        await pilot.pause()
        await pilot.pause()

        assert started == [], "the edited name was fetched on the old reading"

    assert seen == ["first", "second"], seen


@pytest.mark.asyncio
async def test_a_refusal_is_reported_in_the_words_the_api_used(monkeypatch):
    """A login that is not there, a token that cannot read it and a network
    that is down all fail, and only the API can say which.

    Mutation: replace the message with a category and this fails.
    """
    from dossier import download as fetching

    def refuses(session, client, login):
        raise RuntimeError("404 Not Found")

    monkeypatch.setattr(fetching, "inventory", refuses)
    monkeypatch.setattr("dossier.parsers.GitHubClient",
                        lambda *a, **k: _NoClient())

    app = app_for()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app._begin_owner_download()
        await pilot.pause()

        screen = app.screen
        screen.query_one("#download-owner", Input).value = "nobody"
        screen.query_one("#add-btn", Button).press()
        await pilot.pause()
        await pilot.pause()

        said = str(screen.query_one("#download-found", Static).render())
        assert "404 Not Found" in said, said
        assert "Look up" in str(screen.query_one("#add-btn", Button).label)


class _NoClient:
    """A client that is never asked anything: `inventory` is patched out."""

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False
