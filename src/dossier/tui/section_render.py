"""Draw a `Section` as a Rich renderable.

Used where a section is read rather than navigated -- the intersections panel.
The overview draws its sections as `DataTable`s instead, because there a row is
a link to the tab holding its detail, and a Rich table has no selection.

Both take the same `Section`, so the two surfaces cannot disagree about what a
column is called.
"""

from __future__ import annotations

from typing import Any

from rich.console import Group
from rich.table import Table
from rich.text import Text

from dossier.overview import Section
from dossier.rad.tokens import DEFAULT_THEME, roles

_LEAD_COLUMN_WIDTH = 30


def render_section(section: Section, theme: str = DEFAULT_THEME) -> Group:
    role = roles(theme)
    table = Table(box=None, pad_edge=False, padding=(0, 2),
                  header_style=f"bold {role.hub_stroke}", expand=False)
    for index, header in enumerate(section.headers):
        table.add_column(
            header,
            overflow="ellipsis",
            max_width=_LEAD_COLUMN_WIDTH if index == 0 else None,
            style=role.wedge_label_selected if index == 0 else role.wedge_label,
        )
    for row in section.rows:
        table.add_row(*row)

    parts: list[Any] = [Text(section.title.upper(), style=f"bold {role.focus_ring}"),
                        table]
    if section.is_empty:
        parts.insert(1, Text("  nothing recorded yet", style=f"dim {role.hint}"))
    if section.note:
        parts.append(Text(section.note, style=f"dim {role.hint}"))
    parts.append(Text(""))
    return Group(*parts)
