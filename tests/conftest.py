"""Pytest configuration and shared fixtures."""

import os
import subprocess
import pytest
from datetime import datetime, timezone
from pathlib import Path
from sqlmodel import Session, SQLModel, create_engine, select

from dossier.models import (
    DocumentationLevel,
    DocumentSection,
    Project,
    ProjectComponent,
)


# Test database path (only used for file-based tests)
TEST_DB_PATH = "test_dossier.db"
TEST_DB_URL = f"sqlite:///{TEST_DB_PATH}"

# Screenshots directory
SCREENSHOTS_DIR = Path("docs/screenshots")


# --- how the suite is grouped -------------------------------------------------
#
# TWO AXES, APPLIED AUTOMATICALLY. `scale` is how much machinery a test needs,
# and it is what somebody picks when they want a fast answer. `axis` is what a
# test is about, and it is what somebody picks when they have changed one thing.
#
# DERIVED, NOT DECLARED. Marking seven hundred tests by hand would be seven
# hundred chances to mark one wrong, and the marks would drift the moment a test
# moved. These are read from where a test lives and what its module actually
# does, so a file that stops spinning an app stops being `app` without anybody
# remembering to say so.
MARKERS = {
    "unit": "pure logic: no app, no database, no clock, no network",
    "db": "needs a database session",
    "app": "spins a Textual application",
    "e2e": "reaches a subprocess, the filesystem at large, or a sibling clone",
    "ui": "about what is drawn, or which key does what",
    "data": "about facets, overviews, models, ingest",
    "seam": "about the boundary with the harness",
    "governance": "about corpus rules and generated documents",
    "docs": "an executable page, run as written",
}

# What each directory is about. `scale` is refined per module below; the axis is
# a property of where somebody put the file, and that is a decision rather than
# an accident.
# `e2e` is deliberately absent: it is a scale, not a subject, and mapping it
# here gave eight tests `e2e` twice and no axis at all. What an end-to-end test
# is about is decided the same way as anything else.
AXIS_BY_DIR = {
    "ui": "ui",
    "db": "data",
    "core": "data",
}


def _scale_of(source: str, directory: str) -> str:
    """How much machinery a module needs, read from what it does.

    Order matters: a module that spins an app and also opens a database is
    `app`, because the app is what costs the time. `e2e` wins over both --
    a subprocess or a sibling clone is a different kind of dependency, not
    a heavier one.
    """
    if directory == "e2e" or "subprocess" in source:
        return "e2e"
    if "run_test(" in source:
        return "app"
    if "create_engine" in source or "Session(" in source:
        return "db"
    return "unit"


def _axis_of(source: str, directory: str) -> str:
    """What a module is about.

    THE ARTIFACT KIND WINS FIRST. A walkthrough is a page that runs, whatever
    subject it happens to cover -- and every one of them mentions the harness or
    the corpus, so a keyword rule ahead of this claimed four of the five pages
    and left `docs` describing one.

    Then the two subjects that cut across every directory, then the directory.
    """
    if directory == "walkthrough":
        return "docs"
    if "dossier.threads" in source or "harness" in source.lower():
        return "seam"
    if "governance" in source.lower() or "restatement" in source.lower():
        return "governance"
    return AXIS_BY_DIR.get(directory, "data")


def pytest_collection_modifyitems(config, items):
    """Put every test in one scale group and one axis group.

    Read once per module rather than once per test: a suite this size would
    otherwise open the same file several hundred times.
    """
    cache: dict[Path, tuple[str, str]] = {}
    for item in items:
        path = Path(str(getattr(item, "fspath", "") or ""))
        if not path.name:
            continue
        if path not in cache:
            try:
                source = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                source = ""
            directory = path.parent.name
            cache[path] = (_scale_of(source, directory),
                           _axis_of(source, directory))
        scale, axis = cache[path]
        item.add_marker(getattr(pytest.mark, scale))
        item.add_marker(getattr(pytest.mark, axis))


def pytest_addoption(parser):
    """Add custom pytest command line options."""
    parser.addoption(
        "--screenshots",
        action="store_true",
        default=False,
        help="Generate documentation screenshots from TUI tests",
    )


