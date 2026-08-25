"""The screens and widgets that know nothing about the application.

**SIX HUNDRED LINES THAT WERE ALREADY SEPARATE.** `tui/app.py` had grown past ten
thousand, and every slice of work this month had to navigate it -- three
anchoring mistakes in one session came directly from that, including a handler
that landed inside `DraggableSplitter` because two classes had an
`on_mouse_down`.

These eight classes referenced `DossierApp` **zero times** before the move, which
is why they go first: the extraction is mechanical, the seam already existed, and
no behaviour changes. What it buys is a boundary somebody can see -- a widget
that starts reaching for the application now has to import it, and that import is
a thing a reader can object to.

WHAT IS NOT HERE. Anything that reads the app's state, dispatches a rad intent,
or loads a tab. Those are the application's, and moving them is a different
change with a different risk.
"""

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


class WorkProgress(Vertical):
    """What a long operation is doing, while it is doing it.

    **INDETERMINATE UNLESS SOMEBODY KNOWS THE FRACTION.** An import is one
    request to the harness: it is sent, and later it is answered. Nothing in
    between reports a percentage, so a bar creeping to sixty would be a number
    this application made up -- and a made-up number is worse than no number,
    because a reader checks it and stops looking. `start(total=N)` is for the
    cases that genuinely count, like a batch sync over N repositories.

    THE ELAPSED SECONDS ARE THE HONEST FIGURE. They are measured, they always
    exist, and they are what tells somebody the difference between slow and
    stuck -- which is the actual question behind wanting a progress bar.
    """

    def compose(self) -> ComposeResult:
        yield Label("", id="work-progress-label")
        yield ProgressBar(total=None, show_eta=False, id="work-progress-bar")

    def on_mount(self) -> None:
        self.display = False
        self._started = 0.0
        self._what = ""
        self._timer = None

    def start(self, what: str, total: int | None = None) -> None:
        """Show the panel and begin counting. `total` only when it is known."""
        import time

        self._what = what
        self._started = time.monotonic()
        self.display = True
        bar = self.query_one("#work-progress-bar", ProgressBar)
        bar.total = total
        if total is not None:
            bar.update(progress=0)
        self._tick()
        if self._timer is None:
            # Twice a second: fast enough to read as alive, slow enough that the
            # tick is not competing with the work for the event loop.
            self._timer = self.set_interval(0.5, self._tick)

    def advance(self, done: int, of: int, what: str | None = None) -> None:
        """For work that really does know how far along it is."""
        if what:
            self._what = what
        bar = self.query_one("#work-progress-bar", ProgressBar)
        bar.total = of
        bar.update(progress=done)
        self._tick()

    def finish(self, said: str) -> None:
        """Stop, and leave the outcome on screen rather than vanishing.

        A panel that disappears takes the only record of what happened with it,
        and the reader was probably looking somewhere else when it did.
        """
        if self._timer is not None:
            self._timer.stop()
            self._timer = None
        self.query_one("#work-progress-label", Label).update(
            f"{said}  ({self._elapsed():.0f}s)")
        self.query_one("#work-progress-bar", ProgressBar).display = False

    def _elapsed(self) -> float:
        import time

        return time.monotonic() - self._started

    def _tick(self) -> None:
        self.query_one("#work-progress-bar", ProgressBar).display = True
        self.query_one("#work-progress-label", Label).update(
            f"{self._what}  ({self._elapsed():.0f}s)")


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


class ChatScreen(ModalScreen):
    """One archived conversation, read top to bottom.

    **THE ARCHIVE TABLE SAYS WHAT A THREAD IS; THIS SAYS WHAT IT SAID.** The
    Threads tab has listed four hundred conversations since it was built, and
    there has been no way to read one — the row is an address, a title cut to
    thirty characters, and a turn count, and none of those is the conversation.

    `escape` and `q` close it, as everywhere. The transcript is a scrollable
    Static rather than a MarkdownViewer: an archived turn is somebody's text,
    and rendering it as markdown would let a stray backtick or hash silently
    restyle what they wrote.

    **NOTHING HERE OFFERS TO SAVE IT.** The archive is personal material the
    organisation has decided must never be published; a Save button on this
    screen would be that decision, made in passing. `tests/core/test_chat.py`
    holds the check that keeps it that way.
    """

    BINDINGS = [
        Binding("escape", "close", "Close"),
        Binding("q", "close", "Close"),
    ]

    CSS = """
    ChatScreen {
        align: center middle;
    }

    #chat-dialog {
        width: 90%;
        height: 90%;
        background: $surface;
        border: solid $primary;
    }

    #chat-header {
        height: auto;
        padding: 1;
        background: $primary-darken-2;
    }

    #chat-title {
        text-style: bold;
    }

    #chat-transcript {
        height: 1fr;
        padding: 1;
    }

    #chat-footer {
        height: 3;
        padding: 0 1;
        background: $surface-darken-1;
        align: left middle;
    }

    #chat-footer Button {
        margin: 0 1;
        min-width: 8;
    }

    #chat-note {
        margin: 0 1;
        color: $text-muted;
        width: auto;
    }
    """

    def __init__(self, conversation, drawn) -> None:
        super().__init__()
        self.conversation = conversation
        self.drawn = drawn

    def compose(self) -> ComposeResult:
        with Vertical(id="chat-dialog"):
            with Horizontal(id="chat-header"):
                yield Static(f"💬 {self.conversation.title or '(untitled)'}",
                             id="chat-title")
            with VerticalScroll(id="chat-transcript"):
                yield Static(self.drawn.text(), id="chat-body")
            with Horizontal(id="chat-footer"):
                yield Button("Close", id="btn-close", variant="default")
                # Named rather than omitted: a reader comparing this with the
                # original conversation needs to know which channels this window
                # cannot carry, not to discover it by the two disagreeing.
                yield Static(
                    "this window cannot carry: "
                    + ", ".join(self.drawn.channels_dropped),
                    id="chat-note")

    @on(Button.Pressed, "#btn-close")
    def on_close_pressed(self) -> None:
        self.dismiss()

    def action_close(self) -> None:
        self.dismiss()
