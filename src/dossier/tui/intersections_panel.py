"""The Components tab: what this project touches, and what touches it.

The tab held a table of hand-entered links and three buttons. Those stay -- a
declared link carries an intent nothing else here does -- and above them now
sits what can be observed: the corpus this project pins, the packages it shares,
and the people who work on both sides.

It renders through `overview_panel._section`, so an intersection table and an
org table are the same shape on screen. A reader learns one table, not two.
"""

from __future__ import annotations

from rich.console import Group
from rich.text import Text
from textual.containers import VerticalScroll
from textual.widgets import Static

from dossier.intersections import build
from dossier.rad.tokens import DEFAULT_THEME, roles
from dossier.tui.overview_panel import _section


class IntersectionsPanel(VerticalScroll):
    """Intersections for the selected project. Redrawn when it changes."""

    def __init__(self, session_factory, theme: str = DEFAULT_THEME, **kwargs) -> None:
        super().__init__(**kwargs)
        self.session_factory = session_factory
        self.theme_name = theme
        self._body = Static(id="intersections-body")
        self.project_name: str | None = None

    def compose(self):
        yield self._body

    def show_for(self, project) -> None:
        """Draw the intersections for `project`, or a prompt when there is none."""
        role = roles(self.theme_name)
        if project is None:
            self.project_name = None
            self._body.update(Text(
                "Select a project to see what it intersects with.",
                style=f"dim {role.hint}"))
            return

        self.project_name = project.get_full_name()
        with self.session_factory() as session:
            sections = build(session, project)

        header = Text.assemble(
            (self.project_name, f"bold {role.wedge_label_selected}"),
            ("   intersections", f"dim {role.hint}"),
        )
        body = [header, Text("")]
        body.extend(_section(section, self.theme_name) for section in sections)
        body.append(Text(
            "An integration nobody declared is invisible here: two services that talk "
            "over HTTP share no package and no submodule. An empty section is not "
            "evidence of independence.",
            style=f"dim {role.hint}"))
        self._body.update(Group(*body))
