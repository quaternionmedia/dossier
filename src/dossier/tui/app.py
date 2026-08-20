"""Main Dossier TUI application."""

from datetime import datetime
from functools import lru_cache
from typing import Callable, Optional

from sqlmodel import Session, select, or_, and_
from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    ListItem,
    ListView,
    Markdown,
    MarkdownViewer,
    ProgressBar,
    Rule,
    Select,
    Static,
    TabbedContent,
    TabPane,
    Tree,
)

from dossier.models import (
    DeltaLink,
    DeltaNote,
    DeltaPhase,
    DocumentSection,
    DocumentationLevel,
    Project,
    ProjectBranch,
    ProjectComponent,
    ProjectContributor,
    ProjectDependency,
    ProjectDelta,
    ProjectIssue,
    ProjectLanguage,
    ProjectPullRequest,
    ProjectRelease,
    ProjectVersion,
)
from dossier.dossier_file import generate_dossier


# Constants for pagination and performance
PAGE_SIZE = 100  # Number of projects to load per page
DEBOUNCE_MS = 300  # Milliseconds to wait before filtering
TREE_ENTITY_LIMIT = 20  # Max entities to show per section in tree
# The tabs that exist at the top level. `tab-projects` used to be here: it came
# from a nested restructure that was rejected when the delta entity landed, and
# five references to it survived, pointing at a tab nothing composes. They were
# dormant until something took that path, and then failed as
# "No Tab with id '--content-tab-tab-projects'" -- nowhere near the cause.


def extract_file_path(source_file: str | None) -> str | None:
    """Extract the actual file path from a source_file string.
    
    source_file can be in formats like:
    - "github:owner/repo/path/to/file.md" -> "path/to/file.md"
    - "README.md" -> "README.md"
    - "docs/guide.md" -> "docs/guide.md"
    """
    if not source_file:
        return None
    
    # Handle github: prefix format
    if source_file.startswith("github:"):
        # Format: github:owner/repo/path/to/file
        # Remove "github:" prefix and skip owner/repo parts
        remainder = source_file[7:]  # Remove "github:"
        parts = remainder.split("/", 2)  # Split into [owner, repo, path]
        if len(parts) >= 3:
            return parts[2]  # Return just the file path
        return None
    
    return source_file


from dossier.facets import BY_TAB as FACET_BY_TAB, BY_TITLE as FACET_BY_TITLE
from dossier.tui.delta_board import DeltaBoard
from dossier.tui.intersections_panel import IntersectionsPanel

# The prefix `load_projects` puts on an owner group node.
ORG_GROUP_PREFIX = "🏢"
from dossier.tui.overview_panel import OverviewPanel


class ContentViewerScreen(ModalScreen):
    """Modal screen for viewing markdown content with navigation."""
    
    BINDINGS = [
        Binding("escape", "close", "Close"),
        Binding("q", "close", "Close"),
        Binding("o", "open_browser", "Open in Browser"),
        Binding("f", "open_frogmouth", "Open in Frogmouth"),
        Binding("n", "next_doc", "Next"),
        Binding("p", "prev_doc", "Previous"),
        Binding("j", "next_doc", "Next", show=False),
        Binding("k", "prev_doc", "Previous", show=False),
    ]
    
    CSS = """
    ContentViewerScreen {
        align: center middle;
    }
    
    #viewer-dialog {
        width: 90%;
        height: 90%;
        background: $surface;
        border: solid $primary;
    }
    
    #viewer-header {
        height: auto;
        padding: 1;
        background: $primary-darken-2;
    }
    
    #viewer-title {
        text-style: bold;
    }
    
    #viewer-content {
        height: 1fr;
        padding: 1;
        margin-bottom: 0;
    }
    
    #viewer-footer {
        height: 3;
        padding: 0 1;
        background: $surface-darken-1;
        align: left middle;
    }
    
    #viewer-footer Button {
        margin: 0 1;
        min-width: 8;
    }
    
    #nav-info {
        margin: 0 1;
        color: $text-muted;
        width: auto;
    }
    """
    
    def __init__(
        self, 
        title: str, 
        content: str, 
        url: str | None = None,
        file_path: str | None = None,
        doc_index: int = 0,
        doc_list: list | None = None,
        on_navigate: Callable[[int], None] | None = None,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.title_text = title
        self.content = content
        self.url = url
        self.file_path = file_path
        self.doc_index = doc_index
        self.doc_list = doc_list or []
        self.on_navigate = on_navigate  # Callback to load different doc
    
    def compose(self) -> ComposeResult:
        # Use file_path as title if available, otherwise fall back to title
        display_title = self.file_path or self.title_text
        with Vertical(id="viewer-dialog"):
            with Horizontal(id="viewer-header"):
                yield Static(f"📄 {display_title}", id="viewer-title")
            yield MarkdownViewer(self.content, id="viewer-content", show_table_of_contents=False)
            with Horizontal(id="viewer-footer"):
                yield Button("Close", id="btn-close", variant="default")
                if self.url:
                    yield Button("🌐 Browser", id="btn-open-browser", variant="primary")
                yield Button("🐸 Frogmouth", id="btn-open-frogmouth", variant="default")
                if self.doc_list and len(self.doc_list) > 1:
                    yield Static(f"{self.doc_index + 1}/{len(self.doc_list)}", id="nav-info")
                    yield Button("◀ Prev", id="btn-prev-doc", variant="default", disabled=self.doc_index <= 0)
                    yield Button("Next ▶", id="btn-next-doc", variant="default", disabled=self.doc_index >= len(self.doc_list) - 1)
    
    @on(Button.Pressed, "#btn-ingest-threads")
    def on_ingest_threads_pressed(self) -> None:
        """Ask the harness to unpack an export, then show what arrived.

        THE PANEL DOES NOT WRITE THE ARCHIVE. It asks the harness, which owns
        it. The human act -- requesting the export from the service -- happened
        before this button existed, and everything after it may be automated.
        """
        from dossier.threads import request_import, summarise_import

        field = self.query_one("#thread-export-path", Input)
        path = (field.value or "").strip().strip('"')
        if not path:
            self.notify("Give the path to an export first.",
                        severity="warning", title="Nothing to ingest")
            return

        self.notify(f"Asking the harness to unpack {path}...",
                    title="Ingesting")
        result = request_import(path)
        line = summarise_import(result)

        if not result.get("ok"):
            self.notify(line, severity="error", title="Ingest refused")
            return

        # Refresh before reporting, so the count in the message and the rows on
        # the screen are the same reading. Reporting first and refreshing after
        # is how a panel comes to say one number and show another.
        self.action_refresh()
        self.notify(line, title="Ingested")

    @on(Button.Pressed, "#btn-close")
    def on_close_pressed(self) -> None:
        self.dismiss()
    
    @on(Button.Pressed, "#btn-open-browser")
    def on_open_browser_pressed(self) -> None:
        if self.url:
            import webbrowser
            webbrowser.open(self.url)
            self.notify(f"Opening {self.url[:50]}...")
    
    @on(Button.Pressed, "#btn-open-frogmouth")
    def on_open_frogmouth_pressed(self) -> None:
        self.action_open_frogmouth()
    
    @on(Button.Pressed, "#btn-prev-doc")
    def on_prev_doc_pressed(self) -> None:
        self.action_prev_doc()
    
    @on(Button.Pressed, "#btn-next-doc")
    def on_next_doc_pressed(self) -> None:
        self.action_next_doc()
    
    def action_close(self) -> None:
        self.dismiss()
    
    def action_open_browser(self) -> None:
        if self.url:
            import webbrowser
            webbrowser.open(self.url)
            self.notify(f"Opening {self.url[:50]}...")
        else:
            self.notify("No URL available", severity="warning")
    
    def action_open_frogmouth(self) -> None:
        """Open content in frogmouth viewer."""
        import shutil
        import subprocess
        import tempfile
        import os
        
        if not shutil.which("frogmouth"):
            self.notify(
                "frogmouth not installed. Install with: uv add dossier[viewer]",
                severity="warning",
                timeout=5,
            )
            return
        
        # Write content to temp file
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                suffix=".md",
                delete=False,
                encoding="utf-8",
            ) as f:
                f.write(self.content)
                temp_path = f.name
            
            # Use Textual's suspend to hand over terminal to frogmouth
            self.notify("Opening in frogmouth...")
            
            async def run_frogmouth() -> None:
                with self.app.suspend():
                    subprocess.run(["frogmouth", temp_path])
                # Clean up temp file after frogmouth exits
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass
            
            self.app.call_later(run_frogmouth)
            
        except Exception as e:
            self.notify(f"Error: {e}", severity="error")
    
    def action_next_doc(self) -> None:
        """Navigate to next document."""
        if not self.doc_list or self.doc_index >= len(self.doc_list) - 1:
            self.notify("No more documents", severity="warning")
            return
        if self.on_navigate:
            self.on_navigate(self.doc_index + 1)
    
    def action_prev_doc(self) -> None:
        """Navigate to previous document."""
        if not self.doc_list or self.doc_index <= 0:
            self.notify("No previous document", severity="warning")
            return
        if self.on_navigate:
            self.on_navigate(self.doc_index - 1)


class DraggableSplitter(Static):
    """A draggable splitter for resizing horizontal panels."""
    
    DEFAULT_CSS = """
    DraggableSplitter {
        width: 1;
        height: 100%;
        background: $primary-darken-2;
        border-left: solid $primary;
        border-right: solid $primary;
    }
    
    DraggableSplitter:hover {
        background: $primary;
    }
    
    DraggableSplitter.dragging {
        background: $accent;
    }
    """
    
    is_dragging: reactive[bool] = reactive(False)
    
    def __init__(self, left_id: str, right_id: str, **kwargs) -> None:
        super().__init__("┃", **kwargs)
        self.left_id = left_id
        self.right_id = right_id
        self._drag_start_x: int = 0
        self._left_start_width: int = 0
    
    def on_mouse_down(self, event) -> None:
        """Start dragging when mouse is pressed."""
        self.is_dragging = True
        self.add_class("dragging")
        self.capture_mouse()
        self._drag_start_x = event.screen_x
        left_widget = self.screen.query_one(f"#{self.left_id}")
        self._left_start_width = left_widget.size.width
        event.stop()
    
    def on_mouse_up(self, event) -> None:
        """Stop dragging when mouse is released."""
        if self.is_dragging:
            self.is_dragging = False
            self.remove_class("dragging")
            self.release_mouse()
            event.stop()
    
    def on_mouse_move(self, event) -> None:
        """Resize panels while dragging."""
        if self.is_dragging:
            delta = event.screen_x - self._drag_start_x
            new_left_width = max(20, self._left_start_width + delta)
            
            # Get total available width
            parent = self.parent
            if parent:
                total_width = parent.size.width - 3  # Account for splitter width
                new_right_width = max(15, total_width - new_left_width)
                new_left_width = total_width - new_right_width
                
                left_widget = self.screen.query_one(f"#{self.left_id}")
                right_widget = self.screen.query_one(f"#{self.right_id}")
                
                left_widget.styles.width = new_left_width
                right_widget.styles.width = new_right_width
            event.stop()


class ProjectListItem(ListItem):
    """A project item in the list view."""
    
    is_multi_selected: reactive[bool] = reactive(False)
    
    def __init__(self, project: Project) -> None:
        super().__init__()
        self.project = project
    
    def _get_display_name(self) -> str:
        """Get a shortened display name for the project."""
        name = self.project.name
        
        # Shorten global prefixes
        if name.startswith("github/user/"):
            return f"👤 {name[12:]}"  # Remove github/user/
        if name.startswith("lang/"):
            return f"💻 {name[5:]}"  # Remove lang/
        if name.startswith("pkg/"):
            return f"📚 {name[4:]}"  # Remove pkg/
        
        # Shorten repo-scoped entities: owner/repo/type/id -> repo/type/id
        if "/" in name:
            parts = name.split("/")
            if len(parts) >= 4:
                # owner/repo/type/id format - show repo/type/id
                entity_type = parts[2]
                entity_id = "/".join(parts[3:])
                type_icons = {
                    "branch": "🌿",
                    "issue": "🐛",
                    "pr": "🔀",
                    "ver": "🏷️",
                    "doc": "📄",
                    "delta": "🔺",
                }
                icon = type_icons.get(entity_type, "•")
                return f"{icon} {parts[1]}/{entity_type}/{entity_id}"
        
        # Standard owner/repo format - show as is
        return name
    
    def compose(self) -> ComposeResult:
        stars = f" ⭐{self.project.github_stars}" if self.project.github_stars else ""
        synced = "🔄" if self.project.last_synced_at else "○"
        display_name = self._get_display_name()
        yield Label(f"{synced} {display_name}{stars}", id="project-label")
    
    def on_click(self, event) -> None:
        """Handle click with modifier key support for multi-selection."""
        if event.ctrl or event.shift:
            # Toggle multi-selection without changing ListView selection
            self.app.toggle_project_selection(self.project)
            event.stop()  # Prevent default ListView selection behavior
    
    def watch_is_multi_selected(self, selected: bool) -> None:
        """Update visual state when multi-selection changes."""
        if selected:
            self.add_class("multi-selected")
        else:
            self.remove_class("multi-selected")


class SyncStatusWidget(Static):
    """Widget showing sync status and rate limit info."""
    
    status: reactive[str] = reactive("Ready")
    progress: reactive[float] = reactive(0.0)
    rate_remaining: reactive[int] = reactive(5000)
    rate_limit: reactive[int] = reactive(5000)
    
    def compose(self) -> ComposeResult:
        yield Label(f"Status: {self.status}", id="sync-status-label")
        yield ProgressBar(total=100, show_eta=False, id="sync-progress")
        yield Label(f"Rate: {self.rate_remaining}/{self.rate_limit}", id="rate-label")
    
    def watch_status(self, value: str) -> None:
        self.query_one("#sync-status-label", Label).update(f"Status: {value}")
    
    def watch_progress(self, value: float) -> None:
        self.query_one("#sync-progress", ProgressBar).update(progress=value)
    
    def watch_rate_remaining(self, value: int) -> None:
        self.query_one("#rate-label", Label).update(f"Rate: {value}/{self.rate_limit}")


class ProjectDetailPanel(Vertical):
    """Panel showing detailed project information."""
    
    project: reactive[Optional[Project]] = reactive(None)
    # Governance is handed in rather than looked up: this panel has no session,
    # and the app that selects a project already has one. Keeping the lookup out
    # of here also keeps the read-time join in a single place.
    governance: reactive[Optional[tuple]] = reactive(None)
    
    def compose(self) -> ComposeResult:
        yield Label("Select a project", id="project-title", classes="title")
        yield Rule()
        yield VerticalScroll(
            Static("", id="project-info", markup=True),
            Static("", id="project-governance", markup=True),
            Markdown("", id="project-docs"),
            id="detail-scroll",
        )
    
    def watch_project(self, project: Optional[Project]) -> None:
        if project is None:
            self.query_one("#project-title", Label).update("Select a project")
            self.query_one("#project-info", Static).update("")
            self.query_one("#project-governance", Static).update("")
            self.query_one("#project-docs", Markdown).update("")
            return
        
        self.query_one("#project-title", Label).update(f"📁 {project.name}")
        
        # Build info text with Rich markup for clickable links
        info_lines = []
        if project.description:
            info_lines.append(f"📝 {project.description}")
            info_lines.append("")
        
        if project.github_owner_url:
            info_lines.append(f"👤 Owner: [@click=app.open_url('{project.github_owner_url}')]{project._get_owner()}[/]")
        if project.github_stars is not None:
            info_lines.append(f"⭐ Stars: {project.github_stars:,}")
        if project.github_language:
            info_lines.append(f"💻 Language: {project.github_language}")
        if project.github_url:
            info_lines.append(f"🔗 [@click=app.open_url('{project.github_url}')]{project.github_url}[/]")
        if project.last_synced_at:
            info_lines.append(f"🔄 Synced: {project.last_synced_at.strftime('%Y-%m-%d %H:%M')}")
        else:
            info_lines.append("🔄 [dim]Not synced - press 's' to sync[/]")
        
        self.query_one("#project-info", Static).update("\n".join(info_lines))
        self._render_governance()

    def watch_governance(self, _value) -> None:
        """Re-render: the row can arrive after the project it describes."""
        self._render_governance()

    def _render_governance(self) -> None:
        """The selected project's governance state, or why there is none."""
        from dossier import governance as gov

        target = self.query_one("#project-governance", Static)
        if self.project is None:
            target.update("")
            return
        row, matched_by = self.governance or (None, None)
        state = gov.health(row) if row is not None else gov.UNKNOWN_TEXT
        colour = {"ok": "green", "drift": "red", gov.UNKNOWN_TEXT: "yellow"}[state]
        body = "\n".join(f"  {line}" for line in gov.summary_lines(row, matched_by))
        target.update(f"\n[bold]Governance[/] [{colour}]{state}[/]\n{body}")


class StatsWidget(Static):
    """Widget showing database statistics."""
    
    def __init__(self, session_factory) -> None:
        super().__init__()
        self.session_factory = session_factory
    
    def on_mount(self) -> None:
        self.refresh_stats()
    
    def refresh_stats(self) -> None:
        """Refresh stats using efficient COUNT queries instead of loading all rows."""
        from sqlalchemy import func
        
        with self.session_factory() as session:
            # Use COUNT(*) for efficiency instead of loading all records
            # Forks are excluded: the header is a statement about the
            # organisation, and a vendored copy of somebody else's project is
            # not part of what it built.
            project_count = session.exec(
                select(func.count()).select_from(Project)
                .where(Project.is_fork == False)  # noqa: E712
            ).one()
            synced_count = session.exec(
                select(func.count()).select_from(Project)
                .where(Project.is_fork == False)  # noqa: E712
                .where(Project.last_synced_at.isnot(None))
            ).one()
            doc_count = session.exec(select(func.count()).select_from(DocumentSection)).one()
            
        self.update(
            f"📊 Projects: {project_count} ({synced_count} synced) | "
            f"📄 Docs: {doc_count}"
        )


