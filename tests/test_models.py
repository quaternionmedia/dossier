"""Tests for Dossier data models."""

import pytest
from dossier.models import (
    DocumentationLevel,
    DocumentSection,
    DocumentationQuery,
    DocumentationResponse,
    Project,
    ProjectVersion,
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


class TestProjectVersion:
    """Tests for ProjectVersion model and semver parsing."""

    def test_parse_simple_version(self) -> None:
        """Test parsing a simple semver string."""
        parsed = ProjectVersion.parse_version("1.2.3")
        assert parsed["major"] == 1
        assert parsed["minor"] == 2
        assert parsed["patch"] == 3
        assert parsed["prerelease"] is None
        assert parsed["build_metadata"] is None

    def test_parse_version_with_v_prefix(self) -> None:
        """Test parsing version with 'v' prefix."""
        parsed = ProjectVersion.parse_version("v1.2.3")
        assert parsed["major"] == 1
        assert parsed["minor"] == 2
        assert parsed["patch"] == 3

    def test_parse_version_with_prerelease(self) -> None:
        """Test parsing version with prerelease identifier."""
        parsed = ProjectVersion.parse_version("1.0.0-alpha.1")
        assert parsed["major"] == 1
        assert parsed["minor"] == 0
        assert parsed["patch"] == 0
        assert parsed["prerelease"] == "alpha.1"

    def test_parse_version_with_build_metadata(self) -> None:
        """Test parsing version with build metadata."""
        parsed = ProjectVersion.parse_version("1.0.0+build.123")
        assert parsed["major"] == 1
        assert parsed["minor"] == 0
        assert parsed["patch"] == 0
        assert parsed["build_metadata"] == "build.123"

    def test_parse_full_semver(self) -> None:
        """Test parsing full semver with prerelease and build."""
        parsed = ProjectVersion.parse_version("v2.1.0-beta.2+20260117")
        assert parsed["major"] == 2
        assert parsed["minor"] == 1
        assert parsed["patch"] == 0
        assert parsed["prerelease"] == "beta.2"
        assert parsed["build_metadata"] == "20260117"

    def test_parse_version_major_only(self) -> None:
        """Test parsing version with only major number."""
        parsed = ProjectVersion.parse_version("5")
        assert parsed["major"] == 5
        assert parsed["minor"] == 0
        assert parsed["patch"] == 0

    def test_parse_version_major_minor_only(self) -> None:
        """Test parsing version with only major.minor."""
        parsed = ProjectVersion.parse_version("3.14")
        assert parsed["major"] == 3
        assert parsed["minor"] == 14
        assert parsed["patch"] == 0

    def test_from_version_string(self) -> None:
        """Test creating ProjectVersion from version string."""
        version = ProjectVersion.from_version_string(
            project_id=1,
            version_str="v1.2.3-rc.1",
            source="release",
            is_latest=True,
        )
        assert version.project_id == 1
        assert version.version == "v1.2.3-rc.1"
        assert version.major == 1
        assert version.minor == 2
        assert version.patch == 3
        assert version.prerelease == "rc.1"
        assert version.source == "release"
        assert version.is_latest is True

    def test_version_creation(self) -> None:
        """Test creating a project version directly."""
        version = ProjectVersion(
            project_id=1,
            version="2.0.0",
            major=2,
            minor=0,
            patch=0,
            source="pyproject",
        )
        assert version.version == "2.0.0"
        assert version.major == 2
        assert version.is_latest is False  # default

    def test_version_defaults(self) -> None:
        """Test version has appropriate defaults."""
        version = ProjectVersion(
            project_id=1,
            version="1.0.0",
        )
        assert version.major == 0  # needs explicit set or from_version_string
        assert version.minor == 0
        assert version.patch == 0
        assert version.prerelease is None
        assert version.build_metadata is None
        assert version.source == "release"
        assert version.is_latest is False
        assert version.release_url is None
        assert version.changelog_url is None