def pytest_configure(config):
    """Clean up any leftover test data at the start of test run.
    
    Uses 'uv run dossier dev purge' to clean test projects from the main database
    and removes any leftover test database files.
    """
    # Register custom marker
    config.addinivalue_line(
        "markers", "screenshot: mark test as a screenshot test"
    )
    for name, what in MARKERS.items():
        config.addinivalue_line("markers", f"{name}: {what}")
    config.addinivalue_line(
        "markers", "network: this test may open a real connection")
    
    # Create screenshots directory if generating screenshots
    if config.getoption("--screenshots"):
        SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    
    # Purge test projects from main database (silently, in case db doesn't exist)
    # Purge multiple patterns to cover all test project prefixes
    _purge_test_projects()
    
    # Clean up test database files that may have been left from previous runs
    _cleanup_test_db_files()


def pytest_unconfigure(config):
    """Clean up test data at the end of test run."""
    # Purge any test projects created during the run
    _purge_test_projects()
    
    _cleanup_test_db_files()


def _purge_test_projects():
    """Purge test projects matching common test patterns from the database.
    
    This covers patterns generated by unique_name() in tests:
    - test-*, test/*, test_*
    - add-*, duplicate-*, list-*, show-*, remove-*, old-*, new-*
    - sync-*, search-*, export-*, init-*, parse-*
    - lang/*, pkg/*, user/*, doc/*, ver/*, branch/*, issue/*, pr/*
    """
    # Patterns that test projects might match
    test_patterns = [
        "test",      # General test projects (test/*, test-*, etc.)
        "add-",      # From CLI tests: unique_name("add")
        "duplicate-",  # From CLI tests: unique_name("duplicate")
        "list-",     # From CLI tests: unique_name("list-a"), etc.
        "show-",     # From CLI tests: unique_name("show")
        "remove-",   # From CLI tests: unique_name("remove")
        "old-",      # From CLI tests: unique_name("old") for rename
        "new-",      # From CLI tests: unique_name("new") for rename
        "nonexistent-",  # From CLI tests for error cases
        "sync-",     # From sync tests
        "search-",   # From search tests
        "export-",   # From export tests
        "init-",     # From init tests
        "parse-",    # From parser tests
        "lang/",     # Auto-linked language projects
        "pkg/",      # Auto-linked package projects
        "user/",     # Auto-linked user projects
        "doc/",      # Auto-linked doc projects
        "ver/",      # Auto-linked version projects
        "branch/",   # Auto-linked branch projects
        "issue/",    # Auto-linked issue projects
        "pr/",       # Auto-linked PR projects
    ]
    
    # Set UTF-8 encoding for subprocess to handle emoji/unicode characters
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    
    for pattern in test_patterns:
        try:
            result = subprocess.run(
                ["uv", "run", "dossier", "dev", "purge", "-p", pattern, "-y"],
                capture_output=True,
                timeout=30,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=env,
            )
            # Silent operation - no debug output in production
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            pass  # Ignore errors - db may not exist yet


def _cleanup_test_db_files():
    """Remove test database files."""
    test_db_files = [
        "test_dossier.db",
        "test_dossier.db-journal",
        "test_dossier.db-wal",
        "test_dossier.db-shm",
    ]
    for db_file in test_db_files:
        if os.path.exists(db_file):
            try:
                os.remove(db_file)
            except OSError:
                pass  # File may be locked


@pytest.fixture(scope="function")
def test_engine():
    """Create a test database engine using in-memory SQLite."""
    # Use in-memory database to avoid file creep
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    yield engine
    
    # Cleanup
    SQLModel.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture(scope="function")
