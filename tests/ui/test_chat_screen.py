"""Opening one archived conversation from the archive table.

**NO REAL ARCHIVE MATERIAL APPEARS HERE.** The archive carries conversation
titles, session identifiers and repository names the organisation has decided
must never be published, and a fixture is published the moment it is committed.
Everything below is invented.
"""

from __future__ import annotations

import pytest
from textual.widgets import DataTable, Static

from dossier import chat, threads
from dossier.tui.app import ChatScreen, DossierApp


def a_conversation(**over) -> threads.Conversation:
    found = dict(
        reachable=True, where="http://127.0.0.1:3141/v1/threads/claude/abc",
        source="claude", identifier="abc", title="Choosing the ports",
        started_at="2026-08-01T09:00:00Z",
        turns=[{"id": "t1", "role": "user", "at": "09:00",
                "text": "which port for the harness"},
               {"id": "t2", "role": "assistant", "at": "09:01",
                "text": "the one nobody else wants"}],
    )
    found.update(over)
    return threads.Conversation(**found)


def with_one_row(app: DossierApp, address: str = "thread-abc") -> None:
    """Put one row in the archive table, as the facet would."""
    table = app.query_one("#threads-table", DataTable)
    table.clear(columns=True)
    for column in ("delta", "title", "speaks as", "phase", "turns", "state"):
        table.add_column(column)
    table.add_row(address, "Choosing the ports", "--", "brainstorm", "2", "held")


@pytest.mark.asyncio
async def test_selecting_a_row_opens_the_conversation(
        test_session, monkeypatch, no_close):
    """THE ONE THAT MATTERS.

    The archive table has listed conversations since it was built and nothing
    could open one. A row is an address, a trimmed title and a turn count —
    none of which is the conversation.

    Mutation: remove the `DataTable.RowSelected` handler and this fails.
    """
    monkeypatch.setattr(threads, "locate", lambda name, **kw: ("claude", "abc"))
    monkeypatch.setattr(threads, "conversation",
                        lambda source, ident, **kw: a_conversation())

    app = DossierApp(session_factory=lambda: no_close(test_session),
                     initial_tab="tab-threads")
    async with app.run_test(size=(160, 50)) as pilot:
        await pilot.pause()
        with_one_row(app)
        table = app.query_one("#threads-table", DataTable)
        table.focus()
        table.move_cursor(row=0)
        await pilot.pause()
        await pilot.press("enter")

        # Wait for the transcript, not just the screen: `push_screen` returns
        # before `compose` has mounted anything, so a loop that stops at
        # `isinstance(..., ChatScreen)` can query an empty screen. It passed on
        # the reachable cases by timing alone.
        for _ in range(40):
            if isinstance(app.screen, ChatScreen) and app.screen.query("#chat-body"):
                break
            await pilot.pause(0.05)
        opened = isinstance(app.screen, ChatScreen)
        shown = str(app.screen.query_one("#chat-body", Static).render()) if opened else ""

    assert opened, "selecting a row did not open the conversation"
    assert "which port for the harness" in shown
    assert "the one nobody else wants" in shown


@pytest.mark.asyncio
async def test_the_button_opens_the_same_thing(
        test_session, monkeypatch, no_close):
    """`reach.read` promises a button route and a ring route. This is the
    button; both land on one method, so they cannot drift apart.

    Mutation: point the button at a different method and this fails.
    """
    monkeypatch.setattr(threads, "locate", lambda name, **kw: ("claude", "abc"))
    monkeypatch.setattr(threads, "conversation",
                        lambda source, ident, **kw: a_conversation())

    app = DossierApp(session_factory=lambda: no_close(test_session),
                     initial_tab="tab-threads")
    async with app.run_test(size=(160, 50)) as pilot:
        await pilot.pause()
        with_one_row(app)
        await pilot.pause()
        app.query_one("#btn-read-thread").press()
        for _ in range(40):
            if isinstance(app.screen, ChatScreen):
                break
            await pilot.pause(0.05)
        opened = isinstance(app.screen, ChatScreen)

    assert opened, "the Read button did not open the conversation"


