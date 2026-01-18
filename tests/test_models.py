"""Tests for Dossier data models."""

import pytest
from dossier.models import (
    DocumentationLevel,
    DocumentSection,
    DocumentationQuery,
    DocumentationResponse,
    Project,
)


class TestDocumentationLevel:
    """Tests for DocumentationLevel enum."""

    def test_level_values(self) -> None:
        """Test that all documentation levels are defined."""
        assert DocumentationLevel.SUMMARY == "summary"
        assert DocumentationLevel.OVERVIEW == "overview"
        assert DocumentationLevel.DETAILED == "detailed"
        assert DocumentationLevel.TECHNICAL == "technical"

    def test_level_ordering(self) -> None:
        """Test documentation levels can be compared."""
        levels = list(DocumentationLevel)
        assert len(levels) == 4


class TestProject:
    """Tests for Project model."""

    def test_project_creation(self) -> None:
        """Test creating a project."""
        project = Project(
            name="test-project",
            description="A test project",
            repository_url="https://github.com/example/test",
        )
        assert project.name == "test-project"
        assert project.description == "A test project"
        assert project.repository_url == "https://github.com/example/test"

    def test_project_defaults(self) -> None:
        """Test project has appropriate defaults."""
        project = Project(name="test-minimal")
        assert project.id is None
        assert project.description is None
        assert project.documentation_path is None


class TestDocumentSection:
    """Tests for DocumentSection model."""

    def test_section_creation(self) -> None:
        """Test creating a document section."""
        section = DocumentSection(
            project_id=1,
            title="Getting Started",
            content="This is the getting started guide.",
            level=DocumentationLevel.OVERVIEW,
            section_type="setup",
        )
        assert section.title == "Getting Started"
        assert section.level == DocumentationLevel.OVERVIEW
        assert section.section_type == "setup"

    def test_section_defaults(self) -> None:
        """Test section has appropriate defaults."""
        section = DocumentSection(
            project_id=1,
            title="Test",
            content="Content",
        )
        assert section.level == DocumentationLevel.DETAILED
        assert section.section_type == "general"
        assert section.order == 0


class TestDocumentationQuery:
    """Tests for DocumentationQuery model."""

    def test_query_defaults(self) -> None:
        """Test query has appropriate defaults."""
        query = DocumentationQuery()
        assert query.project_name is None
        assert query.level == DocumentationLevel.OVERVIEW
        assert query.section_type is None
        assert query.search_term is None

    def test_query_with_params(self) -> None:
        """Test query with all parameters."""
        query = DocumentationQuery(
            project_name="test-project",
            level=DocumentationLevel.TECHNICAL,
            section_type="api",
            search_term="endpoint",
        )
        assert query.project_name == "test-project"
        assert query.level == DocumentationLevel.TECHNICAL


class TestDocumentationResponse:
    """Tests for DocumentationResponse model."""

    def test_response_creation(self) -> None:
        """Test creating a response."""
        response = DocumentationResponse(
            project_name="test-project",
            level=DocumentationLevel.OVERVIEW,
            sections=[{"title": "Test", "content": "Content"}],
            total_sections=1,
            query_time_ms=5.2,
        )
        assert response.project_name == "test-project"
        assert len(response.sections) == 1
        assert response.total_sections == 1
