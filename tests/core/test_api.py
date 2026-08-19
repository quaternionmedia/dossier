"""Tests for Dossier API."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import dossier.api.main as api_main
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
    
    # Override the module's engine and session
    original_engine = api_main.engine
    original_get_session = api_main.get_session
    
    api_main.engine = test_engine
    
    def get_test_session() -> Session:
        return Session(test_engine)
    
    api_main.get_session = get_test_session
    
    with TestClient(app) as client:
        yield client
    
    # Restore originals
    api_main.engine = original_engine
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
