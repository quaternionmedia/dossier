#!/usr/bin/env python3
"""Local demo: the dossier TUI, driven headlessly and then live.

    uv run python examples/demo_tui.py            # headless, prints a transcript
    uv run python examples/demo_tui.py --live     # the real dashboard, for a human

WHAT IT SHOWS. A seeded database, the dashboard opening on it, the projects it
lists, and three interactions driven by keypress -- help, search, and add --
each confirmed by what the screen actually contains afterwards rather than by
the keypress having been sent.

WHY HEADLESS IS THE DEFAULT. Textual's `run_test` drives the real application
through a `Pilot`: the same widgets, the same bindings, the same compose. It is
the only form of this demo that a test can run, and a demo nothing runs is the
defect this corpus keeps finding. `--live` exists because a dashboard is a thing
somebody should look at, and neither mode is a substitute for the other.

WHY IT BUILDS ITS OWN DATABASE. `dossier.cli` sets
`DATABASE_URL = "sqlite:///dossier.db"` at module import, relative to the
working directory -- so whichever directory you launch from is the database you
edit. The demo points that at a temporary file and puts it back, because a demo
that writes rows into the operator's dossier is one nobody runs twice.

WHAT IT CANNOT SHOW. Anything requiring the network: no GitHub sync, no repository
scan, no live issue or pull-request data. The seeded rows are fixtures written by
this file, and a project row here is not evidence that syncing works.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SEED = [
    {"full_name": "quaternionmedia/qm", "name": "qm", "owner": "quaternionmedia",
     "description": "The QM constitution: the org-level decision corpus.",
     "language": "Python", "stars": 3},
    {"full_name": "quaternionmedia/dossier", "name": "dossier", "owner": "quaternionmedia",
     "description": "Project documentation and change management.",
     "language": "Python", "stars": 2},
    {"full_name": "quaternionmedia/qmcp", "name": "qmcp", "owner": "quaternionmedia",
     "description": "Agent harness: MCP tools with an audit log.",
     "language": "Python", "stars": 1},
]


@contextmanager
def scratch_database() -> Iterator[Path]:
    """Point `dossier.cli`'s module-level engine at a temporary file.

    The engine is replaced rather than the environment adjusted: it is built at
    import time from a hardcoded relative URL, so by the time this runs there is
    no environment left to influence. `dossier/tui/app.py` imports `get_session`
    and `init_db` from `dossier.cli` lazily inside the method that uses them,
    which is why patching the module attributes reaches the running app.
    """
    from sqlmodel import Session, SQLModel, create_engine

    import dossier.cli as cli

    directory = Path(tempfile.mkdtemp(prefix="dossier-demo-"))
    database = directory / "demo.db"
    engine = create_engine(f"sqlite:///{database.as_posix()}", echo=False)
    SQLModel.metadata.create_all(engine)

    real_engine, real_session, real_url = cli.engine, cli.get_session, cli.DATABASE_URL
    cli.engine = engine
    cli.DATABASE_URL = f"sqlite:///{database.as_posix()}"
    cli.get_session = lambda: Session(engine)

    try:
        seed(cli.get_session)
        yield database
    finally:
        cli.engine, cli.get_session, cli.DATABASE_URL = real_engine, real_session, real_url
        engine.dispose()
        database.unlink(missing_ok=True)
        for leftover in directory.glob("*"):
            leftover.unlink(missing_ok=True)
        directory.rmdir()


def seed(session_factory: Any) -> None:
    from dossier.models import Project

    now = datetime.now(timezone.utc)
    with session_factory() as session:
        for row in SEED:
            session.add(Project(**row, created_at=now, updated_at=now))
        session.commit()


def printable(text: str) -> str:
    """Text this console can actually encode.

    The tree labels carry emoji -- a folder glyph on every owner node -- and a
    Windows console runs cp1252, where printing one raises UnicodeEncodeError
    and takes the demo down three lines before its point. The findings keep the
    real labels; only the transcript is degraded, and it says so by leaving the
    replacement character visible rather than silently dropping the glyph.
    """
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    return text.encode(encoding, errors="replace").decode(encoding, errors="replace")


def listed_projects(app: Any) -> list[str]:
    """The project labels the dashboard is actually showing.

    Read from `#project-tree`'s nodes, because that is where `load_projects`
    puts them. Scraping widget text finds nothing here and looks exactly like a
    seed that failed: a Tree's nodes are not widgets, so walking the widget tree
    cannot see one. That was this demo's first reading, and it reported `[]`
    against a database with three rows in it.
    """
    from textual.widgets import Tree

    tree = app.query_one("#project-tree", Tree)
    labels: list[str] = []

    def walk(node: Any) -> None:
        for child in node.children:
            labels.append(str(child.label))
            walk(child)

    walk(tree.root)
    return labels


async def drive() -> dict[str, Any]:
    """Open the dashboard on a seeded database and interact with it.

    The transcript is collected and returned rather than printed. A running
    Textual app replaces `sys.stdout` with its own writer, so a `print` from
    inside reaches the console through Textual -- which is why the first
    version of this demo died on an emoji even after being given an encoding
    guard: the guard measured Textual's stream, not the terminal.
    """
    from dossier.tui import DossierApp

    findings: dict[str, Any] = {}
    transcript: list[str] = []
    out = transcript.append
    findings["transcript"] = transcript

    with scratch_database() as database:
        out(f"database         {database.name} (temporary, {len(SEED)} project(s) seeded)")
        app = DossierApp()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()

            findings["title"] = str(app.title)
            out(f"app title        {findings['title']}")

            shown = listed_projects(app)
            listed = [row["name"] for row in SEED
                      if any(row["name"] in label for label in shown)]
            findings["tree_labels"] = shown
            findings["projects_visible"] = listed
            out(f"tree nodes       {shown}")
            out(f"seeded projects  {listed}")

            bindings = [b.key for b in app.BINDINGS]
            findings["bindings"] = bindings
            out(f"key bindings     {bindings}")

            await pilot.press("?")
            await pilot.pause()
            findings["help_screen"] = type(app.screen).__name__
            out(f"pressed ?        screen is now {findings['help_screen']}")
            await pilot.press("escape")
            await pilot.pause()

            await pilot.press("a")
            await pilot.pause()
            findings["add_screen"] = type(app.screen).__name__
            out(f"pressed a        screen is now {findings['add_screen']}")
            await pilot.press("escape")
            await pilot.pause()

            await pilot.press("/")
            await pilot.pause()
            focused = app.focused
            findings["search_focus"] = type(focused).__name__ if focused else None
            out(f"pressed /        focus is now {findings['search_focus']}")

            findings["closed_cleanly"] = True
    return findings


def run(out=print) -> dict[str, Any]:
    """Drive the app, then print. Printing happens after `run_test` exits, on
    the real console rather than through Textual's stdout replacement."""
    findings = asyncio.run(drive())
    for line in findings["transcript"]:
        out(printable(line))
    return findings


def live() -> int:
    """The real dashboard, on the same seeded scratch database."""
    from dossier.tui import DossierApp

    with scratch_database() as database:
        print(f"Seeded {len(SEED)} project(s) into {database}. Press q to quit.")
        DossierApp().run()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--live", action="store_true",
                        help="run the real dashboard instead of driving it headlessly")
    args = parser.parse_args(argv)

    if args.live:
        return live()

    findings = run()
    print()
    print(f"{len(findings['projects_visible'])} of {len(SEED)} seeded projects "
          f"appeared on the dashboard.")
    print("Every line above is what the widget tree actually held after the "
          "keypress, not that the keypress was sent.")
    return 0 if findings["projects_visible"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
