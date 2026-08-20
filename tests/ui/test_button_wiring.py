"""Every button reaches a handler that can actually be called.

THIS EXISTS BECAUSE A GREP SAID IT WAS FINE. A one-off search for
`@on(Button.Pressed, "#id")` found a decorator for every composed button and
reported nothing unwired. It was searching the file, and a Textual message does
not travel by file: `Button.Pressed` goes up the widget tree it was pressed in,
so a handler on an unrelated class is never on that path.

The Ingest button in the Threads tab was composed by `DossierApp` and handled
on `ContentViewerScreen`, a modal document viewer. A person could type the path
to an export, press Ingest, and have nothing at all happen -- which is what
somebody reported, having tried it.

So this reads the classes, not the file. It is a static check on purpose: the
alternative is clicking twenty-eight buttons in a running app, most of which
open modals or reach the network.
"""

from __future__ import annotations

import ast
import collections
import pathlib

import pytest

SOURCE = pathlib.Path("src/dossier/tui/app.py")


def _walk_class(node: ast.ClassDef):
    """Everything lexically inside one class, including nested functions."""
    for child in ast.iter_child_nodes(node):
        if isinstance(child, ast.ClassDef):
            continue          # a nested class owns its own buttons
        yield from ast.walk(child)


def _survey():
    """(composed, handled, generic) keyed by class name."""
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    composed = collections.defaultdict(set)
    handled = collections.defaultdict(set)
    generic = set()

    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        for sub in _walk_class(node):
            if isinstance(sub, ast.Call) and getattr(sub.func, "id", "") == "Button":
                for keyword in sub.keywords:
                    if keyword.arg == "id" and isinstance(keyword.value, ast.Constant):
                        composed[node.name].add(keyword.value.value)
            if isinstance(sub, ast.FunctionDef):
                if sub.name == "on_button_pressed":
                    generic.add(node.name)
                for decorator in sub.decorator_list:
                    if (isinstance(decorator, ast.Call)
                            and getattr(decorator.func, "id", "") == "on"
                            and len(decorator.args) >= 2
                            and isinstance(decorator.args[1], ast.Constant)):
                        handled[node.name].add(decorator.args[1].value.lstrip("#"))
    return composed, handled, generic


def test_every_button_is_handled_by_the_class_that_composes_it():
    """THE ONE THAT MATTERS.

    Mutation: move any `@on(Button.Pressed, ...)` to another class in this file
    and this fails. The grep it replaces would not have noticed.
    """
    composed, handled, generic = _survey()
    assert composed, "no buttons were found at all, so this asserts nothing"

    orphans = []
    for owner, ids in composed.items():
        if owner in generic:
            continue          # a catch-all handler covers every id it composes
        for button in sorted(ids - handled[owner]):
            elsewhere = sorted(c for c, sels in handled.items() if button in sels)
            orphans.append(
                f"#{button} is composed by {owner} but handled by "
                f"{elsewhere or 'nobody'}")
    assert not orphans, "\n".join(orphans)


def test_the_ingest_button_is_handled_where_it_lives():
    """Named, because it is the one that was wrong and the one a person hit.

    The general rule above would catch it again; this says which button, so a
    failure here reads as "the export path field stopped working" rather than
    as an abstract wiring violation.
    """
    composed, handled, _ = _survey()
    assert "btn-ingest-threads" in composed["DossierApp"]
    assert "btn-ingest-threads" in handled["DossierApp"]


def test_no_handler_names_a_button_that_is_not_composed():
    """The other direction: a selector nothing composes is a handler that can
    never run, and it is what makes a wiring count look complete.

    Mutation: rename a button's id and leave its handler alone -- this fails,
    and so does the test above.
    """
    composed, handled, _ = _survey()
    every_button = set().union(*composed.values())
    dangling = []
    for owner, selectors in handled.items():
        for selector in sorted(selectors):
            # Handlers also watch inputs and other widgets by id; only complain
            # about a selector that looks like one of this app's buttons.
            if selector.startswith("btn-") and selector not in every_button:
                dangling.append(f"{owner} handles #{selector}, which nothing composes")
    assert not dangling, "\n".join(dangling)