@pytest.mark.asyncio
async def test_an_unreachable_harness_still_opens_and_says_why(
        test_session, monkeypatch, no_close):
    """**A NOTIFICATION WOULD VANISH.** The reader would be left looking at the
    same table wondering what happened, which is the shape of the loading-
    overlay defect this panel already had once.

    Mutation: notify instead of pushing the screen and this fails.
    """
    monkeypatch.setattr(threads, "locate", lambda name, **kw: ("claude", "abc"))
    monkeypatch.setattr(threads, "conversation", lambda source, ident, **kw:
                        threads.Conversation(
                            False, "http://127.0.0.1:3141/v1/threads/claude/abc",
                            problem="nothing is answering at http://127.0.0.1:3141",
                            remedy="`uv run qm dashboard --start harness`"))

    app = DossierApp(session_factory=lambda: no_close(test_session),
                     initial_tab="tab-threads")
    async with app.run_test(size=(160, 50)) as pilot:
        await pilot.pause()
        with_one_row(app)
        await pilot.pause()
        app.query_one("#btn-read-thread").press()
        # Wait for the transcript, not just the screen: `push_screen` returns
        # before `compose` has mounted anything, so a loop that stops at
        # `isinstance(..., ChatScreen)` can query an empty screen. It passed on
        # the reachable cases by timing alone.
        for _ in range(40):
            if isinstance(app.screen, ChatScreen) and app.screen.query("#chat-body"):
                break
            await pilot.pause(0.05)
        opened = isinstance(app.screen, ChatScreen)
        shown = str(app.screen.query_one("#chat-body", Static).render()) if opened else ""

    assert opened
    assert "nothing is answering" in shown
    assert "dashboard --start harness" in shown
    assert "would look like an answer" in shown


@pytest.mark.asyncio
async def test_a_row_with_no_address_is_refused_with_a_reason(
        test_session, monkeypatch, no_close):
    """A harness older than the delta fields sends no address, and the facet
    draws `--`. Looking that up would ask the archive for a thread called `--`
    and blame the archive for the 404."""
    asked: list[str] = []
    monkeypatch.setattr(threads, "locate",
                        lambda name, **kw: asked.append(name) or None)

    app = DossierApp(session_factory=lambda: no_close(test_session),
                     initial_tab="tab-threads")
    async with app.run_test(size=(160, 50)) as pilot:
        await pilot.pause()
        with_one_row(app, address="--")
        await pilot.pause()
        app.query_one("#btn-read-thread").press()
        await pilot.pause(0.2)
        still_here = not isinstance(app.screen, ChatScreen)

    assert asked == [], "it looked up a row that carries no address"
    assert still_here


@pytest.mark.asyncio
async def test_an_empty_table_is_refused_before_any_lookup(
        test_session, monkeypatch, no_close):
    """Nothing selected is not a failure; it is nothing selected."""
    asked: list[str] = []
    monkeypatch.setattr(threads, "locate",
                        lambda name, **kw: asked.append(name) or None)

    app = DossierApp(session_factory=lambda: no_close(test_session),
                     initial_tab="tab-threads")
    async with app.run_test(size=(160, 50)) as pilot:
        await pilot.pause()
        table = app.query_one("#threads-table", DataTable)
        table.clear(columns=True)
        await pilot.pause()
        app.query_one("#btn-read-thread").press()
        await pilot.pause(0.2)

    assert asked == []


@pytest.mark.asyncio
async def test_escape_closes_the_conversation(test_session, no_close):
    """`escape` closes whatever is open. It is a convention, not an action of
    this screen, and `actions.CONVENTIONS` says so once for all screens."""
    app = DossierApp(session_factory=lambda: no_close(test_session))
    async with app.run_test(size=(160, 50)) as pilot:
        await pilot.pause()
        conversation = a_conversation()
        app.push_screen(ChatScreen(conversation, chat.draw(conversation)))
        await pilot.pause()
        assert isinstance(app.screen, ChatScreen)
        await pilot.press("escape")
        await pilot.pause()
        closed = not isinstance(app.screen, ChatScreen)

    assert closed


@pytest.mark.asyncio
async def test_the_screen_names_what_it_cannot_carry(test_session, no_close):
    """A reader comparing this with the original conversation needs to know
    which channels are missing, not to discover it by the two disagreeing."""
    app = DossierApp(session_factory=lambda: no_close(test_session))
    async with app.run_test(size=(160, 50)) as pilot:
        await pilot.pause()
        conversation = a_conversation()
        app.push_screen(ChatScreen(conversation, chat.draw(conversation)))
        await pilot.pause()
        note = str(app.screen.query_one("#chat-note", Static).render())

    assert "cannot carry" in note
    assert "attachments" in note


def test_the_screen_offers_no_way_to_save_the_transcript():
    """**THE ARCHIVE MUST NOT BE PUBLISHED.** A Save button here would be that
    decision made in passing, arriving as a one-line change nobody read twice.

    **DOCSTRINGS ARE STRIPPED BEFORE SCANNING.** The first version of this test
    searched the raw source and failed on `ChatScreen`'s own docstring, which
    says a Save button would be a decision -- a text scan matching the prose
    that forbids the thing. `records/DRAFT-decision-record-discipline.md` names
    that exact false reading, and it was made again here.

    Mutation: add a save or export button to `ChatScreen` and this fails.
    """
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(ChatScreen))
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                             ast.AsyncFunctionDef)):
            body = node.body
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                node.body = body[1:] or [ast.Pass()]

    code = ast.unparse(tree).lower()
    for word in ("save", "export", "download", "write_text", "open("):
        assert word not in code, (
            f"ChatScreen's code mentions {word!r}. Writing a transcript out is "
            f"a decision about publishing personal material, not a convenience.")
