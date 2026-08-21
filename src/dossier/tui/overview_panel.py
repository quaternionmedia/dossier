"""The org overview: the same facts the tabs hold, read across every repository.

WHY THE SECTIONS ARE TABLES AND NOT A PICTURE. Each one comes from a facet in
`dossier.facets`, and that facet also fills a tab. Rendering the section as a
`DataTable` means a row can be selected, and selecting it opens the tab holding
that row's detail -- the vertical axis of the screen and the horizontal one are
then the same data with a route between them, rather than two readings that
happen to agree.

Sections with no facet -- governance posture, the phase board, what wants
attention -- exist only at org scope and are drawn the same way. Selecting one
of their rows does nothing, which is honest: there is no per-repository tab
that holds a phase board.

COLOURS COME FROM RAD'S TOKENS. Nothing here names a colour; it asks
`dossier.rad.tokens` for its default, and the section renderer used by the
intersections panel asks it for roles.
"""

from __future__ import annotations

from textual.containers import VerticalScroll
from textual.widgets import DataTable, Static

from dossier.facets import BY_TITLE as FACET_BY_TITLE
from dossier.overview import OrgOverview, Section, build, dominant_owner
# Through `dossier.palette` -- see the note in that module on why
# rad's menu is optional and rad's palette had accidentally not been.
from dossier.palette import DEFAULT_THEME

# The column a row's repository is found in, when it has one. Facets put the
# repository first by convention; a section whose first column is not a repo
# declares so by not appearing here.
REPO_FIRST = {"repo"}


class OverviewPanel(VerticalScroll):
    """Reads on mount and on demand, never on a timer.

    A timer would re-query behind a reader part way down the page, and every
    figure is `as last synced` regardless -- so an unasked-for refresh buys
    nothing and moves the page under them.
    """

    def __init__(self, session_factory, theme: str = DEFAULT_THEME,
                 owner: str | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self.session_factory = session_factory
        self.theme_name = theme
        self.owner = owner
        self.overview: OrgOverview | None = None

    # -- content ----------------------------------------------------------

    def compose(self):
        # Read here rather than in `on_mount`: compose runs first, so a panel
        # that waited for mount would draw an empty page and fill it a frame
        # later -- which is what a reader sees, and what a test sees too.
        if self.overview is None:
            self.overview = self._read()

        yield Static(
            f"[bold]{self.overview.scope}[/bold]   [dim]{self.overview.generated_from}[/dim]",
            id="overview-scope",
        )
        yield Static(self._masthead_markup(), id="overview-masthead")

        for index, section in enumerate(self.overview.sections):
            linked = section.title in FACET_BY_TITLE
            suffix = "   [dim](select a row to open it)[/dim]" if linked else ""
            yield Static(f"[bold]{section.title.upper()}[/bold]{suffix}",
                         classes="overview-heading")
            table = DataTable(id=f"overview-section-{index}", zebra_stripes=False,
                              classes="overview-section")
            table.cursor_type = "row"
            # Filled before yielding: the rows are known now, and populating on
            # mount means one frame of an empty table for every section.
            table.add_columns(*section.headers)
            for row_index, row in enumerate(section.rows):
                table.add_row(*row, key=f"{index}:{row_index}")
            yield table
            if section.note:
                yield Static(f"[dim]{section.note}[/dim]", classes="overview-note")

    def on_mount(self) -> None:
        # After the refresh, not during mount: the stylesheet is applied on the
        # way through, and anything set before it is overwritten.
        self.call_after_refresh(self._let_the_page_be_the_only_scroll)

    def _let_the_page_be_the_only_scroll(self) -> None:
        """Give every section exactly the lines its rows need.

        A `DataTable` is itself a scroll view, so `height: auto` clamps it to
        the space available rather than to its content: a section taller than
        the viewport gets its own scrollbar inside a page that already scrolls,
        and a reader scrolling the page moves past it without ever seeing its
        last rows -- text that is rendered, correct, and unreachable, with no
        cue that a second scroll region was there.

        This runs on mount rather than in `compose` because the stylesheet is
        applied at mount and overwrites anything set before it. Most sections
        take a top-N and never reach the viewport; `overview._governance` takes
        none, one row per roster entry, so it is the one that grows.

        `max_height` is set to the same figure, and that is the part that does
        the work: `ScrollView` carries `max-height: 100%`, so a stated height of
        forty-one lines was still being served twenty-seven. Assigning `None`
        does not help -- it clears the inline layer and re-exposes the `100%`
        underneath, which reads as having worked and does not. Both are stated,
        in lines, from the row count.
        """
        for table in self.query(DataTable):
            lines = table.row_count + (1 if table.show_header else 0)
            table.styles.height = lines
            table.styles.max_height = lines

    def _masthead_markup(self) -> str:
        cells = []
        for cell in self.overview.masthead:
            note = f"  [dim]{cell.note}[/dim]" if cell.note else ""
            cells.append(f"[bold]{cell.value}[/bold] {cell.label}{note}")
        return "\n".join(cells)

    def _read(self) -> OrgOverview:
        with self.session_factory() as session:
            if self.owner is None:
                # Local by default: whichever organisation this database is
                # about. Unscoped totals mix every owner ever synced, which
                # describes the database rather than anybody's work.
                self.owner = dominant_owner(session)
            return build(session, owner=self.owner)

    def set_owner(self, owner: str | None) -> None:
        """Scope to one owner and redraw. Unscoped when `owner` is None."""
        self.owner = owner
        self.refresh_overview()

    def refresh_overview(self) -> None:
        """Rebuild from the database. Safe to call from a binding or a button.

        `refresh(recompose=True)` and not `recompose()`: the latter is a
        coroutine, so calling it from a synchronous handler built the awaitable
        and dropped it. Python said so -- `RuntimeWarning: coroutine
        'Widget.recompose' was never awaited` -- and the tests did not, because
        they asserted `panel.owner` rather than what was drawn. Scoping to an
        owner changed the field and left the screen showing the org.
        """
        self.overview = self._read()
        if self.is_mounted:
            self.refresh(recompose=True)
            # A recompose builds new tables, so the heights are stated again.
            # Without this the redraw a reader asked for is the one that
            # reintroduces the inner scrollbars.
            self.call_after_refresh(self._let_the_page_be_the_only_scroll)

    # `role` is read per render rather than stored, so a theme change needs no
    # invalidation step here.

    # -- the link ---------------------------------------------------------

    def section_for(self, table_id: str) -> Section | None:
        if self.overview is None or not table_id.startswith("overview-section-"):
            return None
        index = int(table_id.rsplit("-", 1)[1])
        if index >= len(self.overview.sections):
            return None
        return self.overview.sections[index]

    def target_for(self, section: Section, row_key: str) -> tuple[str | None, str | None]:
        """The tab a row links to, and the repository it names, if any.

        Returns `(None, None)` for a section with no facet -- an org-only view
        has no per-repository tab to open, and inventing one would send a
        reader somewhere that does not answer their question.
        """
        facet = FACET_BY_TITLE.get(section.title)
        if facet is None:
            return None, None
        try:
            _, row_index = (int(part) for part in row_key.split(":"))
        except (ValueError, AttributeError):
            return facet.tab, None
        if row_index >= len(section.rows):
            return facet.tab, None
        row = section.rows[row_index]
        repo = row[0] if section.headers and section.headers[0] in REPO_FIRST else None
        return facet.tab, repo
