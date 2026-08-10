"""Tests for Dossier API."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import dossier.api.main as api_main
import dossier.database as db_module
from dossier.api.main import app


@pytest.fixture
def client():
    """Create a test client with in-memory test database."""
    # Create test engine with in-memory database using StaticPool
    # to share the connection across multiple sessions
    test_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(test_engine)

    # Save originals from the database module
    original_get_session = db_module.get_session
    original_get_engine = db_module.get_engine

    # Override database module functions
    def get_test_session() -> Session:
        return Session(test_engine)

    def get_test_engine():
        return test_engine

    db_module.get_session = get_test_session
    db_module.get_engine = get_test_engine

    # Also override in api_main if it imported the functions
    api_main.get_session = get_test_session

    with TestClient(app) as client:
        yield client

    # Restore originals
    db_module.get_session = original_get_session
    db_module.get_engine = original_get_engine
    api_main.get_session = original_get_session

    # Clean up test database
    SQLModel.metadata.drop_all(test_engine)
    test_engine.dispose()


class TestRootEndpoint:
    """Tests for the root endpoint."""

    def test_root(self, client: TestClient) -> None:
        """Test root endpoint returns API info."""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Dossier API"
        assert data["version"] == "0.1.0"


class TestHealthEndpoint:
    """Tests for the health check endpoint."""

    def test_health_check(self, client: TestClient) -> None:
        """Test health check returns healthy status."""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"


class TestProjectsEndpoint:
    """Tests for the projects endpoints."""

    def test_list_projects_empty(self, client: TestClient) -> None:
        """Test listing projects when none exist."""
        response = client.get("/projects")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_create_project(self, client: TestClient) -> None:
        """Test creating a new project."""
        project_data = {
            "name": "api-test-project",
            "description": "Created via API",
        }
        response = client.post("/projects", json=project_data)
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "api-test-project"
        assert data["description"] == "Created via API"

    def test_get_project_not_found(self, client: TestClient) -> None:
        """Test getting a project that doesn't exist."""
        response = client.get("/projects/nonexistent-project")
        assert response.status_code == 404


class TestDocsEndpoint:
    """Tests for the documentation query endpoint."""

    def test_query_nonexistent_project(self, client: TestClient) -> None:
        """Test querying docs for nonexistent project."""
        response = client.get("/docs/nonexistent")
        assert response.status_code == 404

    def test_query_with_level(self, client: TestClient) -> None:
        """Test query parameter for documentation level."""
        # First create a project
        client.post("/projects", json={"name": "level-test"})
        
        response = client.get("/docs/level-test?level=summary")
        assert response.status_code == 200
        data = response.json()
        assert data["level"] == "summary"


