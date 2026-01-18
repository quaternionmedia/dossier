"""Main Dossier TUI application."""

from datetime import datetime
from typing import Optional

from sqlmodel import Session, select
from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.reactive import reactive
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
    ProgressBar,
    Rule,
    Select,
    Static,
    TabbedContent,
    TabPane,
    Tree,
)

from dossier.models import (
    DocumentSection,
    DocumentationLevel,
    Project,
    ProjectBranch,
    ProjectComponent,
    ProjectContributor,
    ProjectDependency,
    ProjectIssue,
    ProjectLanguage,
    ProjectPullRequest,
    ProjectRelease,
    ProjectVersion,
)
from dossier.dossier_file import generate_dossier


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
    
    def compose(self) -> ComposeResult:
        stars = f" ⭐{self.project.github_stars}" if self.project.github_stars else ""
        synced = "🔄" if self.project.last_synced_at else "○"
        yield Label(f"{synced} {self.project.name}{stars}", id="project-label")
    
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
    
    def compose(self) -> ComposeResult:
        yield Label("Select a project", id="project-title", classes="title")
        yield Rule()
        yield VerticalScroll(
            Static("", id="project-info", markup=True),
            Markdown("", id="project-docs"),
            id="detail-scroll",
        )
    
    def watch_project(self, project: Optional[Project]) -> None:
        if project is None:
            self.query_one("#project-title", Label).update("Select a project")
            self.query_one("#project-info", Static).update("")
            self.query_one("#project-docs", Markdown).update("")
            return
        
        self.query_one("#project-title", Label).update(f"📁 {project.name}")
        
        # Build info text with Rich markup for clickable links
        info_lines = []
        if project.description:
            info_lines.append(f"📝 {project.description}")
            info_lines.append("")
        
        if project.github_owner:
            owner_url = f"https://github.com/{project.github_owner}"
            info_lines.append(f"👤 Owner: [@click=app.open_url('{owner_url}')]{project.github_owner}[/]")
        if project.github_stars is not None:
            info_lines.append(f"⭐ Stars: {project.github_stars:,}")
        if project.github_language:
            info_lines.append(f"💻 Language: {project.github_language}")
        if project.repository_url:
            info_lines.append(f"🔗 [@click=app.open_url('{project.repository_url}')]{project.repository_url}[/]")
        if project.last_synced_at:
            info_lines.append(f"🔄 Synced: {project.last_synced_at.strftime('%Y-%m-%d %H:%M')}")
        else:
            info_lines.append("🔄 [dim]Not synced - press 's' to sync[/]")
        
        self.query_one("#project-info", Static).update("\n".join(info_lines))


class StatsWidget(Static):
    """Widget showing database statistics."""
    
    def __init__(self, session_factory) -> None:
        super().__init__()
        self.session_factory = session_factory
    
    def on_mount(self) -> None:
        self.refresh_stats()
    
    def refresh_stats(self) -> None:
        with self.session_factory() as session:
            project_count = len(session.exec(select(Project)).all())
            synced_count = len([
                p for p in session.exec(select(Project)).all()
                if p.last_synced_at
            ])
            doc_count = len(session.exec(select(DocumentSection)).all())
            
        self.update(
            f"📊 Projects: {project_count} ({synced_count} synced) | "
            f"📄 Docs: {doc_count}"
        )


