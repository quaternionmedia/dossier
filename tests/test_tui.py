"""Tests for Dossier TUI application."""

import pytest
from click.testing import CliRunner

from dossier.cli import cli


class TestDashboardCommand:
    """Tests for the dashboard command."""
    
    def test_dashboard_command_exists(self) -> None:
        """Test that dashboard command is registered."""
        runner = CliRunner()
        result = runner.invoke(cli, ["dashboard", "--help"])
        assert result.exit_code == 0
        assert "interactive TUI dashboard" in result.output
    
    def test_dashboard_help_shows_shortcuts(self) -> None:
        """Test that help shows keyboard shortcuts."""
        runner = CliRunner()
        result = runner.invoke(cli, ["dashboard", "--help"])
        assert "Keyboard shortcuts" in result.output
        assert "Quit" in result.output
        assert "Refresh" in result.output


class TestTUIModule:
    """Tests for TUI module imports."""
    
    def test_import_dossier_app(self) -> None:
        """Test that DossierApp can be imported."""
        from dossier.tui import DossierApp
        assert DossierApp is not None
    
    def test_app_class_attributes(self) -> None:
        """Test DossierApp has required attributes."""
        from dossier.tui import DossierApp
        assert hasattr(DossierApp, "TITLE")
        assert hasattr(DossierApp, "BINDINGS")
        assert hasattr(DossierApp, "CSS")
    
    def test_app_bindings(self) -> None:
        """Test DossierApp has expected key bindings."""
        from dossier.tui import DossierApp
        binding_keys = [b.key for b in DossierApp.BINDINGS]
        assert "q" in binding_keys  # Quit
        assert "r" in binding_keys  # Refresh
        assert "s" in binding_keys  # Sync
        assert "a" in binding_keys  # Add
        assert "/" in binding_keys  # Search


class TestTUIWidgets:
    """Tests for custom TUI widgets."""
    
    def test_project_list_item_import(self) -> None:
        """Test ProjectListItem can be imported."""
        from dossier.tui.app import ProjectListItem
        assert ProjectListItem is not None
    
    def test_sync_status_widget_import(self) -> None:
        """Test SyncStatusWidget can be imported."""
        from dossier.tui.app import SyncStatusWidget
        assert SyncStatusWidget is not None
    
    def test_project_detail_panel_import(self) -> None:
        """Test ProjectDetailPanel can be imported."""
        from dossier.tui.app import ProjectDetailPanel
        assert ProjectDetailPanel is not None
    
    def test_stats_widget_import(self) -> None:
        """Test StatsWidget can be imported."""
        from dossier.tui.app import StatsWidget
        assert StatsWidget is not None


# Define tabs and resolutions for parameterized screenshot tests
TABS = [
    ("tab-dossier", "Dossier"),
    ("tab-details", "Details"),
    ("tab-docs", "Documentation"),
    ("tab-languages", "Languages"),
    ("tab-branches", "Branches"),
    ("tab-dependencies", "Dependencies"),
    ("tab-contributors", "Contributors"),
    ("tab-issues", "Issues"),
    ("tab-prs", "Pull Requests"),
    ("tab-releases", "Releases"),
    ("tab-components", "Components"),
]

RESOLUTIONS = [
    ((120, 40), "desktop"),      # Standard terminal
    ((160, 50), "wide"),         # Wide terminal
    ((80, 30), "compact"),       # Compact/small terminal
]

MODALS = [
    ("?", "help", "Help Dialog"),
    ("a", "add_project", "Add Project Modal"),
    ("/", "search", "Search Focus"),
]


