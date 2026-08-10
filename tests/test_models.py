"""Tests for Dossier data models."""

import pytest
from dossier.models import (
    DeltaLink,
    DeltaNote,
    DeltaPhase,
    DocumentationLevel,
    DocumentSection,
    DocumentationQuery,
    DocumentationResponse,
    Project,
    ProjectDelta,
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


class TestDeltaPhase:
    """Tests for DeltaPhase enum."""

    def test_phase_values(self) -> None:
        """Test that all delta phases are defined."""
        assert DeltaPhase.BRAINSTORM == "brainstorm"
        assert DeltaPhase.PLANNING == "planning"
        assert DeltaPhase.IMPLEMENTATION == "implementation"
        assert DeltaPhase.REVIEW == "review"
        assert DeltaPhase.DOCUMENTATION == "documentation"
        assert DeltaPhase.COMPLETE == "complete"
        assert DeltaPhase.ABANDONED == "abandoned"

    def test_phase_count(self) -> None:
        """Test all phases are present."""
        phases = list(DeltaPhase)
        assert len(phases) == 7


class TestProjectDelta:
    """Tests for ProjectDelta model."""

    def test_delta_creation(self) -> None:
        """Test creating a delta."""
        delta = ProjectDelta(
            project_id=1,
            name="add-feature",
            title="Add new feature",
            description="Implement a new feature",
        )
        assert delta.project_id == 1
        assert delta.name == "add-feature"
        assert delta.title == "Add new feature"
        assert delta.description == "Implement a new feature"

    def test_delta_defaults(self) -> None:
        """Test delta has appropriate defaults."""
        delta = ProjectDelta(
            project_id=1,
            name="test-delta",
            title="Test Delta",
        )
        assert delta.id is None
        assert delta.phase == DeltaPhase.BRAINSTORM
        assert delta.priority == "medium"
        assert delta.delta_type == "feature"
        assert delta.started_at is None
        assert delta.completed_at is None
        assert delta.issue_number is None
        assert delta.pr_number is None
        assert delta.branch_name is None

    def test_phase_order(self) -> None:
        """Test PHASE_ORDER constant is correct."""
        assert ProjectDelta.PHASE_ORDER == [
            DeltaPhase.BRAINSTORM,
            DeltaPhase.PLANNING,
            DeltaPhase.IMPLEMENTATION,
            DeltaPhase.REVIEW,
            DeltaPhase.DOCUMENTATION,
            DeltaPhase.COMPLETE,
        ]

    def test_can_advance_from_brainstorm(self) -> None:
        """Test can_advance returns True from initial phase."""
        delta = ProjectDelta(project_id=1, name="test", title="Test")
        assert delta.phase == DeltaPhase.BRAINSTORM
        assert delta.can_advance() is True

    def test_can_advance_from_complete(self) -> None:
        """Test can_advance returns False from complete phase."""
        delta = ProjectDelta(project_id=1, name="test", title="Test")
        delta.phase = DeltaPhase.COMPLETE
        assert delta.can_advance() is False

    def test_can_advance_from_abandoned(self) -> None:
        """Test can_advance returns False from abandoned phase."""
        delta = ProjectDelta(project_id=1, name="test", title="Test")
        delta.phase = DeltaPhase.ABANDONED
        assert delta.can_advance() is False

    def test_advance_phase_sequence(self) -> None:
        """Test advancing through all phases."""
        delta = ProjectDelta(project_id=1, name="test", title="Test")

        # Brainstorm -> Planning
        assert delta.phase == DeltaPhase.BRAINSTORM
        assert delta.advance_phase() is True
        assert delta.phase == DeltaPhase.PLANNING

        # Planning -> Implementation
        assert delta.advance_phase() is True
        assert delta.phase == DeltaPhase.IMPLEMENTATION
        assert delta.started_at is not None  # Should be set

        # Implementation -> Review
        assert delta.advance_phase() is True
        assert delta.phase == DeltaPhase.REVIEW

        # Review -> Documentation
        assert delta.advance_phase() is True
        assert delta.phase == DeltaPhase.DOCUMENTATION

        # Documentation -> Complete
        assert delta.advance_phase() is True
        assert delta.phase == DeltaPhase.COMPLETE
        assert delta.completed_at is not None  # Should be set

        # Cannot advance past complete
        assert delta.advance_phase() is False
        assert delta.phase == DeltaPhase.COMPLETE

    def test_advance_phase_sets_timestamps(self) -> None:
        """Test that advance_phase sets appropriate timestamps."""
        delta = ProjectDelta(project_id=1, name="test", title="Test")
        original_phase_changed_at = delta.phase_changed_at

        delta.advance_phase()

        # phase_changed_at and updated_at should be updated
        assert delta.phase_changed_at >= original_phase_changed_at
        assert delta.updated_at >= original_phase_changed_at

    def test_advance_phase_sets_started_at(self) -> None:
        """Test that started_at is set when entering implementation."""
        delta = ProjectDelta(project_id=1, name="test", title="Test")
        assert delta.started_at is None

        # Advance to planning
        delta.advance_phase()
        assert delta.started_at is None

        # Advance to implementation
        delta.advance_phase()
        assert delta.started_at is not None

    def test_advance_phase_sets_completed_at(self) -> None:
        """Test that completed_at is set when entering complete."""
        delta = ProjectDelta(project_id=1, name="test", title="Test")
        delta.phase = DeltaPhase.DOCUMENTATION
        assert delta.completed_at is None

        delta.advance_phase()
        assert delta.phase == DeltaPhase.COMPLETE
        assert delta.completed_at is not None

    def test_advance_phase_from_abandoned(self) -> None:
        """Test that abandoned deltas cannot advance."""
        delta = ProjectDelta(project_id=1, name="test", title="Test")
        delta.phase = DeltaPhase.ABANDONED

        assert delta.advance_phase() is False
        assert delta.phase == DeltaPhase.ABANDONED

    def test_delta_with_github_links(self) -> None:
        """Test delta with GitHub entity links."""
        delta = ProjectDelta(
            project_id=1,
            name="fix-bug",
            title="Fix critical bug",
            issue_number=123,
            pr_number=456,
            branch_name="fix/critical-bug",
        )
        assert delta.issue_number == 123
        assert delta.pr_number == 456
        assert delta.branch_name == "fix/critical-bug"


class TestDeltaNote:
    """Tests for DeltaNote model."""

    def test_note_creation(self) -> None:
        """Test creating a delta note."""
        note = DeltaNote(
            delta_id=1,
            phase=DeltaPhase.PLANNING,
            content="Design document completed.",
        )
        assert note.delta_id == 1
        assert note.phase == DeltaPhase.PLANNING
        assert note.content == "Design document completed."

    def test_note_defaults(self) -> None:
        """Test note has appropriate defaults."""
        note = DeltaNote(
            delta_id=1,
            phase=DeltaPhase.BRAINSTORM,
            content="Initial ideas",
        )
        assert note.id is None
        assert note.created_at is not None


class TestDeltaLink:
    """Tests for DeltaLink model."""

    def test_link_creation_issue(self) -> None:
        """Test creating an issue link."""
        link = DeltaLink(
            delta_id=1,
            link_type="issue",
            target_id=123,
        )
        assert link.delta_id == 1
        assert link.link_type == "issue"
        assert link.target_id == 123
        assert link.target_name is None

    def test_link_creation_branch(self) -> None:
        """Test creating a branch link."""
        link = DeltaLink(
            delta_id=1,
            link_type="branch",
            target_name="feature/new-feature",
        )
        assert link.delta_id == 1
        assert link.link_type == "branch"
        assert link.target_id is None
        assert link.target_name == "feature/new-feature"

    def test_link_creation_delta(self) -> None:
        """Test creating a delta-to-delta link."""
        link = DeltaLink(
            delta_id=1,
            link_type="delta",
            target_id=2,
            target_name="related-delta",
        )
        assert link.link_type == "delta"
        assert link.target_id == 2
        assert link.target_name == "related-delta"

    def test_link_defaults(self) -> None:
        """Test link has appropriate defaults."""
        link = DeltaLink(
            delta_id=1,
            link_type="pr",
            target_id=456,
        )
        assert link.id is None
        assert link.created_at is not None