class DossierApp(App):
    """Main Dossier TUI application for project tracking."""
    
    TITLE = "Dossier"
    SUB_TITLE = "Documentation Standardization Tool"
    
    CSS = """
    /* Simple vertical stack layout - most reliable */
    Screen {
        layout: vertical;
    }
    
    #header-bar {
        height: 3;
        width: 100%;
        background: $primary-darken-2;
        padding: 0 1;
    }
    
    #stats-bar {
        dock: top;
        height: 1;
        background: $surface;
        color: $text-muted;
        padding: 0 1;
    }
    
    /* Main layout uses horizontal with explicit widths */
    #main-layout {
        height: 1fr;
        width: 100%;
    }
    
    #sidebar {
        width: 25%;
        min-width: 30;
        max-width: 60;
        height: 100%;
        border-right: solid $primary;
    }
    
    #main-content {
        width: 1fr;
        height: 100%;
        padding: 0 1;
    }
    
    #project-list-container {
        height: 1fr;
    }
    
    #project-tree {
        height: 100%;
        scrollbar-gutter: stable;
    }
    
    #project-tree > .tree--guides {
        color: $primary 50%;
    }
    
    .multi-selected {
        background: $primary 30%;
        text-style: bold;
    }
    
    .multi-selected:hover {
        background: $primary 40%;
    }
    
    #project-title {
        text-style: bold;
        padding: 1 0;
    }
    
    .title {
        text-style: bold;
        color: $primary;
    }
    
    #detail-scroll {
        height: 1fr;
    }
    
    #project-info {
        padding: 1;
        background: $surface;
        margin-bottom: 1;
    }
    
    #project-docs {
        padding: 1;
    }
    
    #command-bar {
        dock: bottom;
        height: auto;
        width: 100%;
        padding: 0 1;
        background: $surface;
        border-top: solid $primary;
    }
    
    #command-bar Input {
        width: 1fr;
        margin: 0 1 0 0;
    }
    
    #command-bar Button {
        margin: 0 0 0 1;
        min-width: 6;
    }
    
    #search-input {
        border: none;
    }

    #sidebar-controls {
        dock: bottom;
        height: auto;
        width: 100%;
        padding: 1 0 0 0;
        background: $surface;
        border-top: solid $primary;
    }

    #filter-bar-2 {
        height: auto;
        width: 100%;
        margin: 0 0 1 0;
    }

    #filter-bar-2 Select {
        margin: 0 1 0 0;
        width: 1fr;
    }

    #filter-bar {
        height: auto;
        width: 100%;
        margin: 0;
    }

    #filter-bar Button {
        margin: 0 1 0 0;
        min-width: 6;
    }
    
    SyncStatusWidget {
        dock: bottom;
        height: 3;
        background: $surface;
        padding: 0 1;
    }
    
    #sync-progress {
        width: 100%;
    }
    
    DataTable {
        height: 1fr;
    }

    /* The overview stacks many tables in one scroll. `height: 1fr` above makes
       each one flex to fill, so they compete for the same space and every
       section ends up squashed against its neighbours -- which is what a
       reader sees as the page having lost its shape. Here each table is as
       tall as its rows and the panel scrolls. */
    /* NO `max-height` HERE, DELIBERATELY. Capping a table inside a page that
       already scrolls gives the table its own scrollbar, and a reader who
       scrolls the page past a capped section never sees its last rows -- text
       that is present, rendered, and unreachable without noticing there was a
       second scroll region. The page is the only scroll axis; a section that
       grows makes the page longer. Measured against the real database: the
       tallest section is 17 rows, so a cap of 20 would not have bound today
       and would have bound silently later. */
    .overview-section {
        height: auto;
        margin: 0 0 1 0;
    }

    .overview-heading {
        margin: 1 0 0 0;
        padding: 0 1;
        color: $accent;
    }

    /* The note explains what the numbers above it do and do not mean. It sits
       with that table rather than floating between two, so the margin is under
       it and not over. */
    .overview-note {
        margin: 0 0 1 0;
        padding: 0 2;
        color: $text-muted;
    }

    #overview-scope {
        padding: 1 1 0 1;
    }

    #overview-masthead {
        padding: 0 1 1 1;
        border-bottom: solid $primary-darken-2;
        margin: 0 0 1 0;
    }
    
    TabPane {
        padding: 1;
    }

    #tab-details {
        padding: 0;
    }
    
    #dossier-layout {
        height: 1fr;
    }
    
    #dossier-scroll {
        width: 2fr;
        height: 1fr;
    }
    
    #component-tree {
        width: 1fr;
        height: 1fr;
        padding: 0 1;
    }
    
    #dossier-splitter {
        margin: 0;
    }
    
    #dossier-view {
        padding: 1;
    }
    
    #docs-tree {
        height: 1fr;
        padding: 1;
    }
    
    #contributors-table {
        height: 1fr;
    }
    
    #issues-table {
        height: 1fr;
    }
    
    #languages-table {
        height: 1fr;
    }
    
    #dependencies-table {
        height: 1fr;
    }
    
    .language-bar {
        height: 1;
        margin: 0 1;
    }
    
    .issue-open {
        color: $success;
    }
    
    .issue-closed {
        color: $text-muted;
    }
    
    #component-buttons {
        dock: bottom;
        height: auto;
        padding: 1 0;
    }
    
    #component-buttons Button {
        margin: 0 1 0 0;
    }
    
    #components-table {
        height: 1fr;
    }
    """
    
    BINDINGS = [
        Binding("q", "quit", "Quit", show=True),
        Binding("r", "refresh", "Refresh", show=True),
        Binding("s", "sync", "Sync", show=True),
        Binding("a", "add", "Add Project", show=True),
        Binding("o", "open_github", "Open GitHub", show=True),
        Binding("/", "search", "Search", show=True),
        Binding("f", "cycle_filter", "Filter", show=True),
        Binding("m", "rad_menu", "Menu (rad)", show=True),
        Binding("?", "help", "Help", show=True),
        Binding("`", "settings", "Settings", show=False),
        Binding("l", "link_selected", "Link as Project", show=False),
        Binding("d", "delete", "Delete", show=False),
        Binding("c", "add_component", "Add Component", show=False),
        Binding("space", "toggle_select", "Toggle Select", show=False),
        Binding("ctrl+a", "select_all", "Select All", show=False),
        Binding("escape", "clear_selection", "Clear Selection", show=False),
        Binding("tab", "focus_next", "Next", show=False),
        Binding("shift+tab", "focus_previous", "Previous", show=False),
        # Reclaiming from the dashboard, in two keys that are not the same key.
        # `x` only ever plans; `X` only works once a plan has been seen in this
        # session, and both do nothing off the Disk tab. A single key with a
        # confirmation dialog would be one stray Enter from deleting 100GB, and
        # the dialog is the part people learn to dismiss.
        Binding("x", "disk_plan", "Plan Reclaim", show=False),
        Binding("X", "disk_apply", "Apply Reclaim", show=False),
    ]
    
    selected_project: reactive[Optional[Project]] = reactive(None)
    selected_projects: reactive[set] = reactive(set, always_update=True)  # Set of project IDs for multi-select
    filter_synced: reactive[Optional[bool]] = reactive(None)  # None=all, True=synced, False=unsynced
    filter_language: reactive[Optional[str]] = reactive(None)
    filter_entity: reactive[Optional[str]] = reactive(None)  # None=all, or "repo", "branch", "issue", "pr", "ver", "doc", "user", "lang", "pkg"
    filter_starred: reactive[Optional[bool]] = reactive(None)  # None=all, True=has stars, False=no stars
    sort_by: reactive[str] = reactive("stars")  # name, stars, synced - default to stars
    _navigating_from_tree: bool = False  # Flag to prevent tab switch during tree navigation
    _tree_target_tab: Optional[str] = None  # Target tab when navigating from tree
    
    def __init__(self, session_factory=None, initial_tab: str | None = None):
        super().__init__()
        # Which tab to open on, overriding the configured default. Set by
        # `dossier governance dashboard` so one command lands the reader on the
        # view they asked for instead of on whatever they last configured.
        self._initial_tab = initial_tab
        if session_factory is None:
            from dossier.cli import get_session, init_db
            init_db()
            session_factory = get_session
        self.session_factory = session_factory

        # Check if delta tables exist (migration may not have been applied)
        self._delta_tables_exist = self._check_delta_tables_exist()

        # Load config and apply saved settings
        from dossier.config import DossierConfig
        self._config = DossierConfig.load()
        self.theme = self._config.theme

        # Restore view state from config
        if self._config.view_state:
            vs = self._config.view_state
            self.filter_synced = vs.filter_synced
            self.filter_language = vs.filter_language
            # `filter_entity` matched project rows whose names were addresses.
            # That shape is gone, so a restored value would filter to nothing
            # with no control on screen to clear it.
            self.filter_entity = None
            self.filter_starred = vs.filter_starred
            self.sort_by = vs.sort_by

    def _check_delta_tables_exist(self) -> bool:
        """Check if delta tables exist in the database."""
        try:
            from sqlalchemy import inspect as sa_inspect
            with self.session_factory() as session:
                inspector = sa_inspect(session.get_bind())
                tables = inspector.get_table_names()
                return "project_delta" in tables
        except Exception:
            return False
    
    def compose(self) -> ComposeResult:
        yield Header()
        
        with Horizontal(id="header-bar"):
            yield StatsWidget(self.session_factory)
        
        with Horizontal(id="main-layout"):
            with Vertical(id="sidebar"):
                # The work board first: deltas are the unit of work, and the
                # project tree below is how you reach a repository that has no
                # delta open. The board reads `project_delta`; the sidebar's
                # old entity filter matched project rows whose *names* were
                # addresses, which is a shape `ingest.py` refuses to create.
                with Container(id="delta-board-container"):
                    yield DeltaBoard(self.session_factory, id="delta-board")
                with Container(id="project-list-container"):
                    # `auto_expand` toggles a node when it is *selected*, so
                    # clicking an owner collapsed its repositories and the
                    # selection read as "nothing happened". Expansion is the
                    # toggle arrow's job.
                    project_tree = Tree("Projects", id="project-tree")
                    project_tree.auto_expand = False
                    yield project_tree
                with Vertical(id="sidebar-controls"):
                    with Horizontal(id="filter-bar-2"):
                        yield Select(
                            [("Any Language", "")],  # Will be populated on mount
                            value="",
                            id="select-language",
                            allow_blank=False,
                        )
                        yield Select(
                            [("Sort: Stars", "stars"), ("Sort: Name", "name"), ("Sort: Recent", "synced")],
                            value=self.sort_by,
                            id="select-sort",
                            allow_blank=False,
                        )
                    with Horizontal(id="filter-bar"):
                        yield Button("All", id="btn-filter-all", variant="primary")
                        yield Button("Synced", id="btn-filter-synced", variant="default")
                        yield Button("Unsynced", id="btn-filter-unsynced", variant="default")
                        yield Button("Star", id="btn-filter-starred", variant="default")

            with Vertical(id="main-content"):
                with TabbedContent(id="project-tabs"):
                    # First, and org-wide rather than per-project: a reader
                    # arriving cold gets the shape of the organisation before
                    # being asked to pick a repository out of 141.
                    with TabPane("Overview", id="tab-overview"):
                        yield OverviewPanel(self.session_factory, id="org-overview")
                    with TabPane("Dossier", id="tab-dossier"):
                        with Horizontal(id="dossier-layout"):
                            yield VerticalScroll(Markdown("", id="dossier-view"), id="dossier-scroll")
                            yield DraggableSplitter("dossier-scroll", "component-tree", id="dossier-splitter")
                            yield Tree("Components", id="component-tree")
                    with TabPane("Details", id="tab-details"):
                        yield ProjectDetailPanel(id="project-detail")
                    with TabPane("Documentation", id="tab-docs"):
                        yield Tree("📄 Documentation", id="docs-tree")
                    with TabPane("Languages", id="tab-languages"):
                        yield DataTable(id="languages-table")
                    with TabPane("Branches", id="tab-branches"):
                        yield DataTable(id="branches-table")
                    with TabPane("Dependencies", id="tab-dependencies"):
                        yield DataTable(id="dependencies-table")
                    with TabPane("Contributors", id="tab-contributors"):
                        yield DataTable(id="contributors-table")
                    with TabPane("Issues", id="tab-issues"):
                        yield DataTable(id="issues-table")
                    with TabPane("Pull Requests", id="tab-prs"):
                        yield DataTable(id="prs-table")
                    with TabPane("Releases", id="tab-releases"):
                        yield DataTable(id="releases-table")
                    # The harness half of the pair: what qmcp reports having
                    # run, read through the address that names the same row on
                    # both sides.
                    with TabPane("Harness", id="tab-harness"):
                        yield DataTable(id="harness-table")
                    # Its own tab rather than a second table under Harness:
                    # this is the one thing on the screen that is waiting for
                    # the reader, and a queue somebody has to go looking for is
                    # a queue nobody empties.
                    with TabPane("Waiting", id="tab-waiting"):
                        yield DataTable(id="waiting-table")
                    # The harness's thread archive, read over the seam. This is
                    # the only human surface for it: a second one would be a
                    # second definition of what a figure means, and the CLI
                    # beside it is for machines and for debugging.
                    with TabPane("Threads", id="tab-threads"):
                        yield DataTable(id="threads-table")
                        with Horizontal(id="thread-buttons"):
                            yield Input(placeholder="path to an export "
                                                    "(conversations.json or the "
                                                    "folder holding it)",
                                        id="thread-export-path")
                            yield Button("Ingest", id="btn-ingest-threads",
                                         variant="primary")
                    with TabPane("Governance", id="tab-governance"):
                        with Vertical():
                            yield Static("", id="governance-age")
                            yield DataTable(id="governance-table")
                            yield Static("", id="governance-threads-age")
                            yield DataTable(id="governance-threads-table")
                    with TabPane("Disk", id="tab-disk"):
                        with Vertical():
                            yield Static("", id="disk-age")
                            yield DataTable(id="disk-volumes-table")
                            yield Static("", id="disk-delta-age")
                            yield DataTable(id="disk-targets-table")
                    with TabPane("Components", id="tab-components"):
                        with Vertical():
                            # What can be observed, above what was declared.
                            yield IntersectionsPanel(self.session_factory,
                                                     id="intersections")
                            yield DataTable(id="components-table")
                            with Horizontal(id="component-buttons"):
                                yield Button("Add Component", id="btn-add-component", variant="primary")
                                yield Button("Link as Parent", id="btn-link-parent", variant="default")
                                yield Button("Remove", id="btn-remove-component", variant="error")
                    with TabPane("Deltas", id="tab-deltas"):
                        with Vertical():
                            yield DataTable(id="deltas-table")
                            with Horizontal(id="delta-buttons"):
                                yield Button("New Delta", id="btn-new-delta", variant="primary")
                                yield Button("Advance", id="btn-advance-phase", variant="default")
                                yield Button("Note", id="btn-add-note", variant="default")
                                yield Button("Link", id="btn-add-delta-link", variant="default")

        # Bottom command bar
        with Horizontal(id="command-bar"):
            yield Input(placeholder="🔍 Search... or :cmd (try :help)", id="search-input")
            yield Button("Sync", id="btn-sync", variant="primary")
            yield Button("Add", id="btn-add", variant="default")
            yield Button("Del", id="btn-delete", variant="error")
            yield Button("?", id="btn-help", variant="default")
        
        yield Footer()
    
    def action_rad_menu(self) -> None:
        """Open the rad ring, and apply whatever it commits.

        The host half of rad's division of ownership: rad decided *what* was
        chosen, and applying it is ours. Unhandled actions are reported rather
        than swallowed -- a wedge that commits nothing is a dead end, and a
        silent one is worse than a loud one.
        """
        from dossier.rad import resolve
        from dossier.rad.ring import RingScreen
        from dossier.rad.session import RadSession

        if self._rad is None:
            self._rad = RadSession(resolve=resolve)

        def applied(intent) -> None:
            if intent is None:
                return
            self._apply_rad_intent(intent)

        self.push_screen(RingScreen(self._rad), applied)

    # One rad session for the app's lifetime, so the cost ledger accumulates
    # across actions rather than resetting each time the ring opens. A class
    # attribute rather than an __init__ line, so it exists however the app was
    # constructed -- this app has more than one construction path.
    _rad = None

    # Which scope the tabs are describing: an owner, or None for whichever
    # project is selected. A class attribute so a tab loader that runs before
    # any selection reads a value rather than raising.
    _scope_owner = None

    # Actions the ring can commit that map onto a view this app already has.
    # `view.harness` was here and no wedge in the palette names it, so nothing
    # could ever commit it -- a dead entry that made the dispatch look wider
    # than the menu. `tab-harness` is still reachable by its tab; only the
    # unreachable mapping is gone. `test_rad_sync.py` checks the direction.
    RAD_VIEWS = {
        "view.overview": "tab-overview",
        "view.deltas": "tab-deltas",
        "view.governance": "tab-governance",
        "view.disk": "tab-disk",
        "view.details": "tab-details",
    }

    # Every ring action this app actually does something with. Declared rather
    # than inferred, and read by `dossier.rad.index.applied_by` so the command
    # sheet marks what is wired instead of implying everything is.
    RAD_HANDLED = frozenset(RAD_VIEWS) | {"project.sync"}

    # How many repositories `6.2` will fetch off two keystrokes without asking
    # again. Above this it states the plan and waits for the same two keys a
    # second time. The threshold is not about danger -- it is that a hundred
    # requests is a thing somebody should have meant, and repeating the route
    # is the cheapest possible way to mean it.
    SYNC_WITHOUT_CONFIRMING = 5

    # Set by a `6.2` that asked for confirmation, cleared by anything else.
    # A class attribute so it reads as absent however the app was constructed.
    _sync_pending = None

    def _apply_rad_intent(self, intent) -> None:
        """Apply one committed intent, and say so where a reader can see it."""
        tab = self.RAD_VIEWS.get(intent.action)
        if tab is not None:
            self._sync_pending = None
            try:
                self.query_one("#project-tabs").active = tab
            except Exception:
                pass
            self.notify(f"{intent.action}  (ipa {intent.ipa})", timeout=3)
            return
        if intent.action == "project.sync":
            self._sync_current_view()
            return
        self._sync_pending = None
        # Named in the palette and not yet handled here. Reported, because a
        # wedge that quietly does nothing teaches a reader the menu is broken.
        self.notify(
            f"{intent.action}: not applied yet (ipa {intent.ipa})",
            severity="warning", timeout=4,
        )

    def sync_plan(self):
        """What refreshing the view currently on screen would touch.

        Scope comes from the screen rather than from a selection the ring
        cannot see: a chosen repository first, then the owner the tabs are
        scoped to, then everything. `action_sync` refuses without a selection,
        which is right for a command about repositories and wrong for one about
        the view -- the org overview is the view most often stale and the one
        with nothing selected.
        """
        from dossier.freshness import plan_for

        try:
            tab = self.query_one("#project-tabs").active
        except Exception:
            tab = None

        # THE TAB DECIDES THE SCOPE, NOT THE SELECTION. The app selects the
        # first repository on mount, so `_current_project` is set even on a
        # screen showing the whole organisation -- reading it here would scope
        # the org overview's refresh to one repository nobody chose. The
        # overview is an org view whatever is selected behind it, and the
        # panel's own `owner` is what it is drawn from.
        owner, project = self._scope_owner, self._current_project
        if tab == "tab-overview":
            try:
                owner, project = self.query_one(OverviewPanel).owner, None
            except Exception:
                project = None

        with self.session_factory() as session:
            row = None if project is None else session.get(Project, project.id)
            return plan_for(session, tab=tab, owner=owner, project=row)

    def _sync_current_view(self) -> None:
        """`6.2`. Make what is on screen current, or say why it is not stale.

        Every branch here ends in the reader being told something. A refresh
        that finds nothing to do and says nothing is indistinguishable from one
        that did not run, and the second time that happens a person stops
        trusting the key.
        """
        plan = self.sync_plan()

        if plan.inapplicable:
            self._sync_pending = None
            self.notify(plan.summary(), severity="warning", timeout=6)
            return
        if plan.is_current:
            self._sync_pending = None
            self.notify(plan.summary(), title="Already current", timeout=4)
            return
        if not plan.subjects:
            self._sync_pending = None
            self.notify(plan.summary(), severity="warning", timeout=4)
            return

        wanted = plan.wanted
        confirming = self._sync_pending == plan.scope
        if len(wanted) > self.SYNC_WITHOUT_CONFIRMING and not confirming:
            self._sync_pending = plan.scope
            self.notify(
                f"{plan.summary()}. Press 6.2 again to fetch {len(wanted)}.",
                title="Confirm", severity="warning", timeout=10,
            )
            return

        self._sync_pending = None
        names = {subject.name for subject in wanted}
        with self.session_factory() as session:
            rows = [p for p in session.exec(select(Project)).all()
                    if (p.full_name or p.name) in names]
        if not rows:
            # The plan named subjects and the database has no rows for them.
            # Reported rather than passed to a sync that would silently do
            # nothing, because those two look identical from the outside.
            self.notify(f"{plan.scope}: nothing to fetch for "
                        f"{len(names)} named subject(s)",
                        severity="error", timeout=6)
            return

        self.notify(f"Syncing {len(rows)} of {len(plan.subjects)} in "
                    f"{plan.scope}", title="Sync started", timeout=4)
        self.run_sync_batch(rows)

    def on_mount(self) -> None:
        # Setup docs tree
        docs_tree = self.query_one("#docs-tree", Tree)
        docs_tree.root.expand()
        
        # Setup languages table columns
        langs_table = self.query_one("#languages-table", DataTable)
        langs_table.add_columns("Language", "Extensions", "Encoding", "Bytes", "%")
        langs_table.cursor_type = "row"
        
        # Governance: org-wide, not per-project. Both tables live in one tab
        # because the two documents are read together and a reader comparing
        # "who is drifting" against "what is in flight" wants them adjacent.
        governance_table = self.query_one("#governance-table", DataTable)
        governance_table.add_column("Repository", width=24)
        governance_table.add_column("Phase (claim)", width=14)
        governance_table.add_column("Corpus", width=13)
        governance_table.add_column("Seed", width=8)
        governance_table.add_column("Slot", width=9)
        governance_table.add_column("Release", width=22)
        governance_table.add_column("Evidence (landed)", width=40)
        # The reverse link: which governed repositories this store has synced.
        # A blank here means nobody has looked at that project in dossier, which
        # is worth seeing beside its governance state.
        governance_table.add_column("In dossier", width=16)
        governance_table.cursor_type = "row"

        threads_table = self.query_one("#governance-threads-table", DataTable)
        threads_table.add_column("Repository", width=17)
        threads_table.add_column("Thread", width=38)
        threads_table.add_column("Stage", width=16)
        threads_table.add_column("Delta", width=22)
        threads_table.add_column("Idle", width=9)
        threads_table.add_column("PR", width=6)
        threads_table.cursor_type = "row"

        # Disk: machine-wide, not per-project, and two tables in one tab for
        # the same reason governance has two -- the reader asking "what is
        # eating the disk" is asking "and did it just start" in the same
        # breath. Volumes carry the change in FREE space, so a negative number
        # is the disk filling up; that is the direction worth noticing and the
        # column is titled to say so.
        volumes_table = self.query_one("#disk-volumes-table", DataTable)
        volumes_table.add_column("Volume", width=14)
        volumes_table.add_column("Free", width=11)
        volumes_table.add_column("of total", width=11)
        volumes_table.add_column("Free change", width=13)
        volumes_table.add_column("State", width=10)
        volumes_table.add_column("Why", width=52)
        volumes_table.cursor_type = "row"

        targets_table = self.query_one("#disk-targets-table", DataTable)
        targets_table.add_column("Target", width=26)
        targets_table.add_column("Size", width=11)
        targets_table.add_column("Change", width=13)
        targets_table.add_column("Safety", width=12)
        targets_table.add_column("Largest path / why not measured", width=60)
        targets_table.cursor_type = "row"

        # Setup branches table columns (with custom widths)
        branches_table = self.query_one("#branches-table", DataTable)
        branches_table.add_column("Branch", width=20)
        branches_table.add_column("Default", width=8)
        branches_table.add_column("Protected", width=10)
        branches_table.add_column("Latest Commit", width=50)
        branches_table.add_column("Author", width=20)
        branches_table.cursor_type = "row"
        
        # Setup dependencies table columns
        deps_table = self.query_one("#dependencies-table", DataTable)
        deps_table.add_columns("Package", "Version", "Type", "Source")
        deps_table.cursor_type = "row"
        
        # Setup contributors table columns
        contrib_table = self.query_one("#contributors-table", DataTable)
        contrib_table.add_columns("Username", "Contributions", "Profile")
        contrib_table.cursor_type = "row"
        
        # Setup issues table columns
        issues_table = self.query_one("#issues-table", DataTable)
        issues_table.add_columns("#", "Title", "State", "Author", "Labels")
        issues_table.cursor_type = "row"
        
        # Setup pull requests table columns
        prs_table = self.query_one("#prs-table", DataTable)
        prs_table.add_column("#", width=6)
        prs_table.add_column("Title", width=40)
        prs_table.add_column("State", width=12)
        prs_table.add_column("Author", width=15)
        prs_table.add_column("Base ← Head", width=25)
        prs_table.add_column("+/-", width=12)
        prs_table.cursor_type = "row"
        
        # Setup releases table columns
        releases_table = self.query_one("#releases-table", DataTable)
        releases_table.add_column("Tag", width=15)
        releases_table.add_column("Name", width=35)
        releases_table.add_column("Author", width=15)
        releases_table.add_column("Type", width=12)
        releases_table.add_column("Published", width=20)
        releases_table.cursor_type = "row"
        
        # Setup components table columns
        components_table = self.query_one("#components-table", DataTable)
        components_table.add_column("Direction", width=10)
        components_table.add_column("Project", width=40)
        components_table.add_column("Type", width=15)
        components_table.add_column("Order", width=8)
        components_table.cursor_type = "row"

        # Setup deltas table columns
        deltas_table = self.query_one("#deltas-table", DataTable)
        deltas_table.add_column("Name", width=20)
        deltas_table.add_column("Title", width=30)
        deltas_table.add_column("Phase", width=18)
        deltas_table.add_column("Type", width=12)
        deltas_table.add_column("Priority", width=10)
        deltas_table.add_column("Links", width=8)
        deltas_table.cursor_type = "row"

        # Populate language filter dropdown
        self._populate_language_filter()
        
        # Update filter UI to match restored state
        self._update_filter_ui()
        self._update_sort_ui()
        
        # Restore view state - load projects and select last viewed project
        self._restore_view_state()

        # An explicitly requested tab wins over the restored state, and is
        # applied last for that reason: _restore_view_state may select a
        # project, which switches to the configured default tab.
        if self._initial_tab:
            tabs = self.query_one("#project-tabs", TabbedContent)
            tabs.active = self._initial_tab
            self._load_tab_data(self._initial_tab)

    def _populate_language_filter(self) -> None:
        """Populate the language filter dropdown with available languages."""
        with self.session_factory() as session:
            # Use DISTINCT query for efficiency instead of loading all projects
            from sqlalchemy import distinct
            languages = session.exec(
                select(distinct(Project.github_language))
                .where(Project.github_language.isnot(None))
                .order_by(Project.github_language)
            ).all()
        
        select_lang = self.query_one("#select-language", Select)
        options = [("Any Language", "")]
        options.extend((lang, lang) for lang in languages if lang)
        select_lang.set_options(options)
    
    def _get_entity_type_from_name(self, name: str) -> str:
        """Determine entity type from project name pattern."""
        if name.startswith("github/user/"):
            return "user"
        if name.startswith("lang/"):
            return "lang"
        if name.startswith("pkg/"):
            return "pkg"
        if "/branch/" in name:
            return "branch"
        if "/issue/" in name:
            return "issue"
        if "/pr/" in name:
            return "pr"
        if "/ver/" in name:
            return "ver"
        if "/doc/" in name:
            return "doc"
        if "/delta/" in name:
            return "delta"
        # If it has owner/repo format without other patterns, it's a repo
        if "/" in name and name.count("/") == 1:
            return "repo"
        return "other"
    
    def _shorten_project_name(self, name: str) -> str:
        """Shorten a project name for display while keeping it recognizable.
        
        Examples:
            github/user/astral-sh -> @astral-sh
            lang/python -> Python
            pkg/fastapi -> fastapi
            astral-sh/ruff/branch/main -> ruff/branch/main
            astral-sh/ruff/issue/123 -> ruff#123
            astral-sh/ruff/pr/456 -> ruff!456
            astral-sh/ruff/ver/v0.1.0 -> ruff@v0.1.0
            astral-sh/ruff/doc/readme -> ruff/doc/readme
        """
        # Global prefixes - remove prefix
        if name.startswith("github/user/"):
            return f"@{name[12:]}"
        if name.startswith("lang/"):
            return name[5:].title()  # Capitalize language name
        if name.startswith("pkg/"):
            return name[4:]
        
        # Repo-scoped entities: owner/repo/type/id -> repo shorthand
        if "/" in name:
            parts = name.split("/")
            if len(parts) >= 4:
                repo = parts[1]
                entity_type = parts[2]
                entity_id = "/".join(parts[3:])
                
                # Use compact notation for common types
                if entity_type == "issue":
                    return f"{repo}#{entity_id}"
                if entity_type == "pr":
                    return f"{repo}!{entity_id}"
                if entity_type == "ver":
                    return f"{repo}@{entity_id}"
                if entity_type == "delta":
                    return f"{repo}△{entity_id}"
                # For branch/doc, keep slash format
                return f"{repo}/{entity_type}/{entity_id}"
        
        # Standard owner/repo format - return as-is
        return name
    
    def load_projects(self, search: str = "", auto_select: bool = False, offset: int = 0) -> None:
        """Load projects into the tree view with filtering, sorting, and hierarchical grouping.
        
        Groups projects by:
        - Organizations/owners for repos (owner/repo)
        - Global categories: lang/, pkg/, github/user/
        - Repo-scoped entities under their parent repos
        
        Args:
            search: Search string to filter projects by name/description.
            auto_select: If True, automatically select the first project.
            offset: Pagination offset (ignored for tree view, loads all).
        """
        project_tree = self.query_one("#project-tree", Tree)
        project_tree.clear()
        project_tree.root.expand()

        # Pre-fetch deltas in a separate session to avoid corrupting main session
        # if delta tables don't exist
        deltas_by_project: dict[int, list] = {}
        delta_links_by_delta: dict[int, list[DeltaLink]] = {}
        deltas_by_id: dict[int, ProjectDelta] = {}
        deltas_by_project_name: dict[tuple[int, str], ProjectDelta] = {}
        if self._delta_tables_exist:
            try:
                with self.session_factory() as delta_session:
                    all_deltas = delta_session.exec(
                        select(ProjectDelta).order_by(ProjectDelta.updated_at.desc())
                    ).all()
                    for delta in all_deltas:
                        delta_session.expunge(delta)
                        if delta.project_id not in deltas_by_project:
                            deltas_by_project[delta.project_id] = []
                        deltas_by_project[delta.project_id].append(delta)
                        if delta.id is not None:
                            deltas_by_id[delta.id] = delta
                            deltas_by_project_name[(delta.project_id, delta.name)] = delta
                    delta_ids = [delta.id for delta in all_deltas if delta.id is not None]
                    if delta_ids:
                        links = delta_session.exec(
                            select(DeltaLink).where(DeltaLink.delta_id.in_(delta_ids))
                        ).all()
                        for link in links:
                            delta_session.expunge(link)
                            delta_links_by_delta.setdefault(link.delta_id, []).append(link)
            except Exception:
                # Silently fail if delta tables don't exist
                pass

        with self.session_factory() as session:
            # Build base query with SQL-level filtering
            stmt = select(Project)
            
            # Apply filters at SQL level
            filters = []
            
            # Search filter - use SQL LIKE
            if search:
                search_pattern = f"%{search.lower()}%"
                filters.append(
                    or_(
                        Project.name.ilike(search_pattern),
                        Project.description.ilike(search_pattern)
                    )
                )
            
            # Sync status filter
            if self.filter_synced is True:
                filters.append(Project.last_synced_at.isnot(None))
            elif self.filter_synced is False:
                filters.append(Project.last_synced_at.is_(None))
            
            # Starred filter
            if self.filter_starred is True:
                filters.append(and_(Project.github_stars.isnot(None), Project.github_stars > 0))
            elif self.filter_starred is False:
                filters.append(or_(Project.github_stars.is_(None), Project.github_stars == 0))
            
            # Language filter
            if self.filter_language:
                filters.append(Project.github_language == self.filter_language)
            
            # Entity type filter (name pattern matching)
            if self.filter_entity and self.filter_entity != "all":
                entity_patterns = {
                    "user": "github/user/%",
                    "lang": "lang/%",
                    "pkg": "pkg/%",
                    "branch": "%/branch/%",
                    "issue": "%/issue/%",
                    "pr": "%/pr/%",
                    "ver": "%/ver/%",
                    "doc": "%/doc/%",
                    "delta": "%/delta/%",
                    "repo": None,  # Special case: owner/repo without entity type
                }
                pattern = entity_patterns.get(self.filter_entity)
                if pattern:
                    filters.append(Project.name.like(pattern))
                elif self.filter_entity == "repo":
                    filters.append(
                        and_(
                            Project.name.notlike("github/user/%"),
                            Project.name.notlike("lang/%"),
                            Project.name.notlike("pkg/%"),
                            Project.name.notlike("%/branch/%"),
                            Project.name.notlike("%/issue/%"),
                            Project.name.notlike("%/pr/%"),
                            Project.name.notlike("%/ver/%"),
                            Project.name.notlike("%/doc/%"),
                            Project.name.notlike("%/delta/%"),
                        )
                    )
            
            # Apply all filters
            if filters:
                stmt = stmt.where(and_(*filters))
            
            # Always sort by name for tree organization
            stmt = stmt.order_by(Project.name)
            
            projects = session.exec(stmt).all()
            
            # Fetch docs for all repo-type projects (owner/repo format)
            repo_project_ids = []
            for project in projects:
                # Check if this is a repo (owner/repo format, no entity suffix)
                parts = project.name.split("/")
                if len(parts) == 2 and not project.name.startswith(("github/", "lang/", "pkg/")):
                    repo_project_ids.append(project.id)
            
            # Fetch docs grouped by project_id and source_file
            docs_by_project: dict[int, dict[str, list]] = {}
            if repo_project_ids:
                docs = session.exec(
                    select(DocumentSection)
                    .where(DocumentSection.project_id.in_(repo_project_ids))
                    .order_by(DocumentSection.source_file, DocumentSection.order)
                ).all()
                for doc in docs:
                    session.expunge(doc)
                    if doc.project_id not in docs_by_project:
                        docs_by_project[doc.project_id] = {}
                    source = doc.source_file or "(No source)"
                    if source not in docs_by_project[doc.project_id]:
                        docs_by_project[doc.project_id][source] = []
                    docs_by_project[doc.project_id][source].append(doc)
            
            # Fetch all entity data for repos (grouped by project_id)
            langs_by_project: dict[int, list] = {}
            deps_by_project: dict[int, list] = {}
            contribs_by_project: dict[int, list] = {}
            issues_by_project: dict[int, list] = {}
            prs_by_project: dict[int, list] = {}
            releases_by_project: dict[int, list] = {}
            branches_by_project: dict[int, list] = {}
            
            if repo_project_ids:
                # Languages
                langs = session.exec(
                    select(ProjectLanguage)
                    .where(ProjectLanguage.project_id.in_(repo_project_ids))
                    .order_by(ProjectLanguage.percentage.desc())
                ).all()
                for lang in langs:
                    session.expunge(lang)
                    if lang.project_id not in langs_by_project:
                        langs_by_project[lang.project_id] = []
                    langs_by_project[lang.project_id].append(lang)
                
                # Dependencies
                deps = session.exec(
                    select(ProjectDependency)
                    .where(ProjectDependency.project_id.in_(repo_project_ids))
                    .order_by(ProjectDependency.dep_type, ProjectDependency.name)
                ).all()
                for dep in deps:
                    session.expunge(dep)
                    if dep.project_id not in deps_by_project:
                        deps_by_project[dep.project_id] = []
                    deps_by_project[dep.project_id].append(dep)
                
                # Contributors
                contribs = session.exec(
                    select(ProjectContributor)
                    .where(ProjectContributor.project_id.in_(repo_project_ids))
                    .order_by(ProjectContributor.contributions.desc())
                ).all()
                for contrib in contribs:
                    session.expunge(contrib)
                    if contrib.project_id not in contribs_by_project:
                        contribs_by_project[contrib.project_id] = []
                    contribs_by_project[contrib.project_id].append(contrib)
                
                # Issues (recent 20)
                issues = session.exec(
                    select(ProjectIssue)
                    .where(ProjectIssue.project_id.in_(repo_project_ids))
                    .order_by(ProjectIssue.issue_number.desc())
                ).all()
                for issue in issues:
                    session.expunge(issue)
                    if issue.project_id not in issues_by_project:
                        issues_by_project[issue.project_id] = []
                    issues_by_project[issue.project_id].append(issue)
                
                # Pull Requests (recent 20)
                prs = session.exec(
                    select(ProjectPullRequest)
                    .where(ProjectPullRequest.project_id.in_(repo_project_ids))
                    .order_by(ProjectPullRequest.pr_number.desc())
                ).all()
                for pr in prs:
                    session.expunge(pr)
                    if pr.project_id not in prs_by_project:
                        prs_by_project[pr.project_id] = []
                    prs_by_project[pr.project_id].append(pr)
                
                # Releases
                releases = session.exec(
                    select(ProjectRelease)
                    .where(ProjectRelease.project_id.in_(repo_project_ids))
                    .order_by(ProjectRelease.release_published_at.desc())
                ).all()
                for release in releases:
                    session.expunge(release)
                    if release.project_id not in releases_by_project:
                        releases_by_project[release.project_id] = []
                    releases_by_project[release.project_id].append(release)
                
                # Branches
                branches = session.exec(
                    select(ProjectBranch)
                    .where(ProjectBranch.project_id.in_(repo_project_ids))
                    .order_by(ProjectBranch.is_default.desc(), ProjectBranch.name)
                ).all()
                for branch in branches:
                    session.expunge(branch)
                    if branch.project_id not in branches_by_project:
                        branches_by_project[branch.project_id] = []
                    branches_by_project[branch.project_id].append(branch)
            
            # Group projects hierarchically
            # Structure: { group_key: { subgroup_key: [projects] } }
            groups: dict = {}
            
            for project in projects:
                session.expunge(project)
                name = project.name
                
                # Determine grouping based on name pattern
                if name.startswith("github/user/"):
                    # github/user/username -> Users / username
                    group = "👤 Users"
                    subgroup = None
                    display = name[12:]  # Remove prefix
                elif name.startswith("lang/"):
                    # lang/python -> Languages / python
                    group = "💻 Languages"
                    subgroup = None
                    display = name[5:]
                elif name.startswith("pkg/"):
                    # pkg/fastapi -> Packages / fastapi
                    group = "📦 Packages"
                    subgroup = None
                    display = name[4:]
                elif "/" in name:
                    parts = name.split("/")
                    if len(parts) == 2:
                        # owner/repo -> owner / repo
                        group = f"🏢 {parts[0]}"
                        subgroup = None
                        display = parts[1]
                    elif len(parts) >= 4:
                        # owner/repo/type/id -> owner / repo / type-id
                        group = f"🏢 {parts[0]}"
                        subgroup = parts[1]  # repo
                        entity_type = parts[2]
                        entity_id = "/".join(parts[3:])
                        type_icons = {
                            "branch": "🌿",
                            "issue": "🐛",
                            "pr": "🔀",
                            "ver": "🏷️",
                            "doc": "📄",
                            "delta": "🔺",
                        }
                        icon = type_icons.get(entity_type, "•")
                        display = f"{icon} {entity_type}/{entity_id}"
                    else:
                        # Fallback for 3-part names
                        group = "📁 Other"
                        subgroup = None
                        display = name
                else:
                    # No slash - standalone project
                    group = "📁 Other"
                    subgroup = None
                    display = name
                
                # Add stars indicator
                if project.github_stars:
                    display = f"{display} ⭐{project.github_stars}"
                
                # Add sync indicator
                sync_icon = "🔄" if project.last_synced_at else "○"
                display = f"{sync_icon} {display}"
                
                # Build nested structure
                if group not in groups:
                    groups[group] = {}
                
                if subgroup:
                    if subgroup not in groups[group]:
                        groups[group][subgroup] = []
                    groups[group][subgroup].append((display, project))
                else:
                    if "_items" not in groups[group]:
                        groups[group]["_items"] = []
                    groups[group]["_items"].append((display, project))
            
            # Build tree from groups
            # Sort groups: orgs first (🏢), then categories
            sorted_groups = sorted(groups.keys(), key=lambda g: (0 if g.startswith("🏢") else 1, g))
            
            # Helper to add docs tree under a project node
            def add_docs_to_node(parent_node, project):
                """Add documentation files as children of a project node."""
                project_docs = docs_by_project.get(project.id, {})
                if not project_docs:
                    return
                
                # Add docs folder
                doc_count = sum(len(sections) for sections in project_docs.values())
                docs_folder = parent_node.add(f"📚 Docs ({doc_count})", expand=False)
                docs_folder.data = {"type": "docs_folder", "project_id": project.id}
                
                # Group by source file
                for source_file, sections in sorted(project_docs.items()):
                    # Extract display name
                    if source_file.startswith("github:"):
                        parts = source_file.split("/", 2)
                        display_name = parts[2] if len(parts) > 2 else source_file
                    else:
                        display_name = source_file
                    
                    # File icon
                    if display_name.endswith(".md"):
                        file_icon = "📝"
                    elif display_name.endswith(".rst"):
                        file_icon = "📄"
                    else:
                        file_icon = "📃"
                    
                    if len(sections) == 1:
                        # Single section - add as leaf directly
                        section = sections[0]
                        leaf = docs_folder.add_leaf(f"{file_icon} {display_name}")
                        leaf.data = {
                            "type": "tree_doc",
                            "doc_id": section.id,
                            "title": section.title,
                            "source_file": source_file,
                            "project_id": project.id,
                        }
                    else:
                        # Multiple sections - add file node with section children
                        file_node = docs_folder.add(f"{file_icon} {display_name} ({len(sections)})", expand=False)
                        file_node.data = {"type": "source_file", "source": source_file, "project_id": project.id}
                        
                        for section in sections:
                            type_icons = {
                                "readme": "📖", "api": "📡", "setup": "🔧",
                                "guide": "📚", "example": "💡", "changelog": "📋",
                                "license": "⚖️", "contributing": "🤝",
                            }
                            icon = type_icons.get(section.section_type, "•")
                            leaf = file_node.add_leaf(f"{icon} {section.title[:40]}")
                            leaf.data = {
                                "type": "tree_doc",
                                "doc_id": section.id,
                                "title": section.title,
                                "source_file": source_file,
                                "project_id": project.id,
                            }
            
            def add_languages_to_node(parent_node, project):
                """Add languages as children of a project node."""
                project_langs = langs_by_project.get(project.id, [])
                if not project_langs:
                    return
                langs_folder = parent_node.add(f"💻 Languages ({len(project_langs)})", expand=False)
                langs_folder.data = {"type": "section", "section": "tab-languages"}
                for lang in project_langs[:10]:  # Limit to 10
                    bar_width = int(lang.percentage / 10) if lang.percentage else 0
                    bar = "█" * bar_width
                    leaf = langs_folder.add_leaf(f"• {lang.language} {lang.percentage or 0:.1f}% {bar}")
                    leaf.data = {
                        "type": "language",
                        "language": lang.language,
                        "percentage": lang.percentage,
                        "project_id": project.id,
                    }
                if len(project_langs) > 10:
                    more = langs_folder.add_leaf(f"... {len(project_langs) - 10} more")
                    more.data = {"type": "section", "section": "tab-languages"}
            
            def add_deps_to_node(parent_node, project):
                """Add dependencies as children of a project node."""
                project_deps = deps_by_project.get(project.id, [])
                if not project_deps:
                    return
                deps_folder = parent_node.add(f"📦 Dependencies ({len(project_deps)})", expand=False)
                deps_folder.data = {"type": "section", "section": "tab-dependencies"}
                # Group by type
                by_type: dict[str, list] = {}
                for dep in project_deps:
                    dt = dep.dep_type or "runtime"
                    if dt not in by_type:
                        by_type[dt] = []
                    by_type[dt].append(dep)
                for dep_type, deps in sorted(by_type.items()):
                    type_icon = {"runtime": "📦", "dev": "🔧", "optional": "❔"}.get(dep_type, "•")
                    type_node = deps_folder.add(f"{type_icon} {dep_type} ({len(deps)})", expand=False)
                    type_node.data = {"type": "section", "section": "tab-dependencies"}
                    for dep in deps[:15]:
                        version = f" {dep.version_spec}" if dep.version_spec else ""
                        leaf = type_node.add_leaf(f"• {dep.name}{version}")
                        leaf.data = {
                            "type": "dependency",
                            "name": dep.name,
                            "version": dep.version_spec,
                            "dep_type": dep.dep_type,
                            "project_id": project.id,
                        }
                    if len(deps) > 15:
                        more = type_node.add_leaf(f"... {len(deps) - 15} more")
                        more.data = {"type": "section", "section": "tab-dependencies"}
            
            def add_contribs_to_node(parent_node, project):
                """Add contributors as children of a project node."""
                project_contribs = contribs_by_project.get(project.id, [])
                if not project_contribs:
                    return
                contribs_folder = parent_node.add(f"👥 Contributors ({len(project_contribs)})", expand=False)
                contribs_folder.data = {"type": "section", "section": "tab-contributors"}
                for contrib in project_contribs[:10]:
                    leaf = contribs_folder.add_leaf(f"• {contrib.username} ({contrib.contributions})")
                    leaf.data = {
                        "type": "contributor",
                        "username": contrib.username,
                        "contributions": contrib.contributions,
                        "profile_url": contrib.profile_url,
                        "project_id": project.id,
                    }
                if len(project_contribs) > 10:
                    more = contribs_folder.add_leaf(f"... {len(project_contribs) - 10} more")
                    more.data = {"type": "section", "section": "tab-contributors"}
            
            def add_issues_to_node(parent_node, project):
                """Add issues as children of a project node."""
                project_issues = issues_by_project.get(project.id, [])
                if not project_issues:
                    return
                open_count = sum(1 for i in project_issues if i.state == "open")
                issues_folder = parent_node.add(f"🐛 Issues ({len(project_issues)}, {open_count} open)", expand=False)
                issues_folder.data = {"type": "section", "section": "tab-issues"}
                for issue in project_issues[:15]:
                    state_icon = "🟢" if issue.state == "open" else "⚫"
                    leaf = issues_folder.add_leaf(f"{state_icon} #{issue.issue_number} {issue.title[:35]}")
                    leaf.data = {
                        "type": "issue",
                        "number": issue.issue_number,
                        "title": issue.title,
                        "state": issue.state,
                        "author": issue.author,
                        "project_id": project.id,
                        "owner": project.github_owner,
                        "repo": project.github_repo,
                        "url": project.github_issues_url(issue.issue_number) if project.github_owner else None,
                    }
                if len(project_issues) > 15:
                    more = issues_folder.add_leaf(f"... {len(project_issues) - 15} more")
                    more.data = {"type": "section", "section": "tab-issues"}
            
            def add_prs_to_node(parent_node, project):
                """Add pull requests as children of a project node."""
                project_prs = prs_by_project.get(project.id, [])
                if not project_prs:
                    return
                open_count = sum(1 for p in project_prs if p.state == "open")
                prs_folder = parent_node.add(f"🔀 Pull Requests ({len(project_prs)}, {open_count} open)", expand=False)
                prs_folder.data = {"type": "section", "section": "tab-prs"}
                for pr in project_prs[:15]:
                    if pr.is_merged:
                        state_icon = "🟣"
                    elif pr.state == "open":
                        state_icon = "🟢"
                    else:
                        state_icon = "🔴"
                    leaf = prs_folder.add_leaf(f"{state_icon} #{pr.pr_number} {pr.title[:35]}")
                    leaf.data = {
                        "type": "pr",
                        "number": pr.pr_number,
                        "title": pr.title,
                        "state": pr.state,
                        "is_merged": pr.is_merged,
                        "author": pr.author,
                        "project_id": project.id,
                        "owner": project.github_owner,
                        "repo": project.github_repo,
                        "url": project.github_pulls_url(pr.pr_number) if project.github_owner else None,
                    }
                if len(project_prs) > 15:
                    more = prs_folder.add_leaf(f"... {len(project_prs) - 15} more")
                    more.data = {"type": "section", "section": "tab-prs"}
            
            def add_releases_to_node(parent_node, project):
                """Add releases as children of a project node."""
                project_releases = releases_by_project.get(project.id, [])
                if not project_releases:
                    return
                releases_folder = parent_node.add(f"🏷️ Releases ({len(project_releases)})", expand=False)
                releases_folder.data = {"type": "section", "section": "tab-releases"}
                for release in project_releases[:10]:
                    type_icon = "⚠️" if release.is_prerelease else ("📝" if release.is_draft else "•")
                    leaf = releases_folder.add_leaf(f"{type_icon} {release.tag_name}")
                    leaf.data = {
                        "type": "release",
                        "tag": release.tag_name,
                        "name": release.name,
                        "is_prerelease": release.is_prerelease,
                        "is_draft": release.is_draft,
                        "project_id": project.id,
                        "owner": project.github_owner,
                        "repo": project.github_repo,
                        "url": f"{project.github_url}/releases/tag/{release.tag_name}" if project.github_url else None,
                    }
                if len(project_releases) > 10:
                    more = releases_folder.add_leaf(f"... {len(project_releases) - 10} more")
                    more.data = {"type": "section", "section": "tab-releases"}
            
            def add_branches_to_node(parent_node, project):
                """Add branches as children of a project node."""
                project_branches = branches_by_project.get(project.id, [])
                if not project_branches:
                    return
                branches_folder = parent_node.add(f"🌿 Branches ({len(project_branches)})", expand=False)
                branches_folder.data = {"type": "section", "section": "tab-branches"}
                for branch in project_branches[:10]:
                    default_icon = "⭐" if branch.is_default else ""
                    protected_icon = "🔒" if branch.is_protected else ""
                    leaf = branches_folder.add_leaf(f"• {branch.name} {default_icon}{protected_icon}")
                    leaf.data = {
                        "type": "branch",
                        "name": branch.name,
                        "is_default": branch.is_default,
                        "is_protected": branch.is_protected,
                        "project_id": project.id,
                        "owner": project.github_owner,
                        "repo": project.github_repo,
                        "url": f"{project.github_url}/tree/{branch.name}" if project.github_url else None,
                    }
                if len(project_branches) > 10:
                    more = branches_folder.add_leaf(f"... {len(project_branches) - 10} more")
                    more.data = {"type": "section", "section": "tab-branches"}

            def add_deltas_to_node(parent_node, project):
                """Add deltas as children of a project node."""
                project_deltas = deltas_by_project.get(project.id, [])
                if not project_deltas:
                    return
                # Count by phase
                active_count = sum(1 for d in project_deltas if d.phase not in [DeltaPhase.COMPLETE, DeltaPhase.ABANDONED])
                deltas_folder = parent_node.add(f"🔺 Deltas ({len(project_deltas)}, {active_count} active)", expand=False)
                deltas_folder.data = {"type": "section", "section": "tab-deltas"}
                phase_icons = {
                    DeltaPhase.BRAINSTORM: "💡",
                    DeltaPhase.PLANNING: "📋",
                    DeltaPhase.IMPLEMENTATION: "⚙️",
                    DeltaPhase.REVIEW: "🔍",
                    DeltaPhase.DOCUMENTATION: "📝",
                    DeltaPhase.COMPLETE: "✅",
                    DeltaPhase.ABANDONED: "❌",
                }
                for delta in project_deltas[:15]:
                    phase_icon = phase_icons.get(delta.phase, "•")
                    link_items = delta_links_by_delta.get(delta.id, [])
                    delta_node = deltas_folder.add(
                        f"{phase_icon} {delta.name}: {delta.title[:30]}",
                        expand=False,
                    ) if link_items else deltas_folder.add_leaf(
                        f"{phase_icon} {delta.name}: {delta.title[:30]}"
                    )
                    delta_node.data = {
                        "type": "delta",
                        "delta_id": delta.id,
                        "name": delta.name,
                        "title": delta.title,
                        "phase": delta.phase.value,
                        "project_id": project.id,
                    }
                    if link_items:
                        links_node = delta_node.add(f"Links ({len(link_items)})", expand=False)
                        links_node.data = {"type": "section", "section": "tab-deltas"}
                        for link in link_items[:TREE_ENTITY_LIMIT]:
                            link_type = link.link_type
                            target_id = link.target_id
                            target_name = link.target_name or ""
                            label = None
                            nav_data = None
                            if link_type == "issue":
                                number = target_id
                                if number is None and target_name:
                                    try:
                                        number = int(target_name)
                                    except ValueError:
                                        number = None
                                if number is not None:
                                    issue_title = next(
                                        (issue.title for issue in issues_by_project.get(project.id, []) if issue.issue_number == number),
                                        None,
                                    )
                                    label = f"Issue #{number}"
                                    if issue_title:
                                        label = f"Issue #{number}: {issue_title[:30]}"
                                    nav_data = {
                                        "type": "issue",
                                        "number": number,
                                        "title": issue_title,
                                        "project_id": project.id,
                                        "owner": project.github_owner,
                                        "repo": project.github_repo,
                                        "url": project.github_issues_url(number) if project.github_owner else None,
                                    }
                                else:
                                    label = f"Issue {target_name or '?'}"
                            elif link_type == "pr":
                                number = target_id
                                if number is None and target_name:
                                    try:
                                        number = int(target_name)
                                    except ValueError:
                                        number = None
                                if number is not None:
                                    pr_title = next(
                                        (pr.title for pr in prs_by_project.get(project.id, []) if pr.pr_number == number),
                                        None,
                                    )
                                    label = f"PR #{number}"
                                    if pr_title:
                                        label = f"PR #{number}: {pr_title[:30]}"
                                    nav_data = {
                                        "type": "pr",
                                        "number": number,
                                        "title": pr_title,
                                        "project_id": project.id,
                                        "owner": project.github_owner,
                                        "repo": project.github_repo,
                                        "url": project.github_pulls_url(number) if project.github_owner else None,
                                    }
                                else:
                                    label = f"PR {target_name or '?'}"
                            elif link_type == "branch":
                                branch_name = target_name or (str(target_id) if target_id is not None else "")
                                label = f"Branch {branch_name or '?'}"
                                if branch_name:
                                    branch_info = next(
                                        (branch for branch in branches_by_project.get(project.id, []) if branch.name == branch_name),
                                        None,
                                    )
                                    nav_data = {
                                        "type": "branch",
                                        "name": branch_name,
                                        "is_default": branch_info.is_default if branch_info else False,
                                        "is_protected": branch_info.is_protected if branch_info else False,
                                        "project_id": project.id,
                                        "owner": project.github_owner,
                                        "repo": project.github_repo,
                                        "url": project.github_branch_url(branch_name) if project.github_owner else None,
                                    }
                            elif link_type == "doc":
                                doc_title = target_name or (str(target_id) if target_id is not None else "")
                                label = f"Doc {doc_title or '?'}"
                                if doc_title:
                                    nav_data = {
                                        "type": "doc",
                                        "title": doc_title,
                                        "project_id": project.id,
                                    }
                            elif link_type == "delta":
                                target_delta = None
                                if target_id is not None:
                                    target_delta = deltas_by_id.get(target_id)
                                if target_delta is None and target_name:
                                    target_delta = deltas_by_project_name.get((project.id, target_name))
                                if target_delta:
                                    label = f"Delta {target_delta.name}: {target_delta.title[:30]}"
                                    nav_data = {
                                        "type": "delta",
                                        "delta_id": target_delta.id,
                                        "name": target_delta.name,
                                        "title": target_delta.title,
                                        "phase": target_delta.phase.value,
                                        "project_id": target_delta.project_id,
                                    }
                                else:
                                    label = f"Delta {target_name or (str(target_id) if target_id is not None else '?')}"
                            else:
                                label = f"{link_type}: {target_name or target_id or '?'}"
                            link_leaf = links_node.add_leaf(label)
                            if nav_data:
                                link_leaf.data = nav_data
                        if len(link_items) > TREE_ENTITY_LIMIT:
                            more = links_node.add_leaf(f"... {len(link_items) - TREE_ENTITY_LIMIT} more")
                            more.data = {"type": "section", "section": "tab-deltas"}
                if len(project_deltas) > 15:
                    more = deltas_folder.add_leaf(f"... {len(project_deltas) - 15} more")
                    more.data = {"type": "section", "section": "tab-deltas"}

            def add_all_data_to_node(parent_node, project):
                """Add all entity data folders to a project node."""
                add_docs_to_node(parent_node, project)
                add_languages_to_node(parent_node, project)
                add_deps_to_node(parent_node, project)
                add_contribs_to_node(parent_node, project)
                add_branches_to_node(parent_node, project)
                add_releases_to_node(parent_node, project)
                add_issues_to_node(parent_node, project)
                add_prs_to_node(parent_node, project)
                add_deltas_to_node(parent_node, project)
            
            first_project = None
            for group in sorted_groups:
                group_data = groups[group]
                
                # Count items in this group
                item_count = len(group_data.get("_items", []))
                for subgroup_items in group_data.values():
                    if isinstance(subgroup_items, list) and subgroup_items != group_data.get("_items"):
                        item_count += len(subgroup_items)
                
                group_node = project_tree.root.add(f"{group} ({item_count})", expand=group.startswith("🏢"))
                # A category is a selectable thing, not just a heading. An
                # owner group carries its owner so selecting it can show the
                # aggregate for that owner rather than doing nothing -- the
                # same move as a project node showing that project.
                owner = group[2:].strip() if group.startswith(ORG_GROUP_PREFIX) else None
                group_node.data = {"type": "group", "name": group, "owner": owner}
                
                # Add direct items (no subgroup)
                for display, project in group_data.get("_items", []):
                    # Check if this project has any entity data
                    has_data = any([
                        project.id in docs_by_project,
                        project.id in langs_by_project,
                        project.id in deps_by_project,
                        project.id in contribs_by_project,
                        project.id in issues_by_project,
                        project.id in prs_by_project,
                        project.id in releases_by_project,
                        project.id in branches_by_project,
                        project.id in deltas_by_project,
                    ])
                    
                    if has_data:
                        # Add as node with entity children
                        project_node = group_node.add(display, expand=False)
                        project_node.data = {"type": "project", "project": project}
                        add_all_data_to_node(project_node, project)
                    else:
                        # Add as leaf
                        leaf = group_node.add_leaf(display)
                        leaf.data = {"type": "project", "project": project}
                    
                    if first_project is None:
                        first_project = project
                
                # Add subgroups (repos with entities)
                for subgroup_key, items in sorted(group_data.items()):
                    if subgroup_key == "_items":
                        continue
                    subgroup_node = group_node.add(f"📂 {subgroup_key} ({len(items)})", expand=False)
                    subgroup_node.data = {"type": "subgroup", "name": subgroup_key}
                    for display, project in items:
                        leaf = subgroup_node.add_leaf(display)
                        leaf.data = {"type": "project", "project": project}
                        if first_project is None:
                            first_project = project
        
        # Update stats
        try:
            self.query_one(StatsWidget).refresh_stats()
        except Exception:
            pass
        
        # Auto-select first project if requested
        if auto_select and first_project:
            self.selected_project = first_project
            self.show_project_details(first_project)
    
    @on(Markdown.LinkClicked, "#dossier-view")
    def on_dossier_link_clicked(self, event: Markdown.LinkClicked) -> None:
        """Handle link clicks in the dossier view."""
        href = event.href
        
        # Handle internal dossier:// links
        if href.startswith("dossier://"):
            event.prevent_default()
            self._handle_dossier_link(href[10:])  # Remove "dossier://"
        elif href.startswith("http://") or href.startswith("https://"):
            # Let external links open in browser (default behavior)
            import webbrowser
            event.prevent_default()
            webbrowser.open(href)
        elif href.startswith("file://") or href.endswith(".md") or ".." in href:
            # Handle file links - these are relative doc links, prevent default file opening
            event.prevent_default()
            # Try to find matching doc in database
            if self.selected_project:
                # Extract filename from path
                filename = href.split("/")[-1].replace(".md", "")
                self._handle_dossier_link(f"doc/{filename}")
    
    def _handle_dossier_link(self, path: str) -> None:
        """Handle internal dossier:// links.
        
        Link formats:
        - dossier://tab/dossier - Switch to Dossier tab
        - dossier://tab/projects - Switch to Projects tab
        - dossier://tab/deltas - Switch to Deltas tab
        - dossier://tab/languages - Switch to Projects > Languages
        - dossier://lang/python - Link language entity
        - dossier://pkg/fastapi - Link dependency entity  
        - dossier://user/username - Show contributor
        - dossier://issue/123 - Show issue viewer
        - dossier://pr/456 - Show PR viewer
        - dossier://release/v1.0.0 - Show release viewer
        - dossier://branch/main - Show branch viewer
        - dossier://doc/filename - Show doc viewer
        """
        parts = path.split("/", 1)
        if len(parts) < 2:
            return
        
        link_type, value = parts[0], parts[1]
        project = self.selected_project
        if not project:
            return
        
        if link_type == "tab":
            # Switch to tab
            tab_id = f"tab-{value}"
            self._activate_tab(tab_id)
        
        elif link_type == "lang":
            # Link language entity
            self._link_language_project({
                "language": value,
                "project_id": project.id,
            })
        
        elif link_type == "pkg":
            # Link dependency entity
            self._link_dependency_project({
                "name": value,
                "project_id": project.id,
            })
        
        elif link_type == "user":
            # Show contributor info
            url = f"https://github.com/{value}"
            content = f"# {value}\n\n[View on GitHub]({url})"
            self.push_screen(ContentViewerScreen(
                title=f"Contributor: {value}",
                content=content,
                url=url
            ))
        
        elif link_type == "issue":
            # Show issue viewer
            try:
                issue_number = int(value)
                url = project.github_issues_url(issue_number) if project.github_owner else None
                self._show_issue_viewer({
                    "number": issue_number,
                    "project_id": project.id,
                    "owner": project.github_owner,
                    "repo": project.github_repo,
                    "url": url,
                })
            except ValueError:
                pass
        
        elif link_type == "pr":
            # Show PR viewer
            try:
                pr_number = int(value)
                url = project.github_pulls_url(pr_number) if project.github_owner else None
                self._show_pr_viewer({
                    "number": pr_number,
                    "project_id": project.id,
                    "owner": project.github_owner,
                    "repo": project.github_repo,
                    "url": url,
                })
            except ValueError:
                pass
        
        elif link_type == "release":
            # Show release viewer
            url = f"{project.github_url}/releases/tag/{value}" if project.github_url else None
            content = f"# Release: {value}\n\n**Tag:** `{value}`\n\n"
            if url:
                content += f"[View Release on GitHub]({url})"
            self.push_screen(ContentViewerScreen(
                title=f"Release: {value}",
                content=content,
                url=url
            ))
        
        elif link_type == "branch":
            # Show branch viewer
            url = f"{project.github_url}/tree/{value}" if project.github_url else None
            content = f"# Branch: {value}\n\n"
            if url:
                content += f"[View on GitHub]({url})"
            self.push_screen(ContentViewerScreen(
                title=f"Branch: {value}",
                content=content,
                url=url
            ))
        
        elif link_type == "doc":
            # Find and show doc
            with self.session_factory() as session:
                doc = session.exec(
                    select(DocumentSection)
                    .where(DocumentSection.project_id == project.id)
                    .where(DocumentSection.source_file.contains(value))
                ).first()
                if doc:
                    self._show_file_viewer(project.id, doc.source_file)
    
    _search_debounce_timer: object | None = None  # Timer object for cancellation
    _pending_search: str = ""
    
    @on(Input.Changed, "#search-input")
    def filter_projects(self, event: Input.Changed) -> None:
        """Filter projects with debouncing to avoid excessive queries."""
        search_text = event.value.strip()
        
        # Handle commands starting with :
        if search_text.startswith(":"):
            return  # Don't filter, let on_input_submitted handle commands
        
        self._pending_search = search_text
        
        # Cancel any existing timer
        if self._search_debounce_timer is not None:
            self._search_debounce_timer.stop()
        
        # Schedule new debounced search
        self._search_debounce_timer = self.set_timer(
            DEBOUNCE_MS / 1000, 
            self._execute_debounced_search
        )
    
    def _execute_debounced_search(self) -> None:
        """Execute search after debounce period."""
        self._search_debounce_timer = None
        self.load_projects(search=self._pending_search)
    
    @on(Input.Submitted, "#search-input")
    def on_search_submitted(self, event: Input.Submitted) -> None:
        """Handle search/command submission with Enter key."""
        text = event.value.strip()
        search_input = self.query_one("#search-input", Input)
        
        # Handle commands starting with :
        if text.startswith(":"):
            self._handle_command(text[1:])  # Strip the leading :
            search_input.value = ""
            search_input.blur()
            return
        
        # Regular search - cancel pending debounce and search immediately
        if self._search_debounce_timer is not None:
            self._search_debounce_timer.stop()
            self._search_debounce_timer = None
        
        self.load_projects(search=text)
        
        # Focus the project tree after search
        self.query_one("#project-tree", Tree).focus()
    
    def _handle_command(self, command: str) -> None:
        """Handle colon-prefixed commands like vim."""
        parts = command.split(None, 1)  # Split into command and args
        cmd = parts[0].lower() if parts else ""
        args = parts[1] if len(parts) > 1 else ""
        
        # Command aliases
        commands = {
            "q": self._cmd_quit,
            "quit": self._cmd_quit,
            "r": self._cmd_refresh,
            "refresh": self._cmd_refresh,
            "s": self._cmd_sync,
            "sync": self._cmd_sync,
            "a": self._cmd_add,
            "add": self._cmd_add,
            "d": self._cmd_delete,
            "del": self._cmd_delete,
            "delete": self._cmd_delete,
            "h": self._cmd_help,
            "help": self._cmd_help,
            "o": self._cmd_open,
            "open": self._cmd_open,
            "filter": self._cmd_filter,
            "f": self._cmd_filter,
            "sort": self._cmd_sort,
            "clear": self._cmd_clear,
            "starred": self._cmd_starred,
            "star": self._cmd_starred,
        }
        
        handler = commands.get(cmd)
        if handler:
            handler(args)
        else:
            self.notify(f"Unknown command: {cmd}", severity="error")
            self._show_command_help()
    
    def _cmd_quit(self, args: str) -> None:
        """Quit the application."""
        self._save_view_state()
        self.exit()
    
    def _cmd_refresh(self, args: str) -> None:
        """Refresh project list."""
        self.action_refresh()
        self.notify("Refreshed")
    
    def _cmd_sync(self, args: str) -> None:
        """Sync selected or specified project."""
        if args:
            # Sync specific project by name
            with self.session_factory() as session:
                project = session.exec(
                    select(Project).where(Project.full_name.ilike(f"%{args}%"))
                ).first()
                if project:
                    self.selected_project = project
        self.action_sync()
    
    def _cmd_add(self, args: str) -> None:
        """Add a project."""
        if args:
            # Direct add with owner/repo
            self._add_project_direct(args)
        else:
            self.action_add()
    
    def _cmd_delete(self, args: str) -> None:
        """Delete selected project(s)."""
        self.action_delete()
    
    def _cmd_help(self, args: str) -> None:
        """Show help."""
        self.action_help()
    
    def _cmd_open(self, args: str) -> None:
        """Open in browser."""
        self.action_open_github()
    
    def _cmd_filter(self, args: str) -> None:
        """Set filter mode."""
        arg = args.lower().strip()
        if arg in ("all", "a", ""):
            self.filter_synced = None
            self.filter_starred = None
        elif arg in ("synced", "s"):
            self.filter_synced = True
        elif arg in ("unsynced", "u"):
            self.filter_synced = False
        elif arg in ("starred", "star", "*"):
            self.filter_starred = True
        else:
            self.notify(f"Unknown filter: {arg}. Use: all, synced, unsynced, starred", severity="warning")
            return
        
        self._update_filter_buttons()
        self.load_projects()
        self.notify(f"Filter: {arg or 'all'}")
    
    def _cmd_sort(self, args: str) -> None:
        """Set sort mode."""
        arg = args.lower().strip()
        if arg in ("stars", "s", ""):
            self.sort_by = "stars"
        elif arg in ("name", "n", "a"):
            self.sort_by = "name"
        elif arg in ("recent", "r", "synced"):
            self.sort_by = "synced"
        else:
            self.notify(f"Unknown sort: {arg}. Use: stars, name, recent", severity="warning")
            return
        
        self._update_sort_ui()
        self.load_projects()
        self.notify(f"Sort: {self.sort_by}")
    
    def _cmd_clear(self, args: str) -> None:
        """Clear search and filters."""
        self.filter_synced = None
        self.filter_starred = None
        self.filter_entity_type = "all"
        self.filter_language = ""
        self._pending_search = ""
        self._update_filter_buttons()
        search_input = self.query_one("#search-input", Input)
        search_input.value = ""
        self.load_projects()
        self.notify("Cleared filters")
    
    def _cmd_starred(self, args: str) -> None:
        """Toggle starred filter."""
        self.filter_starred = not self.filter_starred if self.filter_starred else True
        self._update_filter_buttons()
        self.load_projects()
        self.notify(f"Starred: {'on' if self.filter_starred else 'off'}")
    
    def _show_command_help(self) -> None:
        """Show available commands."""
        self.notify(
            "Commands: :q :r :s :a :d :h :o :filter :sort :clear :starred",
            timeout=5
        )
    
    def _add_project_direct(self, repo_name: str) -> None:
        """Add a project directly by name without dialog."""
        # Normalize input
        repo_name = repo_name.strip()
        if "/" not in repo_name:
            self.notify("Use format: owner/repo", severity="error")
            return
        
        with self.session_factory() as session:
            # Check if already exists
            existing = session.exec(
                select(Project).where(Project.full_name == repo_name)
            ).first()
            if existing:
                self.notify(f"Project '{repo_name}' already exists")
                self.selected_project = existing
                self.load_projects()
                return
            
            # Create new project
            project = Project(
                name=repo_name.split("/")[-1],
                full_name=repo_name,
                synced=False,
            )
            session.add(project)
            session.commit()
            session.refresh(project)
            
            self.notify(f"Added '{repo_name}'")
            self.load_projects()
            
            # Select the new project
            self.selected_project = project

    @on(Tree.NodeSelected, "#delta-board")
    def on_delta_board_selected(self, event: Tree.NodeSelected) -> None:
        """Selecting a delta selects the project it belongs to.

        Every per-project tab reads `selected_project`. A board that set only
        the delta would leave the rest of the screen describing whatever was
        selected before -- stale content that looks current.
        """
        data = event.node.data
        if not data or data.get("type") != "delta":
            return
        project_id = data.get("project_id")
        if project_id is None:
            return
        with self.session_factory() as session:
            project = session.get(Project, project_id)
            if project is None:
                return
            session.expunge(project)
        self.selected_project = project
        self.show_project_details(project)

    @on(Tree.NodeSelected, "#project-tree")
    def on_project_tree_selected(self, event: Tree.NodeSelected) -> None:
        """Handle project tree node selection."""
        node = event.node
        if not node.data:
            return
        
        nav_data = node.data
        nav_type = nav_data.get("type")
        
        if nav_type == "project":
            project = nav_data.get("project")
            if project:
                self.selected_project = project
                self.show_project_details(project)
                # Switch to configured default tab, unless navigating from tree
                if not self._navigating_from_tree:
                    self._activate_tab(self._config.default_tab)
                elif self._tree_target_tab:
                    self._activate_tab(self._tree_target_tab)
                    self._tree_target_tab = None
                self._navigating_from_tree = False
        
        elif nav_type == "group":
            # Selecting a category shows that category's aggregate. For an
            # owner that is the org overview, scoped to them.
            owner = nav_data.get("owner")
            if owner:
                self.show_org_overview(owner)

        elif nav_type == "tree_doc":
            # Open doc viewer directly from tree
            doc_id = nav_data.get("doc_id")
            if doc_id:
                self._show_tree_doc_viewer(doc_id, nav_data.get("source_file"))
        
        elif nav_type == "source_file":
            # Open entire file with all sections combined
            source = nav_data.get("source")
            project_id = nav_data.get("project_id")
            if source and project_id:
                self._show_file_viewer(project_id, source)

        elif nav_type == "doc":
            # Show documentation content in viewer
            self._show_doc_viewer(nav_data)
        
        elif nav_type == "section":
            # Switch to the corresponding tab
            section = nav_data.get("section")
            if section and section.startswith("tab-"):
                self._activate_tab(section)
        
        elif nav_type == "language":
            # Link language entity
            self._link_language_project(nav_data)
        
        elif nav_type == "dependency":
            # Link dependency entity
            self._link_dependency_project(nav_data)
        
        elif nav_type == "contributor":
            # Show contributor info in viewer
            username = nav_data.get("username")
            contributions = nav_data.get("contributions", 0)
            url = nav_data.get("profile_url") or (f"https://github.com/{username}" if username else None)
            content = f"# {username}\n\n**Contributions:** {contributions}\n\n[View on GitHub]({url})" if url else f"# {username}\n\n**Contributions:** {contributions}"
            self.push_screen(ContentViewerScreen(
                title=f"Contributor: {username}",
                content=content,
                url=url
            ))
        
        elif nav_type == "issue":
            # Show issue in viewer
            self._show_issue_viewer(nav_data)
        
        elif nav_type == "pr":
            # Show PR in viewer
            self._show_pr_viewer(nav_data)
        
        elif nav_type == "release":
            # Show release info in viewer
            tag = nav_data.get("tag")
            name = nav_data.get("name") or tag
            is_prerelease = nav_data.get("is_prerelease", False)
            is_draft = nav_data.get("is_draft", False)
            url = nav_data.get("url")
            content = f"# Release: {name}\n\n**Tag:** `{tag}`\n\n"
            if is_prerelease:
                content += "⚠️ **Pre-release**\n\n"
            if is_draft:
                content += "📝 **Draft**\n\n"
            if url:
                content += f"[View Release on GitHub]({url})"
            self.push_screen(ContentViewerScreen(
                title=f"Release: {tag}",
                content=content,
                url=url
            ))
        
        elif nav_type == "branch":
            # Show branch info in viewer
            branch_name = nav_data.get("name")
            is_default = nav_data.get("is_default", False)
            is_protected = nav_data.get("is_protected", False)
            url = nav_data.get("url")
            content = f"# Branch: {branch_name}\n\n"
            if is_default:
                content += "⭐ **Default branch**\n\n"
            if is_protected:
                content += "🔒 **Protected branch**\n\n"
            if url:
                content += f"[View on GitHub]({url})"
            self.push_screen(ContentViewerScreen(
                title=f"Branch: {branch_name}",
                content=content,
                url=url
            ))

        elif nav_type == "delta":
            # Link delta as project and navigate to it
            self._link_delta_project(nav_data)

    def _activate_tab(self, tab_id: str) -> None:
        """Activate a main or project sub-tab by id."""
        if not tab_id:
            return
        try:
            main_tabs = self.query_one("#project-tabs", TabbedContent)
        except Exception:
            return
        # There is one `TabbedContent`. The two-step routing this replaced was
        # left over from a nested-tab design that was not adopted: it set the
        # active tab to `tab-details` and then to the requested one on the same
        # widget, and it listed neither `tab-overview` nor `tab-governance` --
        # so activating either silently did nothing.
        if any(pane.id == tab_id for pane in main_tabs.query(TabPane)):
            main_tabs.active = tab_id

    def _get_active_tab_id(self) -> Optional[str]:
        """Return the active tab id across main and project tabs."""
        try:
            main_tabs = self.query_one("#project-tabs", TabbedContent)
        except Exception:
            return None
        if main_tabs.active == "tab-details":
            try:
                project_tabs = self.query_one("#project-tabs", TabbedContent)
                return project_tabs.active
            except Exception:
                return "tab-details"
        return main_tabs.active

    def show_project_details(self, project: Project) -> None:
        """Show details for the selected project.
        
        Optimized to only load data for the currently visible tab,
        with lazy loading for other tabs when they're activated.
        """
        # Store current project ID for lazy loading
        self._scope_owner = None
        self._current_project_id = project.id
        self._current_project = project

        # The intersections panel is cheap and always correct for the current
        # selection; leaving it on the previous project would show one repo's
        # relationships under another repo's name.
        try:
            self.query_one(IntersectionsPanel).show_for(project)
        except Exception:
            pass
        
        # Update detail panel
        detail_panel = self.query_one("#project-detail", ProjectDetailPanel)
        detail_panel.project = project
        # Governance is joined by name at read time -- never stored as a key,
        # because github sync rebuilds the project tables and would take it with
        # them. The panel gets the row and how it was matched.
        from dossier import governance as gov

        with self.session_factory() as session:
            detail_panel.governance = gov.governance_for_project(session, project)
        
        # Load dossier view (always needed as default tab)
        self.load_dossier_view(project)
        
        # Mark tabs as needing refresh
        self._tabs_loaded = {"tab-dossier"}
        
        # Load the currently active tab
        active_tab = self._get_active_tab_id()
        if active_tab and active_tab != "tab-dossier":
            self._load_tab_data(active_tab)

    @on(TabbedContent.TabActivated, "#project-tabs")
    def on_main_tab_activated(self, event: TabbedContent.TabActivated) -> None:
        """Lazy load tab data when a main tab is activated."""
        if not hasattr(self, "_current_project_id"):
            return
        if event.pane.id == "tab-details":
            project_tabs = self.query_one("#project-tabs", TabbedContent)
            self._load_tab_data(project_tabs.active)
        elif event.pane.id == "tab-deltas":
            self._load_tab_data("tab-deltas")
    
    @on(TabbedContent.TabActivated, "#project-tabs")
    def on_tab_activated(self, event: TabbedContent.TabActivated) -> None:
        """Lazy load tab data when tab is activated."""
        if event.pane.id == "tab-governance":
            # Handled before the project guard below on purpose: governance is
            # org-wide and has to render with nothing selected. Hanging it off
            # the per-project path would leave it permanently blank, and blank
            # reads as "nothing is wrong".
            self._load_governance_tab()
            return
        if event.pane.id == "tab-disk":
            # Same bypass, same reason: disk is machine-wide. It belongs to no
            # project, so the guard below would leave it blank until somebody
            # happened to select one -- and a blank disk table reads as a
            # machine with nothing on it.
            self._load_disk_tab()
            return
        if hasattr(self, "_current_project_id"):
            # Use pane.id (the TabPane ID like "tab-docs") not tab.id (which is "--content-tab-tab-docs")
            self._load_tab_data(event.pane.id)
    
    def _load_tab_data(self, tab_id: str) -> None:
        """Load data for a specific tab if not already loaded."""
        if not hasattr(self, "_tabs_loaded"):
            self._tabs_loaded = set()
        
        if tab_id in self._tabs_loaded:
            return  # Already loaded
        
        self._tabs_loaded.add(tab_id)

        if tab_id == "tab-disk":
            self._load_disk_tab()
            return

        if tab_id == "tab-governance":
            self._load_governance_tab()
            return

        # A facet reads the same table at either scope, so the tab does not
        # need to know which one it is showing -- only which facet it holds.
        facet = FACET_BY_TAB.get(tab_id)
        owner = getattr(self, "_scope_owner", None)
        if facet is not None and owner:
            self._render_facet_at_org(facet, owner)
            return

        project = getattr(self, "_current_project", None)
        if not project:
            return
        
        # Map tab IDs to loader methods
        loaders = {
            "tab-docs": self._load_docs_tab,
            "tab-languages": self._load_languages_tab,
            "tab-branches": self._load_branches_tab,
            "tab-dependencies": self._load_dependencies_tab,
            "tab-contributors": self._load_contributors_tab,
            "tab-issues": self._load_issues_tab,
            "tab-prs": self._load_prs_tab,
            "tab-releases": self._load_releases_tab,
            "tab-components": self._load_components_tab,
            "tab-deltas": self._load_deltas_tab,
        }
        
        loader = loaders.get(tab_id)
        if loader:
            loader(project)
    
    def _load_docs_tab(self, project: Project) -> None:
        """Load documentation sections as a tree grouped by source file."""
        docs_tree = self.query_one("#docs-tree", Tree)
        docs_tree.clear()
        docs_tree.root.expand()
        
        with self.session_factory() as session:
            sections = session.exec(
                select(DocumentSection)
                .where(DocumentSection.project_id == project.id)
                .order_by(DocumentSection.source_file, DocumentSection.order)
            ).all()
            
            if not sections:
                empty_node = docs_tree.root.add_leaf("(No documentation sections)")
                empty_node.data = {"type": "empty"}
            else:
                # Build list for navigation
                doc_list = []
                for section in sections:
                    session.expunge(section)
                    doc_list.append(section)
                
                # Store doc list for navigation
                self._current_doc_list = doc_list
                
                # Group by source file
                groups: dict[str, list] = {}
                for section in doc_list:
                    source = section.source_file or "(No source)"
                    if source not in groups:
                        groups[source] = []
                    groups[source].append(section)
                
                # Build tree structure
                for source_file, file_sections in sorted(groups.items()):
                    # Extract just the filename for display
                    if source_file.startswith("github:"):
                        # github:owner/repo/path/to/file.md -> path/to/file.md
                        parts = source_file.split("/", 2)
                        display_name = parts[2] if len(parts) > 2 else source_file
                    else:
                        display_name = source_file
                    
                    # File icon based on extension
                    if display_name.endswith(".md"):
                        file_icon = "📝"
                    elif display_name.endswith(".rst"):
                        file_icon = "📄"
                    elif display_name.endswith(".txt"):
                        file_icon = "📃"
                    else:
                        file_icon = "📄"
                    
                    file_node = docs_tree.root.add(f"{file_icon} {display_name} ({len(file_sections)})", expand=True)
                    file_node.data = {"type": "source_file", "source": source_file, "project_id": project.id}
                    
                    for section in file_sections:
                        # Type icons
                        type_icons = {
                            "readme": "📖",
                            "api": "📡",
                            "setup": "🔧",
                            "guide": "📚",
                            "example": "💡",
                            "changelog": "📋",
                            "license": "⚖️",
                            "contributing": "🤝",
                        }
                        icon = type_icons.get(section.section_type, "•")
                        
                        # Find index in full list for navigation
                        doc_index = doc_list.index(section)
                        
                        leaf = file_node.add_leaf(f"{icon} {section.title[:50]}")
                        leaf.data = {
                            "type": "doc",
                            "doc_id": section.id,
                            "title": section.title,
                            "source_file": section.source_file,
                            "project_id": section.project_id,
                            "doc_index": doc_index,
                        }
    
    def _load_languages_tab(self, project: Project) -> None:
        """Render the `languages` facet for one repository.

        The query lives in `dossier.facets`, which the overview reads
        too. Two queries over one table drift into two vocabularies for
        the same column, and nothing fails when they do.
        """
        self._render_facet_for_project(FACET_BY_TAB["tab-languages"], project)

    def _load_branches_tab(self, project: Project) -> None:
        """Render the `branches` facet for one repository.

        The query lives in `dossier.facets`, which the overview reads
        too. Two queries over one table drift into two vocabularies for
        the same column, and nothing fails when they do.
        """
        self._render_facet_for_project(FACET_BY_TAB["tab-branches"], project)

    def _load_dependencies_tab(self, project: Project) -> None:
        """Render the `dependencies` facet for one repository.

        The query lives in `dossier.facets`, which the overview reads
        too. Two queries over one table drift into two vocabularies for
        the same column, and nothing fails when they do.
        """
        self._render_facet_for_project(FACET_BY_TAB["tab-dependencies"], project)

    def _load_contributors_tab(self, project: Project) -> None:
        """Render the `contributors` facet for one repository.

        The query lives in `dossier.facets`, which the overview reads
        too. Two queries over one table drift into two vocabularies for
        the same column, and nothing fails when they do.
        """
        self._render_facet_for_project(FACET_BY_TAB["tab-contributors"], project)

    def _load_issues_tab(self, project: Project) -> None:
        """Render the `issues` facet for one repository.

        The query lives in `dossier.facets`, which the overview reads
        too. Two queries over one table drift into two vocabularies for
        the same column, and nothing fails when they do.
        """
        self._render_facet_for_project(FACET_BY_TAB["tab-issues"], project)

    def _load_prs_tab(self, project: Project) -> None:
        """Render the `prs` facet for one repository.

        The query lives in `dossier.facets`, which the overview reads
        too. Two queries over one table drift into two vocabularies for
        the same column, and nothing fails when they do.
        """
        self._render_facet_for_project(FACET_BY_TAB["tab-prs"], project)

    def _load_releases_tab(self, project: Project) -> None:
        """Render the `releases` facet for one repository.

        The query lives in `dossier.facets`, which the overview reads
        too. Two queries over one table drift into two vocabularies for
        the same column, and nothing fails when they do.
        """
        self._render_facet_for_project(FACET_BY_TAB["tab-releases"], project)

    @staticmethod
    def _disk_size(count) -> str:
        """Bytes at a readable scale, never rounded to nothing.

        A 40MB cache shown as `0.0GB` reads as empty, which is the same lie as
        showing an unmeasured target as zero.
        """
        if count is None:
            return "unknown"
        negative = count < 0
        value = abs(count)
        if value >= 10**9:
            text = f"{value / 10**9:.1f}GB"
        elif value >= 10**6:
            text = f"{value / 10**6:.0f}MB"
        elif value >= 10**3:
            text = f"{value / 10**3:.0f}KB"
        else:
            text = f"{value}B"
        return f"-{text}" if negative else text

    @classmethod
    def _disk_change_cell(cls, change, status: str) -> str:
        """The change, coloured by direction, or the word for why there is none.

        Growth is red and shrinkage green because this table is read by
        somebody who is short of space: on a full disk, a cache that grew is
        the problem and one that shrank is the relief. `new`, `gone` and
        `unknown` are yellow and carry no number, because each is a case where
        subtracting would have invented a fact.
        """
        if change is None:
            return f"[yellow]{status}[/]"
        if change > 0:
            return f"[red]+{cls._disk_size(change)}[/]"
        if change < 0:
            return f"[green]{cls._disk_size(change)}[/]"
        return "[dim]no change[/]"

    def _load_disk_tab(self) -> None:
        """Render the machine's last disk reading, and what changed since the one before.

        Machine-wide, so it takes no project. The states that have to stay
        distinct are the same four as governance, for the same reason:

        * nothing loaded -- say so, and say the command that fixes it
        * stale -- show the age prominently, never silently
        * unknown -- its own word, never blank and never zero
        * only one reading -- "nothing to compare with" is not "nothing changed"
        """
        from dossier import disk_store
        from dossier.models import utcnow

        age_label = self.query_one("#disk-age", Static)
        volumes_table = self.query_one("#disk-volumes-table", DataTable)
        delta_label = self.query_one("#disk-delta-age", Static)
        targets_table = self.query_one("#disk-targets-table", DataTable)
        volumes_table.clear()
        targets_table.clear()

        with self.session_factory() as session:
            rows = disk_store.snapshots(session, limit=1)
            if not rows:
                age_label.update(
                    "[bold]No disk reading has been stored.[/]\n"
                    "This is not a claim that there is space -- it is the "
                    "absence of any measurement.\nRun [b]dossier disk load[/] "
                    "to take one and store it."
                )
                delta_label.update("")
                return

            latest = rows[0]
            volumes = disk_store.volumes_of(session, latest.id)
            targets = disk_store.targets_of(session, latest.id)
            delta = disk_store.latest_delta(session, machine=latest.machine)
            runs = disk_store.reclaims(session, machine=latest.machine, limit=20)
            applied = [r for r in runs if r.applied]
            session_delta = disk_store.compose(
                session,
                *(disk_store.reclaim_delta(session, r) for r in applied),
            )

        age_hours = (utcnow().replace(tzinfo=None) - latest.generated_at).total_seconds() / 3600
        age_label.update(
            f"{self._age_markup('disk-status.json', age_hours, latest.staleness_budget_hours)}"
            f"   [dim]machine[/] {latest.machine}"
        )

        volume_change = {v.path: v for v in delta.volumes} if delta.available else {}
        for volume in volumes:
            change = volume_change.get(volume.path)
            if volume.usage_unknown:
                volumes_table.add_row(
                    volume.path,
                    "[yellow]unknown[/]",
                    "[yellow]unknown[/]",
                    "[yellow]unknown[/]",
                    "[yellow]unknown[/]",
                    volume.usage_unknown,
                    key=f"disk-volume-{volume.path}",
                )
                continue
            severity = volume.severity or "unknown"
            colour = {
                "critical": "red", "warn": "yellow", "ok": "green"
            }.get(severity, "yellow")
            volumes_table.add_row(
                volume.path,
                self._disk_size(volume.free_bytes),
                f"{volume.free_ratio:.1%}" if volume.free_ratio is not None else "unknown",
                self._disk_change_cell(
                    change.change if change else None,
                    change.unknown and "unknown" or "-" if change else "-",
                ),
                f"[{colour}]{severity}[/]",
                (volume.thresholds_fired or "").replace("\n", "; "),
                key=f"disk-volume-{volume.path}",
            )

        if not delta.available:
            change_line = (
                f"[bold]No comparison available:[/] {delta.reason}.\n"
                "That is not a claim that nothing changed -- it is the absence "
                "of a second measurement."
            )
        else:
            change_line = (
                f"Change over [b]{delta.hours:.0f}h[/], against the reading of "
                f"{delta.older.generated_at}. "
                "[dim]Volume change is FREE space, so negative is filling up.[/]"
            )

        # What this machine's reclaims add up to, composed from their endpoints
        # rather than summed -- an unknown run is not a zero one. Shown beside
        # the observed change so the reader can tell what they did from what
        # merely happened.
        if applied:
            if session_delta.available:
                recovered = sum(
                    v.change for v in session_delta.volumes if v.change is not None
                )
                caveat = (
                    "" if session_delta.contiguous
                    else " [dim](spans the time between them too, so not all "
                    "of it is what the runs did)[/]"
                )
                reclaimed = (
                    f"[b]{len(applied)}[/] reclaim run(s) recorded; the volumes "
                    f"gave back [b]{self._disk_size(recovered)}[/] across them"
                    f"{caveat}"
                )
            else:
                reclaimed = (
                    f"[b]{len(applied)}[/] reclaim run(s) recorded, but what "
                    f"they freed could not be composed: {session_delta.reason}"
                )
        else:
            reclaimed = (
                "[dim]No reclaim has been applied here.[/] "
                "[b]x[/] plans one, [b]X[/] applies the plan "
                f"([dim]{self.DISK_TIER} tier only; widen with the CLI[/])"
            )

        delta_label.update(f"{change_line}\n{reclaimed}")

        target_change = {t.name: t for t in delta.targets} if delta.available else {}
        # Largest first, and an unmeasured target sorts to the bottom rather
        # than to the top: `None` treated as a huge number would put every
        # unreadable cache above the real ones.
        for target in sorted(targets, key=lambda t: -(t.bytes or 0)):
            change = target_change.get(target.name)
            if target.bytes_unknown:
                targets_table.add_row(
                    target.name,
                    "[yellow]unknown[/]",
                    "[yellow]unknown[/]",
                    target.safety or "-",
                    f"[yellow]{target.bytes_unknown}[/]",
                    key=f"disk-target-{target.name}",
                )
                continue
            detail = target.largest_path or "-"
            if target.unreadable:
                detail = f"[yellow]{target.unreadable} paths unreadable - a floor[/] {detail}"
            targets_table.add_row(
                target.name,
                self._disk_size(target.bytes),
                self._disk_change_cell(
                    change.change if change else None,
                    change.status if change else "-",
                ),
                target.safety or "-",
                detail,
                key=f"disk-target-{target.name}",
            )

    # The tier the dashboard is allowed to reclaim at, and the only one. Every
    # more expensive tier costs a rebuild or is irreversible, and widening it
    # belongs where somebody types the word: `dossier disk reclaim --allow`.
    # A dashboard that could empty the recycle bin on a keypress is a dashboard
    # nobody should leave open.
    DISK_TIER = "refetched"

    def _disk_corpus_root(self):
        """Which corpus checkout the reclaim runs in.

        Its own method so a test can point it somewhere harmless. The
        alternative is a suite that exercises the apply path against whatever
        corpus the developer happens to have beside them, on their real disk,
        deleting their real caches -- which is not a test anybody runs twice.
        """
        from dossier import governance as gov

        override = getattr(self, "_disk_corpus_override", None)
        if override is not None:
            return override
        return gov.resolve_corpus_dir(None)[0]

    def _on_disk_tab(self) -> bool:
        try:
            return self.query_one("#project-tabs", TabbedContent).active == "tab-disk"
        except Exception:
            return False

    def action_disk_plan(self) -> None:
        """Dry-run a reclaim and show what it would remove. Deletes nothing."""
        if not self._on_disk_tab():
            return
        self._reclaim_worker(apply=False)

    def action_disk_apply(self) -> None:
        """Carry out the plan that was just shown, and re-measure.

        Refuses without a plan from this session. The point is not that
        planning is a formality to get past -- it is that the numbers move,
        and applying a plan nobody has seen is applying a plan against a disk
        that may have changed since.
        """
        if not self._on_disk_tab():
            return
        if not getattr(self, "_disk_planned", None):
            self.notify(
                "Press x first to see what would be removed. Nothing is "
                "applied that has not been planned in this session.",
                severity="warning",
                timeout=8,
            )
            return
        self._reclaim_worker(apply=True)

    @work(thread=True, exclusive=True, group="disk-reclaim")
    def _reclaim_worker(self, apply: bool) -> None:
        """Plan or apply, off the event loop, then redraw from the store.

        Threaded because a reclaim walks a hundred gigabytes and an apply
        deletes it: on the event loop the whole dashboard would sit frozen for
        minutes, which reads as a crash and invites the impatient second
        keypress this design exists to prevent.
        """
        from dossier import disk as disk_tools

        root = self._disk_corpus_root()
        blocked = disk_tools.can_measure(root)
        if blocked:
            self.call_from_thread(
                self.notify,
                f"Cannot reclaim: {blocked}",
                severity="error",
                timeout=12,
            )
            return

        self.call_from_thread(
            self.notify,
            ("Applying" if apply else "Planning")
            + f" a {self.DISK_TIER} reclaim against {root} ...",
            timeout=6,
        )

        try:
            with self.session_factory() as session:
                record, outcome = disk_tools.reclaim_and_record(
                    session, root, allow=self.DISK_TIER, apply=apply
                )
                message = self._reclaim_message(session, record, outcome)
        except Exception as error:  # noqa: BLE001 - surfaced, never swallowed
            self.call_from_thread(
                self.notify, f"Reclaim failed: {error}", severity="error", timeout=15
            )
            return

        # Armed by a plan, disarmed by an apply. A plan that has been carried
        # out is not a licence for the next one.
        self._disk_planned = None if apply else (record.claimed_bytes or 0)

        self.call_from_thread(
            self.notify,
            message,
            severity="information" if outcome.ok else "error",
            timeout=20,
        )
        self.call_from_thread(self._load_disk_tab)

    @classmethod
    def _reclaim_message(cls, session, record, outcome) -> str:
        """What to tell the operator, with claimed and freed side by side.

        Never claimed alone. The reclaimer reports what it removed and the
        volume reports what came back; on a container disk that does not
        shrink those differ by the whole amount, and a dashboard that showed
        only the first would announce 23GB that is still gone.
        """
        if not record.applied:
            planned = cls._disk_size(record.claimed_bytes)
            if not record.claimed_bytes:
                return "Nothing to reclaim at the refetched tier."
            return (
                f"Plan: would remove {planned} across "
                f"{record.claimed_paths or 0} paths. Press X to apply."
            )

        claimed = cls._disk_size(record.claimed_bytes)
        if record.freed_bytes is None:
            return (
                f"Removed {claimed}. What came back could not be measured: "
                f"{record.freed_unknown or 'no reading'}."
            )
        if record.freed_bytes < 0:
            # A negative number wearing the word `freed` is worse than no
            # number. The volume ended smaller because something else was
            # writing; what this removed still went.
            return (
                f"Removed {claimed}, but the volume ended "
                f"{cls._disk_size(abs(record.freed_bytes))} smaller than it "
                "started — something else was writing during the run."
            )
        freed = cls._disk_size(record.freed_bytes)
        gap = (record.claimed_bytes or 0) - record.freed_bytes
        if record.claimed_bytes and abs(gap) > 10**9:
            return (
                f"Removed {claimed}; the volume gave back {freed}. The two "
                "disagree by " + cls._disk_size(gap) + " — space freed inside "
                "a container disk does not shrink the host file, and anything "
                "else writing counted too."
            )
        return f"Removed {claimed}; the volume gave back {freed}."

    def _load_governance_tab(self) -> None:
        """Render what the corpus's generated documents say.

        Org-wide, so it takes no project. Four states have to stay visually
        distinct, because collapsing any of them is how a dashboard becomes
        worse than no dashboard:

        * nothing loaded -- say so, and say the command that fixes it
        * stale -- show the age prominently, never silently
        * unknown -- its own word, never blank and never the healthy value
        * drift -- distinct in form as well as text, not only in a number
        """
        from dossier import governance as gov

        age_label = self.query_one("#governance-age", Static)
        table = self.query_one("#governance-table", DataTable)
        threads_label = self.query_one("#governance-threads-age", Static)
        threads_table = self.query_one("#governance-threads-table", DataTable)
        table.clear()
        threads_table.clear()

        with self.session_factory() as session:
            rows = gov.repositories(session)
            thread_rows = gov.threads(session)
            ages = gov.document_age(session)
            # One pass for the reverse link, so the table is not N queries deep.
            projects = {}
            synced_prs = set()
            for row in rows:
                match, how = gov.project_for_repository(session, row)
                projects[row.name] = gov.coverage_text(match, how)
                if match is not None:
                    synced_prs |= gov.synced_pr_numbers(session, match)
            budget = next(
                (r.harness_staleness_budget_hours for r in rows
                 if r.harness_staleness_budget_hours),
                None,
            )

        if not rows:
            age_label.update(
                "[bold]No governance document has been read.[/]\n"
                "This is not a claim that nothing is wrong -- it is the absence "
                "of any measurement.\nRun [b]dossier governance load[/] to read "
                "them from the vendored corpus."
            )
            threads_label.update("")
            return

        age_label.update(self._age_markup("governance-status.yaml", ages["governance"], None))

        for row in rows:
            state = gov.health(row)
            marker = {"unknown": "[yellow]?[/] ", "drift": "[red]![/] ", "ok": "  "}[state]
            evidence = gov.show_pair(row.precondition, row.precondition_unknown)
            if row.precondition_missing:
                evidence = f"{evidence} ({row.precondition_missing})"
            if row.slot_violations:
                evidence = f"{evidence} [holds {row.slot_violations}]"
            table.add_row(
                f"{marker}{row.name}",
                f"{row.phase or '-'}",
                self._governance_cell(gov.drift_text(row)),
                self._governance_cell(
                    gov.show_pair(row.seed_drift, row.seed_drift_unknown)
                ),
                self._governance_cell(
                    gov.show_pair(row.slot_state, row.slot_unknown)
                ),
                self._release_cell(gov.release_text(row)),
                self._governance_cell(evidence),
                self._coverage_cell(projects.get(row.name, "not synced")),
                key=f"governance-{row.name}",
            )

        if ages["harness"] is None:
            threads_label.update(
                "[bold]harness-status.json has never been read.[/] "
                "Nothing is known about work in flight,\nwhich is not the same "
                "as nothing being in flight."
            )
            return

        threads_label.update(
            self._age_markup("harness-status.json", ages["harness"], budget)
            + "  [dim]stages are observable states, not progress[/]"
        )
        if not thread_rows:
            threads_table.add_row(
                "[dim]The document was read and reports no threads in flight.[/]",
                "", "", "", "", "", key="threads-empty",
            )
            return

        for thread in thread_rows:
            stage = thread.stage or "-"
            if thread.stalled:
                stage = f"[red]{stage} STALLED[/]"
            idle = (
                f"{thread.idle_hours:.0f}h"
                if thread.idle_hours is not None
                else "[yellow]unknown[/]"
            )
            threads_table.add_row(
                thread.repository_name,
                thread.name,
                stage,
                f"{thread.commits or 0}c {thread.changed_files or 0}f "
                f"+{thread.additions or 0}/-{thread.deletions or 0}",
                idle,
                self._pr_cell(thread.pr, synced_prs),
                key=f"thread-{thread.id}",
            )

    @staticmethod
    def _release_cell(text: str) -> str:
        """Colour the two states that need a reader's attention.

        Never-tagged is dimmed rather than reddened: it is the normal state of
        a project nobody has released, not a fault.
        """
        if text.startswith("unknown"):
            return f"[yellow]{text}[/]"
        if "lightweight" in text:
            return f"[red]{text}[/]"
        if text == "never tagged":
            return f"[dim]{text}[/]"
        return text

    @staticmethod
    def _coverage_cell(text: str) -> str:
        """Dim what this store does not hold; flag a match made on a weak key."""
        if text == "not synced":
            return f"[dim]{text}[/]"
        if text != "synced":
            return f"[yellow]{text}[/]"
        return text

    @staticmethod
    def _pr_cell(number, synced: set) -> str:
        """The pull request, dimmed when this store has not synced it.

        Absence is not an error: it means the project has not been synced since
        that pull request opened.
        """
        if not number:
            return "-"
        return f"#{number}" if number in synced else f"[dim]#{number}[/]"

    @staticmethod
    def _governance_cell(text: str) -> str:
        """Colour unknown and drift, so form carries the distinction too.

        A reader scanning the column should not have to read every cell to
        find the ones nobody could measure.
        """
        if text.startswith("unknown"):
            return f"[yellow]{text}[/]"
        if "behind" in text or text.startswith("drift") or text.startswith("over"):
            return f"[red]{text}[/]"
        return text

    @staticmethod
    def _age_markup(name: str, age, budget) -> str:
        """Always state the document's age. Never let it read as live."""
        if age is None:
            return f"[bold]{name}: never read[/]"
        if budget is None:
            return f"{name}: generated [b]{age:.0f}h[/] ago [dim](no stated budget)[/]"
        if age > budget:
            return (
                f"[red]{name}: generated {age:.0f}h ago, PAST its {budget:.0f}h "
                f"budget -- treat every figure below as stale[/]"
            )
        return f"{name}: generated [b]{age:.0f}h[/] ago, within its {budget:.0f}h budget"

    def _load_components_tab(self, project: Project) -> None:
        """Load components tab."""
        components_table = self.query_one("#components-table", DataTable)
        components_table.clear()
        
        with self.session_factory() as session:
            # Get children (projects this is a parent of)
            child_links = session.exec(
                select(ProjectComponent)
                .where(ProjectComponent.parent_id == project.id)
                .order_by(ProjectComponent.order)
            ).all()
            
            # Get parents (projects this is a child of)
            parent_links = session.exec(
                select(ProjectComponent)
                .where(ProjectComponent.child_id == project.id)
            ).all()
            
            has_components = False
            
            # Add child components
            for link in child_links:
                child = session.get(Project, link.child_id)
                if child:
                    has_components = True
                    type_icon = {"component": "🧩", "dependency": "📦", "related": "🔗"}.get(link.relationship_type, "•")
                    components_table.add_row(
                        "→ child",
                        child.name,
                        f"{type_icon} {link.relationship_type}",
                        str(link.order),
                        key=f"comp-child-{child.id}",
                    )
            
            # Add parent components
            for link in parent_links:
                parent = session.get(Project, link.parent_id)
                if parent:
                    has_components = True
                    type_icon = {"component": "🧩", "dependency": "📦", "related": "🔗"}.get(link.relationship_type, "•")
                    components_table.add_row(
                        "← parent",
                        parent.name,
                        f"{type_icon} {link.relationship_type}",
                        str(link.order),
                        key=f"comp-parent-{parent.id}",
                    )
            
            if not has_components:
                components_table.add_row("", "(No component relationships)", "", "", key="empty")

    def _load_deltas_tab(self, project: Project) -> None:
        """Load deltas tab."""
        deltas_table = self.query_one("#deltas-table", DataTable)
        deltas_table.clear()

        # Skip if delta tables don't exist
        if not self._delta_tables_exist:
            deltas_table.add_row(
                "(No deltas)", "-", "-", "-", "-", "-", key="empty"
            )
            return

        # Phase display icons
        phase_icons = {
            DeltaPhase.BRAINSTORM: "💡",
            DeltaPhase.PLANNING: "📋",
            DeltaPhase.IMPLEMENTATION: "⚙️",
            DeltaPhase.REVIEW: "🔍",
            DeltaPhase.DOCUMENTATION: "📝",
            DeltaPhase.COMPLETE: "✅",
            DeltaPhase.ABANDONED: "❌",
        }
        priority_icons = {
            "critical": "🔴",
            "high": "🟠",
            "medium": "🟡",
            "low": "🟢",
        }
        type_icons = {
            "feature": "✨",
            "bugfix": "🐛",
            "refactor": "♻️",
            "docs": "📚",
            "chore": "🔧",
        }

        with self.session_factory() as session:
            # Query deltas ordered by phase (active first) then by update time
            deltas = session.exec(
                select(ProjectDelta)
                .where(ProjectDelta.project_id == project.id)
                .order_by(ProjectDelta.updated_at.desc())
            ).all()

            if not deltas:
                deltas_table.add_row(
                    "(No deltas)", "-", "-", "-", "-", "-", key="empty"
                )
            else:
                for delta in deltas:
                    # Count links for this delta
                    link_count = session.exec(
                        select(DeltaLink).where(DeltaLink.delta_id == delta.id)
                    ).all()

                    phase_icon = phase_icons.get(delta.phase, "❓")
                    priority_icon = priority_icons.get(delta.priority, "⚪")
                    type_icon = type_icons.get(delta.delta_type, "❓")

                    # Truncate title if needed
                    title_display = delta.title
                    if len(title_display) > 28:
                        title_display = title_display[:25] + "..."

                    deltas_table.add_row(
                        delta.name,
                        title_display,
                        f"{phase_icon} {delta.phase.value}",
                        f"{type_icon} {delta.delta_type}",
                        f"{priority_icon} {delta.priority}",
                        f"🔗{len(link_count)}" if link_count else "-",
                        key=f"delta-{delta.id}",
                    )
                    if link_count:
                        for link in link_count:
                            link_type = link.link_type or "link"
                            target = None
                            if link_type in ("issue", "pr"):
                                number = link.target_id
                                if number is None and link.target_name:
                                    try:
                                        number = int(link.target_name)
                                    except ValueError:
                                        number = None
                                target = f"#{number}" if number is not None else (link.target_name or "?")
                            elif link_type == "delta":
                                if link.target_id is not None:
                                    target = f"#{link.target_id}"
                                else:
                                    target = link.target_name or "?"
                            else:
                                target = link.target_name or (str(link.target_id) if link.target_id is not None else "?")
                            link_label = f"{link_type} {target}".strip()
                            deltas_table.add_row(
                                f"  -> {link_label}",
                                "-",
                                "-",
                                "-",
                                "-",
                                "-",
                                key=f"delta-link-{link.id}",
                            )

    def load_dossier_view(self, project: Project) -> None:
        """Load the dossier view for a project."""
        dossier_md = self.query_one("#dossier-view", Markdown)
        
        with self.session_factory() as session:
            # Generate dossier data
            dossier = generate_dossier(session, project)
            
            # Format as Markdown for display
            md_lines = []
            
            # Header
            md_lines.append(f"# 📋 {project.name}")
            md_lines.append("")
            
            # Project info
            if project.description:
                md_lines.append(f"> {project.description}")
                md_lines.append("")
            
            # Quick stats bar with clickable links
            stats = []
            if project.github_stars:
                stats.append(f"⭐ {project.github_stars:,}")
            if project.github_language:
                # Make language clickable
                stats.append(f"💻 [{project.github_language}](dossier://lang/{project.github_language})")
            if dossier.get("activity"):
                activity = dossier["activity"]
                if activity.get("contributors"):
                    stats.append(f"[👥 {activity['contributors']}](dossier://tab/contributors)")
                if activity.get("open_issues"):
                    stats.append(f"[🐛 {activity['open_issues']} open](dossier://tab/issues)")
                if activity.get("open_prs"):
                    stats.append(f"[🔀 {activity['open_prs']} PRs](dossier://tab/prs)")
            if self._delta_tables_exist:
                deltas = session.exec(
                    select(ProjectDelta).where(ProjectDelta.project_id == project.id)
                ).all()
                if deltas:
                    active_count = sum(
                        1 for d in deltas
                        if d.phase not in (DeltaPhase.COMPLETE, DeltaPhase.ABANDONED)
                    )
                    stats.append(
                        f"[Deltas {len(deltas)} / {active_count} active](dossier://tab/deltas)"
                    )

            
            if stats:
                md_lines.append(" • ".join(stats))
                md_lines.append("")
            
            # Repository link
            if project.repository_url:
                md_lines.append(f"🔗 [{project.repository_url}]({project.repository_url})")
                md_lines.append("")
            
            # Tech Stack - make languages clickable
            if dossier.get("tech_stack"):
                md_lines.append("## 🛠️ [Tech Stack](dossier://tab/languages)")
                md_lines.append("")
                for lang in dossier["tech_stack"][:5]:  # Top 5 languages
                    bar_width = int(lang["percentage"] / 5)  # Scale to ~20 chars max
                    bar = "█" * bar_width
                    lang_name = lang["name"]
                    md_lines.append(f"- **[{lang_name}](dossier://lang/{lang_name})** {lang['percentage']}% `{bar}`")
                md_lines.append("")
            
            # Activity - make items clickable
            if dossier.get("activity"):
                activity = dossier["activity"]
                md_lines.append("## 📊 Activity")
                md_lines.append("")
                
                if activity.get("last_release"):
                    release_tag = activity['last_release']
                    release_info = f"🏷️ **Latest Release:** [`{release_tag}`](dossier://release/{release_tag})"
                    if activity.get("release_date"):
                        release_info += f" ({activity['release_date'][:10]})"
                    md_lines.append(release_info)
                
                if activity.get("default_branch"):
                    branch = activity['default_branch']
                    md_lines.append(f"🌿 **Default Branch:** [`{branch}`](dossier://branch/{branch})")
                
                if activity.get("branches"):
                    md_lines.append(f"🌳 **[Branches](dossier://tab/branches):** {activity['branches']}")
                
                md_lines.append("")
                
                # Activity grid with clickable links
                md_lines.append("| Metric | Count |")
                md_lines.append("|--------|-------|")
                md_lines.append(f"| [🐛 Open Issues](dossier://tab/issues) | {activity.get('open_issues', 0)} |")
                md_lines.append(f"| [🔀 Open PRs](dossier://tab/prs) | {activity.get('open_prs', 0)} |")
                md_lines.append(f"| [👥 Contributors](dossier://tab/contributors) | {activity.get('contributors', 0)} |")
                md_lines.append("")
            
            # Dependencies - make packages clickable
            if dossier.get("dependencies"):
                md_lines.append("## 📦 [Dependencies](dossier://tab/dependencies)")
                md_lines.append("")
                
                for dep_type, deps in dossier["dependencies"].items():
                    icon = {"runtime": "📦", "dev": "🔧", "optional": "❔"}.get(dep_type, "•")
                    md_lines.append(f"### {icon} {dep_type.title()} ({len(deps)})")
                    md_lines.append("")
                    
                    # Show first 10 dependencies - make clickable
                    for dep in deps[:10]:
                        version = f" `{dep['version']}`" if dep.get("version") else ""
                        pkg_name = dep['name']
                        md_lines.append(f"- [{pkg_name}](dossier://pkg/{pkg_name}){version}")
                    
                    if len(deps) > 10:
                        md_lines.append(f"- *[...and {len(deps) - 10} more](dossier://tab/dependencies)*")
                    md_lines.append("")
            
            # Links
            if dossier.get("links"):
                md_lines.append("## 🔗 Links")
                md_lines.append("")
                for link_name, url in dossier["links"].items():
                    if url:
                        display_name = link_name.replace("_", " ").title()
                        md_lines.append(f"- [{display_name}]({url})")
                md_lines.append("")
            
            # Sync info
            if project.last_synced_at:
                md_lines.append("---")
                md_lines.append(f"*Synced: {project.last_synced_at.strftime('%Y-%m-%d %H:%M')}*")
            else:
                md_lines.append("---")
                md_lines.append("*Not synced - press `s` to sync from GitHub*")
            
            dossier_md.update("\n".join(md_lines))
        
        # Load component tree
        self._load_component_tree(project)
    
    def _load_component_tree(self, project: Project) -> None:
        """Load the component hierarchy tree.
        
        Optimized to use batched queries instead of N+1 queries.
        
        Each tree node stores navigation data as a dict:
        - {"type": "project", "name": "owner/repo"} - Navigate to project
        - {"type": "section", "section": "languages"} - Switch to tab
        - {"type": "url", "url": "https://..."} - Open URL
        - {"type": "language|dependency|contributor|doc|version|branch|issue|pr", ...} - Linkable entities
        """
        tree = self.query_one("#component-tree", Tree)
        tree.clear()
        tree.root.expand()
        
        # Get base URL using Project helper
        base_url = project.github_url or ""
        
        with self.session_factory() as session:
            # Batch load all needed data in minimal queries
            # Get parent projects (this project is a child of)
            parent_links = session.exec(
                select(ProjectComponent)
                .where(ProjectComponent.child_id == project.id)
            ).all()
            
            # Get child projects (this project is a parent of)
            child_links = session.exec(
                select(ProjectComponent)
                .where(ProjectComponent.parent_id == project.id)
                .order_by(ProjectComponent.order)
            ).all()
            
            # Batch load all parent and child project objects
            parent_ids = [link.parent_id for link in parent_links]
            child_ids = [link.child_id for link in child_links]
            all_linked_ids = set(parent_ids + child_ids)
            
            # Single query to get all linked projects
            linked_projects = {}
            if all_linked_ids:
                linked_projs = session.exec(
                    select(Project).where(Project.id.in_(all_linked_ids))
                ).all()
                linked_projects = {p.id: p for p in linked_projs}
            
            # Batch load grandchildren (children of children) in ONE query
            grandchild_links = []
            grandchild_projects = {}
            if child_ids:
                grandchild_links = session.exec(
                    select(ProjectComponent)
                    .where(ProjectComponent.parent_id.in_(child_ids))
                    .order_by(ProjectComponent.parent_id, ProjectComponent.order)
                ).all()
                
                # Get grandchild project IDs
                gc_ids = set(link.child_id for link in grandchild_links)
                if gc_ids:
                    gc_projs = session.exec(
                        select(Project).where(Project.id.in_(gc_ids))
                    ).all()
                    grandchild_projects = {p.id: p for p in gc_projs}
            
            # Group grandchildren by parent for easy lookup
            grandchildren_by_parent = {}
            for gc_link in grandchild_links:
                if gc_link.parent_id not in grandchildren_by_parent:
                    grandchildren_by_parent[gc_link.parent_id] = []
                grandchildren_by_parent[gc_link.parent_id].append(gc_link)
            
            # Get data entities with LIMIT for performance
            languages = session.exec(
                select(ProjectLanguage)
                .where(ProjectLanguage.project_id == project.id)
                .order_by(ProjectLanguage.percentage.desc())
                .limit(TREE_ENTITY_LIMIT + 1)
            ).all()
            
            dependencies = session.exec(
                select(ProjectDependency)
                .where(ProjectDependency.project_id == project.id)
                .order_by(ProjectDependency.dep_type, ProjectDependency.name)
                .limit(TREE_ENTITY_LIMIT + 1)
            ).all()
            
            contributors = session.exec(
                select(ProjectContributor)
                .where(ProjectContributor.project_id == project.id)
                .order_by(ProjectContributor.contributions.desc())
                .limit(TREE_ENTITY_LIMIT + 1)
            ).all()
            
            doc_sections = session.exec(
                select(DocumentSection)
                .where(DocumentSection.project_id == project.id)
                .order_by(DocumentSection.source_file, DocumentSection.order)
                .limit(TREE_ENTITY_LIMIT + 1)
            ).all()
            
            releases = session.exec(
                select(ProjectRelease)
                .where(ProjectRelease.project_id == project.id)
                .order_by(ProjectRelease.release_published_at.desc())
                .limit(TREE_ENTITY_LIMIT + 1)
            ).all()
            
            versions = session.exec(
                select(ProjectVersion)
                .where(ProjectVersion.project_id == project.id)
                .order_by(ProjectVersion.major.desc(), ProjectVersion.minor.desc(), ProjectVersion.patch.desc())
                .limit(TREE_ENTITY_LIMIT + 1)
            ).all()
            
            branches = session.exec(
                select(ProjectBranch)
                .where(ProjectBranch.project_id == project.id)
                .order_by(ProjectBranch.is_default.desc(), ProjectBranch.name)
                .limit(TREE_ENTITY_LIMIT + 1)
            ).all()
            
            issues = session.exec(
                select(ProjectIssue)
                .where(ProjectIssue.project_id == project.id)
                .order_by(ProjectIssue.issue_number.desc())
                .limit(TREE_ENTITY_LIMIT + 1)
            ).all()
            
            prs = session.exec(
                select(ProjectPullRequest)
                .where(ProjectPullRequest.project_id == project.id)
                .order_by(ProjectPullRequest.pr_number.desc())
                .limit(TREE_ENTITY_LIMIT + 1)
            ).all()
            
            # Helper function for relationship icons
            def rel_icon(rel_type: str) -> str:
                return {"component": "🧩", "dependency": "📦", "related": "🔗", "language": "🌐", "contributor": "👤", "doc": "📄", "version": "🏷️", "branch": "🌿", "issue": "🐛", "pr": "🔀", "delta": "🔺"}.get(rel_type, "•")
            
            # Add parent section if there are parents
            if parent_links:
                parents_node = tree.root.add("⬆️ Parents", expand=True)
                for link in parent_links:
                    parent = linked_projects.get(link.parent_id)
                    if parent:
                        display_name = self._shorten_project_name(parent.name)
                        node = parents_node.add_leaf(f"{rel_icon(link.relationship_type)} {display_name}")
                        node.data = {"type": "project", "name": parent.name}
            
            # Add current project as the center
            current_node = tree.root.add(f"📍 {project.name}", expand=True)
            current_node.data = {"type": "project", "name": project.name}
            
            # Add children under current project (using pre-fetched data)
            if child_links:
                for link in child_links:
                    child = linked_projects.get(link.child_id)
                    if child:
                        display_name = self._shorten_project_name(child.name)
                        child_node = current_node.add(f"{rel_icon(link.relationship_type)} {display_name}", expand=True)
                        child_node.data = {"type": "project", "name": child.name}
                        
                        # Add grandchildren using pre-fetched data (NO N+1!)
                        gc_links = grandchildren_by_parent.get(child.id, [])
                        for gc_link in gc_links[:TREE_ENTITY_LIMIT]:  # Limit grandchildren too
                            grandchild = grandchild_projects.get(gc_link.child_id)
                            if grandchild:
                                gc_display = self._shorten_project_name(grandchild.name)
                                gc_node = child_node.add_leaf(f"{rel_icon(gc_link.relationship_type)} {gc_display}")
                                gc_node.data = {"type": "project", "name": grandchild.name}
                        
                        if len(gc_links) > TREE_ENTITY_LIMIT:
                            more_gc = child_node.add_leaf(f"... and {len(gc_links) - TREE_ENTITY_LIMIT} more")
                            more_gc.data = {"type": "project", "name": child.name}
            
            if not child_links:
                current_node.add_leaf("(No linked subprojects)")
            
            # === DOCUMENTATION SECTIONS - Grouped by file ===
            if doc_sections:
                has_more = len(doc_sections) > TREE_ENTITY_LIMIT
                docs_node = tree.root.add(f"📄 Documentation ({len(doc_sections) if not has_more else f'{TREE_ENTITY_LIMIT}+'})", expand=False)
                docs_node.data = {"type": "section", "section": "docs"}
                
                # Group sections by source file
                file_groups: dict[str, list] = {}
                for doc in doc_sections[:TREE_ENTITY_LIMIT]:
                    source = doc.source_file or "(No source)"
                    if source not in file_groups:
                        file_groups[source] = []
                    file_groups[source].append(doc)
                
                # Build file-based tree
                for source_file, sections in sorted(file_groups.items()):
                    # Extract display name
                    if source_file.startswith("github:"):
                        parts = source_file.split("/", 2)
                        display_name = parts[2] if len(parts) > 2 else source_file
                    else:
                        display_name = source_file
                    
                    # File icon
                    if display_name.endswith(".md"):
                        file_icon = "📝"
                    elif display_name.endswith(".rst"):
                        file_icon = "📄"
                    else:
                        file_icon = "📃"
                    
                    file_path = extract_file_path(source_file)
                    
                    if len(sections) == 1:
                        # Single section - add as leaf directly
                        section = sections[0]
                        leaf = docs_node.add_leaf(f"{file_icon} {display_name}")
                        leaf.data = {
                            "type": "source_file",
                            "source": source_file,
                            "project_id": project.id,
                            "url": f"{base_url}/blob/main/{file_path}" if base_url and file_path else None,
                        }
                    else:
                        # Multiple sections - add file node
                        file_node = docs_node.add(f"{file_icon} {display_name} ({len(sections)})", expand=False)
                        file_node.data = {
                            "type": "source_file",
                            "source": source_file,
                            "project_id": project.id,
                            "url": f"{base_url}/blob/main/{file_path}" if base_url and file_path else None,
                        }
                        
                        for section in sections:
                            type_icon = {"readme": "📖", "api": "📡", "setup": "🔧", "guide": "📚", "example": "💡"}.get(section.section_type, "📄")
                            leaf = file_node.add_leaf(f"{type_icon} {section.title[:40]}")
                            leaf.data = {
                                "type": "doc",
                                "title": section.title,
                                "section_type": section.section_type,
                                "source_file": section.source_file,
                                "file_path": file_path,
                                "project_id": project.id,
                                "owner": project.github_owner,
                                "repo": project.github_repo,
                                "url": f"{base_url}/blob/main/{file_path}" if base_url and file_path else None,
                            }
                
                if has_more:
                    more_leaf = docs_node.add_leaf(f"... see Documentation tab for all")
                    more_leaf.data = {"type": "section", "section": "tab-docs"}
            
            # === VERSIONS/RELEASES - Linkable entities ===
            if versions:
                has_more = len(versions) > TREE_ENTITY_LIMIT
                ver_node = tree.root.add(f"🏷️ Versions ({len(versions) if not has_more else f'{TREE_ENTITY_LIMIT}+'})", expand=False)
                ver_node.data = {"type": "section", "section": "releases"}
                for ver in versions[:TREE_ENTITY_LIMIT]:
                    prerelease = f" ({ver.prerelease})" if ver.prerelease else ""
                    latest = " ⭐" if ver.is_latest else ""
                    leaf = ver_node.add_leaf(f"• v{ver.version}{prerelease}{latest}")
                    leaf.data = {
                        "type": "version",
                        "version": ver.version,
                        "major": ver.major,
                        "minor": ver.minor,
                        "patch": ver.patch,
                        "prerelease": ver.prerelease,
                        "project_id": project.id,
                        "owner": project.github_owner,
                        "repo": project.github_repo,
                        "url": ver.release_url or (f"{base_url}/releases/tag/v{ver.version}" if base_url else None),
                    }
                if has_more:
                    more_leaf = ver_node.add_leaf(f"... see Releases tab for all")
                    more_leaf.data = {"type": "section", "section": "tab-releases"}
            elif releases:
                has_more = len(releases) > TREE_ENTITY_LIMIT
                rel_node = tree.root.add(f"🏷️ Releases ({len(releases) if not has_more else f'{TREE_ENTITY_LIMIT}+'})", expand=False)
                rel_node.data = {"type": "section", "section": "releases"}
                for rel in releases[:TREE_ENTITY_LIMIT]:
                    type_indicator = ""
                    if rel.is_prerelease:
                        type_indicator = " ⚠️"
                    elif rel.is_draft:
                        type_indicator = " 📝"
                    leaf = rel_node.add_leaf(f"• {rel.tag_name}{type_indicator}")
                    leaf.data = {
                        "type": "version",
                        "version": rel.tag_name,
                        "tag_name": rel.tag_name,
                        "is_prerelease": rel.is_prerelease,
                        "project_id": project.id,
                        "owner": project.github_owner,
                        "repo": project.github_repo,
                        "url": f"{base_url}/releases/tag/{rel.tag_name}" if base_url else None,
                    }
                if len(releases) > TREE_ENTITY_LIMIT:
                    more_leaf = rel_node.add_leaf(f"... see Releases tab for all")
                    more_leaf.data = {"type": "section", "section": "tab-releases"}
            
            # === BRANCHES - Linkable entities ===
            if branches:
                has_more = len(branches) > TREE_ENTITY_LIMIT
                branch_node = tree.root.add(f"🌿 Branches ({len(branches) if not has_more else f'{TREE_ENTITY_LIMIT}+'})", expand=False)
                branch_node.data = {"type": "section", "section": "branches"}
                for branch in branches[:TREE_ENTITY_LIMIT]:
                    default = " ⭐" if branch.is_default else ""
                    protected = " 🔒" if branch.is_protected else ""
                    leaf = branch_node.add_leaf(f"• {branch.name}{default}{protected}")
                    leaf.data = {
                        "type": "branch",
                        "name": branch.name,
                        "is_default": branch.is_default,
                        "is_protected": branch.is_protected,
                        "project_id": project.id,
                        "owner": project.github_owner,
                        "repo": project.github_repo,
                        "url": f"{base_url}/tree/{branch.name}" if base_url else None,
                    }
                if has_more:
                    more_leaf = branch_node.add_leaf(f"... see Branches tab for all")
                    more_leaf.data = {"type": "section", "section": "tab-branches"}
            
            # === LANGUAGES - Linkable entities ===
            if languages:
                has_more = len(languages) > TREE_ENTITY_LIMIT
                lang_node = tree.root.add(f"🌐 Languages ({len(languages) if not has_more else f'{TREE_ENTITY_LIMIT}+'})", expand=False)
                lang_node.data = {"type": "section", "section": "languages"}
                for lang in languages[:TREE_ENTITY_LIMIT]:
                    pct = f"{lang.percentage:.1f}%" if lang.percentage else ""
                    leaf = lang_node.add_leaf(f"• {lang.language} {pct}")
                    leaf.data = {
                        "type": "language",
                        "name": lang.language,
                        "project_id": project.id,
                        "owner": project.github_owner,
                        "repo": project.github_repo,
                    }
                if has_more:
                    more_leaf = lang_node.add_leaf(f"... see Languages tab for all")
                    more_leaf.data = {"type": "section", "section": "tab-languages"}
            
            # === DEPENDENCIES - Linkable entities ===
            if dependencies:
                dep_node = tree.root.add(f"📦 Dependencies ({len(dependencies)})", expand=False)
                dep_node.data = {"type": "section", "section": "dependencies"}
                # Group by type
                runtime_deps = [d for d in dependencies if d.dep_type == "runtime"]
                dev_deps = [d for d in dependencies if d.dep_type == "dev"]
                other_deps = [d for d in dependencies if d.dep_type not in ("runtime", "dev")]
                
                if runtime_deps:
                    runtime_node = dep_node.add(f"Runtime ({len(runtime_deps)})", expand=False)
                    runtime_node.data = {"type": "section", "section": "dependencies"}
                    for dep in runtime_deps[:8]:
                        version = f" {dep.version_spec}" if dep.version_spec else ""
                        leaf = runtime_node.add_leaf(f"• {dep.name}{version}")
                        leaf.data = {
                            "type": "dependency",
                            "name": dep.name,
                            "version": dep.version_spec,
                            "source": dep.source,
                            "project_id": project.id,
                            "owner": project.github_owner,
                            "repo": project.github_repo,
                        }
                    if len(runtime_deps) > 8:
                        more_leaf = runtime_node.add_leaf(f"... and {len(runtime_deps) - 8} more")
                        more_leaf.data = {"type": "section", "section": "dependencies"}
                
                if dev_deps:
                    dev_node = dep_node.add(f"Dev ({len(dev_deps)})", expand=False)
                    dev_node.data = {"type": "section", "section": "dependencies"}
                    for dep in dev_deps[:8]:
                        version = f" {dep.version_spec}" if dep.version_spec else ""
                        leaf = dev_node.add_leaf(f"• {dep.name}{version}")
                        leaf.data = {
                            "type": "dependency",
                            "name": dep.name,
                            "version": dep.version_spec,
                            "source": dep.source,
                            "project_id": project.id,
                            "owner": project.github_owner,
                            "repo": project.github_repo,
                        }
                    if len(dev_deps) > 8:
                        more_leaf = dev_node.add_leaf(f"... and {len(dev_deps) - 8} more")
                        more_leaf.data = {"type": "section", "section": "dependencies"}
                
                if other_deps:
                    other_node = dep_node.add(f"Other ({len(other_deps)})", expand=False)
                    other_node.data = {"type": "section", "section": "dependencies"}
                    for dep in other_deps[:5]:
                        version = f" {dep.version_spec}" if dep.version_spec else ""
                        leaf = other_node.add_leaf(f"• {dep.name}{version}")
                        leaf.data = {
                            "type": "dependency",
                            "name": dep.name,
                            "version": dep.version_spec,
                            "source": dep.source,
                            "project_id": project.id,
                            "owner": project.github_owner,
                            "repo": project.github_repo,
                        }
                    if len(other_deps) > 5:
                        more_leaf = other_node.add_leaf(f"... and {len(other_deps) - 5} more")
                        more_leaf.data = {"type": "section", "section": "dependencies"}
            
            # === CONTRIBUTORS - Linkable entities ===
            if contributors:
                contrib_node = tree.root.add(f"👥 Contributors ({len(contributors)})", expand=False)
                contrib_node.data = {"type": "section", "section": "contributors"}
                for contrib in contributors[:10]:
                    count = f" ({contrib.contributions})" if contrib.contributions else ""
                    leaf = contrib_node.add_leaf(f"• {contrib.username}{count}")
                    leaf.data = {
                        "type": "contributor",
                        "username": contrib.username,
                        "profile_url": contrib.profile_url or f"https://github.com/{contrib.username}",
                        "project_id": project.id,
                        "owner": project.github_owner,
                        "repo": project.github_repo,
                    }
                if len(contributors) > 10:
                    more_leaf = contrib_node.add_leaf(f"... and {len(contributors) - 10} more")
                    more_leaf.data = {"type": "section", "section": "contributors"}
            
            # === ISSUES - Linkable entities ===
            if issues:
                open_issues = [i for i in issues if i.state == "open"]
                closed_issues = [i for i in issues if i.state == "closed"]
                
                issues_node = tree.root.add(f"🐛 Issues ({len(issues)})", expand=False)
                issues_node.data = {"type": "section", "section": "issues"}
                
                if open_issues:
                    open_node = issues_node.add(f"🟢 Open ({len(open_issues)})", expand=False)
                    open_node.data = {"type": "section", "section": "issues"}
                    for issue in open_issues[:5]:
                        leaf = open_node.add_leaf(f"#{issue.issue_number} {issue.title[:30]}")
                        leaf.data = {
                            "type": "issue",
                            "number": issue.issue_number,
                            "title": issue.title,
                            "state": issue.state,
                            "author": issue.author,
                            "project_id": project.id,
                            "owner": project.github_owner,
                            "repo": project.github_repo,
                            "url": f"{base_url}/issues/{issue.issue_number}" if base_url else None,
                        }
                    if len(open_issues) > 5:
                        more_leaf = open_node.add_leaf(f"... and {len(open_issues) - 5} more")
                        more_leaf.data = {"type": "section", "section": "issues"}
                
                if closed_issues:
                    closed_node = issues_node.add(f"⚫ Closed ({len(closed_issues)})", expand=False)
                    closed_node.data = {"type": "section", "section": "issues"}
                    for issue in closed_issues[:5]:
                        leaf = closed_node.add_leaf(f"#{issue.issue_number} {issue.title[:30]}")
                        leaf.data = {
                            "type": "issue",
                            "number": issue.issue_number,
                            "title": issue.title,
                            "state": issue.state,
                            "author": issue.author,
                            "project_id": project.id,
                            "owner": project.github_owner,
                            "repo": project.github_repo,
                            "url": f"{base_url}/issues/{issue.issue_number}" if base_url else None,
                        }
                    if len(closed_issues) > 5:
                        more_leaf = closed_node.add_leaf(f"... and {len(closed_issues) - 5} more")
                        more_leaf.data = {"type": "section", "section": "issues"}
            
            # === PULL REQUESTS - Linkable entities ===
            if prs:
                open_prs = [p for p in prs if p.state == "open"]
                merged_prs = [p for p in prs if p.is_merged]
                closed_prs = [p for p in prs if p.state == "closed" and not p.is_merged]
                
                prs_node = tree.root.add(f"🔀 Pull Requests ({len(prs)})", expand=False)
                prs_node.data = {"type": "section", "section": "prs"}
                
                if open_prs:
                    open_node = prs_node.add(f"🟢 Open ({len(open_prs)})", expand=False)
                    open_node.data = {"type": "section", "section": "prs"}
                    for pr in open_prs[:5]:
                        draft = " 📝" if pr.is_draft else ""
                        leaf = open_node.add_leaf(f"#{pr.pr_number} {pr.title[:25]}{draft}")
                        leaf.data = {
                            "type": "pr",
                            "number": pr.pr_number,
                            "title": pr.title,
                            "state": pr.state,
                            "author": pr.author,
                            "is_merged": pr.is_merged,
                            "project_id": project.id,
                            "owner": project.github_owner,
                            "repo": project.github_repo,
                            "url": f"{base_url}/pull/{pr.pr_number}" if base_url else None,
                        }
                    if len(open_prs) > 5:
                        more_leaf = open_node.add_leaf(f"... and {len(open_prs) - 5} more")
                        more_leaf.data = {"type": "section", "section": "prs"}
                
                if merged_prs:
                    merged_node = prs_node.add(f"🟣 Merged ({len(merged_prs)})", expand=False)
                    merged_node.data = {"type": "section", "section": "prs"}
                    for pr in merged_prs[:5]:
                        leaf = merged_node.add_leaf(f"#{pr.pr_number} {pr.title[:28]}")
                        leaf.data = {
                            "type": "pr",
                            "number": pr.pr_number,
                            "title": pr.title,
                            "state": pr.state,
                            "author": pr.author,
                            "is_merged": pr.is_merged,
                            "project_id": project.id,
                            "owner": project.github_owner,
                            "repo": project.github_repo,
                            "url": f"{base_url}/pull/{pr.pr_number}" if base_url else None,
                        }
                    if len(merged_prs) > 5:
                        more_leaf = merged_node.add_leaf(f"... and {len(merged_prs) - 5} more")
                        more_leaf.data = {"type": "section", "section": "prs"}
                
                if closed_prs:
                    closed_node = prs_node.add(f"🔴 Closed ({len(closed_prs)})", expand=False)
                    closed_node.data = {"type": "section", "section": "prs"}
                    for pr in closed_prs[:5]:
                        leaf = closed_node.add_leaf(f"#{pr.pr_number} {pr.title[:28]}")
                        leaf.data = {
                            "type": "pr",
                            "number": pr.pr_number,
                            "title": pr.title,
                            "state": pr.state,
                            "author": pr.author,
                            "is_merged": pr.is_merged,
                            "project_id": project.id,
                            "owner": project.github_owner,
                            "repo": project.github_repo,
                            "url": f"{base_url}/pull/{pr.pr_number}" if base_url else None,
                        }
                    if len(closed_prs) > 5:
                        more_leaf = closed_node.add_leaf(f"... and {len(closed_prs) - 5} more")
                        more_leaf.data = {"type": "section", "section": "prs"}
            
            # Update tree label
            tree.root.label = f"🌳 {project.name}"
    
    # Track the last selected tree node for 'o' key binding
    _last_tree_node_data: dict | None = None
    
    @on(Tree.NodeSelected, "#component-tree")
    def on_component_tree_selected(self, event: Tree.NodeSelected) -> None:
        """Handle component tree node selection - show viewer or navigate.
        
        Click: Show content in viewer (for docs, issues, PRs, etc.)
        Press 'o': Open in browser (when tree is focused)
        """
        node = event.node
        if not node.data:
            return
        
        nav_data = node.data
        nav_type = nav_data.get("type")
        
        # Store for 'o' key binding
        self._last_tree_node_data = nav_data
        
        if nav_type == "project":
            # Navigate to the project (skip if already selected)
            project_name = nav_data.get("name")
            if project_name:
                # Don't reload if it's the current project
                if self.selected_project and self.selected_project.name == project_name:
                    return
                self._select_project_by_name(project_name)
        
        elif nav_type == "section":
            # Switch to the corresponding tab for section headers
            section = nav_data.get("section")
            tab_map = {
                "languages": "tab-languages",
                "dependencies": "tab-dependencies", 
                "contributors": "tab-contributors",
                "docs": "tab-docs",
                "releases": "tab-releases",
                "branches": "tab-branches",
                "issues": "tab-issues",
                "prs": "tab-prs",
            }
            tab_id = tab_map.get(section)
            if tab_id:
                self._activate_tab(tab_id)
        
        elif nav_type == "language":
            # Create/find language project and link it
            self._link_language_project(nav_data)
        
        elif nav_type == "dependency":
            # Create/find dependency project and link it
            self._link_dependency_project(nav_data)
        
        elif nav_type == "contributor":
            # Show contributor info in viewer
            username = nav_data.get("username")
            contributions = nav_data.get("contributions", 0)
            url = nav_data.get("profile_url") or (f"https://github.com/{username}" if username else None)
            content = f"# {username}\n\n**Contributions:** {contributions}\n\n[View on GitHub]({url})" if url else f"# {username}\n\n**Contributions:** {contributions}"
            self.push_screen(ContentViewerScreen(
                title=f"Contributor: {username}",
                content=content,
                url=url
            ))
        
        elif nav_type == "source_file":
            # Show entire file with all sections combined
            source = nav_data.get("source")
            project_id = nav_data.get("project_id")
            if source and project_id:
                self._show_file_viewer(project_id, source)
        
        elif nav_type == "doc":
            # Show documentation content in viewer
            self._show_doc_viewer(nav_data)
        
        elif nav_type == "version":
            # Show version/release info in viewer
            version = nav_data.get("version")
            prerelease = nav_data.get("prerelease")
            url = nav_data.get("url")
            content = f"# Version {version}\n\n"
            if prerelease:
                content += f"**Prerelease:** {prerelease}\n\n"
            if url:
                content += f"[View Release on GitHub]({url})"
            self.push_screen(ContentViewerScreen(
                title=f"Release: v{version}",
                content=content,
                url=url
            ))
        
        elif nav_type == "branch":
            # Show branch info in viewer
            branch_name = nav_data.get("name")
            is_default = nav_data.get("is_default", False)
            url = nav_data.get("url")
            content = f"# Branch: {branch_name}\n\n"
            if is_default:
                content += "**Default branch** ✓\n\n"
            if url:
                content += f"[View on GitHub]({url})"
            self.push_screen(ContentViewerScreen(
                title=f"Branch: {branch_name}",
                content=content,
                url=url
            ))
        
        elif nav_type == "issue":
            # Show issue info in viewer
            self._show_issue_viewer(nav_data)
        
        elif nav_type == "pr":
            # Show PR info in viewer
            self._show_pr_viewer(nav_data)
        
        elif nav_type == "url":
            # For generic URLs, open browser directly
            url = nav_data.get("url")
            if url:
                import webbrowser
                webbrowser.open(url)
    
    def _show_doc_viewer(self, nav_data: dict) -> None:
        """Show documentation content in the viewer."""
        title = nav_data.get("title", "Documentation")
        source_file = nav_data.get("source_file")
        project_id = nav_data.get("project_id")
        url = nav_data.get("url")
        
        # Fetch the actual content from database
        content = ""
        if project_id:
            with self.session_factory() as session:
                doc = session.exec(
                    select(DocumentSection)
                    .where(DocumentSection.project_id == project_id)
                    .where(DocumentSection.title == title)
                ).first()
                if doc:
                    content = doc.content
        
        if not content:
            content = f"# {title}\n\n*Content not available*"
        
        self.push_screen(ContentViewerScreen(
            title=title,
            content=content,
            url=url
        ))
    
    def _show_issue_viewer(self, nav_data: dict) -> None:
        """Show issue details in the viewer."""
        issue_number = nav_data.get("number") or nav_data.get("issue_number")
        title = nav_data.get("title", f"Issue #{issue_number}")
        state = nav_data.get("state", "unknown")
        author = nav_data.get("author")
        labels = nav_data.get("labels")
        url = nav_data.get("url")
        project_id = nav_data.get("project_id")
        
        # Fetch body content if available
        body = ""
        if project_id and issue_number:
            with self.session_factory() as session:
                issue = session.exec(
                    select(ProjectIssue)
                    .where(ProjectIssue.project_id == project_id)
                    .where(ProjectIssue.issue_number == issue_number)
                ).first()
                if issue:
                    title = issue.title
                    state = issue.state
                    author = issue.author
                    labels = issue.labels
        
        state_icon = "🟢" if state == "open" else "⚫"
        content = f"# {title}\n\n"
        content += f"**Issue #{issue_number}** {state_icon} {state}\n\n"
        if author:
            content += f"**Author:** {author}\n\n"
        if labels:
            content += f"**Labels:** {labels}\n\n"
        content += "---\n\n"
        content += body or "*No description provided*"
        
        self.push_screen(ContentViewerScreen(
            title=f"Issue #{issue_number}: {title[:50]}",
            content=content,
            url=url
        ))
    
    def _show_pr_viewer(self, nav_data: dict) -> None:
        """Show pull request details in the viewer."""
        pr_number = nav_data.get("number") or nav_data.get("pr_number")
        title = nav_data.get("title", f"PR #{pr_number}")
        state = nav_data.get("state", "unknown")
        author = nav_data.get("author")
        is_merged = nav_data.get("is_merged", False)
        url = nav_data.get("url")
        project_id = nav_data.get("project_id")
        
        # Fetch more details if available
        body = ""
        base_branch = head_branch = ""
        additions = deletions = 0
        if project_id and pr_number:
            with self.session_factory() as session:
                pr = session.exec(
                    select(ProjectPullRequest)
                    .where(ProjectPullRequest.project_id == project_id)
                    .where(ProjectPullRequest.pr_number == pr_number)
                ).first()
                if pr:
                    title = pr.title
                    state = pr.state
                    author = pr.author
                    is_merged = pr.is_merged
                    base_branch = pr.base_branch
                    head_branch = pr.head_branch
                    additions = pr.additions or 0
                    deletions = pr.deletions or 0
        
        if is_merged:
            state_icon = "🟣"
            state_text = "merged"
        elif state == "open":
            state_icon = "🟢"
            state_text = "open"
        else:
            state_icon = "🔴"
            state_text = "closed"
        
        content = f"# {title}\n\n"
        content += f"**PR #{pr_number}** {state_icon} {state_text}\n\n"
        if author:
            content += f"**Author:** {author}\n\n"
        if base_branch and head_branch:
            content += f"**Branches:** `{head_branch}` → `{base_branch}`\n\n"
        if additions or deletions:
            content += f"**Changes:** +{additions} / -{deletions}\n\n"
        content += "---\n\n"
        content += body or "*No description provided*"
        
        self.push_screen(ContentViewerScreen(
            title=f"PR #{pr_number}: {title[:50]}",
            content=content,
            url=url
        ))
    
    @on(Tree.NodeSelected, "#docs-tree")
    def on_docs_tree_selected(self, event: Tree.NodeSelected) -> None:
        """Handle documentation tree node selection - show in viewer with navigation."""
        if not self.selected_project:
            return
        
        node = event.node
        if not node.data:
            return
        
        nav_type = node.data.get("type")
        if nav_type == "empty":
            return
        
        if nav_type == "source_file":
            # Show entire file with all sections combined
            source = node.data.get("source")
            project_id = node.data.get("project_id")
            if source and project_id:
                self._show_file_viewer(project_id, source)
        
        elif nav_type == "doc":
            doc_id = node.data.get("doc_id")
            doc_index = node.data.get("doc_index", 0)
            
            if doc_id:
                self._show_doc_with_navigation(doc_id, doc_index)
    
    def _show_doc_with_navigation(self, doc_id: int, doc_index: int) -> None:
        """Show document viewer with prev/next navigation support."""
        with self.session_factory() as session:
            doc = session.get(DocumentSection, doc_id)
            if not doc:
                return
            
            # Get content
            content = doc.content or f"# {doc.title}\n\n*Content not available*"
            
            # Construct URL
            base_url = self.selected_project.github_url
            file_path = extract_file_path(doc.source_file)
            url = f"{base_url}/blob/main/{file_path}" if base_url and file_path else None
            
            # Get doc list for navigation
            doc_list = getattr(self, "_current_doc_list", [])
            
            def navigate_to_doc(new_index: int):
                """Callback to navigate to a different document."""
                if 0 <= new_index < len(doc_list):
                    new_doc = doc_list[new_index]
                    # Pop current screen and show new one
                    self.pop_screen()
                    self._show_doc_with_navigation(new_doc.id, new_index)
            
            self.push_screen(ContentViewerScreen(
                title=doc.title,
                content=content,
                url=url,
                file_path=file_path,
                doc_index=doc_index,
                doc_list=doc_list,
                on_navigate=navigate_to_doc,
            ))
    
    def _show_tree_doc_viewer(self, doc_id: int, source_file: str | None = None) -> None:
        """Show document viewer for a doc clicked in the project tree (no navigation)."""
        with self.session_factory() as session:
            doc = session.get(DocumentSection, doc_id)
            if not doc:
                return
            
            # Get the project for this doc to build URL
            project = session.get(Project, doc.project_id)
            if not project:
                return
            
            # Get content
            content = doc.content or f"# {doc.title}\n\n*Content not available*"
            
            # Construct URL
            base_url = project.github_url
            file_path = extract_file_path(doc.source_file)
            url = f"{base_url}/blob/main/{file_path}" if base_url and file_path else None
            
            self.push_screen(ContentViewerScreen(
                title=doc.title,
                content=content,
                url=url,
                file_path=file_path,
            ))
    
    def _show_file_viewer(self, project_id: int, source_file: str) -> None:
        """Show viewer for an entire file with all sections combined vertically."""
        with self.session_factory() as session:
            # Get the project for this file
            project = session.get(Project, project_id)
            if not project:
                return
            
            # Fetch all sections for this source file, ordered
            sections = session.exec(
                select(DocumentSection)
                .where(DocumentSection.project_id == project_id)
                .where(DocumentSection.source_file == source_file)
                .order_by(DocumentSection.order)
            ).all()
            
            if not sections:
                return
            
            # Combine all section contents vertically
            combined_parts = []
            for section in sections:
                if section.content:
                    combined_parts.append(section.content)
            
            combined_content = "\n\n---\n\n".join(combined_parts) if combined_parts else "*No content available*"
            
            # Use the first section's title or file name as the title
            file_path = extract_file_path(source_file)
            title = file_path or sections[0].title
            
            # Construct URL
            base_url = project.github_url
            url = f"{base_url}/blob/main/{file_path}" if base_url and file_path else None
            
            self.push_screen(ContentViewerScreen(
                title=title,
                content=combined_content,
                url=url,
                file_path=file_path,
            ))
    
    @on(DataTable.RowSelected, "#issues-table")
    def on_issues_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle issues table row selection - show in viewer."""
        if not self.selected_project or event.row_key.value == "empty":
            return
        
        # Extract issue number from row key (format: "issue-{number}")
        row_key = str(event.row_key.value)
        if not row_key.startswith("issue-"):
            return
        
        try:
            issue_number = int(row_key.replace("issue-", ""))
        except ValueError:
            return
        
        # Fetch issue details and link to entity
        with self.session_factory() as session:
            issue = session.exec(
                select(ProjectIssue)
                .where(ProjectIssue.project_id == self.selected_project.id)
                .where(ProjectIssue.issue_number == issue_number)
            ).first()
            if issue:
                url = self.selected_project.github_issues_url(issue_number)
                self._link_issue_project({
                    "number": issue_number,
                    "title": issue.title,
                    "state": issue.state,
                    "project_id": self.selected_project.id,
                    "owner": self.selected_project.github_owner,
                    "repo": self.selected_project.github_repo,
                    "url": url,
                })
    
    @on(DataTable.RowSelected, "#prs-table")
    def on_prs_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle PRs table row selection - show in viewer."""
        if not self.selected_project or event.row_key.value == "empty":
            return
        
        # Extract PR number from row key (format: "pr-{number}")
        row_key = str(event.row_key.value)
        if not row_key.startswith("pr-"):
            return
        
        try:
            pr_number = int(row_key.replace("pr-", ""))
        except ValueError:
            return
        
        # Fetch PR details and link to entity
        with self.session_factory() as session:
            pr = session.exec(
                select(ProjectPullRequest)
                .where(ProjectPullRequest.project_id == self.selected_project.id)
                .where(ProjectPullRequest.pr_number == pr_number)
            ).first()
            if pr:
                url = self.selected_project.github_pulls_url(pr_number)
                self._link_pr_project({
                    "number": pr_number,
                    "title": pr.title,
                    "is_merged": pr.is_merged,
                    "project_id": self.selected_project.id,
                    "owner": self.selected_project.github_owner,
                    "repo": self.selected_project.github_repo,
                    "url": url,
                })
    
    @on(DataTable.RowSelected, "#releases-table")
    def on_releases_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle releases table row selection - show in viewer."""
        if not self.selected_project or event.row_key.value == "empty":
            return
        
        # Extract release ID from row key (format: "release-{id}")
        row_key = str(event.row_key.value)
        if not row_key.startswith("release-"):
            return
        
        try:
            release_id = int(row_key.replace("release-", ""))
        except ValueError:
            return
        
        # Fetch the release and link to entity
        with self.session_factory() as session:
            release = session.get(ProjectRelease, release_id)
            if release:
                url = self.selected_project.github_releases_url(release.tag_name)
                self._link_version_project({
                    "version": release.tag_name,
                    "prerelease": release.is_prerelease,
                    "project_id": self.selected_project.id,
                    "owner": self.selected_project.github_owner,
                    "repo": self.selected_project.github_repo,
                    "url": url,
                })
    
    @on(DataTable.RowSelected, "#languages-table")
    def on_languages_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle languages table row selection - show language info in viewer."""
        if not self.selected_project or event.row_key.value == "empty":
            return
        
        # Extract language ID from row key (format: "lang-{id}")
        row_key = str(event.row_key.value)
        if not row_key.startswith("lang-"):
            return
        
        try:
            lang_id = int(row_key.replace("lang-", ""))
        except ValueError:
            return
        
        with self.session_factory() as session:
            lang = session.get(ProjectLanguage, lang_id)
            if lang:
                self._link_language_project({
                    "name": lang.language,
                    "project_id": self.selected_project.id,
                    "owner": self.selected_project.github_owner,
                    "repo": self.selected_project.github_repo,
                })
    
    @on(DataTable.RowSelected, "#branches-table")
    def on_branches_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle branches table row selection - show branch info in viewer."""
        if not self.selected_project or event.row_key.value == "empty":
            return
        
        # Extract branch ID from row key (format: "branch-{id}")
        row_key = str(event.row_key.value)
        if not row_key.startswith("branch-"):
            return
        
        try:
            branch_id = int(row_key.replace("branch-", ""))
        except ValueError:
            return
        
        with self.session_factory() as session:
            branch = session.get(ProjectBranch, branch_id)
            if branch:
                url = self.selected_project.github_branch_url(branch.name)
                self._link_branch_project({
                    "name": branch.name,
                    "is_default": branch.is_default,
                    "project_id": self.selected_project.id,
                    "owner": self.selected_project.github_owner,
                    "repo": self.selected_project.github_repo,
                    "url": url,
                })
    
    @on(DataTable.RowSelected, "#dependencies-table")
    def on_dependencies_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle dependencies table row selection - show dependency info in viewer."""
        if not self.selected_project or event.row_key.value == "empty":
            return
        
        # Extract dependency ID from row key (format: "dep-{id}")
        row_key = str(event.row_key.value)
        if not row_key.startswith("dep-"):
            return
        
        try:
            dep_id = int(row_key.replace("dep-", ""))
        except ValueError:
            return
        
        with self.session_factory() as session:
            dep = session.get(ProjectDependency, dep_id)
            if dep:
                self._link_dependency_project({
                    "name": dep.name,
                    "version": dep.version_spec,
                    "project_id": self.selected_project.id,
                    "owner": self.selected_project.github_owner,
                    "repo": self.selected_project.github_repo,
                })
    
    @on(DataTable.RowSelected, "#components-table")
    def on_components_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle components table row selection - navigate to linked project."""
        if not self.selected_project or event.row_key.value == "empty":
            return
        
        # Extract project ID from row key (format: "comp-child-{id}" or "comp-parent-{id}")
        row_key = str(event.row_key.value)
        if row_key.startswith("comp-child-"):
            try:
                project_id = int(row_key.replace("comp-child-", ""))
            except ValueError:
                return
        elif row_key.startswith("comp-parent-"):
            try:
                project_id = int(row_key.replace("comp-parent-", ""))
            except ValueError:
                return
        else:
            return
        
        # Navigate to the linked project
        with self.session_factory() as session:
            linked_project = session.get(Project, project_id)
            if linked_project:
                self._select_project_by_name(linked_project.name)
                self.notify(f"Navigated to {linked_project.name}")

    @on(DataTable.RowSelected, "#deltas-table")
    def on_deltas_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle deltas table row selection."""
        if not self.selected_project or event.row_key.value == "empty":
            return

        row_key = str(event.row_key.value)
        if row_key.startswith("delta-link-"):
            try:
                link_id = int(row_key.replace("delta-link-", ""))
            except ValueError:
                return
            self._handle_delta_link_row(link_id)
            return

        if not row_key.startswith("delta-"):
            return

        try:
            delta_id = int(row_key.replace("delta-", ""))
        except ValueError:
            return

        with self.session_factory() as session:
            delta = session.get(ProjectDelta, delta_id)
            if delta:
                self._link_delta_project({
                    "delta_id": delta.id,
                    "name": delta.name,
                    "title": delta.title,
                    "phase": delta.phase.value,
                    "project_id": delta.project_id,
                })

    def _handle_delta_link_row(self, link_id: int) -> None:
        """Handle delta link subrows from the deltas table."""
        with self.session_factory() as session:
            link = session.get(DeltaLink, link_id)
            if not link:
                return
            delta = session.get(ProjectDelta, link.delta_id)
            if not delta:
                return
            project = session.get(Project, delta.project_id)
            if not project:
                return

            link_type = link.link_type
            if link_type == "issue":
                number = link.target_id
                if number is None and link.target_name:
                    try:
                        number = int(link.target_name)
                    except ValueError:
                        number = None
                if number is None:
                    return
                issue = session.exec(
                    select(ProjectIssue)
                    .where(ProjectIssue.project_id == project.id)
                    .where(ProjectIssue.issue_number == number)
                ).first()
                self._link_issue_project({
                    "number": number,
                    "title": issue.title if issue else "",
                    "state": issue.state if issue else "open",
                    "project_id": project.id,
                    "owner": project.github_owner,
                    "repo": project.github_repo,
                    "url": project.github_issues_url(number) if project.github_owner else None,
                })
            elif link_type == "pr":
                number = link.target_id
                if number is None and link.target_name:
                    try:
                        number = int(link.target_name)
                    except ValueError:
                        number = None
                if number is None:
                    return
                pr = session.exec(
                    select(ProjectPullRequest)
                    .where(ProjectPullRequest.project_id == project.id)
                    .where(ProjectPullRequest.pr_number == number)
                ).first()
                self._link_pr_project({
                    "number": number,
                    "title": pr.title if pr else "",
                    "is_merged": pr.is_merged if pr else False,
                    "project_id": project.id,
                    "owner": project.github_owner,
                    "repo": project.github_repo,
                    "url": project.github_pulls_url(number) if project.github_owner else None,
                })
            elif link_type == "branch":
                branch_name = link.target_name or (str(link.target_id) if link.target_id is not None else None)
                if not branch_name:
                    return
                branch = session.exec(
                    select(ProjectBranch)
                    .where(ProjectBranch.project_id == project.id)
                    .where(ProjectBranch.name == branch_name)
                ).first()
                self._link_branch_project({
                    "name": branch_name,
                    "is_default": branch.is_default if branch else False,
                    "project_id": project.id,
                    "owner": project.github_owner,
                    "repo": project.github_repo,
                    "url": project.github_branch_url(branch_name) if project.github_owner else None,
                })
            elif link_type == "doc":
                doc_title = link.target_name or (str(link.target_id) if link.target_id is not None else None)
                if not doc_title:
                    return
                doc = session.exec(
                    select(DocumentSection)
                    .where(DocumentSection.project_id == project.id)
                    .where(DocumentSection.title == doc_title)
                ).first()
                self._link_doc_project({
                    "title": doc.title if doc else doc_title,
                    "section_type": doc.section_type if doc else "doc",
                    "source_file": doc.source_file if doc else None,
                    "project_id": project.id,
                    "owner": project.github_owner,
                    "repo": project.github_repo,
                })
            elif link_type == "delta":
                target_delta = None
                if link.target_id is not None:
                    target_delta = session.get(ProjectDelta, link.target_id)
                if target_delta is None and link.target_name:
                    target_delta = session.exec(
                        select(ProjectDelta)
                        .where(ProjectDelta.project_id == project.id)
                        .where(ProjectDelta.name == link.target_name)
                    ).first()
                if not target_delta:
                    return
                self._link_delta_project({
                    "delta_id": target_delta.id,
                    "name": target_delta.name,
                    "title": target_delta.title,
                    "phase": target_delta.phase.value,
                    "project_id": target_delta.project_id,
                })
    
    def action_open_tree_url(self) -> None:
        """Open the URL of the last selected tree item in browser."""
        if not self._last_tree_node_data:
            self.notify("Select an item in the tree first", severity="warning")
            return
        
        url = self._last_tree_node_data.get("url")
        if not url:
            # Try to construct URL from other data
            nav_type = self._last_tree_node_data.get("type")
            if nav_type == "contributor":
                username = self._last_tree_node_data.get("username")
                if username:
                    url = f"https://github.com/{username}"
        
        if url:
            import webbrowser
            webbrowser.open(url)
            self.notify(f"Opening {url[:50]}...")
        else:
            self.notify("No URL available for this item", severity="warning")
    
    def _link_language_project(self, nav_data: dict) -> None:
        """Create or find a language project and link it to the current project."""
        lang_name = nav_data.get("name")
        parent_project_id = nav_data.get("project_id")
        owner = nav_data.get("owner")
        repo = nav_data.get("repo")
        
        if not lang_name or not parent_project_id:
            return
        
        # Languages are global - same language across all repos
        project_name = f"lang/{lang_name.lower()}"
        
        with self.session_factory() as session:
            # Check if language project exists
            lang_project = session.exec(
                select(Project).where(Project.name == project_name)
            ).first()
            
            if not lang_project:
                # Create the language project (global, no owner/repo scope)
                lang_project = Project(
                    name=project_name,
                    description=f"{lang_name} programming language",
                    github_language=lang_name,
                )
                session.add(lang_project)
                session.commit()
                session.refresh(lang_project)
                self.notify(f"Created language project: {project_name}")
            
            # Check if link already exists
            existing_link = session.exec(
                select(ProjectComponent).where(
                    ProjectComponent.parent_id == parent_project_id,
                    ProjectComponent.child_id == lang_project.id,
                )
            ).first()
            
            if not existing_link:
                # Create the link
                link = ProjectComponent(
                    parent_id=parent_project_id,
                    child_id=lang_project.id,
                    relationship_type="language",
                    order=0,
                )
                session.add(link)
                session.commit()
                self.notify(f"Linked {lang_name} as language component")
            else:
                self.notify(f"{lang_name} already linked", severity="warning")
        
        # Refresh the tree and navigate to the language project
        self.load_projects()
        self._select_project_by_name(project_name)
    
    def _link_dependency_project(self, nav_data: dict) -> None:
        """Create or find a dependency project and link it to the current project."""
        dep_name = nav_data.get("name")
        version = nav_data.get("version")
        parent_project_id = nav_data.get("project_id")
        owner = nav_data.get("owner")
        repo = nav_data.get("repo")
        
        if not dep_name or not parent_project_id:
            return
        
        # Packages are global - same package across all repos
        project_name = f"pkg/{dep_name.lower()}"
        
        with self.session_factory() as session:
            # Check if dependency project exists
            dep_project = session.exec(
                select(Project).where(Project.name == project_name)
            ).first()
            
            if not dep_project:
                # Create the dependency project (global, no owner/repo scope)
                description = f"{dep_name} package"
                if version:
                    description += f" (version: {version})"
                dep_project = Project(
                    name=project_name,
                    description=description,
                )
                session.add(dep_project)
                session.commit()
                session.refresh(dep_project)
                self.notify(f"Created package project: {project_name}")
            
            # Check if link already exists
            existing_link = session.exec(
                select(ProjectComponent).where(
                    ProjectComponent.parent_id == parent_project_id,
                    ProjectComponent.child_id == dep_project.id,
                )
            ).first()
            
            if not existing_link:
                # Create the link
                link = ProjectComponent(
                    parent_id=parent_project_id,
                    child_id=dep_project.id,
                    relationship_type="dependency",
                    order=0,
                )
                session.add(link)
                session.commit()
                self.notify(f"Linked {dep_name} as dependency")
            else:
                self.notify(f"{dep_name} already linked", severity="warning")
        
        # Refresh the tree and navigate to the dependency project
        self.load_projects()
        self._select_project_by_name(project_name)
    
    def _link_contributor_project(self, nav_data: dict) -> None:
        """Create or find a contributor project and link it to the current project."""
        username = nav_data.get("username")
        profile_url = nav_data.get("profile_url")
        parent_project_id = nav_data.get("project_id")
        owner = nav_data.get("owner")
        repo = nav_data.get("repo")
        
        if not username or not parent_project_id:
            return
        
        # Create a project name for the contributor scoped to platform (app-wide)
        # Same user across all repos on GitHub
        project_name = f"github/user/{username.lower()}"
        
        with self.session_factory() as session:
            # Check if contributor project exists
            user_project = session.exec(
                select(Project).where(Project.name == project_name)
            ).first()
            
            if not user_project:
                # Create the contributor project
                user_project = Project(
                    name=project_name,
                    description=f"GitHub user: {username}",
                    repository_url=profile_url,
                    github_owner=owner or username,
                    github_repo=repo,
                )
                session.add(user_project)
                session.commit()
                session.refresh(user_project)
                self.notify(f"Created user project: {project_name}")
            
            # Check if link already exists
            existing_link = session.exec(
                select(ProjectComponent).where(
                    ProjectComponent.parent_id == parent_project_id,
                    ProjectComponent.child_id == user_project.id,
                )
            ).first()
            
            if not existing_link:
                # Create the link
                link = ProjectComponent(
                    parent_id=parent_project_id,
                    child_id=user_project.id,
                    relationship_type="contributor",
                    order=0,
                )
                session.add(link)
                session.commit()
                self.notify(f"Linked {username} as contributor")
            else:
                self.notify(f"{username} already linked", severity="warning")
        
        # Refresh the tree and navigate to the contributor project
        self.load_projects()
        self._select_project_by_name(project_name)
    
    def _link_doc_project(self, nav_data: dict) -> None:
        """Create or find a documentation project and link it to the current project."""
        title = nav_data.get("title")
        section_type = nav_data.get("section_type", "doc")
        source_file = nav_data.get("source_file")
        parent_project_id = nav_data.get("project_id")
        url = nav_data.get("url")
        owner = nav_data.get("owner")
        repo = nav_data.get("repo")
        
        if not title or not parent_project_id:
            return
        
        # Create a project name for the doc with owner/repo for disambiguation
        slug = title.lower().replace(" ", "-")[:30]
        if owner and repo:
            project_name = f"{owner}/{repo}/doc/{section_type}-{slug}"
        else:
            project_name = f"doc/{section_type}-{slug}"
        
        with self.session_factory() as session:
            doc_project = session.exec(
                select(Project).where(Project.name == project_name)
            ).first()
            
            if not doc_project:
                doc_project = Project(
                    name=project_name,
                    description=f"Documentation: {title}",
                    repository_url=url,
                    documentation_path=source_file,
                    github_owner=owner,
                    github_repo=repo,
                )
                session.add(doc_project)
                session.commit()
                session.refresh(doc_project)
                self.notify(f"Created doc project: {project_name}")
            
            existing_link = session.exec(
                select(ProjectComponent).where(
                    ProjectComponent.parent_id == parent_project_id,
                    ProjectComponent.child_id == doc_project.id,
                )
            ).first()
            
            if not existing_link:
                link = ProjectComponent(
                    parent_id=parent_project_id,
                    child_id=doc_project.id,
                    relationship_type="doc",
                    order=0,
                )
                session.add(link)
                session.commit()
                self.notify(f"Linked '{title}' as documentation")
            else:
                self.notify(f"'{title}' already linked", severity="warning")
        
        self.load_projects()
        self._select_project_by_name(project_name)
    
    def _link_version_project(self, nav_data: dict) -> None:
        """Create or find a version project and link it to the current project."""
        version = nav_data.get("version")
        tag_name = nav_data.get("tag_name", version)
        parent_project_id = nav_data.get("project_id")
        url = nav_data.get("url")
        owner = nav_data.get("owner")
        repo = nav_data.get("repo")
        
        if not version or not parent_project_id:
            return
        
        # Create a project name for the version with owner/repo for disambiguation
        # Normalize version string
        ver_slug = version.lstrip("v").replace("/", "-")
        if owner and repo:
            project_name = f"{owner}/{repo}/ver/v{ver_slug}"
        else:
            project_name = f"ver/v{ver_slug}"
        
        with self.session_factory() as session:
            ver_project = session.exec(
                select(Project).where(Project.name == project_name)
            ).first()
            
            if not ver_project:
                ver_project = Project(
                    name=project_name,
                    description=f"Version {version}",
                    repository_url=url,
                    github_owner=owner,
                    github_repo=repo,
                )
                session.add(ver_project)
                session.commit()
                session.refresh(ver_project)
                self.notify(f"Created version project: {project_name}")
            
            existing_link = session.exec(
                select(ProjectComponent).where(
                    ProjectComponent.parent_id == parent_project_id,
                    ProjectComponent.child_id == ver_project.id,
                )
            ).first()
            
            if not existing_link:
                link = ProjectComponent(
                    parent_id=parent_project_id,
                    child_id=ver_project.id,
                    relationship_type="version",
                    order=0,
                )
                session.add(link)
                session.commit()
                self.notify(f"Linked version {version}")
            else:
                self.notify(f"Version {version} already linked", severity="warning")
        
        self.load_projects()
        self._select_project_by_name(project_name)
    
    def _link_branch_project(self, nav_data: dict) -> None:
        """Create or find a branch project and link it to the current project."""
        name = nav_data.get("name")
        is_default = nav_data.get("is_default", False)
        parent_project_id = nav_data.get("project_id")
        url = nav_data.get("url")
        owner = nav_data.get("owner")
        repo = nav_data.get("repo")
        
        if not name or not parent_project_id:
            return
        
        # Create a project name for the branch with owner/repo for disambiguation
        branch_slug = name.replace("/", "-")
        if owner and repo:
            project_name = f"{owner}/{repo}/branch/{branch_slug}"
        else:
            project_name = f"branch/{branch_slug}"
        
        with self.session_factory() as session:
            branch_project = session.exec(
                select(Project).where(Project.name == project_name)
            ).first()
            
            if not branch_project:
                desc = f"Branch: {name}"
                if is_default:
                    desc += " (default)"
                branch_project = Project(
                    name=project_name,
                    description=desc,
                    repository_url=url,
                    github_owner=owner,
                    github_repo=repo,
                )
                session.add(branch_project)
                session.commit()
                session.refresh(branch_project)
                self.notify(f"Created branch project: {project_name}")
            
            existing_link = session.exec(
                select(ProjectComponent).where(
                    ProjectComponent.parent_id == parent_project_id,
                    ProjectComponent.child_id == branch_project.id,
                )
            ).first()
            
            if not existing_link:
                link = ProjectComponent(
                    parent_id=parent_project_id,
                    child_id=branch_project.id,
                    relationship_type="branch",
                    order=0,
                )
                session.add(link)
                session.commit()
                self.notify(f"Linked branch {name}")
            else:
                self.notify(f"Branch {name} already linked", severity="warning")
        
        self.load_projects()
        self._select_project_by_name(project_name)
    
    def _link_issue_project(self, nav_data: dict) -> None:
        """Create or find an issue project and link it to the current project."""
        number = nav_data.get("number")
        title = nav_data.get("title", "")
        state = nav_data.get("state", "open")
        parent_project_id = nav_data.get("project_id")
        url = nav_data.get("url")
        owner = nav_data.get("owner")
        repo = nav_data.get("repo")
        
        if not number or not parent_project_id:
            return
        
        # Create a project name for the issue with owner/repo for disambiguation
        if owner and repo:
            project_name = f"{owner}/{repo}/issue/{number}"
        else:
            project_name = f"issue/{number}"
        
        with self.session_factory() as session:
            issue_project = session.exec(
                select(Project).where(Project.name == project_name)
            ).first()
            
            if not issue_project:
                desc = f"Issue #{number}: {title[:80]}"
                issue_project = Project(
                    name=project_name,
                    description=desc,
                    repository_url=url,
                    github_owner=owner,
                    github_repo=repo,
                )
                session.add(issue_project)
                session.commit()
                session.refresh(issue_project)
                self.notify(f"Created issue project: {project_name}")
            
            existing_link = session.exec(
                select(ProjectComponent).where(
                    ProjectComponent.parent_id == parent_project_id,
                    ProjectComponent.child_id == issue_project.id,
                )
            ).first()
            
            if not existing_link:
                link = ProjectComponent(
                    parent_id=parent_project_id,
                    child_id=issue_project.id,
                    relationship_type="issue",
                    order=0,
                )
                session.add(link)
                session.commit()
                self.notify(f"Linked issue #{number}")
            else:
                self.notify(f"Issue #{number} already linked", severity="warning")
        
        self.load_projects()
        self._select_project_by_name(project_name)
    
    def _link_pr_project(self, nav_data: dict) -> None:
        """Create or find a pull request project and link it to the current project."""
        number = nav_data.get("number")
        title = nav_data.get("title", "")
        is_merged = nav_data.get("is_merged", False)
        parent_project_id = nav_data.get("project_id")
        url = nav_data.get("url")
        owner = nav_data.get("owner")
        repo = nav_data.get("repo")
        
        if not number or not parent_project_id:
            return
        
        # Create a project name for the PR with owner/repo for disambiguation
        if owner and repo:
            project_name = f"{owner}/{repo}/pr/{number}"
        else:
            project_name = f"pr/{number}"
        
        with self.session_factory() as session:
            pr_project = session.exec(
                select(Project).where(Project.name == project_name)
            ).first()
            
            if not pr_project:
                desc = f"PR #{number}: {title[:80]}"
                if is_merged:
                    desc += " (merged)"
                pr_project = Project(
                    name=project_name,
                    description=desc,
                    repository_url=url,
                    github_owner=owner,
                    github_repo=repo,
                )
                session.add(pr_project)
                session.commit()
                session.refresh(pr_project)
                self.notify(f"Created PR project: {project_name}")
            
            existing_link = session.exec(
                select(ProjectComponent).where(
                    ProjectComponent.parent_id == parent_project_id,
                    ProjectComponent.child_id == pr_project.id,
                )
            ).first()
            
            if not existing_link:
                link = ProjectComponent(
                    parent_id=parent_project_id,
                    child_id=pr_project.id,
                    relationship_type="pr",
                    order=0,
                )
                session.add(link)
                session.commit()
                self.notify(f"Linked PR #{number}")
            else:
                self.notify(f"PR #{number} already linked", severity="warning")
        
        self.load_projects()
        self._select_project_by_name(project_name)

    def _link_delta_project(self, nav_data: dict) -> None:
        """Create or find a delta project and link it to the current project."""
        delta_id = nav_data.get("delta_id")
        name = nav_data.get("name")
        title = nav_data.get("title", "")
        phase = nav_data.get("phase", "brainstorm")
        parent_project_id = nav_data.get("project_id")

        if not delta_id or not name or not parent_project_id:
            return

        # Get parent project info for naming
        with self.session_factory() as session:
            parent_project = session.get(Project, parent_project_id)
            if not parent_project:
                return

            owner = parent_project.github_owner
            repo = parent_project.github_repo

            # Create a project name for the delta with owner/repo for disambiguation
            if owner and repo:
                project_name = f"{owner}/{repo}/delta/{name}"
            else:
                project_name = f"delta/{name}"

            delta_project = session.exec(
                select(Project).where(Project.name == project_name)
            ).first()

            if not delta_project:
                desc = f"Delta: {title[:80]} [{phase}]"
                delta_project = Project(
                    name=project_name,
                    full_name=project_name,
                    description=desc,
                    github_owner=owner,
                    github_repo=repo,
                )
                session.add(delta_project)
                session.commit()
                session.refresh(delta_project)
                self.notify(f"Created delta project: {project_name}")

            existing_link = session.exec(
                select(ProjectComponent).where(
                    ProjectComponent.parent_id == parent_project_id,
                    ProjectComponent.child_id == delta_project.id,
                )
            ).first()

            if not existing_link:
                link = ProjectComponent(
                    parent_id=parent_project_id,
                    child_id=delta_project.id,
                    relationship_type="delta",
                    order=0,
                )
                session.add(link)
                session.commit()
                self.notify(f"Linked delta: {name}")
            else:
                self.notify(f"Delta {name} already linked", severity="warning")

        self.load_projects()
        self._select_project_by_name(project_name)

    def _select_project_by_name(self, name: str, target_tab: Optional[str] = None) -> None:
        """Select a project by name in the project tree.

        Args:
            name: The project name to select
            target_tab: Optional tab to switch to after selection (e.g., 'tab-languages')
        """
        # Skip if already on this project
        if self.selected_project and self.selected_project.name == name:
            # Still switch tab if requested
            if target_tab:
                self._activate_tab(target_tab)
            return
        
        # Set flag to prevent auto-switch to dossier tab
        self._navigating_from_tree = True
        self._tree_target_tab = target_tab
        
        # Search tree for the project
        project_tree = self.query_one("#project-tree", Tree)
        
        def find_project_node(node):
            """Recursively search tree for project node."""
            if node.data and node.data.get("type") == "project":
                proj = node.data.get("project")
                if proj and proj.name == name:
                    return node
            for child in node.children:
                result = find_project_node(child)
                if result:
                    return result
            return None
        
        found_node = find_project_node(project_tree.root)
        if found_node:
            # Expand parent nodes
            parent = found_node.parent
            while parent:
                parent.expand()
                parent = parent.parent
            # Select the node
            project_tree.select_node(found_node)
            project = found_node.data.get("project")
            self.selected_project = project
            self.show_project_details(project)
            self.notify(f"Navigated to {name}")
            return
        
        # Not in current tree - try database lookup
        with self.session_factory() as session:
            project = session.exec(
                select(Project).where(Project.name == name)
            ).first()
            
            if project:
                session.expunge(project)
                # Reload tree to include the new project and select it
                self.load_projects()
                # Try again after reload
                found_node = find_project_node(project_tree.root)
                if found_node:
                    parent = found_node.parent
                    while parent:
                        parent.expand()
                        parent = parent.parent
                    project_tree.select_node(found_node)
                self.selected_project = project
                self.show_project_details(project)
                self.notify(f"Navigated to {name}")
                return
        
        # Reset flags if project not found
        self._navigating_from_tree = False
        self._tree_target_tab = None
        # Project not in database
        self.notify(f"Project '{name}' not found", severity="warning")
    
    def watch_selected_project(self, project: Optional[Project]) -> None:
        """React to project selection changes."""
        if project:
            display_name = self._shorten_project_name(project.name)
            self.sub_title = f"Viewing: {display_name}"
        else:
            self.sub_title = "Documentation Standardization Tool"
    
    @on(Button.Pressed, "#btn-sync")
    def on_sync_pressed(self) -> None:
        """Handle sync button press."""
        self.action_sync()
    
    @on(Button.Pressed, "#btn-add")
    def on_add_pressed(self) -> None:
        """Handle add button press."""
        self.action_add()
    
    @on(Button.Pressed, "#btn-delete")
    def on_delete_pressed(self) -> None:
        """Handle delete button press."""
        self.action_delete()
    
    @on(Button.Pressed, "#btn-help")
    def on_help_pressed(self) -> None:
        """Handle help button press."""
        self.action_help()
    
    @on(Button.Pressed, "#btn-add-component")
    def on_add_component_pressed(self) -> None:
        """Handle add component button press."""
        self.action_add_component()
    
    @on(Button.Pressed, "#btn-link-parent")
    def on_link_parent_pressed(self) -> None:
        """Handle link as parent button press."""
        self.action_link_parent()
    
    @on(Button.Pressed, "#btn-remove-component")
    def on_remove_component_pressed(self) -> None:
        """Handle remove component button press."""
        self.action_remove_component()

    @on(Button.Pressed, "#btn-new-delta")
    def on_new_delta_pressed(self) -> None:
        """Handle new delta button press."""
        self.action_new_delta()

    @on(Button.Pressed, "#btn-advance-phase")
    def on_advance_phase_pressed(self) -> None:
        """Handle advance phase button press."""
        self.action_advance_delta_phase()

    @on(Button.Pressed, "#btn-add-note")
    def on_add_note_pressed(self) -> None:
        """Handle add note button press."""
        self.action_add_delta_note()

    @on(Button.Pressed, "#btn-add-delta-link")
    def on_add_delta_link_pressed(self) -> None:
        """Handle add delta link button press."""
        self.action_add_delta_link()

    @on(Button.Pressed, "#btn-filter-all")
    def on_filter_all_pressed(self) -> None:
        """Show all projects (clear sync filter)."""
        self.filter_synced = None
        self._update_filter_buttons()
        search_input = self.query_one("#search-input", Input)
        self.load_projects(search=search_input.value)
    
    @on(Button.Pressed, "#btn-filter-synced")
    def on_filter_synced_pressed(self) -> None:
        """Show only synced projects."""
        self.filter_synced = True
        self._update_filter_buttons()
        search_input = self.query_one("#search-input", Input)
        self.load_projects(search=search_input.value)
    
    @on(Button.Pressed, "#btn-filter-unsynced")
    def on_filter_unsynced_pressed(self) -> None:
        """Show only unsynced projects."""
        self.filter_synced = False
        self._update_filter_buttons()
        search_input = self.query_one("#search-input", Input)
        self.load_projects(search=search_input.value)
    
    @on(Button.Pressed, "#btn-filter-starred")
    def on_filter_starred_pressed(self) -> None:
        """Toggle starred filter: None -> True (starred) -> False (no stars) -> None."""
        if self.filter_starred is None:
            self.filter_starred = True
        elif self.filter_starred is True:
            self.filter_starred = False
        else:
            self.filter_starred = None
        self._update_filter_buttons()
        search_input = self.query_one("#search-input", Input)
        self.load_projects(search=search_input.value)
        
        status = "starred only" if self.filter_starred is True else "no stars" if self.filter_starred is False else "all"
        self.notify(f"Filter: {status}")
    
    # Sorting is a Select (`#select-sort`), not buttons. Three
    # `@on(Button.Pressed, "#btn-sort-*")` handlers outlived the buttons they
    # were written for and are gone: a handler for a widget that does not exist
    # reads like a feature to anybody grepping for one.

    @on(Select.Changed, "#select-language")
    def on_language_changed(self, event: Select.Changed) -> None:
        """Handle language filter change."""
        self.filter_language = event.value if event.value else None
        search_input = self.query_one("#search-input", Input)
        self.load_projects(search=search_input.value)

    @on(Select.Changed, "#select-sort")
    def on_sort_changed(self, event: Select.Changed) -> None:
        """Handle sort selection change."""
        if event.value:
            self.sort_by = event.value
        search_input = self.query_one("#search-input", Input)
        self.load_projects(search=search_input.value)
    
    def _update_filter_buttons(self) -> None:
        """Update filter button variants to show active state."""
        btn_all = self.query_one("#btn-filter-all", Button)
        btn_synced = self.query_one("#btn-filter-synced", Button)
        btn_unsynced = self.query_one("#btn-filter-unsynced", Button)
        btn_starred = self.query_one("#btn-filter-starred", Button)

        # Update sync filter buttons
        btn_all.variant = "primary" if self.filter_synced is None else "default"
        btn_synced.variant = "primary" if self.filter_synced is True else "default"
        btn_unsynced.variant = "primary" if self.filter_synced is False else "default"

        # Update starred filter button (cycles through states)
        if self.filter_starred is None:
            btn_starred.variant = "default"
            btn_starred.label = "Star"
        elif self.filter_starred is True:
            btn_starred.variant = "primary"
            btn_starred.label = "Starred"
        else:
            btn_starred.variant = "warning"
            btn_starred.label = "Unstarred"

    def _update_filter_ui(self) -> None:
        """Update all filter UI elements to match current filter state."""
        self._update_filter_buttons()
        
        # Update language select  
        try:
            select_lang = self.query_one("#select-language", Select)
            select_lang.value = self.filter_language if self.filter_language else ""
        except Exception:
            pass

        self._update_sort_ui()
    
    def _update_sort_ui(self) -> None:
        """Update sort UI to match current sort state."""
        try:
            select_sort = self.query_one("#select-sort", Select)
            select_sort.value = self.sort_by
        except Exception:
            pass

    @on(DataTable.RowSelected, ".overview-section")
    def on_overview_row_selected(self, event: DataTable.RowSelected) -> None:
        """A row in the overview opens the tab holding its detail.

        This is the link between the two axes: the overview says how much of
        something there is across the org, and the tab says what it is for one
        repository. Without the route they are two readings a person has to
        reconcile by hand.
        """
        table_id = event.data_table.id or ""
        panel = self.query_one(OverviewPanel)
        section = panel.section_for(table_id)
        if section is None:
            return
        tab, repo = panel.target_for(section, str(event.row_key.value))
        if tab is None:
            return

        # The tab is activated before the project is selected. Selecting first
        # and activating second looked more natural and did not work: selecting
        # runs a refresh that settles after this handler returns, and the tab
        # set during it was overwritten by the state the refresh had captured.
        self._activate_tab(tab)
        if repo:
            with self.session_factory() as session:
                project = session.exec(
                    select(Project).where(
                        (Project.full_name == repo) | (Project.name == repo)
                    )
                ).first()
                if project is not None:
                    session.expunge(project)
                    self.selected_project = project
                    self.show_project_details(project)
        self._load_tab_data(tab)

        # Focus follows the reader to the destination. Without this the tab
        # switches and switches back: focus is still on the overview's table,
        # which lives in the overview pane, and the pane holding focus wins.
        facet = FACET_BY_TAB.get(tab)
        if facet is not None:
            try:
                self.query_one(f"#{facet.table}", DataTable).focus()
            except Exception:
                pass

    def _render_section(self, table_id: str, section) -> None:
        """Draw a `Section` into a `DataTable`, whatever scope produced it.

        Columns are reset rather than assumed: the same table shows an org
        reading and a project reading of one facet, and those have different
        widths. A table whose columns are declared once can only ever show one
        of them.
        """
        table = self.query_one(f"#{table_id}", DataTable)
        table.clear(columns=True)
        table.add_columns(*section.headers)
        if not section.rows:
            table.add_row(*["--"] * len(section.headers), key="empty")
            return
        for index, row in enumerate(section.rows):
            table.add_row(*row, key=f"{table_id}-{index}")

    def _render_facet_at_org(self, facet, owner: str) -> None:
        from dossier.overview import scope_ids

        with self.session_factory() as session:
            ids = scope_ids(session, owner)
            section = facet.at(session, ids=ids)
        self._render_section(facet.table, section)

    def _render_facet_for_project(self, facet, project) -> None:
        with self.session_factory() as session:
            section = facet.at(session, project=project)
        self._render_section(facet.table, section)

    def show_org_overview(self, owner: str) -> None:
        """Select the organisation itself, and show it.

        An owner is a scope, not a heading: every facet tab can be read across
        it exactly as it can be read for one repository, and they read it
        through the same facet. So selecting an owner clears the project
        selection rather than leaving the tabs describing whichever repository
        was chosen before.
        """
        self._scope_owner = owner
        self._current_project = None
        self._current_project_id = None
        self._tabs_loaded = set()
        panel = self.query_one(OverviewPanel)
        panel.set_owner(owner)
        self._activate_tab("tab-overview")
        self._load_tab_data("tab-overview")

    def _filter_matches_anything(self) -> bool:
        """Whether the current filters select at least one project."""
        filters = []
        if self.filter_synced is True:
            filters.append(Project.last_synced_at.isnot(None))
        elif self.filter_synced is False:
            filters.append(Project.last_synced_at.is_(None))
        if not filters:
            return True
        from sqlalchemy import func

        with self.session_factory() as session:
            stmt = select(func.count()).select_from(Project)
            for clause in filters:
                stmt = stmt.where(clause)
            return bool(session.exec(stmt).one())

    def _restore_view_state(self) -> None:
        """Restore view state from config on app mount."""
        vs = self._config.view_state

        # A restored filter that now matches nothing empties the sidebar with
        # no visible reason: the saved state said "unsynced" and every project
        # had since been synced, so the list was blank and the control that
        # explained it was two panels away. A filter is worth restoring only
        # while it still selects something.
        if vs and vs.filter_synced is not None and not self._filter_matches_anything():
            self.filter_synced = None

        # Load projects first
        self.load_projects(auto_select=False)
        
        # Try to restore the last selected project
        if vs and vs.last_project:
            with self.session_factory() as session:
                project = session.exec(
                    select(Project).where(Project.full_name == vs.last_project)
                ).first()
                if project:
                    self.selected_project = project
                    self.show_project_details(project)
                    
                    # Restore active tab
                    if vs.active_tab:
                        self._activate_tab(vs.active_tab)
                    return
        
        # Fall back to auto-selecting first project
        self.load_projects(auto_select=True)
    
    def _save_view_state(self) -> None:
        """Save current view state to config."""
        # Get current active tab
        active_tab = self._get_active_tab_id()
        
        # Get selected project's full_name
        last_project = None
        if self.selected_project:
            last_project = self.selected_project.full_name
        
        # Save to config
        self._config.save_view_state(
            last_project=last_project,
            active_tab=active_tab,
            filter_synced=self.filter_synced,
            filter_language=self.filter_language,
            filter_entity=self.filter_entity,
            filter_starred=self.filter_starred,
            sort_by=self.sort_by,
        )
    
    def action_quit(self) -> None:
        """Quit the application, saving view state."""
        self._save_view_state()
        self.exit()
    
    def action_refresh(self) -> None:
        """Refresh the project list."""
        search_input = self.query_one("#search-input", Input)
        self.load_projects(search=search_input.value)
        self.notify("Refreshed project list")
    
    def action_open_url(self, url: str) -> None:
        """Open a URL in the system browser."""
        import webbrowser
        webbrowser.open(url)
        self.notify(f"Opening {url[:50]}...")
    
    def action_open_github(self) -> None:
        """Open in browser - context sensitive.
        
        If tree has focus and an item is selected, open that item's URL.
        Otherwise, open the selected project's GitHub page.
        """
        # Check if tree has focus and has a selected item
        try:
            tree = self.query_one("#component-tree", Tree)
            if tree.has_focus and self._last_tree_node_data:
                self.action_open_tree_url()
                return
        except Exception:
            pass
        
        # Fall back to opening the selected project
        if self.selected_project:
            url = self.selected_project.github_url
            if url:
                self.action_open_url(url)
            else:
                self.notify("Project has no GitHub URL", severity="warning")
        else:
            self.notify("Select a project first", severity="warning")
    
    def action_link_selected(self) -> None:
        """Link the currently selected tree item as a project component.
        
        Press 'l' when a tree item is highlighted to create/link it as a project.
        This is useful for building project hierarchies from entities.
        """
        try:
            tree = self.query_one("#component-tree", Tree)
            node = tree.cursor_node
            if not node or not node.data:
                self.notify("Select an item in the tree first", severity="warning")
                return
            
            nav_data = node.data
            nav_type = nav_data.get("type")
            
            if nav_type == "language":
                self._link_language_project(nav_data)
            elif nav_type == "dependency":
                self._link_dependency_project(nav_data)
            elif nav_type == "contributor":
                self._link_contributor_project(nav_data)
            elif nav_type == "doc":
                self._link_doc_project(nav_data)
            elif nav_type == "version":
                self._link_version_project(nav_data)
            elif nav_type == "branch":
                self._link_branch_project(nav_data)
            elif nav_type == "issue":
                self._link_issue_project(nav_data)
            elif nav_type == "pr":
                self._link_pr_project(nav_data)
            elif nav_type == "delta":
                self._link_delta_project(nav_data)
            elif nav_type == "project":
                self.notify("Already a project", severity="warning")
            elif nav_type == "section":
                self.notify("Section headers cannot be linked", severity="warning")
            else:
                self.notify(f"Cannot link {nav_type} as project", severity="warning")
        except Exception:
            self.notify("Focus the tree panel first", severity="warning")

    def action_toggle_select(self) -> None:
        """Toggle multi-selection for the current project."""
        if not self.selected_project:
            self.notify("Select a project first", severity="warning")
            return
        
        project_id = self.selected_project.id
        new_selection = set(self.selected_projects)
        
        if project_id in new_selection:
            new_selection.discard(project_id)
        else:
            new_selection.add(project_id)
        
        self.selected_projects = new_selection
        self._update_selection_display()
        
        count = len(self.selected_projects)
        if count > 0:
            self.notify(f"{count} project(s) selected")
    
    def action_select_all(self) -> None:
        """Select all visible projects."""
        project_tree = self.query_one("#project-tree", Tree)
        new_selection = set()
        
        def collect_projects(node):
            if node.data and node.data.get("type") == "project":
                proj = node.data.get("project")
                if proj:
                    new_selection.add(proj.id)
            for child in node.children:
                collect_projects(child)
        
        collect_projects(project_tree.root)
        
        self.selected_projects = new_selection
        self._update_selection_display()
        self.notify(f"Selected {len(new_selection)} project(s)")
    
    def action_clear_selection(self) -> None:
        """Clear multi-selection."""
        if self.selected_projects:
            self.selected_projects = set()
            self._update_selection_display()
            self.notify("Selection cleared")
    
    def toggle_project_selection(self, project: Project) -> None:
        """Toggle multi-selection for a specific project (used by ctrl/shift+click)."""
        project_id = project.id
        new_selection = set(self.selected_projects)
        
        if project_id in new_selection:
            new_selection.discard(project_id)
        else:
            new_selection.add(project_id)
        
        self.selected_projects = new_selection
        self._update_selection_display()
        
        count = len(self.selected_projects)
        if count > 0:
            self.notify(f"{count} project(s) selected")
    
    def _update_selection_display(self) -> None:
        """Update the visual display of selected items."""
        # Tree doesn't support visual multi-select like ListView
        # Selection state is tracked in self.selected_projects
        pass
    
    def _get_selected_or_multi(self) -> list[Project]:
        """Get list of selected projects (multi-select or single)."""
        if self.selected_projects:
            # Return projects from multi-selection by querying database
            projects = []
            with self.session_factory() as session:
                for proj_id in self.selected_projects:
                    proj = session.get(Project, proj_id)
                    if proj:
                        session.expunge(proj)
                        projects.append(proj)
            return projects
        elif self.selected_project:
            return [self.selected_project]
        return []

    def action_sync(self) -> None:
        """Sync the selected project(s)."""
        projects = self._get_selected_or_multi()
        
        if not projects:
            self.notify("Select a project to sync", severity="warning")
            return
        
        if len(projects) == 1:
            self.notify(
                f"Syncing {projects[0].name}...",
                title="Sync Started",
            )
            self.run_sync(projects[0])
        else:
            self.notify(
                f"Syncing {len(projects)} projects...",
                title="Batch Sync Started",
            )
            self.run_sync_batch(projects)
    
    @work(exclusive=True, thread=True)
    def run_sync_batch(self, projects: list) -> None:
        """Sync multiple projects in sequence."""
        from dossier.parsers import GitHubParser, GitHubClient
        import os
        
        token = os.environ.get("GITHUB_TOKEN")
        success_count = 0
        
        for i, project in enumerate(projects):
            self.call_from_thread(
                self.notify,
                f"Syncing {i+1}/{len(projects)}: {project.name}...",
            )
            
            if not project.github_owner or not project.github_repo:
                continue
            
            try:
                with GitHubParser(token) as parser:
                    repo, sections = parser.parse_repo(
                        project.github_owner,
                        project.github_repo,
                    )
                
                with GitHubClient(token) as client:
                    contributors = client.get_contributors(project.github_owner, project.github_repo)
                    issues = client.get_issues(project.github_owner, project.github_repo, state="all")
                    languages = client.get_languages(project.github_owner, project.github_repo)
                    dependencies = client.get_dependencies(project.github_owner, project.github_repo)
                    branches = client.get_branches(project.github_owner, project.github_repo)
                    prs = client.get_pull_requests(project.github_owner, project.github_repo, state="all")
                    releases = client.get_releases(project.github_owner, project.github_repo)
                
                with self.session_factory() as session:
                    from datetime import datetime, timezone
                    
                    db_project = session.get(Project, project.id)
                    if db_project:
                        db_project.description = repo.get("description") or db_project.description
                        db_project.github_stars = repo.get("stargazers_count")
                        db_project.github_language = repo.get("language")
                        db_project.last_synced_at = datetime.now(timezone.utc)
                        session.add(db_project)
                        session.commit()
                
                success_count += 1
                
            except Exception as e:
                self.call_from_thread(
                    self.notify,
                    f"Failed to sync {project.name}: {e}",
                    severity="error",
                )
        
        self.call_from_thread(
            self.notify,
            f"Synced {success_count}/{len(projects)} projects",
            title="Batch Sync Complete",
        )
        self.call_from_thread(self.load_projects)
        self.call_from_thread(self.action_clear_selection)

    @work(exclusive=True, thread=True)
    def run_sync(self, project: Project) -> None:
        """Run sync in background thread."""
        from dossier.parsers import GitHubParser, GitHubClient
        import os
        
        token = os.environ.get("GITHUB_TOKEN")
        
        if not project.github_owner or not project.github_repo:
            self.call_from_thread(
                self.notify,
                "Project has no GitHub info",
                severity="error",
            )
            return
        
        try:
            with GitHubParser(token) as parser:
                repo, sections = parser.parse_repo(
                    project.github_owner,
                    project.github_repo,
                )
            
            # Also fetch extended data
            with GitHubClient(token) as client:
                contributors = client.get_contributors(
                    project.github_owner, project.github_repo
                )
                issues = client.get_issues(
                    project.github_owner, project.github_repo, state="all"
                )
                languages = client.get_languages(
                    project.github_owner, project.github_repo
                )
                dependencies = client.get_dependencies(
                    project.github_owner, project.github_repo
                )
                branches = client.get_branches(
                    project.github_owner, project.github_repo
                )
                pull_requests = client.get_pull_requests(
                    project.github_owner, project.github_repo, state="all"
                )
                releases = client.get_releases(
                    project.github_owner, project.github_repo
                )
            
            with self.session_factory() as session:
                # Update project
                db_project = session.exec(
                    select(Project).where(Project.id == project.id)
                ).first()
                
                if db_project:
                    db_project.github_stars = repo.stars
                    db_project.github_language = repo.language
                    db_project.description = repo.description
                    from dossier.models import utcnow
                    db_project.last_synced_at = utcnow()
                    
                    # Remove old sections
                    old_sections = session.exec(
                        select(DocumentSection).where(
                            DocumentSection.project_id == project.id
                        )
                    ).all()
                    for old in old_sections:
                        session.delete(old)
                    
                    # Add new sections
                    for section in sections:
                        section.project_id = project.id
                        session.add(section)
                    
                    # Remove and add contributors
                    old_contribs = session.exec(
                        select(ProjectContributor).where(
                            ProjectContributor.project_id == project.id
                        )
                    ).all()
                    for old in old_contribs:
                        session.delete(old)
                    
                    for contrib in contributors:
                        session.add(ProjectContributor(
                            project_id=project.id,
                            username=contrib["username"],
                            avatar_url=contrib.get("avatar_url"),
                            contributions=contrib.get("contributions", 0),
                            profile_url=contrib.get("profile_url"),
                        ))
                    
                    # Remove and add issues
                    old_issues = session.exec(
                        select(ProjectIssue).where(
                            ProjectIssue.project_id == project.id
                        )
                    ).all()
                    for old in old_issues:
                        session.delete(old)
                    
                    for issue in issues:
                        session.add(ProjectIssue(
                            project_id=project.id,
                            issue_number=issue["issue_number"],
                            title=issue["title"],
                            state=issue.get("state", "open"),
                            author=issue.get("author"),
                            labels=issue.get("labels"),
                        ))
                    
                    # Remove and add languages
                    old_langs = session.exec(
                        select(ProjectLanguage).where(
                            ProjectLanguage.project_id == project.id
                        )
                    ).all()
                    for old in old_langs:
                        session.delete(old)
                    
                    for lang in languages:
                        session.add(ProjectLanguage(
                            project_id=project.id,
                            language=lang["language"],
                            bytes_count=lang.get("bytes_count", 0),
                            percentage=lang.get("percentage", 0.0),
                        ))
                    
                    # Remove and add dependencies
                    old_deps = session.exec(
                        select(ProjectDependency).where(
                            ProjectDependency.project_id == project.id
                        )
                    ).all()
                    for old in old_deps:
                        session.delete(old)
                    
                    for dep in dependencies:
                        session.add(ProjectDependency(
                            project_id=project.id,
                            name=dep["name"],
                            version_spec=dep.get("version_spec"),
                            dep_type=dep.get("dep_type", "runtime"),
                            source=dep.get("source", "unknown"),
                        ))
                    
                    # Remove and add branches
                    old_branches = session.exec(
                        select(ProjectBranch).where(
                            ProjectBranch.project_id == project.id
                        )
                    ).all()
                    for old in old_branches:
                        session.delete(old)
                    
                    for branch in branches:
                        session.add(ProjectBranch(
                            project_id=project.id,
                            name=branch["name"],
                            is_default=branch.get("is_default", False),
                            is_protected=branch.get("is_protected", False),
                            commit_sha=branch.get("commit_sha"),
                            commit_message=branch.get("commit_message"),
                            commit_author=branch.get("commit_author"),
                            committed_at=branch.get("committed_at"),
                        ))
                    
                    # Remove and add pull requests
                    old_prs = session.exec(
                        select(ProjectPullRequest).where(
                            ProjectPullRequest.project_id == project.id
                        )
                    ).all()
                    for old in old_prs:
                        session.delete(old)
                    
                    for pr in pull_requests:
                        session.add(ProjectPullRequest(
                            project_id=project.id,
                            pr_number=pr["pr_number"],
                            title=pr["title"],
                            state=pr.get("state", "open"),
                            author=pr.get("author"),
                            base_branch=pr.get("base_branch"),
                            head_branch=pr.get("head_branch"),
                            is_draft=pr.get("is_draft", False),
                            is_merged=pr.get("is_merged", False),
                            additions=pr.get("additions", 0),
                            deletions=pr.get("deletions", 0),
                            labels=pr.get("labels"),
                            created_at=pr.get("created_at"),
                            merged_at=pr.get("merged_at"),
                            closed_at=pr.get("closed_at"),
                        ))
                    
                    # Remove and add releases
                    old_releases = session.exec(
                        select(ProjectRelease).where(
                            ProjectRelease.project_id == project.id
                        )
                    ).all()
                    for old in old_releases:
                        session.delete(old)
                    
                    for release in releases:
                        session.add(ProjectRelease(
                            project_id=project.id,
                            tag_name=release["tag_name"],
                            name=release.get("name"),
                            body=release.get("body"),
                            is_prerelease=release.get("is_prerelease", False),
                            is_draft=release.get("is_draft", False),
                            author=release.get("author"),
                            target_commitish=release.get("target_commitish"),
                            release_created_at=release.get("release_created_at"),
                            release_published_at=release.get("release_published_at"),
                        ))
                    
                    session.commit()
                    
                    # Auto-link languages, dependencies, and contributors as component projects
                    self._auto_link_components(session, project.id, languages, dependencies, contributors)
            
            stats = f"{len(sections)} docs, {len(languages)} langs, {len(dependencies)} deps, {len(contributors)} contribs, {len(issues)} issues, {len(pull_requests)} PRs, {len(releases)} releases"
            self.call_from_thread(
                self.notify,
                f"Synced {project.name}: {stats}",
                title="Sync Complete",
            )
            self.call_from_thread(self.action_refresh)
            
        except Exception as e:
            self.call_from_thread(
                self.notify,
                f"Sync failed: {e}",
                severity="error",
            )
    
    def _auto_link_components(
        self, 
        session: Session, 
        project_id: int, 
        languages: list, 
        dependencies: list, 
        contributors: list
    ) -> None:
        """Auto-create and link language, dependency, and contributor projects.
        
        This creates lang/*, pkg/*, and user/* projects and links them as
        components of the parent project during sync.
        """
        # Link languages
        for lang in languages:
            lang_name = lang.get("language")
            if not lang_name:
                continue
            
            project_name = f"lang/{lang_name.lower()}"
            
            # Check if language project exists
            lang_project = session.exec(
                select(Project).where(Project.name == project_name)
            ).first()
            
            if not lang_project:
                lang_project = Project(
                    name=project_name,
                    description=f"{lang_name} programming language",
                    github_language=lang_name,
                )
                session.add(lang_project)
                session.flush()  # Get the ID without committing
            
            # Check if link already exists
            existing_link = session.exec(
                select(ProjectComponent).where(
                    ProjectComponent.parent_id == project_id,
                    ProjectComponent.child_id == lang_project.id,
                )
            ).first()
            
            if not existing_link:
                link = ProjectComponent(
                    parent_id=project_id,
                    child_id=lang_project.id,
                    relationship_type="language",
                    order=0,
                )
                session.add(link)
        
        # Link dependencies
        for dep in dependencies:
            dep_name = dep.get("name")
            if not dep_name:
                continue
            
            project_name = f"pkg/{dep_name.lower()}"
            
            dep_project = session.exec(
                select(Project).where(Project.name == project_name)
            ).first()
            
            if not dep_project:
                description = f"{dep_name} package"
                version = dep.get("version_spec")
                if version:
                    description += f" ({version})"
                dep_project = Project(
                    name=project_name,
                    description=description,
                )
                session.add(dep_project)
                session.flush()
            
            existing_link = session.exec(
                select(ProjectComponent).where(
                    ProjectComponent.parent_id == project_id,
                    ProjectComponent.child_id == dep_project.id,
                )
            ).first()
            
            if not existing_link:
                link = ProjectComponent(
                    parent_id=project_id,
                    child_id=dep_project.id,
                    relationship_type="dependency",
                    order=0,
                )
                session.add(link)
        
        # Link top contributors (limit to top 5 to avoid clutter)
        for contrib in contributors[:5]:
            username = contrib.get("username")
            if not username:
                continue
            
            # Contributors are app-scoped (same user across all GitHub repos)
            project_name = f"github/user/{username.lower()}"
            
            user_project = session.exec(
                select(Project).where(Project.name == project_name)
            ).first()
            
            if not user_project:
                user_project = Project(
                    name=project_name,
                    description=f"GitHub user: {username}",
                    repository_url=contrib.get("profile_url"),
                    github_owner=username,
                )
                session.add(user_project)
                session.flush()
            
            existing_link = session.exec(
                select(ProjectComponent).where(
                    ProjectComponent.parent_id == project_id,
                    ProjectComponent.child_id == user_project.id,
                )
            ).first()
            
            if not existing_link:
                link = ProjectComponent(
                    parent_id=project_id,
                    child_id=user_project.id,
                    relationship_type="contributor",
                    order=0,
                )
                session.add(link)
        
        session.commit()

    def action_add(self) -> None:
        """Add a new project."""
        from textual.screen import ModalScreen
        from textual.widgets import Input, Button
        from textual.containers import Vertical, Horizontal
        
        class AddProjectModal(ModalScreen[Optional[str]]):
            """Modal for adding a new project."""
            
            CSS = """
            AddProjectModal {
                align: center middle;
            }
            
            #add-dialog {
                width: 60;
                height: auto;
                padding: 1 2;
                background: $surface;
                border: solid $primary;
            }
            
            #add-dialog Input {
                margin: 1 0;
            }
            
            #add-dialog Horizontal {
                margin-top: 1;
                align: right middle;
            }
            
            #add-dialog Button {
                margin-left: 1;
            }
            """
            
            BINDINGS = [
                Binding("escape", "cancel", "Cancel"),
            ]
            
            def compose(self) -> ComposeResult:
                with Vertical(id="add-dialog"):
                    yield Label("Add Project", classes="title")
                    yield Input(placeholder="Project name or GitHub URL", id="project-input")
                    yield Input(placeholder="Description (optional)", id="desc-input")
                    with Horizontal():
                        yield Button("Cancel", id="cancel-btn")
                        yield Button("Add", id="add-btn", variant="primary")
            
            @on(Button.Pressed, "#add-btn")
            def on_add(self) -> None:
                name = self.query_one("#project-input", Input).value
                if name:
                    self.dismiss(name)
                else:
                    self.notify("Project name required", severity="warning")
            
            @on(Button.Pressed, "#cancel-btn")
            def on_cancel(self) -> None:
                self.dismiss(None)
            
            def action_cancel(self) -> None:
                self.dismiss(None)
        
        def handle_result(name: Optional[str]) -> None:
            if name:
                # Check if it's a GitHub URL
                if "github.com" in name or "/" in name:
                    self.add_from_github(name)
                else:
                    self.add_project(name)
        
        self.push_screen(AddProjectModal(), handle_result)
    
    def add_project(self, name: str) -> None:
        """Add a new project by name."""
        with self.session_factory() as session:
            existing = session.exec(
                select(Project).where(Project.name == name)
            ).first()
            
            if existing:
                self.notify(f"Project '{name}' already exists", severity="warning")
                return
            
            project = Project(name=name)
            session.add(project)
            session.commit()
        
        self.notify(f"Added project: {name}")
        self.action_refresh()
    
    @work(exclusive=True, thread=True)
    def add_from_github(self, url: str) -> None:
        """Add a project from GitHub URL."""
        from dossier.parsers import GitHubParser, GitHubClient
        from dossier.parsers.github import GitHubRepo
        import os
        
        token = os.environ.get("GITHUB_TOKEN")
        
        try:
            # Parse URL to get owner/repo
            if "github.com" not in url:
                # Assume owner/repo format
                parts = url.split("/")
                if len(parts) == 2:
                    url = f"https://github.com/{url}"
            
            with GitHubParser(token) as parser:
                repo, sections = parser.parse_repo_url(url)
            
            # Also fetch extended data
            with GitHubClient(token) as client:
                contributors = client.get_contributors(repo.owner, repo.name)
                issues = client.get_issues(repo.owner, repo.name, state="all")
                languages = client.get_languages(repo.owner, repo.name)
                dependencies = client.get_dependencies(repo.owner, repo.name)
                branches = client.get_branches(repo.owner, repo.name)
                pull_requests = client.get_pull_requests(repo.owner, repo.name, state="all")
                releases = client.get_releases(repo.owner, repo.name)
            
            project_name = f"{repo.owner}/{repo.name}"
            
            with self.session_factory() as session:
                existing = session.exec(
                    select(Project).where(Project.name == project_name)
                ).first()
                
                if existing:
                    self.call_from_thread(
                        self.notify,
                        f"Project '{project_name}' already exists",
                        severity="warning",
                    )
                    return
                
                from dossier.models import utcnow
                project = Project(
                    name=project_name,
                    description=repo.description,
                    repository_url=repo.html_url,
                    github_owner=repo.owner,
                    github_repo=repo.name,
                    github_stars=repo.stars,
                    github_language=repo.language,
                    last_synced_at=utcnow(),
                )
                session.add(project)
                session.flush()
                
                for section in sections:
                    section.project_id = project.id
                    session.add(section)
                
                # Add contributors
                for contrib in contributors:
                    session.add(ProjectContributor(
                        project_id=project.id,
                        username=contrib["username"],
                        avatar_url=contrib.get("avatar_url"),
                        contributions=contrib.get("contributions", 0),
                        profile_url=contrib.get("profile_url"),
                    ))
                
                # Add issues
                for issue in issues:
                    session.add(ProjectIssue(
                        project_id=project.id,
                        issue_number=issue["issue_number"],
                        title=issue["title"],
                        state=issue.get("state", "open"),
                        author=issue.get("author"),
                        labels=issue.get("labels"),
                    ))
                
                # Add languages
                for lang in languages:
                    session.add(ProjectLanguage(
                        project_id=project.id,
                        language=lang["language"],
                        bytes_count=lang.get("bytes_count", 0),
                        percentage=lang.get("percentage", 0.0),
                    ))
                
                # Add dependencies
                for dep in dependencies:
                    session.add(ProjectDependency(
                        project_id=project.id,
                        name=dep["name"],
                        version_spec=dep.get("version_spec"),
                        dep_type=dep.get("dep_type", "runtime"),
                        source=dep.get("source", "unknown"),
                    ))
                
                # Add branches
                for branch in branches:
                    session.add(ProjectBranch(
                        project_id=project.id,
                        name=branch["name"],
                        is_default=branch.get("is_default", False),
                        is_protected=branch.get("is_protected", False),
                        commit_sha=branch.get("commit_sha"),
                        commit_message=branch.get("commit_message"),
                        commit_author=branch.get("commit_author"),
                        committed_at=branch.get("committed_at"),
                    ))
                
                # Add pull requests
                for pr in pull_requests:
                    session.add(ProjectPullRequest(
                        project_id=project.id,
                        pr_number=pr["pr_number"],
                        title=pr["title"],
                        state=pr.get("state", "open"),
                        author=pr.get("author"),
                        base_branch=pr.get("base_branch"),
                        head_branch=pr.get("head_branch"),
                        is_draft=pr.get("is_draft", False),
                        is_merged=pr.get("is_merged", False),
                        additions=pr.get("additions", 0),
                        deletions=pr.get("deletions", 0),
                        labels=pr.get("labels"),
                        created_at=pr.get("created_at"),
                        merged_at=pr.get("merged_at"),
                        closed_at=pr.get("closed_at"),
                    ))
                
                # Add releases
                for release in releases:
                    session.add(ProjectRelease(
                        project_id=project.id,
                        tag_name=release["tag_name"],
                        name=release.get("name"),
                        body=release.get("body"),
                        is_prerelease=release.get("is_prerelease", False),
                        is_draft=release.get("is_draft", False),
                        author=release.get("author"),
                        target_commitish=release.get("target_commitish"),
                        release_created_at=release.get("release_created_at"),
                        release_published_at=release.get("release_published_at"),
                    ))
                
                session.commit()
            
            stats = f"{len(sections)} docs, {len(languages)} langs, {len(dependencies)} deps, {len(pull_requests)} PRs, {len(releases)} releases"
            self.call_from_thread(
                self.notify,
                f"Added {project_name}: {stats}",
            )
            self.call_from_thread(self.action_refresh)
            
        except Exception as e:
            self.call_from_thread(
                self.notify,
                f"Failed to add: {e}",
                severity="error",
            )
    
    def action_delete(self) -> None:
        """Delete the selected project(s)."""
        projects = self._get_selected_or_multi()
        
        if not projects:
            self.notify("Select a project to delete", severity="warning")
            return
        
        project_ids = [p.id for p in projects]
        project_names = [p.name for p in projects]
        
        def confirm_delete(result: bool) -> None:
            if result:
                for pid, pname in zip(project_ids, project_names):
                    self.delete_project(pid, pname)
                self.action_clear_selection()
        
        from textual.screen import ModalScreen
        from textual.widgets import Button
        from textual.containers import Vertical, Horizontal
        
        if len(projects) == 1:
            message = f"Delete '{project_names[0]}'?"
            detail = "This will also delete all documentation sections."
        else:
            message = f"Delete {len(projects)} projects?"
            detail = f"Projects: {', '.join(project_names[:3])}{'...' if len(projects) > 3 else ''}"
        
        class ConfirmDialog(ModalScreen[bool]):
            """Confirmation dialog."""
            
            CSS = """
            ConfirmDialog {
                align: center middle;
            }
            
            #confirm-dialog {
                width: 60;
                height: auto;
                padding: 1 2;
                background: $surface;
                border: solid $error;
            }
            
            #confirm-dialog Horizontal {
                margin-top: 1;
                align: right middle;
            }
            
            #confirm-dialog Button {
                margin-left: 1;
            }
            """
            
            def compose(self_inner) -> ComposeResult:
                with Vertical(id="confirm-dialog"):
                    yield Label(message, classes="title")
                    yield Label(detail)
                    with Horizontal():
                        yield Button("Cancel", id="cancel-btn")
                        yield Button("Delete", id="delete-btn", variant="error")
            
            @on(Button.Pressed, "#delete-btn")
            def on_delete(self_inner) -> None:
                self_inner.dismiss(True)
            
            @on(Button.Pressed, "#cancel-btn")
            def on_cancel(self_inner) -> None:
                self_inner.dismiss(False)
        
        self.push_screen(ConfirmDialog(), confirm_delete)
    
    def delete_project(self, project_id: int, project_name: str) -> None:
        """Delete a project from the database."""
        with self.session_factory() as session:
            # Delete sections
            sections = session.exec(
                select(DocumentSection).where(DocumentSection.project_id == project_id)
            ).all()
            for section in sections:
                session.delete(section)
            
            # Delete component relationships
            components = session.exec(
                select(ProjectComponent).where(
                    (ProjectComponent.parent_id == project_id) |
                    (ProjectComponent.child_id == project_id)
                )
            ).all()
            for comp in components:
                session.delete(comp)
            
            # Delete contributors
            contributors = session.exec(
                select(ProjectContributor).where(ProjectContributor.project_id == project_id)
            ).all()
            for contrib in contributors:
                session.delete(contrib)
            
            # Delete issues
            issues = session.exec(
                select(ProjectIssue).where(ProjectIssue.project_id == project_id)
            ).all()
            for issue in issues:
                session.delete(issue)
            
            # Delete languages
            languages = session.exec(
                select(ProjectLanguage).where(ProjectLanguage.project_id == project_id)
            ).all()
            for lang in languages:
                session.delete(lang)
            
            # Delete dependencies
            dependencies = session.exec(
                select(ProjectDependency).where(ProjectDependency.project_id == project_id)
            ).all()
            for dep in dependencies:
                session.delete(dep)
            
            # Delete branches
            branches = session.exec(
                select(ProjectBranch).where(ProjectBranch.project_id == project_id)
            ).all()
            for branch in branches:
                session.delete(branch)
            
            # Delete pull requests
            prs = session.exec(
                select(ProjectPullRequest).where(ProjectPullRequest.project_id == project_id)
            ).all()
            for pr in prs:
                session.delete(pr)
            
            # Delete versions (must be before releases due to FK constraint)
            versions = session.exec(
                select(ProjectVersion).where(ProjectVersion.project_id == project_id)
            ).all()
            for version in versions:
                session.delete(version)
            
            # Delete releases
            releases = session.exec(
                select(ProjectRelease).where(ProjectRelease.project_id == project_id)
            ).all()
            for release in releases:
                session.delete(release)
            
            # Delete project
            project = session.get(Project, project_id)
            if project:
                session.delete(project)
            
            session.commit()
        
        self.selected_project = None
        self.notify(f"Deleted '{project_name}'")
        self.action_refresh()
    
    def action_add_component(self) -> None:
        """Add a component (subproject) to the selected project."""
        if not self.selected_project:
            self.notify("Select a project first", severity="warning")
            return
        
        parent_name = self.selected_project.name
        parent_id = self.selected_project.id
        
        from textual.screen import ModalScreen
        from textual.widgets import Button, Input, Select
        from textual.containers import Vertical, Horizontal
        
        # Get available projects to link
        with self.session_factory() as session:
            projects = session.exec(
                select(Project).where(Project.id != parent_id).order_by(Project.name)
            ).all()
            project_options = [(p.name, p.name) for p in projects]
        
        if not project_options:
            self.notify("No other projects available to link", severity="warning")
            return
        
        class AddComponentModal(ModalScreen[Optional[tuple]]):
            """Modal for adding a component."""
            
            CSS = """
            AddComponentModal {
                align: center middle;
            }
            
            #add-component-dialog {
                width: 70;
                height: auto;
                padding: 1 2;
                background: $surface;
                border: solid $primary;
            }
            
            #add-component-dialog Select {
                margin: 1 0;
                width: 100%;
            }
            
            #add-component-dialog Input {
                margin: 1 0;
            }
            
            #add-component-dialog Horizontal {
                margin-top: 1;
                align: right middle;
            }
            
            #add-component-dialog Button {
                margin-left: 1;
            }
            """
            
            BINDINGS = [
                Binding("escape", "cancel", "Cancel"),
            ]
            
            def compose(self) -> ComposeResult:
                with Vertical(id="add-component-dialog"):
                    yield Label(f"Add Component to '{parent_name}'", classes="title")
                    yield Label("Select project to add as subcomponent:")
                    yield Select(project_options, id="project-select", prompt="Select project...")
                    yield Label("Relationship type:")
                    yield Select(
                        [("🧩 Component", "component"), ("📦 Dependency", "dependency"), ("🔗 Related", "related")],
                        value="component",
                        id="type-select",
                    )
                    yield Label("Display order:")
                    yield Input(value="0", id="order-input", placeholder="0")
                    with Horizontal():
                        yield Button("Cancel", id="cancel-btn")
                        yield Button("Add", id="add-btn", variant="primary")
            
            @on(Button.Pressed, "#add-btn")
            def on_add(self) -> None:
                project_select = self.query_one("#project-select", Select)
                type_select = self.query_one("#type-select", Select)
                order_input = self.query_one("#order-input", Input)
                
                if project_select.value == Select.BLANK:
                    self.notify("Select a project", severity="warning")
                    return
                
                try:
                    order = int(order_input.value)
                except ValueError:
                    order = 0
                
                self.dismiss((project_select.value, type_select.value, order))
            
            @on(Button.Pressed, "#cancel-btn")
            def on_cancel(self) -> None:
                self.dismiss(None)
            
            def action_cancel(self) -> None:
                self.dismiss(None)
        
        def handle_result(result: Optional[tuple]) -> None:
            if result:
                child_name, rel_type, order = result
                self._create_component(parent_id, child_name, rel_type, order)
        
        self.push_screen(AddComponentModal(), handle_result)
    
    def _create_component(self, parent_id: int, child_name: str, rel_type: str, order: int) -> None:
        """Create a component relationship."""
        with self.session_factory() as session:
            child = session.exec(
                select(Project).where(Project.name == child_name)
            ).first()
            
            if not child:
                self.notify(f"Project '{child_name}' not found", severity="error")
                return
            
            # Check for existing relationship
            existing = session.exec(
                select(ProjectComponent)
                .where(ProjectComponent.parent_id == parent_id)
                .where(ProjectComponent.child_id == child.id)
            ).first()
            
            if existing:
                self.notify(f"Component relationship already exists", severity="warning")
                return
            
            component = ProjectComponent(
                parent_id=parent_id,
                child_id=child.id,
                relationship_type=rel_type,
                order=order,
            )
            session.add(component)
            session.commit()
        
        self.notify(f"Added '{child_name}' as {rel_type}")
        if self.selected_project:
            self.show_project_details(self.selected_project)
    
    def action_link_parent(self) -> None:
        """Link the selected project as a component of another project."""
        if not self.selected_project:
            self.notify("Select a project first", severity="warning")
            return
        
        child_name = self.selected_project.name
        child_id = self.selected_project.id
        
        from textual.screen import ModalScreen
        from textual.widgets import Button, Input, Select
        from textual.containers import Vertical, Horizontal
        
        # Get available projects to link to
        with self.session_factory() as session:
            projects = session.exec(
                select(Project).where(Project.id != child_id).order_by(Project.name)
            ).all()
            project_options = [(p.name, p.name) for p in projects]
        
        if not project_options:
            self.notify("No other projects available to link", severity="warning")
            return
        
        class LinkParentModal(ModalScreen[Optional[tuple]]):
            """Modal for linking to a parent project."""
            
            CSS = """
            LinkParentModal {
                align: center middle;
            }
            
            #link-parent-dialog {
                width: 70;
                height: auto;
                padding: 1 2;
                background: $surface;
                border: solid $primary;
            }
            
            #link-parent-dialog Select {
                margin: 1 0;
                width: 100%;
            }
            
            #link-parent-dialog Input {
                margin: 1 0;
            }
            
            #link-parent-dialog Horizontal {
                margin-top: 1;
                align: right middle;
            }
            
            #link-parent-dialog Button {
                margin-left: 1;
            }
            """
            
            BINDINGS = [
                Binding("escape", "cancel", "Cancel"),
            ]
            
            def compose(self) -> ComposeResult:
                with Vertical(id="link-parent-dialog"):
                    yield Label(f"Link '{child_name}' to Parent", classes="title")
                    yield Label("Select parent project:")
                    yield Select(project_options, id="project-select", prompt="Select project...")
                    yield Label("Relationship type:")
                    yield Select(
                        [("🧩 Component", "component"), ("📦 Dependency", "dependency"), ("🔗 Related", "related")],
                        value="component",
                        id="type-select",
                    )
                    yield Label("Display order:")
                    yield Input(value="0", id="order-input", placeholder="0")
                    with Horizontal():
                        yield Button("Cancel", id="cancel-btn")
                        yield Button("Link", id="add-btn", variant="primary")
            
            @on(Button.Pressed, "#add-btn")
            def on_add(self) -> None:
                project_select = self.query_one("#project-select", Select)
                type_select = self.query_one("#type-select", Select)
                order_input = self.query_one("#order-input", Input)
                
                if project_select.value == Select.BLANK:
                    self.notify("Select a project", severity="warning")
                    return
                
                try:
                    order = int(order_input.value)
                except ValueError:
                    order = 0
                
                self.dismiss((project_select.value, type_select.value, order))
            
            @on(Button.Pressed, "#cancel-btn")
            def on_cancel(self) -> None:
                self.dismiss(None)
            
            def action_cancel(self) -> None:
                self.dismiss(None)
        
        def handle_result(result: Optional[tuple]) -> None:
            if result:
                parent_name, rel_type, order = result
                self._link_to_parent(parent_name, child_id, rel_type, order)
        
        self.push_screen(LinkParentModal(), handle_result)
    
    def _link_to_parent(self, parent_name: str, child_id: int, rel_type: str, order: int) -> None:
        """Create a component relationship with parent."""
        with self.session_factory() as session:
            parent = session.exec(
                select(Project).where(Project.name == parent_name)
            ).first()
            
            if not parent:
                self.notify(f"Project '{parent_name}' not found", severity="error")
                return
            
            # Check for existing relationship
            existing = session.exec(
                select(ProjectComponent)
                .where(ProjectComponent.parent_id == parent.id)
                .where(ProjectComponent.child_id == child_id)
            ).first()
            
            if existing:
                self.notify(f"Component relationship already exists", severity="warning")
                return
            
            component = ProjectComponent(
                parent_id=parent.id,
                child_id=child_id,
                relationship_type=rel_type,
                order=order,
            )
            session.add(component)
            session.commit()
        
        self.notify(f"Linked to '{parent_name}' as {rel_type}")
        if self.selected_project:
            self.show_project_details(self.selected_project)
    
    def action_remove_component(self) -> None:
        """Remove a component relationship from the selected row."""
        if not self.selected_project:
            self.notify("Select a project first", severity="warning")
            return
        
        components_table = self.query_one("#components-table", DataTable)
        
        if components_table.cursor_row is None:
            self.notify("Select a component to remove", severity="warning")
            return
        
        try:
            row_key = components_table.coordinate_to_cell_key((components_table.cursor_row, 0)).row_key
            row_data = components_table.get_row(row_key)
        except Exception:
            self.notify("Select a component to remove", severity="warning")
            return
        
        if not row_data or row_data[1] == "(No component relationships)":
            self.notify("No component selected", severity="warning")
            return
        
        direction = str(row_data[0]).strip()
        other_project_name = str(row_data[1]).strip()
        
        from textual.screen import ModalScreen
        from textual.widgets import Button
        from textual.containers import Vertical, Horizontal
        
        class ConfirmRemoveComponent(ModalScreen[bool]):
            """Confirm component removal."""
            
            CSS = """
            ConfirmRemoveComponent {
                align: center middle;
            }
            
            #confirm-remove-dialog {
                width: 60;
                height: auto;
                padding: 1 2;
                background: $surface;
                border: solid $error;
            }
            
            #confirm-remove-dialog Horizontal {
                margin-top: 1;
                align: right middle;
            }
            
            #confirm-remove-dialog Button {
                margin-left: 1;
            }
            """
            
            def compose(self) -> ComposeResult:
                with Vertical(id="confirm-remove-dialog"):
                    yield Label(f"Remove component relationship?", classes="title")
                    yield Label(f"This will unlink '{other_project_name}'.")
                    yield Label("The project itself will not be deleted.")
                    with Horizontal():
                        yield Button("Cancel", id="cancel-btn")
                        yield Button("Remove", id="remove-btn", variant="error")
            
            @on(Button.Pressed, "#remove-btn")
            def on_remove(self) -> None:
                self.dismiss(True)
            
            @on(Button.Pressed, "#cancel-btn")
            def on_cancel(self) -> None:
                self.dismiss(False)
        
        def handle_result(result: bool) -> None:
            if result:
                self._remove_component(direction, other_project_name)
        
        self.push_screen(ConfirmRemoveComponent(), handle_result)
    
    def _remove_component(self, direction: str, other_project_name: str) -> None:
        """Remove a component relationship."""
        with self.session_factory() as session:
            other = session.exec(
                select(Project).where(Project.name == other_project_name)
            ).first()
            
            if not other:
                self.notify(f"Project '{other_project_name}' not found", severity="error")
                return
            
            # Determine which is parent and which is child
            if "child" in direction:
                # This project is parent, other is child
                parent_id = self.selected_project.id
                child_id = other.id
            else:
                # Other is parent, this project is child
                parent_id = other.id
                child_id = self.selected_project.id
            
            component = session.exec(
                select(ProjectComponent)
                .where(ProjectComponent.parent_id == parent_id)
                .where(ProjectComponent.child_id == child_id)
            ).first()
            
            if not component:
                self.notify("Component relationship not found", severity="error")
                return
            
            session.delete(component)
            session.commit()
        
        self.notify(f"Removed relationship with '{other_project_name}'")
        if self.selected_project:
            self.show_project_details(self.selected_project)

    def action_new_delta(self) -> None:
        """Create a new delta for the selected project."""
        if not self.selected_project:
            self.notify("Select a project first", severity="warning")
            return

        project_id = self.selected_project.id
        project_name = self.selected_project.name

        class NewDeltaModal(ModalScreen[Optional[dict]]):
            """Modal for creating a new delta."""

            CSS = """
            NewDeltaModal {
                align: center middle;
            }

            #new-delta-dialog {
                width: 70;
                height: auto;
                padding: 1 2;
                background: $surface;
                border: solid $primary;
            }

            #new-delta-dialog Input {
                margin: 1 0;
            }

            #new-delta-dialog Select {
                margin: 1 0;
                width: 100%;
            }

            #new-delta-dialog Horizontal {
                margin-top: 1;
                align: right middle;
            }

            #new-delta-dialog Button {
                margin-left: 1;
            }
            """

            def compose(self) -> ComposeResult:
                with Vertical(id="new-delta-dialog"):
                    yield Label(f"New Delta for {project_name}", classes="title")
                    yield Label("Name (slug):")
                    yield Input(placeholder="e.g., add-dark-mode", id="delta-name")
                    yield Label("Title:")
                    yield Input(placeholder="Human-readable title", id="delta-title")
                    yield Label("Type:")
                    yield Select(
                        [("✨ Feature", "feature"), ("🐛 Bugfix", "bugfix"),
                         ("♻️ Refactor", "refactor"), ("📚 Docs", "docs"), ("🔧 Chore", "chore")],
                        value="feature",
                        id="delta-type",
                        allow_blank=False,
                    )
                    yield Label("Priority:")
                    yield Select(
                        [("🟢 Low", "low"), ("🟡 Medium", "medium"),
                         ("🟠 High", "high"), ("🔴 Critical", "critical")],
                        value="medium",
                        id="delta-priority",
                        allow_blank=False,
                    )
                    with Horizontal():
                        yield Button("Cancel", id="cancel-btn")
                        yield Button("Create", id="create-btn", variant="primary")

            @on(Button.Pressed, "#create-btn")
            def on_create(self) -> None:
                name = self.query_one("#delta-name", Input).value.strip()
                title = self.query_one("#delta-title", Input).value.strip()
                delta_type = self.query_one("#delta-type", Select).value
                priority = self.query_one("#delta-priority", Select).value

                if not name:
                    self.notify("Name is required", severity="error")
                    return
                if not title:
                    self.notify("Title is required", severity="error")
                    return

                self.dismiss({
                    "name": name,
                    "title": title,
                    "delta_type": delta_type,
                    "priority": priority,
                })

            @on(Button.Pressed, "#cancel-btn")
            def on_cancel(self) -> None:
                self.dismiss(None)

        def handle_result(result: Optional[dict]) -> None:
            if result:
                self._create_delta(project_id, result)

        self.push_screen(NewDeltaModal(), handle_result)

    def _create_delta(self, project_id: int, data: dict) -> None:
        """Create a new delta in the database."""
        with self.session_factory() as session:
            delta = ProjectDelta(
                project_id=project_id,
                name=data["name"],
                title=data["title"],
                delta_type=data["delta_type"],
                priority=data["priority"],
                phase=DeltaPhase.BRAINSTORM,
            )
            session.add(delta)
            session.commit()

        self.notify(f"Created delta: {data['name']}")
        # Reload deltas tab
        if hasattr(self, "_tabs_loaded"):
            self._tabs_loaded.discard("tab-deltas")
        if self.selected_project:
            self._load_deltas_tab(self.selected_project)

    def action_advance_delta_phase(self) -> None:
        """Advance the selected delta to the next phase."""
        if not self.selected_project:
            self.notify("Select a project first", severity="warning")
            return

        deltas_table = self.query_one("#deltas-table", DataTable)

        if deltas_table.cursor_row is None:
            self.notify("Select a delta to advance", severity="warning")
            return

        try:
            row_key = deltas_table.coordinate_to_cell_key((deltas_table.cursor_row, 0)).row_key
        except Exception:
            self.notify("Select a delta to advance", severity="warning")
            return

        row_key_str = str(row_key.value) if row_key else ""
        if not row_key_str.startswith("delta-") or row_key_str.startswith("delta-link-"):
            self.notify("Select a delta to advance", severity="warning")
            return

        try:
            delta_id = int(row_key_str.split("-")[1])
        except ValueError:
            self.notify("Select a delta to advance", severity="warning")
            return

        with self.session_factory() as session:
            delta = session.get(ProjectDelta, delta_id)
            if not delta:
                self.notify("Delta not found", severity="error")
                return

            if not delta.can_advance():
                if delta.phase == DeltaPhase.COMPLETE:
                    self.notify("Delta is already complete", severity="warning")
                elif delta.phase == DeltaPhase.ABANDONED:
                    self.notify("Cannot advance abandoned delta", severity="warning")
                else:
                    self.notify("Cannot advance delta", severity="warning")
                return

            old_phase = delta.phase.value
            delta.advance_phase()
            new_phase = delta.phase.value
            session.commit()

        self.notify(f"Advanced delta: {old_phase} → {new_phase}")
        # Reload deltas tab
        if hasattr(self, "_tabs_loaded"):
            self._tabs_loaded.discard("tab-deltas")
        if self.selected_project:
            self._load_deltas_tab(self.selected_project)

    def action_add_delta_note(self) -> None:
        """Add a note to the selected delta."""
        if not self.selected_project:
            self.notify("Select a project first", severity="warning")
            return

        deltas_table = self.query_one("#deltas-table", DataTable)

        if deltas_table.cursor_row is None:
            self.notify("Select a delta first", severity="warning")
            return

        try:
            row_key = deltas_table.coordinate_to_cell_key((deltas_table.cursor_row, 0)).row_key
        except Exception:
            self.notify("Select a delta first", severity="warning")
            return

        row_key_str = str(row_key.value) if row_key else ""
        if not row_key_str.startswith("delta-") or row_key_str.startswith("delta-link-"):
            self.notify("Select a delta first", severity="warning")
            return

        try:
            delta_id = int(row_key_str.split("-")[1])
        except ValueError:
            self.notify("Select a delta first", severity="warning")
            return

        # Get delta info for the modal
        with self.session_factory() as session:
            delta = session.get(ProjectDelta, delta_id)
            if not delta:
                self.notify("Delta not found", severity="error")
                return
            delta_name = delta.name
            delta_phase = delta.phase

        class AddNoteModal(ModalScreen[Optional[str]]):
            """Modal for adding a note to a delta."""

            CSS = """
            AddNoteModal {
                align: center middle;
            }

            #add-note-dialog {
                width: 70;
                height: auto;
                padding: 1 2;
                background: $surface;
                border: solid $primary;
            }

            #add-note-dialog Input {
                margin: 1 0;
            }

            #add-note-dialog Horizontal {
                margin-top: 1;
                align: right middle;
            }

            #add-note-dialog Button {
                margin-left: 1;
            }
            """

            def compose(self) -> ComposeResult:
                with Vertical(id="add-note-dialog"):
                    yield Label(f"Add Note to '{delta_name}'", classes="title")
                    yield Label(f"Current phase: {delta_phase.value}")
                    yield Label("Note content:")
                    yield Input(placeholder="Enter your note...", id="note-content")
                    with Horizontal():
                        yield Button("Cancel", id="cancel-btn")
                        yield Button("Add Note", id="add-btn", variant="primary")

            @on(Button.Pressed, "#add-btn")
            def on_add(self) -> None:
                content = self.query_one("#note-content", Input).value.strip()
                if not content:
                    self.notify("Note content is required", severity="error")
                    return
                self.dismiss(content)

            @on(Button.Pressed, "#cancel-btn")
            def on_cancel(self) -> None:
                self.dismiss(None)

        def handle_result(content: Optional[str]) -> None:
            if content:
                self._add_delta_note(delta_id, delta_phase, content)

        self.push_screen(AddNoteModal(), handle_result)

    def _add_delta_note(self, delta_id: int, phase: DeltaPhase, content: str) -> None:
        """Add a note to a delta."""
        with self.session_factory() as session:
            note = DeltaNote(
                delta_id=delta_id,
                phase=phase,
                content=content,
            )
            session.add(note)
            session.commit()

        self.notify("Note added successfully")

    def action_add_delta_link(self) -> None:
        """Add a link to the selected delta."""
        if not self.selected_project:
            self.notify("Select a project first", severity="warning")
            return

        if not self._delta_tables_exist:
            self.notify("Delta tables not available (run migration)", severity="warning")
            return

        deltas_table = self.query_one("#deltas-table", DataTable)

        if deltas_table.cursor_row is None:
            self.notify("Select a delta first", severity="warning")
            return

        try:
            row_key = deltas_table.coordinate_to_cell_key((deltas_table.cursor_row, 0)).row_key
        except Exception:
            self.notify("Select a delta first", severity="warning")
            return

        row_key_str = str(row_key.value) if row_key else ""
        if not row_key_str.startswith("delta-") or row_key_str.startswith("delta-link-"):
            self.notify("Select a delta first", severity="warning")
            return

        try:
            delta_id = int(row_key_str.split("-")[1])
        except ValueError:
            self.notify("Select a delta first", severity="warning")
            return

        # Get delta info for the modal
        with self.session_factory() as session:
            delta = session.get(ProjectDelta, delta_id)
            if not delta:
                self.notify("Delta not found", severity="error")
                return
            delta_name = delta.name

        class AddLinkModal(ModalScreen[Optional[tuple[str, str]]]):
            """Modal for adding a link to a delta."""

            CSS = """
            AddLinkModal {
                align: center middle;
            }

            #add-link-dialog {
                width: 70;
                height: auto;
                padding: 1 2;
                background: $surface;
                border: solid $primary;
            }

            #add-link-dialog Select {
                margin: 1 0;
            }

            #add-link-dialog Input {
                margin: 1 0;
            }

            #add-link-dialog Horizontal {
                margin-top: 1;
                align: right middle;
            }

            #add-link-dialog Button {
                margin-left: 1;
            }
            """

            def compose(self) -> ComposeResult:
                with Vertical(id="add-link-dialog"):
                    yield Label(f"Add Link to '{delta_name}'", classes="title")
                    yield Label("Link type:")
                    yield Select(
                        [
                            ("Issue", "issue"),
                            ("Pull Request", "pr"),
                            ("Branch", "branch"),
                            ("Documentation", "doc"),
                            ("Other Delta", "delta"),
                        ],
                        id="link-type",
                        value="issue",
                    )
                    yield Label("Target (issue #, PR #, branch name, etc.):")
                    yield Input(placeholder="Enter target identifier...", id="link-target")
                    with Horizontal():
                        yield Button("Cancel", id="cancel-btn")
                        yield Button("Add Link", id="add-btn", variant="primary")

            @on(Button.Pressed, "#add-btn")
            def on_add(self) -> None:
                link_type = self.query_one("#link-type", Select).value
                target = self.query_one("#link-target", Input).value.strip()
                if not target:
                    self.notify("Target is required", severity="error")
                    return
                self.dismiss((link_type, target))

            @on(Button.Pressed, "#cancel-btn")
            def on_cancel(self) -> None:
                self.dismiss(None)

        def handle_result(result: Optional[tuple[str, str]]) -> None:
            if result:
                link_type, target = result
                self._add_delta_link(delta_id, link_type, target)

        self.push_screen(AddLinkModal(), handle_result)

    def _add_delta_link(self, delta_id: int, link_type: str, target: str) -> None:
        """Add a link to a delta."""
        # Parse target based on link type
        target_id = None
        target_name = target

        # Try to parse numeric targets for issue/pr/delta
        if link_type in ("issue", "pr", "delta"):
            try:
                # Remove leading # if present
                clean_target = target.lstrip("#")
                target_id = int(clean_target)
                target_name = None
            except ValueError:
                # Keep as name if not a number
                pass

        with self.session_factory() as session:
            link = DeltaLink(
                delta_id=delta_id,
                link_type=link_type,
                target_id=target_id,
                target_name=target_name,
            )
            session.add(link)
            session.commit()

        self.notify(f"Link added: {link_type} -> {target}")

        # Refresh the deltas tab
        if self.selected_project:
            self._load_deltas_tab(self.selected_project)

    def action_search(self) -> None:
        """Focus the search input."""
        self.query_one("#search-input", Input).focus()
    
    def action_cycle_filter(self) -> None:
        """Cycle through filter states: All -> Synced -> Unsynced -> All."""
        if self.filter_synced is None:
            self.filter_synced = True
            filter_name = "synced"
        elif self.filter_synced is True:
            self.filter_synced = False
            filter_name = "unsynced"
        else:
            self.filter_synced = None
            filter_name = "all"
        
        self._update_filter_buttons()
        search_input = self.query_one("#search-input", Input)
        self.load_projects(search=search_input.value)
        self.notify(f"Filter: {filter_name}")
    
    def action_help(self) -> None:
        """Show help information."""
        help_text = """
# Dossier TUI Help

## Command Bar

Type in the search bar at the bottom. Start with `:` for commands:

| Command | Aliases | Action |
|---------|---------|--------|
| `:q` | `:quit` | Quit application |
| `:r` | `:refresh` | Refresh project list |
| `:s` | `:sync` | Sync selected project |
| `:a` | `:add` | Add new project |
| `:a owner/repo` | | Add project directly |
| `:d` | `:del`, `:delete` | Delete selected |
| `:o` | `:open` | Open in browser |
| `:h` | `:help` | Show this help |
| `:f all` | `:filter all` | Show all projects |
| `:f synced` | `:filter s` | Filter to synced |
| `:f unsynced` | `:filter u` | Filter to unsynced |
| `:f starred` | `:filter *` | Filter to starred |
| `:sort stars` | `:sort s` | Sort by stars |
| `:sort name` | `:sort n` | Sort by name |
| `:sort recent` | `:sort r` | Sort by sync time |
| `:clear` | | Clear all filters |
| `:starred` | `:star` | Toggle starred filter |

Without `:`, typing searches/filters projects. Press Enter to search immediately.

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `q` | Quit |
| `r` | Refresh project list |
| `s` | Sync selected project(s) |
| `a` | Add new project |
| `o` | Open in browser (project or tree item) |
| `d` | Delete selected project(s) |
| `c` | Add component (in Components tab) |
| `/` | Focus search |
| `f` | Cycle filter (All → Synced → Unsynced) |
| `?` | Show this help |
| `` ` `` | Open settings (theme, app info) |
| `Tab` | Navigate between panels |

## Component Tree Navigation

Click on tree items to view content in a modal viewer:
- **Docs**: Shows documentation content
- **Issues/PRs**: Shows details with description
- **Branches/Releases**: Shows info with link

Press `o` while tree is focused to open the item in your web browser.

## Multi-Selection

| Key | Action |
|-----|--------|
| `Ctrl+Click` | Toggle select clicked project |
| `Shift+Click` | Toggle select clicked project |
| `Space` | Toggle select current project |
| `Ctrl+A` | Select all visible projects |
| `Escape` | Clear selection |

Selected projects are highlighted. Use multi-select with Sync or Delete to batch operate.

## Sidebar Controls

### Selectors (Row 1)
- **Type** - Filter by entity type (Repos, Branches, Issues, PRs, Docs, Deltas, Users, Languages, Packages)
- **Language** - Filter by primary language
- **Sort** - Sort by stars, name, or recent sync

### Buttons (Row 2)
- **All** - Show all projects (clear sync filter)
- **Synced** - Show only synced projects
- **Unsynced** - Show only unsynced projects
- **Star** - Cycle starred filter (all ? starred ? unstarred)

## Tabs

Main Tabs:
- **Dossier** - Formatted overview with component tree
- **Projects** - Project detail workspace (subtabs below)
- **Deltas** - Delta list with phases, notes, and links

Project Subtabs (inside Projects):
- **Details** - Project info with clickable links
- **Documentation** - Parsed doc sections
- **Languages** - Language breakdown with visual bars
- **Branches** - Repository branches with commit info
- **Dependencies** - Clickable links to PyPI/npm
- **Contributors** - Top contributors with GitHub links
- **Issues** - Clickable issue numbers
- **Pull Requests** - PRs with merge status and diff stats
- **Releases** - Version releases with tags
- **Components** - Manage subproject relationships

## Deltas Tab

Deltas are the unit of change. Use this tab to manage phases, add notes, and compose/link deltas to issues, PRs, branches, docs, or other deltas.

## Projects > Components

Link projects together as components, dependencies, or related projects:
- **➕ Add Component** - Add a subproject to the current project
- **🔗 Link as Parent** - Link current project to a parent
- **❌ Remove** - Remove selected relationship

Relationship types:
- 🧩 **Component** - A submodule or part of the parent
- 📦 **Dependency** - Parent depends on this project
- 🔗 **Related** - Projects are related but not hierarchical

## Adding Projects

You can add projects by:
- Name only (e.g., "my-project")
- GitHub URL (e.g., "https://github.com/owner/repo")
- Short format (e.g., "owner/repo")

## Syncing

Projects with GitHub info will sync:
- Repository metadata (stars, language)
- README content
- Documentation from docs/ folder
- Language breakdown
- Branches with commit info
- Dependencies (pyproject.toml, package.json)
- Top contributors
- Issues
- Pull requests with diff stats
- Releases

Set `GITHUB_TOKEN` environment variable for:
- Private repositories
- Higher rate limits (5000/hr vs 60/hr)
        """
        
        from textual.screen import ModalScreen
        from textual.widgets import Button
        from textual.containers import Vertical, VerticalScroll
        
        class HelpScreen(ModalScreen):
            """Help screen."""
            
            CSS = """
            HelpScreen {
                align: center middle;
            }
            
            #help-dialog {
                width: 70;
                height: 80%;
                padding: 1 2;
                background: $surface;
                border: solid $primary;
            }
            
            #help-scroll {
                height: 1fr;
            }
            
            #help-dialog Button {
                margin-top: 1;
                align: center middle;
            }
            """
            
            BINDINGS = [
                Binding("escape", "close", "Close"),
                Binding("q", "close", "Close"),
            ]
            
            def compose(self) -> ComposeResult:
                with Vertical(id="help-dialog"):
                    with VerticalScroll(id="help-scroll"):
                        yield Markdown(help_text)
                    yield Button("Close", id="close-btn")
            
            @on(Button.Pressed, "#close-btn")
            def on_close(self) -> None:
                self.dismiss()
            
            def action_close(self) -> None:
                self.dismiss()
        
        self.push_screen(HelpScreen())
    
    def action_settings(self) -> None:
        """Show settings overlay with theme selection and app info."""
        import platform
        import sys
        from pathlib import Path
        
        from textual.screen import ModalScreen
        from textual.widgets import Button, RadioButton, RadioSet, Switch, Input
        from textual.containers import Vertical, Horizontal, VerticalScroll
        
        from dossier import __version__
        from dossier.config import (
            DossierConfig, 
            AVAILABLE_THEMES, 
            AVAILABLE_TABS,
            TREE_DENSITY_OPTIONS,
            EXPORT_FORMAT_OPTIONS,
        )
        
        # Which stores this installation is reading, and which it merely might.
        # Gathered here rather than in `compose` so a slow answer -- the archive
        # is an HTTP call -- happens once while the screen is being built.
        from dossier.sources import all_sources

        try:
            data_sources = all_sources()
        except Exception as exc:                      # noqa: BLE001
            # A settings screen that will not open because one source is
            # unreachable is worse than one that says so in a row.
            from dossier.sources import Source
            data_sources = [Source("data sources", "could not be read",
                                   str(exc), in_use=False, present=False)]
        
        # Get project count
        project_count = 0
        try:
            with self.session_factory() as session:
                from sqlmodel import func
                result = session.exec(select(func.count()).select_from(Project))
                project_count = result.one()
        except Exception:
            pass
        
        # Load current config
        config = self._config
        app_ref = self  # Reference to app for settings changes
        
        class SettingsScreen(ModalScreen):
            """Settings screen with theme selection, preferences, and app info."""
            
            CSS = """
            SettingsScreen {
                align: center middle;
            }
            
            #settings-dialog {
                width: 80;
                height: auto;
                max-height: 90%;
                padding: 1 2;
                background: $surface;
                border: solid $primary;
            }
            
            #settings-scroll {
                height: auto;
                max-height: 70;
            }
            
            .settings-section {
                margin-bottom: 1;
            }
            
            .settings-label {
                text-style: bold;
                margin-bottom: 1;
                color: $primary;
            }
            
            .settings-sublabel {
                margin-top: 1;
                margin-bottom: 0;
                color: $text-muted;
            }
            
            .info-row {
                height: 1;
                margin-bottom: 0;
            }
            
            .info-label {
                width: 20;
                color: $text-muted;
            }
            
            .info-value {
                width: 1fr;
            }
            
            .setting-row {
                height: 3;
                margin-bottom: 1;
                align: left middle;
            }
            
            .setting-row-label {
                width: 25;
            }
            
            .setting-row-control {
                width: 1fr;
            }
            
            #theme-select {
                margin: 1 0;
                height: auto;
            }
            
            #default-tab-select {
                margin: 1 0;
                height: auto;
            }
            
            #settings-buttons {
                margin-top: 1;
                height: auto;
                align: center middle;
            }
            
            #settings-buttons Button {
                margin: 0 1;
            }
            
            .sync-input {
                width: 10;
            }
            """
            
            BINDINGS = [
                Binding("escape", "close", "Close"),
                Binding("q", "close", "Close"),
            ]
            
            def compose(self) -> ComposeResult:
                with Vertical(id="settings-dialog"):
                    with VerticalScroll(id="settings-scroll"):
                        # App Info Section
                        yield Static("⚙️  App Info", classes="settings-label")
                        with Vertical(classes="settings-section"):
                            with Horizontal(classes="info-row"):
                                yield Static("Version:", classes="info-label")
                                yield Static(f"{__version__}", classes="info-value")
                            with Horizontal(classes="info-row"):
                                yield Static("Python:", classes="info-label")
                                yield Static(f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}", classes="info-value")
                            with Horizontal(classes="info-row"):
                                yield Static("Platform:", classes="info-label")
                                yield Static(f"{platform.system()} {platform.release()}", classes="info-value")
                            with Horizontal(classes="info-row"):
                                yield Static("Projects:", classes="info-label")
                                yield Static(f"{project_count}", classes="info-value")

                        yield Rule()

                        # Data sources. This replaced a single "Database:" row
                        # showing `dossier_home()/dossier.db` -- a path this
                        # application does not necessarily open. It was a real
                        # number about the wrong file, which is worse than none:
                        # a reader checks it, sees a plausible size, and stops
                        # looking. Every candidate is listed and the live one is
                        # marked, because two databases with nothing on screen
                        # saying which is live is the failure `health.py` exists
                        # for.
                        yield Static("🗄  Data sources", classes="settings-label")
                        with Vertical(classes="settings-section"):
                            for source in data_sources:
                                with Horizontal(classes="info-row"):
                                    mark = f" [{source.marker}]" if source.marker else ""
                                    yield Static(f"{source.label}{mark}:",
                                                 classes="info-label")
                                    yield Static(source.where, classes="info-value")
                                with Horizontal(classes="info-row"):
                                    yield Static("", classes="info-label")
                                    yield Static(source.detail,
                                                 classes="info-value")

                        yield Rule()
                        
                        # Theme Section
                        yield Static("🎨 Theme", classes="settings-label")
                        with RadioSet(id="theme-select"):
                            for theme_id, theme_name in AVAILABLE_THEMES:
                                yield RadioButton(
                                    theme_name, 
                                    value=(theme_id == config.theme),
                                    id=f"theme-{theme_id}",
                                )
                        
                        yield Rule()
                        
                        # Default Tab Section
                        yield Static("📋 Default Tab", classes="settings-label")
                        yield Static("Tab to open when selecting a project", classes="settings-sublabel")
                        with RadioSet(id="default-tab-select"):
                            for tab_id, tab_name in AVAILABLE_TABS:
                                yield RadioButton(
                                    tab_name,
                                    value=(tab_id == config.default_tab),
                                    id=f"deftab-{tab_id}",
                                )
                        
                        yield Rule()
                        
                        # Sync Preferences
                        yield Static("🔄 Sync Preferences", classes="settings-label")
                        with Horizontal(classes="setting-row"):
                            yield Static("Batch size:", classes="setting-row-label")
                            yield Input(
                                str(config.sync_batch_size),
                                id="sync-batch-size",
                                type="integer",
                                classes="sync-input",
                            )
                        with Horizontal(classes="setting-row"):
                            yield Static("Delay (seconds):", classes="setting-row-label")
                            yield Input(
                                str(config.sync_delay),
                                id="sync-delay",
                                type="number",
                                classes="sync-input",
                            )
                        
                        yield Rule()
                        
                        # Export Preferences
                        yield Static("📁 Export Format", classes="settings-label")
                        with RadioSet(id="export-format-select"):
                            for fmt_id, fmt_name in EXPORT_FORMAT_OPTIONS:
                                yield RadioButton(
                                    fmt_name,
                                    value=(fmt_id == config.export_format),
                                    id=f"export-{fmt_id}",
                                )
                    
                    with Horizontal(id="settings-buttons"):
                        yield Button("Reset Defaults", id="reset-btn", variant="warning")
                        yield Button("Close", id="close-btn", variant="primary")
            
            def _auto_save(self) -> None:
                """Auto-save settings to config file."""
                config.save()
                app_ref._config = config
            
            @on(RadioSet.Changed, "#theme-select")
            def on_theme_changed(self, event: RadioSet.Changed) -> None:
                """Handle theme selection change."""
                if event.pressed:
                    radio_id = event.pressed.id
                    if radio_id and radio_id.startswith("theme-"):
                        theme_id = radio_id[6:]  # Remove "theme-" prefix
                        config.theme = theme_id
                        app_ref.theme = theme_id
                        self._auto_save()
            
            @on(RadioSet.Changed, "#default-tab-select")
            def on_default_tab_changed(self, event: RadioSet.Changed) -> None:
                """Handle default tab selection change."""
                if event.pressed:
                    radio_id = event.pressed.id
                    if radio_id and radio_id.startswith("deftab-"):
                        tab_id = radio_id[7:]  # Remove "deftab-" prefix
                        config.default_tab = tab_id
                        self._auto_save()
            
            @on(RadioSet.Changed, "#export-format-select")
            def on_export_format_changed(self, event: RadioSet.Changed) -> None:
                """Handle export format selection change."""
                if event.pressed:
                    radio_id = event.pressed.id
                    if radio_id and radio_id.startswith("export-"):
                        fmt_id = radio_id[7:]  # Remove "export-" prefix
                        config.export_format = fmt_id
                        self._auto_save()
            
            @on(Input.Changed, "#sync-batch-size")
            def on_batch_size_changed(self, event: Input.Changed) -> None:
                """Handle batch size input change."""
                try:
                    value = int(event.value)
                    if value > 0:
                        config.sync_batch_size = value
                        self._auto_save()
                except ValueError:
                    pass
            
            @on(Input.Changed, "#sync-delay")
            def on_delay_changed(self, event: Input.Changed) -> None:
                """Handle delay input change."""
                try:
                    value = float(event.value)
                    if value >= 0:
                        config.sync_delay = value
                        self._auto_save()
                except ValueError:
                    pass
            
            @on(Button.Pressed, "#reset-btn")
            def on_reset(self) -> None:
                """Reset settings to defaults."""
                config.reset()
                config.save()
                app_ref._config = config
                app_ref.theme = config.theme
                self.notify("🔄 Settings reset to defaults", severity="warning")
                # Refresh the screen to show reset values
                self.dismiss()
                app_ref.push_screen(SettingsScreen())
            
            @on(Button.Pressed, "#close-btn")
            def on_close(self) -> None:
                self.dismiss()
            
            def action_close(self) -> None:
                self.dismiss()
        
        self.push_screen(SettingsScreen())


def run_tui() -> None:
    """Run the Dossier TUI application."""
    app = DossierApp()
    app.run()


if __name__ == "__main__":
    run_tui()