@pytest.mark.screenshot
class TestTUIScreenshots:
    """Screenshot tests for generating documentation images.
    
    Run with: uv run pytest tests/test_tui.py -k screenshot --screenshots
    """
    
    @pytest.mark.asyncio
    async def test_screenshot_main_dashboard(self, screenshot_helper) -> None:
        """Capture screenshot of the main dashboard view."""
        from dossier.tui import DossierApp
        
        app = DossierApp()
        async with app.run_test(size=(120, 40)) as pilot:
            # Wait for app to fully load
            await pilot.pause()
            
            # Take screenshot
            path = await screenshot_helper.capture(
                app, 
                "dashboard_main",
                title="Dossier Dashboard"
            )
            if path:
                assert path.exists()
    
    @pytest.mark.asyncio
    async def test_screenshot_help_dialog(self, screenshot_helper) -> None:
        """Capture screenshot of the help dialog."""
        from dossier.tui import DossierApp
        
        app = DossierApp()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            
            # Open help dialog
            await pilot.press("?")
            await pilot.pause()
            
            path = await screenshot_helper.capture(
                app,
                "dashboard_help",
                title="Dossier Help"
            )
            if path:
                assert path.exists()
    
    @pytest.mark.asyncio
    async def test_screenshot_add_project_modal(self, screenshot_helper) -> None:
        """Capture screenshot of the add project modal."""
        from dossier.tui import DossierApp
        
        app = DossierApp()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            
            # Open add project modal
            await pilot.press("a")
            await pilot.pause()
            
            path = await screenshot_helper.capture(
                app,
                "dashboard_add_project",
                title="Add Project Modal"
            )
            if path:
                assert path.exists()
    
    @pytest.mark.asyncio
    async def test_screenshot_search(self, screenshot_helper) -> None:
        """Capture screenshot with search active."""
        from dossier.tui import DossierApp
        
        app = DossierApp()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            
            # Focus search
            await pilot.press("/")
            await pilot.pause()
            
            path = await screenshot_helper.capture(
                app,
                "dashboard_search",
                title="Search Projects"
            )
            if path:
                assert path.exists()


@pytest.mark.screenshot
class TestTUIScreenshotsParameterized:
    """Parameterized screenshot tests for all tabs and resolutions.
    
    Generates comprehensive documentation screenshots.
    Run with: uv run pytest tests/test_tui.py -k Parameterized --screenshots -v
    """
    
    @pytest.mark.asyncio
    @pytest.mark.parametrize("tab_id,tab_name", TABS)
    @pytest.mark.parametrize("size,resolution_name", RESOLUTIONS)
    async def test_screenshot_tab_at_resolution(
        self, 
        screenshot_helper, 
        tab_id: str, 
        tab_name: str,
        size: tuple,
        resolution_name: str,
    ) -> None:
        """Capture screenshot of each tab at each resolution."""
        from dossier.tui import DossierApp
        from textual.widgets import TabbedContent
        
        app = DossierApp()
        async with app.run_test(size=size) as pilot:
            # Wait for app to fully load
            await pilot.pause()
            # Additional wait for data to load
            await pilot.pause()
            await pilot.pause()
            
            # Switch to the target tab
            try:
                tabs = app.query_one("#project-tabs", TabbedContent)
                tabs.active = tab_id
                # Wait for tab content to render
                await pilot.pause()
                await pilot.pause()
            except Exception:
                # Tab may not exist or app may not have that widget yet
                pass
            
            # Generate descriptive filename
            filename = f"tab_{tab_id.replace('tab-', '')}_{resolution_name}"
            
            path = await screenshot_helper.capture(
                app,
                filename,
                title=f"{tab_name} - {resolution_name}"
            )
            if path:
                assert path.exists(), f"Screenshot not created: {path}"
    
    @pytest.mark.asyncio
    @pytest.mark.parametrize("key,modal_name,description", MODALS)
    @pytest.mark.parametrize("size,resolution_name", RESOLUTIONS[:1])  # Just desktop for modals
    async def test_screenshot_modal_at_resolution(
        self,
        screenshot_helper,
        key: str,
        modal_name: str,
        description: str,
        size: tuple,
        resolution_name: str,
    ) -> None:
        """Capture screenshot of each modal/overlay."""
        from dossier.tui import DossierApp
        
        app = DossierApp()
        async with app.run_test(size=size) as pilot:
            # Wait for app to fully load
            await pilot.pause()
            await pilot.pause()
            
            # Open the modal/activate feature
            await pilot.press(key)
            # Wait for modal to render
            await pilot.pause()
            await pilot.pause()
            
            filename = f"modal_{modal_name}_{resolution_name}"
            
            path = await screenshot_helper.capture(
                app,
                filename,
                title=f"{description} - {resolution_name}"
            )
            if path:
                assert path.exists(), f"Screenshot not created: {path}"
    
    @pytest.mark.asyncio
    @pytest.mark.parametrize("size,resolution_name", RESOLUTIONS)
    async def test_screenshot_empty_state(
        self,
        screenshot_helper,
        size: tuple,
        resolution_name: str,
    ) -> None:
        """Capture screenshot of empty/initial state at each resolution."""
        from dossier.tui import DossierApp
        
        app = DossierApp()
        async with app.run_test(size=size) as pilot:
            # Wait for app to fully load
            await pilot.pause()
            await pilot.pause()
            
            filename = f"empty_state_{resolution_name}"
            
            path = await screenshot_helper.capture(
                app,
                filename,
                title=f"Empty State - {resolution_name}"
            )
            if path:
                assert path.exists(), f"Screenshot not created: {path}"