@pytest.mark.asyncio
async def test_pressing_ingest_actually_reaches_the_ingest_code():
    """The static check proves the handler is on the right class. This proves a
    press arrives, which is the thing that was broken.

    Nothing reaches the harness: `request_import` is replaced, and what is
    asserted is that it was called with what the field held.
    """
    from sqlmodel import Session, SQLModel, create_engine
    from textual.widgets import Input

    from dossier.tui import DossierApp

    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    app = DossierApp(session_factory=lambda: Session(engine))

    asked = []
    async with app.run_test(size=(140, 45)) as pilot:
        await pilot.pause()
        import dossier.threads as threads_module

        threads_module.request_import = (
            lambda path, *a, **k: asked.append(path) or {"ok": False, "error": "stub"})

        app.query_one("#project-tabs").active = "tab-threads"
        await pilot.pause()
        app.query_one("#thread-export-path", Input).value = "some/export/path"
        await pilot.pause()

        await pilot.click("#btn-ingest-threads")
        await pilot.pause()
        await pilot.pause()

    assert asked == ["some/export/path"], (
        "the press did not reach the ingest code")


# --- wired is not the same as reachable ---------------------------------------


@pytest.mark.parametrize("size", [(80, 30), (100, 35), (140, 45)])
@pytest.mark.asyncio
async def test_the_ingest_button_is_on_the_screen(size):
    """A HANDLER ON THE RIGHT CLASS IS NOT ENOUGH IF NOBODY CAN PRESS IT.

    The ingest row had no stylesheet, so the `Input` beside the button took the
    full width of the container and pushed the button past the right edge. At
    140 columns its region began at x=138, leaving two columns showing; at 80
    it was not on the screen at all. Typing a path and having nowhere to press
    is indistinguishable, from the outside, from the handler being missing --
    and both were true here at once.

    Every declared size, because the failure is a function of width and passing
    at one width says nothing about another.

    Mutation: drop `#thread-export-path { width: 1fr }` and this fails.
    """
    from sqlmodel import Session, SQLModel, create_engine
    from textual.widgets import Button

    from dossier.tui import DossierApp

    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    app = DossierApp(session_factory=lambda: Session(engine))

    async with app.run_test(size=size) as pilot:
        await pilot.pause()
        app.query_one("#project-tabs").active = "tab-threads"
        await pilot.pause()
        await pilot.pause()

        button = app.query_one("#btn-ingest-threads", Button)
        region, screen = button.region, app.screen.size
        assert region.width > 0, "the button was given no width"
        assert region.right <= screen.width, (
            f"the button runs to x={region.right} on a {screen.width}-column "
            f"screen: {screen.width - region.right} columns off the edge")
        assert region.bottom <= screen.height, (
            f"the button runs to y={region.bottom} on a {screen.height}-row screen")


@pytest.mark.asyncio
async def test_enter_in_the_path_field_ingests_without_the_button():
    """The keyboard route has to end somewhere. `4.6` focuses this field, and a
    field only a mouse can submit would make that route one key short of
    useful.

    Mutation: drop the `Input.Submitted` handler and this fails.
    """
    from sqlmodel import Session, SQLModel, create_engine
    from textual.widgets import Input

    from dossier.tui import DossierApp

    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    app = DossierApp(session_factory=lambda: Session(engine))

    asked = []
    async with app.run_test(size=(100, 35)) as pilot:
        await pilot.pause()
        import dossier.threads as threads_module

        threads_module.request_import = (
            lambda path, *a, **k: asked.append(path) or {"ok": False, "error": "stub"})

        app.query_one("#project-tabs").active = "tab-threads"
        await pilot.pause()
        field = app.query_one("#thread-export-path", Input)
        field.focus()
        field.value = "typed/by/hand"
        await pilot.pause()

        await pilot.press("enter")
        await pilot.pause()
        await pilot.pause()

    assert asked == ["typed/by/hand"]
