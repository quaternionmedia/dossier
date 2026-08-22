"""The Topology tab, and the class of defect that shipped with it.

**A CALL TO A METHOD THAT DOES NOT EXIST PARSES.** The tab shipped calling
`self._progress_done(...)`; the method is `_progress_finish`. Every static check
passed — the file compiled, imports resolved, the suite was green — and the tab
raised `AttributeError` the first time a person opened it. A compile check
cannot catch this, and neither can any test that never runs the code.

So this file has two halves, and the second is the more valuable:

1. **The tab works** — it draws, it reports an unreachable harness as a
   sentence, and it never draws an empty topology.
2. **Every `self._method(...)` in the application resolves.** One cheap static
   sweep over the whole panel, which would have caught `_progress_done` the
   moment it was written and catches the next one for free.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from dossier import threads

APP = Path(__file__).resolve().parents[2] / "src" / "dossier" / "tui" / "app.py"


# --- the class of defect ------------------------------------------------------


def test_every_self_call_names_a_method_that_exists():
    """THE ONE THAT MATTERS, AND IT IS NOT ABOUT TOPOLOGY.

    `self._progress_done(...)` was written where `_progress_finish` exists. It
    compiled, imported, and passed every test, because nothing ran that line.

    This reads the panel's own source: every `self._x(` must be a name the class
    defines, or inherits from Textual's `App`. It is a floor, not a type
    checker — it says the name exists, not that the arguments match.

    Mutation: rename any method without updating a call site and this fails.
    """
    source = APP.read_text(encoding="utf-8")

    # **ANY INDENTATION.** The first version matched definitions at exactly
    # four spaces and reported `_auto_save` missing -- it is defined at twelve,
    # inside a class inside a function. A checker that reports a false positive
    # on its first run gets switched off, which is worse than not having it.
    defined = set(re.findall(r"^\s+(?:async\s+)?def\s+(\w+)", source, re.M))
    # Names the class gets from elsewhere: Textual's App and its mixins, plus
    # anything assigned as an attribute rather than defined as a method.
    from textual.app import App

    inherited = {name for name in dir(App)}
    assigned = set(re.findall(r"^\s{4,}self\.(\w+)\s*=", source, re.M))
    known = defined | inherited | assigned

    called = set(re.findall(r"self\.(_\w+)\(", source))
    missing = sorted(name for name in called if name not in known)

    assert not missing, (
        f"these are called on self and defined nowhere: {missing}. "
        f"A call to a method that does not exist parses, imports, and raises "
        f"only when somebody runs that line."
    )


def test_every_button_handler_names_a_button_that_exists():
    """A handler bound to an id nothing yields never fires, and nothing says so
    — the button is simply dead.

    Mutation: bind a handler to `#btn-nothing` and this fails.
    """
    source = APP.read_text(encoding="utf-8")
    bound = set(re.findall(r'@on\(Button\.Pressed,\s*"#([\w-]+)"', source))
    yielded = set(re.findall(r'Button\([^)]*id="([\w-]+)"', source, re.S))
    orphans = sorted(bound - yielded)
    assert not orphans, f"handlers bound to buttons nothing yields: {orphans}"


# --- the tab itself -----------------------------------------------------------


@pytest.mark.asyncio
async def test_an_unreachable_harness_is_a_sentence_and_draws_nothing(
        session, monkeypatch):
    """**AN EMPTY DRAWING WOULD LOOK LIKE AN ANSWER.** The harness is a separate
    process on a separate port and is very often not running; that must produce
    the problem, the command that fixes it, and no topology at all.

    Mutation: draw the canvas anyway and this fails.
    """
    from dossier.tui.app import DossierApp
    from textual.widgets import Static

    monkeypatch.setattr(threads, "topology", lambda **kw: threads.Topology(
        False, "http://127.0.0.1:3141/v1/topology/shape/delegation",
        problem="nothing is answering at http://127.0.0.1:3141",
        remedy="`uv run qm dashboard --start harness`"))

    app = DossierApp(session_factory=lambda: _NoClose(session),
                     initial_tab="tab-topology")
    async with app.run_test(size=(160, 50)) as pilot:
        await pilot.pause()
        # The worker is a thread; give it a moment to come back.
        for _ in range(40):
            drawing = str(app.query_one("#topology-drawing", Static).render())
            if drawing:
                break
            await pilot.pause(0.05)
        note = str(app.query_one("#topology-note", Static).render())

    assert "nothing is answering" in drawing
    assert "qm dashboard --start harness" in drawing
    assert "would look like an answer" in drawing
    assert "-?>" not in drawing and "-->" not in drawing
    assert note == ""


@pytest.mark.asyncio
async def test_a_topology_is_drawn_with_its_caveat(session, monkeypatch):
    """The drawing and the sentence that must be read before believing it.

    Mutation: stop reporting how much was measured and this fails.
    """
    from dossier.tui.app import DossierApp
    from textual.widgets import Static

    monkeypatch.setattr(threads, "topology", lambda **kw: threads.Topology(
        True, "fixture", payload=_payload(), source="topology"))

    app = DossierApp(session_factory=lambda: _NoClose(session),
                     initial_tab="tab-topology")
    async with app.run_test(size=(160, 50)) as pilot:
        await pilot.pause()
        for _ in range(40):
            caveat = str(app.query_one("#topology-caveat", Static).render())
            if caveat:
                break
            await pilot.pause(0.05)
        drawing = str(app.query_one("#topology-drawing", Static).render())

    assert "1 of 2 edge(s) measured" in caveat
    assert "-?>" in drawing, "the unmeasured glyph never reached the screen"


@pytest.mark.asyncio
async def test_the_tab_does_not_wait_for_a_project(session, monkeypatch):
    """A topology is the organisation's, not one repository's. Sweep and
    Threads are unscoped for the same reason, and a tab that sat blank until
    somebody chose a project would look broken."""
    from dossier.tui.app import DossierApp
    from textual.widgets import Static

    monkeypatch.setattr(threads, "topology", lambda **kw: threads.Topology(
        True, "fixture", payload=_payload(), source="topology"))

    app = DossierApp(session_factory=lambda: _NoClose(session),
                     initial_tab="tab-topology")
    async with app.run_test(size=(160, 50)) as pilot:
        await pilot.pause()
        assert app.selected_project is None
        for _ in range(40):
            drawing = str(app.query_one("#topology-drawing", Static).render())
            if drawing:
                break
            await pilot.pause(0.05)

    assert drawing.strip(), "nothing was drawn without a project chosen"


# --- helpers ------------------------------------------------------------------


@pytest.fixture()
def session():
    """An empty database. These tests are about the tab, not about projects —
    the topology is the organisation's and does not read this."""
    from sqlmodel import Session, SQLModel, create_engine

    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def _payload() -> dict:
    return {
        "topology": "delegation", "level": 2, "caption": "one per repository",
        "status": "runs", "marks": [],
        "boxes": [
            {"id": "subject", "label": "work", "kind": "input",
             "note": "", "count": None},
            {"id": "r0", "label": "worker", "kind": "worker",
             "note": "qm/dossier", "count": None},
        ],
        "arrows": [
            {"from": "subject", "to": "r0", "label": "part-of", "kind": "flow",
             "weight": 0.9, "basis": "mentions"},
            {"from": "subject", "to": "r0", "label": "crosses", "kind": "flow",
             "weight": None, "basis": ""},
        ],
    }


class _NoClose:
    """A session the app cannot close out from under the test."""

    def __init__(self, session):
        self._session = session

    def __enter__(self):
        return self._session

    def __exit__(self, *exc):
        return False
