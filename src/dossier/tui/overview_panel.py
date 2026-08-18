"""The org overview, rendered.

This module turns `dossier.overview.OrgOverview` into Rich renderables and
nothing else. It holds no queries: what to count lives in `dossier.overview`,
which imports no Textual and can therefore be asked the same question by the
API, by a test, and eventually by the ring's `Show` verb.

DENSITY IS THE POINT, AND IT HAS A LIMIT. A reader opening this should see the
shape of the whole organisation without scrolling, and then find the detail by
scrolling. So the masthead is a wrapped grid of figures rather than a sentence,
and every section is a table. What density must not buy is a number without its
qualification -- each section carries the note its data needs, dimmed, directly
under the table, because a figure whose caveat is one screen away is a figure
that will be quoted without it.

COLOURS COME FROM RAD'S TOKENS. Nothing here names a colour. `dossier.rad.tokens`
holds the palette and role tiers read from rad, and this module asks for roles,
so a theme change is a palette swap rather than an edit here.
"""

from __future__ import annotations

from typing import Any

from rich.console import Group
from rich.table import Table
from rich.text import Text
from textual.containers import VerticalScroll
from textual.widgets import Static

from dossier.overview import Cell, OrgOverview, Section, build
from dossier.rad.tokens import DEFAULT_THEME, roles

# Sections whose first column is a name worth leaning on. Everything else reads
# as a figure, and a table where every column is bold is a table with no
# emphasis at all.
_LEAD_COLUMN_WIDTH = 30


def _masthead(cells: tuple[Cell, ...], theme: str) -> Table:
    """The figures, wrapped into columns rather than listed down the page."""
    role = roles(theme)
    grid = Table.grid(padding=(0, 3))
    for _ in range(4):
        grid.add_column(justify="left")

    entries = []
    for cell in cells:
        stacked = Table.grid()
        stacked.add_row(Text(cell.value, style=f"bold {role.wedge_label_selected}"))
        stacked.add_row(Text(cell.label, style=role.hub_stroke))
        if cell.note:
            stacked.add_row(Text(cell.note, style=f"dim {role.hint}"))
        entries.append(stacked)

    for start in range(0, len(entries), 4):
        row = entries[start:start + 4]
        row += [Text("")] * (4 - len(row))
        grid.add_row(*row)
    return grid


def _section(section: Section, theme: str) -> Group:
    role = roles(theme)
    table = Table(
        title=None,
        box=None,
        pad_edge=False,
        padding=(0, 2),
        header_style=f"bold {role.hub_stroke}",
        expand=False,
    )
    for index, header in enumerate(section.headers):
        table.add_column(
            header,
            overflow="ellipsis",
            max_width=_LEAD_COLUMN_WIDTH if index == 0 else None,
            style=role.wedge_label_selected if index == 0 else role.wedge_label,
        )
    for row in section.rows:
        table.add_row(*row)

    heading = Text(section.title.upper(), style=f"bold {role.focus_ring}")
    parts: list[Any] = [heading, table]
    if section.note:
        parts.append(Text(section.note, style=f"dim {role.hint}"))
    if section.is_empty:
        parts.insert(1, Text("  nothing recorded yet", style=f"dim {role.hint}"))
    parts.append(Text(""))
    return Group(*parts)


def render(overview: OrgOverview, theme: str = DEFAULT_THEME) -> Group:
    """One renderable for the whole overview, in the order `build` returned.

    The order is the module's, not this one's. A renderer that re-ordered the
    sections would be a second statement of what matters most.
    """
    role = roles(theme)
    header = Text.assemble(
        (overview.scope, f"bold {role.wedge_label_selected}"),
        ("   ", ""),
        (overview.generated_from, f"dim {role.hint}"),
    )
    body: list[Any] = [header, Text(""), _masthead(overview.masthead, theme), Text("")]
    body.extend(_section(section, theme) for section in overview.sections)
    return Group(*body)


class OverviewPanel(VerticalScroll):
    """The overview tab. Reads on mount and on demand, never on a timer.

    A timer here would re-query the database behind a reader who is part way
    down the page, and the figures are `as last synced` regardless -- so a
    refresh that the reader did not ask for buys nothing and moves the page
    under them.
    """

    def __init__(self, session_factory, theme: str = DEFAULT_THEME, **kwargs) -> None:
        super().__init__(**kwargs)
        self.session_factory = session_factory
        self.theme_name = theme
        self._body = Static(id="overview-body")
        self.overview: OrgOverview | None = None

    def compose(self):
        yield self._body

    def on_mount(self) -> None:
        self.refresh_overview()

    def refresh_overview(self) -> None:
        """Rebuild from the database. Safe to call from a binding or a button."""
        with self.session_factory() as session:
            self.overview = build(session)
        self._body.update(render(self.overview, self.theme_name))