class TestComponentsEndpoint:
    """Tests for the project components endpoints."""

    def test_list_components_empty(self, client: TestClient) -> None:
        """Test listing components when none exist."""
        # Create a project first
        client.post("/projects", json={"name": "parent-project"})
        
        response = client.get("/projects/parent-project/components")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["components"] == []

    def test_add_component(self, client: TestClient) -> None:
        """Test adding a component relationship."""
        # Create parent and child projects
        client.post("/projects", json={"name": "parent-proj"})
        client.post("/projects", json={"name": "child-proj"})
        
        # Add component relationship
        response = client.post(
            "/projects/parent-proj/components?child_name=child-proj&relationship_type=component"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["parent_name"] == "parent-proj"
        assert data["child_name"] == "child-proj"
        assert data["relationship_type"] == "component"

    def test_add_component_project_not_found(self, client: TestClient) -> None:
        """Test adding component with nonexistent project."""
        client.post("/projects", json={"name": "only-parent"})
        
        response = client.post(
            "/projects/only-parent/components?child_name=nonexistent"
        )
        assert response.status_code == 404

    def test_add_component_duplicate(self, client: TestClient) -> None:
        """Test adding duplicate component relationship."""
        client.post("/projects", json={"name": "dup-parent"})
        client.post("/projects", json={"name": "dup-child"})
        
        # Add first time
        client.post("/projects/dup-parent/components?child_name=dup-child")
        
        # Add again - should fail
        response = client.post("/projects/dup-parent/components?child_name=dup-child")
        assert response.status_code == 409

    def test_add_component_self_reference(self, client: TestClient) -> None:
        """Test that a project cannot be a component of itself."""
        client.post("/projects", json={"name": "self-ref"})
        
        response = client.post("/projects/self-ref/components?child_name=self-ref")
        assert response.status_code == 400

    def test_list_components_with_data(self, client: TestClient) -> None:
        """Test listing components when relationships exist."""
        # Create projects
        client.post("/projects", json={"name": "list-parent"})
        client.post("/projects", json={"name": "list-child1"})
        client.post("/projects", json={"name": "list-child2"})
        
        # Add relationships
        client.post("/projects/list-parent/components?child_name=list-child1&order=1")
        client.post("/projects/list-parent/components?child_name=list-child2&order=2")
        
        response = client.get("/projects/list-parent/components")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert len(data["components"]) == 2
        assert data["components"][0]["child_name"] == "list-child1"
        assert data["components"][1]["child_name"] == "list-child2"

    def test_update_component(self, client: TestClient) -> None:
        """Test updating a component relationship."""
        client.post("/projects", json={"name": "update-parent"})
        client.post("/projects", json={"name": "update-child"})
        client.post("/projects/update-parent/components?child_name=update-child")
        
        response = client.put(
            "/projects/update-parent/components/update-child",
            json={"relationship_type": "dependency", "order": 5}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["relationship_type"] == "dependency"
        assert data["order"] == 5

    def test_remove_component(self, client: TestClient) -> None:
        """Test removing a component relationship."""
        client.post("/projects", json={"name": "remove-parent"})
        client.post("/projects", json={"name": "remove-child"})
        client.post("/projects/remove-parent/components?child_name=remove-child")
        
        response = client.delete("/projects/remove-parent/components/remove-child")
        assert response.status_code == 200
        assert response.json()["status"] == "removed"
        
        # Verify it's gone
        list_response = client.get("/projects/remove-parent/components")
        assert list_response.json()["total"] == 0

    def test_list_all_components(self, client: TestClient) -> None:
        """Test listing all component relationships."""
        client.post("/projects", json={"name": "all-parent"})
        client.post("/projects", json={"name": "all-child"})
        client.post("/projects/all-parent/components?child_name=all-child")

        response = client.get("/components")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1


class TestDeltasEndpoint:
    """Tests for the delta endpoints."""

    def test_list_deltas_empty(self, client: TestClient) -> None:
        """Test listing deltas when none exist."""
        client.post("/projects", json={"name": "delta-project"})

        response = client.get("/projects/delta-project/deltas")
        assert response.status_code == 200
        assert response.json() == []

    def test_list_deltas_project_not_found(self, client: TestClient) -> None:
        """Test listing deltas for nonexistent project."""
        response = client.get("/projects/nonexistent/deltas")
        assert response.status_code == 404

    def test_create_delta(self, client: TestClient) -> None:
        """Test creating a new delta."""
        client.post("/projects", json={"name": "create-delta-proj"})

        delta_data = {
            "name": "add-feature",
            "title": "Add new feature",
            "description": "Implement a new feature",
            "delta_type": "feature",
            "priority": "high",
        }
        response = client.post("/projects/create-delta-proj/deltas", json=delta_data)
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "add-feature"
        assert data["title"] == "Add new feature"
        assert data["description"] == "Implement a new feature"
        assert data["delta_type"] == "feature"
        assert data["priority"] == "high"
        assert data["phase"] == "brainstorm"

    def test_create_delta_minimal(self, client: TestClient) -> None:
        """Test creating a delta with minimal fields."""
        client.post("/projects", json={"name": "minimal-delta-proj"})

        delta_data = {
            "name": "quick-fix",
            "title": "Quick fix",
        }
        response = client.post("/projects/minimal-delta-proj/deltas", json=delta_data)
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "quick-fix"
        assert data["delta_type"] == "feature"  # default
        assert data["priority"] == "medium"  # default

    def test_create_delta_duplicate_name(self, client: TestClient) -> None:
        """Test creating a delta with duplicate name fails."""
        client.post("/projects", json={"name": "dup-delta-proj"})

        delta_data = {"name": "duplicate", "title": "First delta"}
        client.post("/projects/dup-delta-proj/deltas", json=delta_data)

        response = client.post("/projects/dup-delta-proj/deltas", json=delta_data)
        assert response.status_code == 409
        assert "already exists" in response.json()["detail"]

    def test_create_delta_project_not_found(self, client: TestClient) -> None:
        """Test creating delta for nonexistent project."""
        delta_data = {"name": "orphan", "title": "Orphan delta"}
        response = client.post("/projects/nonexistent/deltas", json=delta_data)
        assert response.status_code == 404

    def test_get_delta(self, client: TestClient) -> None:
        """Test getting delta details."""
        client.post("/projects", json={"name": "get-delta-proj"})
        client.post(
            "/projects/get-delta-proj/deltas",
            json={"name": "test-delta", "title": "Test Delta"},
        )

        response = client.get("/projects/get-delta-proj/deltas/test-delta")
        assert response.status_code == 200
        data = response.json()
        assert "delta" in data
        assert "notes" in data
        assert "links" in data
        assert data["delta"]["name"] == "test-delta"

    def test_get_delta_not_found(self, client: TestClient) -> None:
        """Test getting nonexistent delta."""
        client.post("/projects", json={"name": "no-delta-proj"})

        response = client.get("/projects/no-delta-proj/deltas/nonexistent")
        assert response.status_code == 404

    def test_advance_delta(self, client: TestClient) -> None:
        """Test advancing delta to next phase."""
        client.post("/projects", json={"name": "advance-proj"})
        client.post(
            "/projects/advance-proj/deltas",
            json={"name": "advancing", "title": "Advancing Delta"},
        )

        response = client.put(
            "/projects/advance-proj/deltas/advancing/advance",
            json={},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["old_phase"] == "brainstorm"
        assert data["new_phase"] == "planning"
        assert data["note_added"] is False

    def test_advance_delta_with_note(self, client: TestClient) -> None:
        """Test advancing delta with a note."""
        client.post("/projects", json={"name": "advance-note-proj"})
        client.post(
            "/projects/advance-note-proj/deltas",
            json={"name": "with-note", "title": "Delta With Note"},
        )

        response = client.put(
            "/projects/advance-note-proj/deltas/with-note/advance",
            json={"note": "Completed brainstorming, moving to planning."},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["note_added"] is True

    def test_advance_delta_already_complete(self, client: TestClient) -> None:
        """Test advancing delta that's already complete fails."""
        client.post("/projects", json={"name": "complete-proj"})
        client.post(
            "/projects/complete-proj/deltas",
            json={"name": "done", "title": "Done Delta"},
        )

        # Advance through all phases
        for _ in range(5):  # brainstorm -> planning -> impl -> review -> docs -> complete
            client.put("/projects/complete-proj/deltas/done/advance", json={})

        # Try to advance past complete
        response = client.put("/projects/complete-proj/deltas/done/advance", json={})
        assert response.status_code == 400
        assert "final phase" in response.json()["detail"]

    def test_advance_delta_not_found(self, client: TestClient) -> None:
        """Test advancing nonexistent delta."""
        client.post("/projects", json={"name": "no-advance-proj"})

        response = client.put(
            "/projects/no-advance-proj/deltas/nonexistent/advance",
            json={},
        )
        assert response.status_code == 404

    def test_create_delta_link_issue(self, client: TestClient) -> None:
        """Test creating an issue link."""
        client.post("/projects", json={"name": "link-issue-proj"})
        client.post(
            "/projects/link-issue-proj/deltas",
            json={"name": "linked", "title": "Linked Delta"},
        )

        response = client.post(
            "/projects/link-issue-proj/deltas/linked/links",
            json={"link_type": "issue", "target_id": 123},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["link_type"] == "issue"
        assert data["target_id"] == 123

    def test_create_delta_link_branch(self, client: TestClient) -> None:
        """Test creating a branch link."""
        client.post("/projects", json={"name": "link-branch-proj"})
        client.post(
            "/projects/link-branch-proj/deltas",
            json={"name": "branched", "title": "Branched Delta"},
        )

        response = client.post(
            "/projects/link-branch-proj/deltas/branched/links",
            json={"link_type": "branch", "target_name": "feature/new-feature"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["link_type"] == "branch"
        assert data["target_name"] == "feature/new-feature"

    def test_create_delta_link_invalid_type(self, client: TestClient) -> None:
        """Test creating a link with invalid type fails."""
        client.post("/projects", json={"name": "bad-link-proj"})
        client.post(
            "/projects/bad-link-proj/deltas",
            json={"name": "bad-link", "title": "Bad Link Delta"},
        )

        response = client.post(
            "/projects/bad-link-proj/deltas/bad-link/links",
            json={"link_type": "invalid", "target_id": 1},
        )
        assert response.status_code == 400
        assert "Invalid link type" in response.json()["detail"]

    def test_create_delta_link_delta_not_found(self, client: TestClient) -> None:
        """Test creating link for nonexistent delta."""
        client.post("/projects", json={"name": "orphan-link-proj"})

        response = client.post(
            "/projects/orphan-link-proj/deltas/nonexistent/links",
            json={"link_type": "issue", "target_id": 1},
        )
        assert response.status_code == 404

    def test_list_deltas_with_phase_filter(self, client: TestClient) -> None:
        """Test listing deltas filtered by phase."""
        client.post("/projects", json={"name": "filter-proj"})
        client.post(
            "/projects/filter-proj/deltas",
            json={"name": "delta1", "title": "Delta 1"},
        )
        client.post(
            "/projects/filter-proj/deltas",
            json={"name": "delta2", "title": "Delta 2"},
        )
        # Advance delta2 to planning
        client.put("/projects/filter-proj/deltas/delta2/advance", json={})

        # Filter by planning phase
        response = client.get("/projects/filter-proj/deltas?phase=planning")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["name"] == "delta2"

    def test_list_deltas_include_completed(self, client: TestClient) -> None:
        """Test listing deltas including completed ones."""
        client.post("/projects", json={"name": "include-complete-proj"})
        client.post(
            "/projects/include-complete-proj/deltas",
            json={"name": "active", "title": "Active Delta"},
        )
        client.post(
            "/projects/include-complete-proj/deltas",
            json={"name": "done", "title": "Done Delta"},
        )
        # Complete the second delta
        for _ in range(5):
            client.put("/projects/include-complete-proj/deltas/done/advance", json={})

        # Without include_completed
        response = client.get("/projects/include-complete-proj/deltas")
        assert len(response.json()) == 1

        # With include_completed
        response = client.get("/projects/include-complete-proj/deltas?include_completed=true")
        assert len(response.json()) == 2
