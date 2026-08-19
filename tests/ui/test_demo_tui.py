"""The local TUI demo runs, and it shows what it claims to show.

WHY A DEMO NEEDS A TEST. A dashboard demonstrated once in a session is a claim
nobody can re-derive. These tests drive the same module the operator runs, so
the suite covers the demo and a change that empties the dashboard is caught here
rather than by someone opening it.

WHY THE ASSERTIONS ARE ABOUT THE TREE AND NOT THE SCREEN TEXT. Projects live in
`#project-tree`, and a Tree's nodes are not widgets -- walking the widget tree
finds nothing and looks exactly like a database that failed to seed. The demo's
first reading reported zero projects against three committed rows for that
reason, so the test asserts on the nodes.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from examples.demo_tui import SEED, drive, main, printable  # noqa: E402


@pytest.fixture(scope="module")
def findings():
    """One drive, shared. Each run boots a full Textual app; three seconds of
    setup per assertion would make the suite slower than the thing it covers."""
    import asyncio

    return asyncio.run(drive())


def test_every_seeded_project_reaches_the_dashboard(findings):
    assert findings["projects_visible"] == [row["name"] for row in SEED]


def test_the_tree_is_not_empty(findings):
    """The assertion the first version of this demo could not make."""
    assert findings["tree_labels"]


def test_the_help_key_opens_the_help_screen(findings):
    assert findings["help_screen"] == "HelpScreen"


def test_the_add_key_opens_the_add_modal(findings):
    assert findings["add_screen"] == "AddProjectModal"


def test_the_search_key_moves_focus_to_an_input(findings):
    assert findings["search_focus"] == "Input"


def test_the_app_closed_without_raising(findings):
    assert findings["closed_cleanly"] is True


def test_the_transcript_records_each_step(findings):
    printed = "\n".join(findings["transcript"])
    for expected in ("database", "app title", "tree nodes", "key bindings",
                     "pressed ?", "pressed a", "pressed /"):
        assert expected in printed


def test_the_demo_leaves_no_database_behind():
    """`dossier.cli.DATABASE_URL` is relative to the working directory, so a
    demo that did not clean up would leave a `dossier.db` wherever it ran."""
    import dossier.cli as cli

    before = cli.DATABASE_URL
    working = _REPO_ROOT / "dossier.db"
    stamp = working.stat().st_mtime if working.is_file() else None

    main([])

    assert cli.DATABASE_URL == before, "the module engine was not put back"
    after = working.stat().st_mtime if working.is_file() else None
    assert stamp == after, "the demo wrote to the working database"


def test_the_transcript_survives_a_console_that_cannot_encode_emoji():
    """The tree labels carry a folder glyph and a Windows console is cp1252.
    Printing one raised UnicodeEncodeError and took the demo down."""
    assert printable("folder \U0001f4c1 node")


def test_the_demo_exits_zero():
    assert main([]) == 0