def test_file_engine():
    """Create a test database engine using a file (for tests that need it)."""
    # Clean up first in case of leftovers
    if os.path.exists(TEST_DB_PATH):
        try:
            os.remove(TEST_DB_PATH)
        except OSError:
            pass
    
    engine = create_engine(
        TEST_DB_URL,
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    yield engine
    
    # Cleanup
    SQLModel.metadata.drop_all(engine)
    engine.dispose()
    
    # Remove the file
    for suffix in ["", "-journal", "-wal", "-shm"]:
        path = f"{TEST_DB_PATH}{suffix}"
        if os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                pass


@pytest.fixture(scope="function")
def test_session(test_engine):
    """Create a test database session."""
    with Session(test_engine) as session:
        yield session


@pytest.fixture(scope="function")
def seeded_session(test_engine):
    """Create a test session with sample data."""
    with Session(test_engine) as session:
        # Create sample projects
        project1 = Project(
            name="test/fastapi",
            description="FastAPI framework, high performance, easy to learn",
            repository_url="https://github.com/fastapi/fastapi",
            github_owner="fastapi",
            github_repo="fastapi",
            github_stars=70000,
            github_language="Python",
            last_synced_at=datetime.now(timezone.utc),
        )
        project2 = Project(
            name="test/click",
            description="Python composable command line interface toolkit",
            repository_url="https://github.com/pallets/click",
            github_owner="pallets",
            github_repo="click",
            github_stars=15000,
            github_language="Python",
            last_synced_at=datetime.now(timezone.utc),
        )
        project3 = Project(
            name="test-org/unsynced-repo",
            description="A repo that has never been synced",
            repository_url="https://github.com/test-org/unsynced-repo",
            github_owner="test-org",
            github_repo="unsynced-repo",
            github_stars=None,
            github_language=None,
            last_synced_at=None,
        )
        
        session.add(project1)
        session.add(project2)
        session.add(project3)
        session.commit()
        session.refresh(project1)
        session.refresh(project2)
        session.refresh(project3)
        
        # Create document sections for project1
        readme_section = DocumentSection(
            project_id=project1.id,
            title="FastAPI README",
            content="# FastAPI\n\nFastAPI framework, high performance, easy to learn.",
            level=DocumentationLevel.OVERVIEW,
            section_type="readme",
            source_file="README.md",
            order=0,
        )
        setup_section = DocumentSection(
            project_id=project1.id,
            title="Installation",
            content="```bash\npip install fastapi\n```",
            level=DocumentationLevel.DETAILED,
            section_type="setup",
            source_file="README.md",
            order=1,
        )
        
        session.add(readme_section)
        session.add(setup_section)
        
        # Create document sections for project2
        click_readme = DocumentSection(
            project_id=project2.id,
            title="Click README",
            content="# Click\n\nClick is a Python package for creating beautiful CLIs.",
            level=DocumentationLevel.OVERVIEW,
            section_type="readme",
            source_file="README.md",
            order=0,
        )
        session.add(click_readme)
        
        # Create a parent-child relationship (fastapi uses click)
        component = ProjectComponent(
            parent_id=project1.id,
            child_id=project2.id,
            relationship_type="dependency",
            order=0,
        )
        session.add(component)
        
        session.commit()
        
        yield session


@pytest.fixture
def sample_project():
    """Create a sample project instance (not persisted)."""
    return Project(
        name="test/sample-project",
        description="A sample project for testing",
        repository_url="https://github.com/test/sample-project",
        github_owner="test",
        github_repo="sample-project",
    )


@pytest.fixture
def sample_section(sample_project):
    """Create a sample document section (not persisted)."""
    return DocumentSection(
        project_id=1,  # Will be updated when project is persisted
        title="Sample Section",
        content="This is sample content for testing.",
        level=DocumentationLevel.OVERVIEW,
        section_type="readme",
    )


@pytest.fixture
def screenshots_enabled(request):
    """Check if screenshots are enabled via --screenshots flag."""
    return request.config.getoption("--screenshots")


@pytest.fixture
def screenshot_path(request):
    """Get the path for saving a screenshot based on test name."""
    test_name = request.node.name
    # Clean up test name for filename
    safe_name = test_name.replace("[", "_").replace("]", "_").replace("/", "_")
    return SCREENSHOTS_DIR / f"{safe_name}.svg"


class ScreenshotHelper:
    """Helper class for taking TUI screenshots in tests."""
    
    def __init__(self, enabled: bool, output_dir: Path):
        self.enabled = enabled
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    async def capture(self, app, name: str, title: str = None) -> Path | None:
        """Capture a screenshot of the app.
        
        Args:
            app: The Textual App instance
            name: Name for the screenshot file (without extension)
            title: Optional title (used in filename if provided)
            
        Returns:
            Path to the saved screenshot, or None if screenshots disabled
        """
        if not self.enabled:
            return None
        
        # Clean up name for filename
        safe_name = name.replace(" ", "_").replace("/", "_").lower()
        filename = f"{safe_name}.svg"
        
        # Use Textual's built-in screenshot functionality
        # path is the directory, filename is the file name
        app.save_screenshot(filename=filename, path=str(self.output_dir))
        return self.output_dir / filename
    
    def capture_sync(self, app, name: str, title: str = None) -> Path | None:
        """Synchronous version of capture for non-async contexts."""
        if not self.enabled:
            return None
        
        safe_name = name.replace(" ", "_").replace("/", "_").lower()
        filename = f"{safe_name}.svg"
        
        app.save_screenshot(filename=filename, path=str(self.output_dir))
        return self.output_dir / filename


@pytest.fixture
def screenshot_helper(screenshots_enabled):
    """Fixture providing screenshot helper for TUI tests."""
    return ScreenshotHelper(screenshots_enabled, SCREENSHOTS_DIR)


@pytest.fixture(autouse=True, scope="session")
def _isolate_dossier_home(tmp_path_factory):
    """Keep the suite out of the operator's `~/.dossier`.

    The TUI tests drive the real app, and the app writes its view state on
    exit. Without this the suite rewrote a real person's dashboard: last
    project, active tab, and a synced filter that afterwards matched nothing,
    so their sidebar came up empty with no visible cause. Autouse and
    session-scoped because the leak is in the app, not in any one test -- an
    opt-in fixture only protects the tests that remember it.
    """
    home = tmp_path_factory.mktemp("dossier-home")
    previous = os.environ.get("DOSSIER_HOME")
    os.environ["DOSSIER_HOME"] = str(home)
    yield home
    if previous is None:
        os.environ.pop("DOSSIER_HOME", None)
    else:
        os.environ["DOSSIER_HOME"] = previous


@pytest.fixture(scope="session")
def repo_root() -> Path:
    """The repository root, found rather than counted to.

    Tests reached it as `Path(__file__).parent.parent`, which is a count of
    directories between a test file and the root -- so organising the suite
    into categories moved every one of them one level and broke tests that had
    nothing to do with the change. Anchoring on a file that only exists at the
    root makes the depth irrelevant.
    """
    from tests.structural import repo_root as find_root

    return find_root()


# --- no ambient network -------------------------------------------------------


@pytest.fixture(autouse=True)
def no_ambient_network(request, monkeypatch):
    """Any connection this suite did not arrange fails at once.

    **THIS IS A CORRECTNESS FIX THAT HAPPENS TO BE A SPEED FIX.** The suite
    reached the harness for real. With one running it saw two hundred threads;
    with none it waited out a connect timeout and saw none -- so two tests
    passed or failed depending on whether something was listening on a port,
    which is the suite measuring its surroundings rather than the code.

    The speed is the same fact from the other side. An unreachable host does not
    refuse here, it times out: measured at 2.25s per call against both a closed
    port and a filtered one. A full run with the harness up took 229s and with
    it down took 558s, and the difference is that timeout paid a hundred and
    fifty times over.

    Tests that arrange their own transport are unaffected and compose with this:
    the usual pattern captures `httpx.Client`, adds a `transport`, and calls
    through -- and a call that already names a transport is passed straight to
    the real client. A test that genuinely wants a socket says so with
    `@pytest.mark.network`.
    """
    if "network" in request.keywords:
        return

    # A module using respx is already guaranteeing no real connection -- that is
    # what respx is -- and it intercepts at a different layer, so injecting a
    # transport underneath it replaces respx's routing with a refusal and every
    # one of its tests fails. Exempting it gives up nothing this fixture was
    # protecting.
    if getattr(request.module, "respx", None) is not None:
        return

    import httpx

    real_client = httpx.Client

    def refusing(*args, **kwargs):
        if "transport" not in kwargs:
            def handler(sent):
                raise httpx.ConnectError(
                    "this suite does not open real connections; stub the "
                    "transport, or mark the test with @pytest.mark.network",
                    request=sent)
            kwargs["transport"] = httpx.MockTransport(handler)
        return real_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "Client", refusing)