class DossierApp(App):
    """Main Dossier TUI application for project tracking."""
    
    TITLE = "Dossier"
    SUB_TITLE = "Documentation Standardization Tool"
    
    CSS = """
    Screen {
        layout: grid;
        grid-size: 2 2;
        grid-columns: 1fr 2fr;
        grid-rows: auto 1fr;
    }
    
    #header-bar {
        column-span: 2;
        height: 3;
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
    
    #sidebar {
        width: 100%;
        height: 100%;
        border-right: solid $primary;
    }
    
    #project-list-container {
        height: 1fr;
    }
    
    #project-list {
        height: 100%;
        scrollbar-gutter: stable;
    }
    
    .multi-selected {
        background: $primary 30%;
        text-style: bold;
    }
    
    .multi-selected:hover {
        background: $primary 40%;
    }
    
    #main-content {
        width: 100%;
        height: 100%;
        padding: 0 1;
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
    
    #search-input {
        dock: top;
        margin: 0 0 1 0;
    }
    
    #filter-bar {
        dock: top;
        height: auto;
        margin: 0 0 1 0;
    }
    
    #filter-bar Button {
        margin: 0 1 0 0;
        min-width: 4;
    }
    
    #action-buttons {
        dock: bottom;
        height: auto;
        padding: 1 0;
    }
    
    #action-buttons Button {
        margin: 0 1 0 0;
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
    
    TabPane {
        padding: 1;
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
    
    #docs-table {
        height: 1fr;
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
        Binding("?", "help", "Help", show=True),
        Binding("d", "delete", "Delete", show=False),
        Binding("c", "add_component", "Add Component", show=False),
        Binding("space", "toggle_select", "Toggle Select", show=False),
        Binding("ctrl+a", "select_all", "Select All", show=False),
        Binding("escape", "clear_selection", "Clear Selection", show=False),
        Binding("tab", "focus_next", "Next", show=False),
        Binding("shift+tab", "focus_previous", "Previous", show=False),
    ]
    
    selected_project: reactive[Optional[Project]] = reactive(None)
    selected_projects: reactive[set] = reactive(set, always_update=True)  # Set of project IDs for multi-select
    filter_synced: reactive[Optional[bool]] = reactive(None)  # None=all, True=synced, False=unsynced
    filter_language: reactive[Optional[str]] = reactive(None)
    sort_by: reactive[str] = reactive("stars")  # name, stars, synced - default to stars
    _navigating_from_tree: bool = False  # Flag to prevent tab switch during tree navigation
    _tree_target_tab: Optional[str] = None  # Target tab when navigating from tree
    
    def __init__(self, session_factory=None):
        super().__init__()
        if session_factory is None:
            from dossier.cli import get_session, init_db
            init_db()
            session_factory = get_session
        self.session_factory = session_factory
    
    def compose(self) -> ComposeResult:
        yield Header()
        
        with Horizontal(id="header-bar"):
            yield StatsWidget(self.session_factory)
        
        with Vertical(id="sidebar"):
            yield Input(placeholder="🔍 Search projects...", id="search-input")
            with Horizontal(id="filter-bar"):
                yield Button("All", id="btn-filter-all", variant="primary")
                yield Button("🔄", id="btn-filter-synced", variant="default")
                yield Button("○", id="btn-filter-unsynced", variant="default")
                yield Button("⭐", id="btn-sort-stars", variant="primary")  # Default to stars sort
            with Container(id="project-list-container"):
                yield ListView(id="project-list")
            with Horizontal(id="action-buttons"):
                yield Button("Sync", id="btn-sync", variant="primary")
                yield Button("Add", id="btn-add", variant="default")
                yield Button("Del", id="btn-delete", variant="error")
        
        with Vertical(id="main-content"):
            with TabbedContent(id="project-tabs"):
                with TabPane("Dossier", id="tab-dossier"):
                    with Horizontal(id="dossier-layout"):
                        yield VerticalScroll(Markdown("", id="dossier-view"), id="dossier-scroll")
                        yield DraggableSplitter("dossier-scroll", "component-tree", id="dossier-splitter")
                        yield Tree("Components", id="component-tree")
                with TabPane("Details", id="tab-details"):
                    yield ProjectDetailPanel(id="project-detail")
                with TabPane("Documentation", id="tab-docs"):
                    yield DataTable(id="docs-table")
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
                with TabPane("Components", id="tab-components"):
                    with Vertical():
                        yield DataTable(id="components-table")
                        with Horizontal(id="component-buttons"):
                            yield Button("➕ Add Component", id="btn-add-component", variant="primary")
                            yield Button("🔗 Link as Parent", id="btn-link-parent", variant="default")
                            yield Button("❌ Remove", id="btn-remove-component", variant="error")
        
        yield Footer()
    
    def on_mount(self) -> None:
        # Setup docs table columns
        docs_table = self.query_one("#docs-table", DataTable)
        docs_table.add_columns("Title", "Type", "Level", "Source")
        docs_table.cursor_type = "row"
        
        # Setup languages table columns
        langs_table = self.query_one("#languages-table", DataTable)
        langs_table.add_columns("Language", "Extensions", "Encoding", "Bytes", "%")
        langs_table.cursor_type = "row"
        
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
        
        # Load projects and auto-select the first one (by stars)
        self.load_projects(auto_select=True)
    
    def load_projects(self, search: str = "", auto_select: bool = False) -> None:
        """Load projects into the list view with filtering and sorting.
        
        Args:
            search: Search string to filter projects by name/description.
            auto_select: If True, automatically select the first project.
        """
        project_list = self.query_one("#project-list", ListView)
        project_list.clear()
        
        with self.session_factory() as session:
            # Build query with sorting
            if self.sort_by == "stars":
                stmt = select(Project).order_by(Project.github_stars.desc(), Project.name)
            elif self.sort_by == "synced":
                stmt = select(Project).order_by(Project.last_synced_at.desc(), Project.name)
            else:
                stmt = select(Project).order_by(Project.name)
            
            projects = session.exec(stmt).all()
            
            for project in projects:
                # Apply search filter
                if search and search.lower() not in project.name.lower():
                    if not project.description or search.lower() not in project.description.lower():
                        continue
                
                # Apply sync status filter
                if self.filter_synced is True and not project.last_synced_at:
                    continue
                if self.filter_synced is False and project.last_synced_at:
                    continue
                
                # Apply language filter
                if self.filter_language and project.github_language != self.filter_language:
                    continue
                
                # Detach from session for use in widget
                session.expunge(project)
                project_list.append(ProjectListItem(project))
        
        # Update stats
        try:
            self.query_one(StatsWidget).refresh_stats()
        except Exception:
            pass
        
        # Auto-select first project if requested and list is not empty
        if auto_select and project_list.children:
            first_item = project_list.children[0]
            if isinstance(first_item, ProjectListItem):
                project_list.index = 0
                self.selected_project = first_item.project
                self.show_project_details(first_item.project)
    
    @on(Input.Changed, "#search-input")
    def filter_projects(self, event: Input.Changed) -> None:
        """Filter projects as user types."""
        self.load_projects(search=event.value)
    
    @on(ListView.Selected, "#project-list")
    def on_project_selected(self, event: ListView.Selected) -> None:
        """Handle project selection."""
        if isinstance(event.item, ProjectListItem):
            self.selected_project = event.item.project
            self.show_project_details(event.item.project)
            # Switch to Dossier tab by default, unless navigating from tree
            if not self._navigating_from_tree:
                tabbed_content = self.query_one("#project-tabs", TabbedContent)
                tabbed_content.active = "tab-dossier"
            elif self._tree_target_tab:
                # Switch to the target tab from tree navigation
                tabbed_content = self.query_one("#project-tabs", TabbedContent)
                tabbed_content.active = self._tree_target_tab
                self._tree_target_tab = None
            self._navigating_from_tree = False
    
    def show_project_details(self, project: Project) -> None:
        """Show details for the selected project."""
        detail_panel = self.query_one("#project-detail", ProjectDetailPanel)
        detail_panel.project = project
        
        # Load dossier view
        self.load_dossier_view(project)
        
        # Load documentation sections
        docs_table = self.query_one("#docs-table", DataTable)
        docs_table.clear()
        
        with self.session_factory() as session:
            sections = session.exec(
                select(DocumentSection)
                .where(DocumentSection.project_id == project.id)
                .order_by(DocumentSection.order)
            ).all()
            
            if not sections:
                docs_table.add_row("(No documentation sections)", "-", "-", "-")
            else:
                for section in sections:
                    docs_table.add_row(
                        section.title[:40],
                        section.section_type,
                        section.level.value,
                        section.source_file or "-",
                    )
        
        # Load languages
        langs_table = self.query_one("#languages-table", DataTable)
        langs_table.clear()
        
        with self.session_factory() as session:
            languages = session.exec(
                select(ProjectLanguage)
                .where(ProjectLanguage.project_id == project.id)
                .order_by(ProjectLanguage.bytes_count.desc())
            ).all()
            
            if not languages:
                langs_table.add_row("(No language data - sync to fetch)", "-", "-", "-", "-")
            else:
                for lang in languages:
                    langs_table.add_row(
                        lang.language,
                        lang.file_extensions or "-",
                        lang.encoding or "-",
                        f"{lang.bytes_count:,}",
                        f"{lang.percentage:.1f}%",
                    )
        
        # Load branches
        branches_table = self.query_one("#branches-table", DataTable)
        branches_table.clear()
        
        # Build branch URL base
        branch_url_base = ""
        if project.github_owner and project.github_repo:
            branch_url_base = f"https://github.com/{project.github_owner}/{project.github_repo}/tree/"
        
        with self.session_factory() as session:
            branches = session.exec(
                select(ProjectBranch)
                .where(ProjectBranch.project_id == project.id)
                .order_by(ProjectBranch.is_default.desc(), ProjectBranch.name)
            ).all()
            
            if not branches:
                branches_table.add_row("(No branch data - sync to fetch)", "-", "-", "-", "-")
            else:
                for branch in branches:
                    # Branch name as clickable link
                    if branch_url_base:
                        branch_link = f"[link={branch_url_base}{branch.name}]🌿 {branch.name}[/]"
                    else:
                        branch_link = f"🌿 {branch.name}"
                    
                    default_icon = "✓" if branch.is_default else ""
                    protected_icon = "🔒" if branch.is_protected else ""
                    commit_msg = branch.commit_message[:40] + "..." if branch.commit_message and len(branch.commit_message) > 40 else (branch.commit_message or "-")
                    
                    branches_table.add_row(
                        branch_link,
                        default_icon,
                        protected_icon,
                        commit_msg,
                        branch.commit_author or "-",
                    )
        
        # Load dependencies
        deps_table = self.query_one("#dependencies-table", DataTable)
        deps_table.clear()
        
        with self.session_factory() as session:
            dependencies = session.exec(
                select(ProjectDependency)
                .where(ProjectDependency.project_id == project.id)
                .order_by(ProjectDependency.dep_type, ProjectDependency.name)
            ).all()
            
            if not dependencies:
                deps_table.add_row("(No dependencies - sync to fetch)", "-", "-", "-")
            else:
                for dep in dependencies:
                    type_icon = {
                        "runtime": "📦",
                        "dev": "🔧",
                        "optional": "❔",
                        "peer": "🔗",
                    }.get(dep.dep_type, "•")
                    
                    # Create package link based on source
                    if dep.source in ("pyproject.toml", "requirements.txt"):
                        pkg_link = f"[link=https://pypi.org/project/{dep.name}/]{dep.name}[/]"
                    elif dep.source == "package.json":
                        pkg_link = f"[link=https://www.npmjs.com/package/{dep.name}]{dep.name}[/]"
                    else:
                        pkg_link = dep.name
                    
                    deps_table.add_row(
                        pkg_link,
                        dep.version_spec or "*",
                        f"{type_icon} {dep.dep_type}",
                        dep.source,
                    )
        
        # Load contributors
        contrib_table = self.query_one("#contributors-table", DataTable)
        contrib_table.clear()
        
        with self.session_factory() as session:
            contributors = session.exec(
                select(ProjectContributor)
                .where(ProjectContributor.project_id == project.id)
                .order_by(ProjectContributor.contributions.desc())
            ).all()
            
            if not contributors:
                contrib_table.add_row("(No contributors - sync to fetch)", "-", "-")
            else:
                for contrib in contributors:
                    contrib_table.add_row(
                        f"👤 {contrib.username}",
                        str(contrib.contributions),
                        f"[link={contrib.profile_url}]🔗 GitHub[/]" if contrib.profile_url else "-",
                    )
        
        # Load issues
        issues_table = self.query_one("#issues-table", DataTable)
        issues_table.clear()
        
        # Build issue URL base
        issue_url_base = ""
        if project.github_owner and project.github_repo:
            issue_url_base = f"https://github.com/{project.github_owner}/{project.github_repo}/issues/"
        
        with self.session_factory() as session:
            issues = session.exec(
                select(ProjectIssue)
                .where(ProjectIssue.project_id == project.id)
                .order_by(ProjectIssue.issue_number.desc())
            ).all()
            
            if not issues:
                issues_table.add_row("(No issues - sync to fetch)", "-", "-", "-", "-")
            else:
                for issue in issues:
                    state_icon = "🟢" if issue.state == "open" else "⚫"
                    # Issue number as clickable link
                    issue_link = f"[link={issue_url_base}{issue.issue_number}]#{issue.issue_number}[/]" if issue_url_base else f"#{issue.issue_number}"
                    issues_table.add_row(
                        issue_link,
                        issue.title[:50] + ("..." if len(issue.title) > 50 else ""),
                        f"{state_icon} {issue.state}",
                        issue.author or "-",
                        issue.labels[:30] if issue.labels else "-",
                    )
        
        # Load pull requests
        prs_table = self.query_one("#prs-table", DataTable)
        prs_table.clear()
        
        # Build PR URL base
        pr_url_base = ""
        if project.github_owner and project.github_repo:
            pr_url_base = f"https://github.com/{project.github_owner}/{project.github_repo}/pull/"
        
        with self.session_factory() as session:
            prs = session.exec(
                select(ProjectPullRequest)
                .where(ProjectPullRequest.project_id == project.id)
                .order_by(ProjectPullRequest.pr_number.desc())
            ).all()
            
            if not prs:
                prs_table.add_row("(No PRs - sync to fetch)", "-", "-", "-", "-", "-")
            else:
                for pr in prs:
                    # State with icon
                    if pr.is_merged:
                        state_display = "🟣 merged"
                    elif pr.state == "open":
                        state_display = "🟢 open"
                    else:
                        state_display = "🔴 closed"
                    
                    if pr.is_draft:
                        state_display += " 📝"
                    
                    # PR number as clickable link
                    pr_link = f"[link={pr_url_base}{pr.pr_number}]#{pr.pr_number}[/]" if pr_url_base else f"#{pr.pr_number}"
                    
                    # Branch info
                    branch_info = f"{pr.base_branch} ← {pr.head_branch}" if pr.base_branch and pr.head_branch else "-"
                    if len(branch_info) > 25:
                        branch_info = branch_info[:22] + "..."
                    
                    # Additions/deletions
                    additions = pr.additions or 0
                    deletions = pr.deletions or 0
                    diff_display = f"[green]+{additions}[/] [red]-{deletions}[/]"
                    
                    prs_table.add_row(
                        pr_link,
                        pr.title[:40] + ("..." if len(pr.title) > 40 else ""),
                        state_display,
                        pr.author or "-",
                        branch_info,
                        diff_display,
                    )
        
        # Load releases
        releases_table = self.query_one("#releases-table", DataTable)
        releases_table.clear()
        
        # Build release URL base
        release_url_base = ""
        if project.github_owner and project.github_repo:
            release_url_base = f"https://github.com/{project.github_owner}/{project.github_repo}/releases/tag/"
        
        with self.session_factory() as session:
            releases = session.exec(
                select(ProjectRelease)
                .where(ProjectRelease.project_id == project.id)
                .order_by(ProjectRelease.release_published_at.desc())
            ).all()
            
            if not releases:
                releases_table.add_row("(No releases - sync to fetch)", "-", "-", "-", "-")
            else:
                for release in releases:
                    # Tag as clickable link
                    tag_link = f"[link={release_url_base}{release.tag_name}]🏷️ {release.tag_name}[/]" if release_url_base else f"🏷️ {release.tag_name}"
                    
                    # Type indicator
                    if release.is_draft:
                        type_display = "📝 draft"
                    elif release.is_prerelease:
                        type_display = "⚠️ prerelease"
                    else:
                        type_display = "✅ release"
                    
                    # Format published date
                    published = release.release_published_at.strftime("%Y-%m-%d %H:%M") if release.release_published_at else "-"
                    
                    releases_table.add_row(
                        tag_link,
                        (release.name or release.tag_name)[:35] + ("..." if release.name and len(release.name) > 35 else ""),
                        release.author or "-",
                        type_display,
                        published,
                    )
        
        # Load components (both children and parents)
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
                    )
            
            if not has_components:
                components_table.add_row("", "(No component relationships)", "", "")
    
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
            
            # Quick stats bar
            stats = []
            if project.github_stars:
                stats.append(f"⭐ {project.github_stars:,}")
            if project.github_language:
                stats.append(f"💻 {project.github_language}")
            if dossier.get("activity"):
                activity = dossier["activity"]
                if activity.get("contributors"):
                    stats.append(f"👥 {activity['contributors']}")
                if activity.get("open_issues"):
                    stats.append(f"🐛 {activity['open_issues']} open")
                if activity.get("open_prs"):
                    stats.append(f"🔀 {activity['open_prs']} PRs")
            
            if stats:
                md_lines.append(" • ".join(stats))
                md_lines.append("")
            
            # Repository link
            if project.repository_url:
                md_lines.append(f"🔗 [{project.repository_url}]({project.repository_url})")
                md_lines.append("")
            
            # Tech Stack
            if dossier.get("tech_stack"):
                md_lines.append("## 🛠️ Tech Stack")
                md_lines.append("")
                for lang in dossier["tech_stack"][:5]:  # Top 5 languages
                    bar_width = int(lang["percentage"] / 5)  # Scale to ~20 chars max
                    bar = "█" * bar_width
                    md_lines.append(f"- **{lang['name']}** {lang['percentage']}% `{bar}`")
                md_lines.append("")
            
            # Activity
            if dossier.get("activity"):
                activity = dossier["activity"]
                md_lines.append("## 📊 Activity")
                md_lines.append("")
                
                if activity.get("last_release"):
                    release_info = f"🏷️ **Latest Release:** `{activity['last_release']}`"
                    if activity.get("release_date"):
                        release_info += f" ({activity['release_date'][:10]})"
                    md_lines.append(release_info)
                
                if activity.get("default_branch"):
                    md_lines.append(f"🌿 **Default Branch:** `{activity['default_branch']}`")
                
                if activity.get("branches"):
                    md_lines.append(f"🌳 **Branches:** {activity['branches']}")
                
                md_lines.append("")
                
                # Activity grid
                md_lines.append("| Metric | Count |")
                md_lines.append("|--------|-------|")
                md_lines.append(f"| 🐛 Open Issues | {activity.get('open_issues', 0)} |")
                md_lines.append(f"| 🔀 Open PRs | {activity.get('open_prs', 0)} |")
                md_lines.append(f"| 👥 Contributors | {activity.get('contributors', 0)} |")
                md_lines.append("")
            
            # Dependencies
            if dossier.get("dependencies"):
                md_lines.append("## 📦 Dependencies")
                md_lines.append("")
                
                for dep_type, deps in dossier["dependencies"].items():
                    icon = {"runtime": "📦", "dev": "🔧", "optional": "❔"}.get(dep_type, "•")
                    md_lines.append(f"### {icon} {dep_type.title()} ({len(deps)})")
                    md_lines.append("")
                    
                    # Show first 10 dependencies
                    for dep in deps[:10]:
                        version = f" `{dep['version']}`" if dep.get("version") else ""
                        md_lines.append(f"- {dep['name']}{version}")
                    
                    if len(deps) > 10:
                        md_lines.append(f"- *...and {len(deps) - 10} more*")
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
        
        Each tree node stores navigation data as a dict:
        - {"type": "project", "name": "owner/repo"} - Navigate to project
        - {"type": "section", "section": "languages"} - Switch to tab
        - {"type": "url", "url": "https://..."} - Open URL
        - {"type": "language|dependency|contributor|doc|version|branch|issue|pr", ...} - Linkable entities
        """
        tree = self.query_one("#component-tree", Tree)
        tree.clear()
        tree.root.expand()
        
        # Build base URLs for linking
        base_url = ""
        if project.github_owner and project.github_repo:
            base_url = f"https://github.com/{project.github_owner}/{project.github_repo}"
        
        with self.session_factory() as session:
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
            
            # Get all data entities
            languages = session.exec(
                select(ProjectLanguage)
                .where(ProjectLanguage.project_id == project.id)
                .order_by(ProjectLanguage.percentage.desc())
            ).all()
            
            dependencies = session.exec(
                select(ProjectDependency)
                .where(ProjectDependency.project_id == project.id)
                .order_by(ProjectDependency.dep_type, ProjectDependency.name)
            ).all()
            
            contributors = session.exec(
                select(ProjectContributor)
                .where(ProjectContributor.project_id == project.id)
                .order_by(ProjectContributor.contributions.desc())
            ).all()
            
            # Get documentation sections
            doc_sections = session.exec(
                select(DocumentSection)
                .where(DocumentSection.project_id == project.id)
                .order_by(DocumentSection.order)
            ).all()
            
            # Get releases/versions
            releases = session.exec(
                select(ProjectRelease)
                .where(ProjectRelease.project_id == project.id)
                .order_by(ProjectRelease.release_published_at.desc())
            ).all()
            
            # Get versions (if available)
            versions = session.exec(
                select(ProjectVersion)
                .where(ProjectVersion.project_id == project.id)
                .order_by(ProjectVersion.major.desc(), ProjectVersion.minor.desc(), ProjectVersion.patch.desc())
            ).all()
            
            # Get branches
            branches = session.exec(
                select(ProjectBranch)
                .where(ProjectBranch.project_id == project.id)
                .order_by(ProjectBranch.is_default.desc(), ProjectBranch.name)
            ).all()
            
            # Get issues
            issues = session.exec(
                select(ProjectIssue)
                .where(ProjectIssue.project_id == project.id)
                .order_by(ProjectIssue.issue_number.desc())
            ).all()
            
            # Get pull requests
            prs = session.exec(
                select(ProjectPullRequest)
                .where(ProjectPullRequest.project_id == project.id)
                .order_by(ProjectPullRequest.pr_number.desc())
            ).all()
            
            # Add parent section if there are parents
            if parent_links:
                parents_node = tree.root.add("⬆️ Parents", expand=True)
                for link in parent_links:
                    parent = session.get(Project, link.parent_id)
                    if parent:
                        type_icon = {"component": "🧩", "dependency": "📦", "related": "🔗", "language": "🌐", "contributor": "👤", "doc": "📄", "version": "🏷️", "branch": "🌿", "issue": "🐛", "pr": "🔀"}.get(link.relationship_type, "•")
                        node = parents_node.add_leaf(f"{type_icon} {parent.name}")
                        node.data = {"type": "project", "name": parent.name}
            
            # Add current project as the center
            current_node = tree.root.add(f"📍 {project.name}", expand=True)
            current_node.data = {"type": "project", "name": project.name}
            
            # Add children under current project
            if child_links:
                for link in child_links:
                    child = session.get(Project, link.child_id)
                    if child:
                        type_icon = {"component": "🧩", "dependency": "📦", "related": "🔗", "language": "🌐", "contributor": "👤", "doc": "📄", "version": "🏷️", "branch": "🌿", "issue": "🐛", "pr": "🔀"}.get(link.relationship_type, "•")
                        child_node = current_node.add(f"{type_icon} {child.name}", expand=True)
                        child_node.data = {"type": "project", "name": child.name}
                        
                        # Recursively add grandchildren (one level deep)
                        grandchild_links = session.exec(
                            select(ProjectComponent)
                            .where(ProjectComponent.parent_id == child.id)
                            .order_by(ProjectComponent.order)
                        ).all()
                        
                        for gc_link in grandchild_links:
                            grandchild = session.get(Project, gc_link.child_id)
                            if grandchild:
                                gc_icon = {"component": "🧩", "dependency": "📦", "related": "🔗", "language": "🌐", "contributor": "👤", "doc": "📄", "version": "🏷️", "branch": "🌿", "issue": "🐛", "pr": "🔀"}.get(gc_link.relationship_type, "•")
                                gc_node = child_node.add_leaf(f"{gc_icon} {grandchild.name}")
                                gc_node.data = {"type": "project", "name": grandchild.name}
            
            if not child_links:
                current_node.add_leaf("(No linked subprojects)")
            
            # === DOCUMENTATION SECTIONS - Linkable entities ===
            if doc_sections:
                docs_node = tree.root.add(f"📄 Documentation ({len(doc_sections)})", expand=False)
                docs_node.data = {"type": "section", "section": "docs"}
                for doc in doc_sections[:10]:
                    type_icon = {"readme": "📖", "api": "📡", "setup": "🔧", "guide": "📚", "example": "💡"}.get(doc.section_type, "📄")
                    leaf = docs_node.add_leaf(f"{type_icon} {doc.title[:40]}")
                    leaf.data = {
                        "type": "doc",
                        "title": doc.title,
                        "section_type": doc.section_type,
                        "source_file": doc.source_file,
                        "project_id": project.id,
                        "url": f"{base_url}/blob/main/{doc.source_file}" if base_url and doc.source_file else None,
                    }
                if len(doc_sections) > 10:
                    more_leaf = docs_node.add_leaf(f"... and {len(doc_sections) - 10} more")
                    more_leaf.data = {"type": "section", "section": "docs"}
            
            # === VERSIONS/RELEASES - Linkable entities ===
            # Use versions if available, fall back to releases
            if versions:
                ver_node = tree.root.add(f"🏷️ Versions ({len(versions)})", expand=False)
                ver_node.data = {"type": "section", "section": "releases"}
                for ver in versions[:10]:
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
                        "url": ver.release_url or (f"{base_url}/releases/tag/v{ver.version}" if base_url else None),
                    }
                if len(versions) > 10:
                    more_leaf = ver_node.add_leaf(f"... and {len(versions) - 10} more")
                    more_leaf.data = {"type": "section", "section": "releases"}
            elif releases:
                rel_node = tree.root.add(f"🏷️ Releases ({len(releases)})", expand=False)
                rel_node.data = {"type": "section", "section": "releases"}
                for rel in releases[:10]:
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
                        "url": f"{base_url}/releases/tag/{rel.tag_name}" if base_url else None,
                    }
                if len(releases) > 10:
                    more_leaf = rel_node.add_leaf(f"... and {len(releases) - 10} more")
                    more_leaf.data = {"type": "section", "section": "releases"}
            
            # === BRANCHES - Linkable entities ===
            if branches:
                branch_node = tree.root.add(f"🌿 Branches ({len(branches)})", expand=False)
                branch_node.data = {"type": "section", "section": "branches"}
                for branch in branches[:10]:
                    default = " ⭐" if branch.is_default else ""
                    protected = " 🔒" if branch.is_protected else ""
                    leaf = branch_node.add_leaf(f"• {branch.name}{default}{protected}")
                    leaf.data = {
                        "type": "branch",
                        "name": branch.name,
                        "is_default": branch.is_default,
                        "is_protected": branch.is_protected,
                        "project_id": project.id,
                        "url": f"{base_url}/tree/{branch.name}" if base_url else None,
                    }
                if len(branches) > 10:
                    more_leaf = branch_node.add_leaf(f"... and {len(branches) - 10} more")
                    more_leaf.data = {"type": "section", "section": "branches"}
            
            # === LANGUAGES - Linkable entities ===
            if languages:
                lang_node = tree.root.add(f"🌐 Languages ({len(languages)})", expand=False)
                lang_node.data = {"type": "section", "section": "languages"}
                for lang in languages[:10]:
                    pct = f"{lang.percentage:.1f}%" if lang.percentage else ""
                    leaf = lang_node.add_leaf(f"• {lang.language} {pct}")
                    leaf.data = {
                        "type": "language",
                        "name": lang.language,
                        "project_id": project.id,
                    }
                if len(languages) > 10:
                    more_leaf = lang_node.add_leaf(f"... and {len(languages) - 10} more")
                    more_leaf.data = {"type": "section", "section": "languages"}
            
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
                            "url": f"{base_url}/pull/{pr.pr_number}" if base_url else None,
                        }
                    if len(closed_prs) > 5:
                        more_leaf = closed_node.add_leaf(f"... and {len(closed_prs) - 5} more")
                        more_leaf.data = {"type": "section", "section": "prs"}
            
            # Update tree label
            tree.root.label = f"🌳 {project.name}"
    
    @on(Tree.NodeSelected, "#component-tree")
    def on_component_tree_selected(self, event: Tree.NodeSelected) -> None:
        """Handle component tree node selection - navigate to entity or create link."""
        node = event.node
        if not node.data:
            return
        
        nav_data = node.data
        nav_type = nav_data.get("type")
        
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
                tabs = self.query_one("#project-tabs", TabbedContent)
                if tabs.active != tab_id:
                    tabs.active = tab_id
        
        elif nav_type == "language":
            # Create/find language project and link it
            self._link_language_project(nav_data)
        
        elif nav_type == "dependency":
            # Create/find dependency project and link it
            self._link_dependency_project(nav_data)
        
        elif nav_type == "contributor":
            # Create/find contributor project and link it
            self._link_contributor_project(nav_data)
        
        elif nav_type == "doc":
            # Create/find documentation project and link it
            self._link_doc_project(nav_data)
        
        elif nav_type == "version":
            # Create/find version project and link it
            self._link_version_project(nav_data)
        
        elif nav_type == "branch":
            # Create/find branch project and link it
            self._link_branch_project(nav_data)
        
        elif nav_type == "issue":
            # Create/find issue project and link it
            self._link_issue_project(nav_data)
        
        elif nav_type == "pr":
            # Create/find PR project and link it
            self._link_pr_project(nav_data)
        
        elif nav_type == "url":
            # Open URL in browser
            url = nav_data.get("url")
            if url:
                import webbrowser
                webbrowser.open(url)
    
    def _link_language_project(self, nav_data: dict) -> None:
        """Create or find a language project and link it to the current project."""
        lang_name = nav_data.get("name")
        parent_project_id = nav_data.get("project_id")
        
        if not lang_name or not parent_project_id:
            return
        
        # Create a project name for the language (e.g., "lang/python")
        project_name = f"lang/{lang_name.lower()}"
        
        with self.session_factory() as session:
            # Check if language project exists
            lang_project = session.exec(
                select(Project).where(Project.name == project_name)
            ).first()
            
            if not lang_project:
                # Create the language project
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
        
        if not dep_name or not parent_project_id:
            return
        
        # Create a project name for the dependency (e.g., "pkg/fastapi")
        project_name = f"pkg/{dep_name.lower()}"
        
        with self.session_factory() as session:
            # Check if dependency project exists
            dep_project = session.exec(
                select(Project).where(Project.name == project_name)
            ).first()
            
            if not dep_project:
                # Create the dependency project
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
        
        if not username or not parent_project_id:
            return
        
        # Create a project name for the contributor (e.g., "user/octocat")
        project_name = f"user/{username.lower()}"
        
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
                    github_owner=username,
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
        
        if not title or not parent_project_id:
            return
        
        # Create a project name for the doc (e.g., "doc/readme-getting-started")
        slug = title.lower().replace(" ", "-")[:30]
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
        
        if not version or not parent_project_id:
            return
        
        # Create a project name for the version (e.g., "ver/v1.2.3")
        # Normalize version string
        ver_slug = version.lstrip("v").replace("/", "-")
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
        
        if not name or not parent_project_id:
            return
        
        # Create a project name for the branch (e.g., "branch/main")
        branch_slug = name.replace("/", "-")
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
        
        if not number or not parent_project_id:
            return
        
        # Create a project name for the issue (e.g., "issue/123")
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
        
        if not number or not parent_project_id:
            return
        
        # Create a project name for the PR (e.g., "pr/456")
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
    
    def _select_project_by_name(self, name: str, target_tab: Optional[str] = None) -> None:
        """Select a project by name in the project list.
        
        Args:
            name: The project name to select
            target_tab: Optional tab to switch to after selection (e.g., 'tab-languages')
        """
        # Skip if already on this project
        if self.selected_project and self.selected_project.name == name:
            # Still switch tab if requested
            if target_tab:
                tabs = self.query_one("#project-tabs", TabbedContent)
                if tabs.active != target_tab:
                    tabs.active = target_tab
            return
        
        # Set flag to prevent auto-switch to dossier tab
        self._navigating_from_tree = True
        self._tree_target_tab = target_tab
            
        list_view = self.query_one("#project-list", ListView)
        
        for index, item in enumerate(list_view.children):
            if isinstance(item, ProjectListItem) and item.project.name == name:
                list_view.index = index
                self.selected_project = item.project
                self.show_project_details(item.project)
                self.notify(f"Navigated to {name}")
                return
        
        # Reset flags if project not found
        self._navigating_from_tree = False
        self._tree_target_tab = None
        # Project not in list - might not be synced
        self.notify(f"Project '{name}' not found in list", severity="warning")
    
    def watch_selected_project(self, project: Optional[Project]) -> None:
        """React to project selection changes."""
        if project:
            self.sub_title = f"Viewing: {project.name}"
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
    
    @on(Button.Pressed, "#btn-filter-all")
    def on_filter_all_pressed(self) -> None:
        """Show all projects."""
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
    
    @on(Button.Pressed, "#btn-sort-stars")
    def on_sort_stars_pressed(self) -> None:
        """Toggle sort by stars."""
        if self.sort_by == "stars":
            self.sort_by = "name"
        else:
            self.sort_by = "stars"
        self._update_filter_buttons()
        search_input = self.query_one("#search-input", Input)
        self.load_projects(search=search_input.value)
        self.notify(f"Sorted by {'stars' if self.sort_by == 'stars' else 'name'}")
    
    def _update_filter_buttons(self) -> None:
        """Update filter button variants to show active state."""
        btn_all = self.query_one("#btn-filter-all", Button)
        btn_synced = self.query_one("#btn-filter-synced", Button)
        btn_unsynced = self.query_one("#btn-filter-unsynced", Button)
        btn_stars = self.query_one("#btn-sort-stars", Button)
        
        # Update filter buttons
        btn_all.variant = "primary" if self.filter_synced is None else "default"
        btn_synced.variant = "primary" if self.filter_synced is True else "default"
        btn_unsynced.variant = "primary" if self.filter_synced is False else "default"
        
        # Update sort button
        btn_stars.variant = "primary" if self.sort_by == "stars" else "default"
    
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
        """Open the selected project's GitHub page."""
        if self.selected_project and self.selected_project.repository_url:
            self.action_open_url(self.selected_project.repository_url)
        elif self.selected_project:
            self.notify("Project has no GitHub URL", severity="warning")
        else:
            self.notify("Select a project first", severity="warning")
    
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
        list_view = self.query_one("#project-list", ListView)
        new_selection = set()
        
        for item in list_view.children:
            if isinstance(item, ProjectListItem):
                new_selection.add(item.project.id)
        
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
        list_view = self.query_one("#project-list", ListView)
        
        for item in list_view.children:
            if isinstance(item, ProjectListItem):
                item.is_multi_selected = item.project.id in self.selected_projects
    
    def _get_selected_or_multi(self) -> list[Project]:
        """Get list of selected projects (multi-select or single)."""
        if self.selected_projects:
            # Return projects from multi-selection
            projects = []
            list_view = self.query_one("#project-list", ListView)
            for item in list_view.children:
                if isinstance(item, ProjectListItem) and item.project.id in self.selected_projects:
                    projects.append(item.project)
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
            
            project_name = f"user/{username.lower()}"
            
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

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `q` | Quit |
| `r` | Refresh project list |
| `s` | Sync selected project(s) |
| `a` | Add new project |
| `o` | Open GitHub in browser |
| `d` | Delete selected project(s) |
| `c` | Add component (in Components tab) |
| `/` | Focus search |
| `f` | Cycle filter (All → Synced → Unsynced) |
| `?` | Show this help |
| `Tab` | Navigate between panels |

## Multi-Selection

| Key | Action |
|-----|--------|
| `Ctrl+Click` | Toggle select clicked project |
| `Shift+Click` | Toggle select clicked project |
| `Space` | Toggle select current project |
| `Ctrl+A` | Select all visible projects |
| `Escape` | Clear selection |

Selected projects are highlighted. Use multi-select with Sync or Delete to batch operate.

## Filter Bar

- **All** - Show all projects
- **🔄** - Show only synced projects
- **○** - Show only unsynced projects
- **⭐** - Sort by stars (toggle)

## Tabs

- **Dossier** - Formatted project overview (default on select)
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

## Components Tab

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


def run_tui() -> None:
    """Run the Dossier TUI application."""
    app = DossierApp()
    app.run()


if __name__ == "__main__":
    run_tui()
