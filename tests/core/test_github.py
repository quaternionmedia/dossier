"""Tests for GitHub parser functionality."""

import base64
import pytest
import respx
from httpx import Response
from sqlmodel import Session, select

from dossier.parsers.github import (
    GitHubClient,
    GitHubParser,
    GitHubRepo,
    sync_github_repo,
    RateLimitInfo,
    BatchResult,
)
from dossier.models import DocumentationLevel, DocumentSection, Project


class TestGitHubRepo:
    """Tests for GitHubRepo class."""
    
    def test_full_name(self):
        """Test full_name property."""
        repo = GitHubRepo(owner="microsoft", name="vscode")
        assert repo.full_name == "microsoft/vscode"
    
    def test_from_url_https(self):
        """Test parsing HTTPS URL."""
        repo = GitHubRepo.from_url("https://github.com/fastapi/fastapi")
        assert repo.owner == "fastapi"
        assert repo.name == "fastapi"
    
    def test_from_url_https_with_git_suffix(self):
        """Test parsing HTTPS URL with .git suffix."""
        repo = GitHubRepo.from_url("https://github.com/pallets/click.git")
        assert repo.owner == "pallets"
        assert repo.name == "click"
    
    def test_from_url_ssh(self):
        """Test parsing SSH URL."""
        repo = GitHubRepo.from_url("git@github.com:tiangolo/sqlmodel.git")
        assert repo.owner == "tiangolo"
        assert repo.name == "sqlmodel"
    
    def test_from_url_invalid(self):
        """Test parsing invalid URL raises error."""
        with pytest.raises(ValueError, match="Unable to parse"):
            GitHubRepo.from_url("not-a-github-url")
    
    def test_from_url_shorthand(self):
        """Test parsing owner/repo shorthand."""
        repo = GitHubRepo.from_url("owner/repo")
        assert repo.owner == "owner"
        assert repo.name == "repo"


class TestRateLimitInfo:
    """Tests for RateLimitInfo dataclass."""
    
    def test_is_exhausted_true(self):
        """Test rate limit is exhausted when remaining is 0."""
        info = RateLimitInfo(limit=5000, remaining=0, reset_at=9999999999)
        assert info.is_exhausted is True
    
    def test_is_exhausted_false(self):
        """Test rate limit is not exhausted when remaining > 0."""
        info = RateLimitInfo(limit=5000, remaining=100, reset_at=9999999999)
        assert info.is_exhausted is False
    
    def test_seconds_until_reset(self):
        """Test seconds until reset calculation."""
        import time
        future_time = int(time.time()) + 60
        info = RateLimitInfo(limit=5000, remaining=0, reset_at=future_time)
        # Should be approximately 60 seconds (allow for test execution time)
        assert 55 <= info.seconds_until_reset <= 65


class TestBatchResult:
    """Tests for BatchResult dataclass."""
    
    def test_empty_batch_result(self):
        """Test empty batch result."""
        result = BatchResult()
        assert result.synced == []
        assert result.failed == []
        assert result.skipped == []
        assert result.rate_limited is False
    
    def test_batch_result_with_data(self):
        """Test batch result with data."""
        result = BatchResult(
            synced=["repo1", "repo2"],
            failed=["repo3"],
            skipped=["repo4"],
            rate_limited=True,
        )
        assert len(result.synced) == 2
        assert len(result.failed) == 1
        assert len(result.skipped) == 1
        assert result.rate_limited is True


class TestGitHubClient:
    """Tests for GitHubClient class."""
    
    def test_init_without_token(self):
        """Test client initialization without token."""
        client = GitHubClient()
        assert client.token is None
        client.close()
    
    def test_init_with_token(self):
        """Test client initialization with token."""
        client = GitHubClient(token="test-token")
        assert client.token == "test-token"
        client.close()
    
    def test_init_with_retry_config(self):
        """Test client initialization with retry config."""
        client = GitHubClient(max_retries=5, retry_delay=2.0)
        assert client.max_retries == 5
        assert client.retry_delay == 2.0
        client.close()
    
    def test_context_manager(self):
        """Test client as context manager."""
        with GitHubClient() as client:
            assert isinstance(client, GitHubClient)
    
    @respx.mock
    def test_get_repo(self):
        """Test fetching repository info."""
        respx.get("https://api.github.com/repos/fastapi/fastapi").mock(
            return_value=Response(
                200,
                json={
                    "owner": {"login": "fastapi"},
                    "name": "fastapi",
                    "description": "FastAPI framework",
                    "default_branch": "main",
                    "html_url": "https://github.com/fastapi/fastapi",
                    "topics": ["python", "api"],
                    "language": "Python",
                    "stargazers_count": 70000,
                },
                headers={
                    "x-ratelimit-remaining": "100",
                    "x-ratelimit-limit": "5000",
                    "x-ratelimit-reset": "0",
                },
            )
        )
        
        with GitHubClient() as client:
            repo = client.get_repo("fastapi", "fastapi")
        
        assert repo.owner == "fastapi"
        assert repo.name == "fastapi"
        assert repo.description == "FastAPI framework"
        assert repo.stars == 70000
    
    @respx.mock
    def test_get_readme(self):
        """Test fetching README content."""
        readme_content = "# My Project\n\nThis is a test project."
        encoded = base64.b64encode(readme_content.encode()).decode()
        
        respx.get("https://api.github.com/repos/owner/repo/readme").mock(
            return_value=Response(
                200,
                json={"content": encoded},
                headers={
                    "x-ratelimit-remaining": "100",
                    "x-ratelimit-limit": "5000",
                    "x-ratelimit-reset": "0",
                },
            )
        )
        
        with GitHubClient() as client:
            readme = client.get_readme("owner", "repo")
        
        assert readme == readme_content
    
    @respx.mock
    def test_get_readme_not_found(self):
        """Test fetching README when it doesn't exist."""
        respx.get("https://api.github.com/repos/owner/repo/readme").mock(
            return_value=Response(404)
        )
        
        with GitHubClient() as client:
            readme = client.get_readme("owner", "repo")
        
        assert readme is None
    
    @respx.mock
    def test_search_repos(self):
        """Test searching repositories."""
        respx.get("https://api.github.com/search/repositories").mock(
            return_value=Response(
                200,
                json={
                    "items": [
                        {
                            "owner": {"login": "owner1"},
                            "name": "repo1",
                            "description": "Test repo 1",
                            "default_branch": "main",
                            "html_url": "https://github.com/owner1/repo1",
                            "topics": ["test"],
                            "language": "Python",
                            "stargazers_count": 100,
                        },
                        {
                            "owner": {"login": "owner2"},
                            "name": "repo2",
                            "description": "Test repo 2",
                            "default_branch": "master",
                            "html_url": "https://github.com/owner2/repo2",
                            "topics": [],
                            "language": "JavaScript",
                            "stargazers_count": 50,
                        },
                    ]
                },
            )
        )
        
        with GitHubClient() as client:
            repos = client.search_repos("test")
        
        assert len(repos) == 2
        assert repos[0].owner == "owner1"
        assert repos[1].owner == "owner2"
    
    @respx.mock
    def test_check_rate_limit(self):
        """Test checking rate limit status."""
        respx.get("https://api.github.com/rate_limit").mock(
            return_value=Response(
                200,
                json={
                    "resources": {
                        "core": {
                            "limit": 5000,
                            "remaining": 4500,
                            "reset": 1234567890,
                        }
                    }
                },
            )
        )
        
        with GitHubClient() as client:
            rate_info = client.check_rate_limit()
        
        assert rate_info.limit == 5000
        assert rate_info.remaining == 4500
        assert rate_info.reset_at == 1234567890
    
    @respx.mock
    def test_list_user_repos(self):
        """Test listing user repositories."""
        respx.get("https://api.github.com/users/testuser/repos").mock(
            return_value=Response(
                200,
                json=[
                    {
                        "owner": {"login": "testuser"},
                        "name": "repo1",
                        "description": "User repo 1",
                        "default_branch": "main",
                        "html_url": "https://github.com/testuser/repo1",
                        "topics": [],
                        "language": "Python",
                        "stargazers_count": 10,
                    },
                ],
            )
        )
        
        with GitHubClient() as client:
            repos = client.list_user_repos("testuser")
        
        assert len(repos) == 1
        assert repos[0].owner == "testuser"
        assert repos[0].name == "repo1"


class TestGitHubParser:
    """Tests for GitHubParser class."""
    
    def test_init(self):
        """Test parser initialization."""
        parser = GitHubParser()
        assert parser.markdown_parser is not None
        parser.close()
    
    def test_context_manager(self):
        """Test parser as context manager."""
        with GitHubParser() as parser:
            assert isinstance(parser, GitHubParser)
    
    @respx.mock
    def test_parse_repo(self):
        """Test parsing repository documentation."""
        # Mock repo info
        respx.get("https://api.github.com/repos/test/repo").mock(
            return_value=Response(
                200,
                json={
                    "owner": {"login": "test"},
                    "name": "repo",
                    "description": "Test repository",
                    "default_branch": "main",
                    "html_url": "https://github.com/test/repo",
                    "topics": [],
                    "language": "Python",
                    "stargazers_count": 100,
                },
                headers={
                    "x-ratelimit-remaining": "100",
                    "x-ratelimit-limit": "5000",
                    "x-ratelimit-reset": "0",
                },
            )
        )
        
        # Mock readme
        readme_content = "# Test Repo\n\nThis is a test.\n\n## Installation\n\nRun `pip install`."
        encoded = base64.b64encode(readme_content.encode()).decode()
        respx.get("https://api.github.com/repos/test/repo/readme").mock(
            return_value=Response(
                200,
                json={"content": encoded},
                headers={
                    "x-ratelimit-remaining": "99",
                    "x-ratelimit-limit": "5000",
                    "x-ratelimit-reset": "0",
                },
            )
        )
        
        # Mock docs listing (empty) - both paths that list_docs_files checks
        respx.get("https://api.github.com/repos/test/repo/contents/docs").mock(
            return_value=Response(404)
        )
        respx.get("https://api.github.com/repos/test/repo/contents/").mock(
            return_value=Response(
                200,
                json=[],  # Empty root directory
                headers={
                    "x-ratelimit-remaining": "98",
                    "x-ratelimit-limit": "5000",
                    "x-ratelimit-reset": "0",
                },
            )
        )
        
        with GitHubParser() as parser:
            repo, sections = parser.parse_repo("test", "repo", project_id=1)
        
        assert repo.owner == "test"
        assert repo.name == "repo"
        assert len(sections) >= 1
        assert sections[0].project_id == 1
    
    @respx.mock
    def test_parse_repo_url(self):
        """Test parsing repository from URL."""
        # Mock repo info
        respx.get("https://api.github.com/repos/fastapi/fastapi").mock(
            return_value=Response(
                200,
                json={
                    "owner": {"login": "fastapi"},
                    "name": "fastapi",
                    "description": "FastAPI framework",
                    "default_branch": "main",
                    "html_url": "https://github.com/fastapi/fastapi",
                    "topics": ["python"],
                    "language": "Python",
                    "stargazers_count": 70000,
                },
                headers={
                    "x-ratelimit-remaining": "100",
                    "x-ratelimit-limit": "5000",
                    "x-ratelimit-reset": "0",
                },
            )
        )
        
        # Mock readme
        readme_content = "# FastAPI\n\nFast API framework."
        encoded = base64.b64encode(readme_content.encode()).decode()
        respx.get("https://api.github.com/repos/fastapi/fastapi/readme").mock(
            return_value=Response(
                200,
                json={"content": encoded},
                headers={
                    "x-ratelimit-remaining": "99",
                    "x-ratelimit-limit": "5000",
                    "x-ratelimit-reset": "0",
                },
            )
        )
        
        # Mock docs listing - both paths
        respx.get("https://api.github.com/repos/fastapi/fastapi/contents/docs").mock(
            return_value=Response(404)
        )
        respx.get("https://api.github.com/repos/fastapi/fastapi/contents/").mock(
            return_value=Response(
                200,
                json=[],
                headers={
                    "x-ratelimit-remaining": "98",
                    "x-ratelimit-limit": "5000",
                    "x-ratelimit-reset": "0",
                },
            )
        )
        
        with GitHubParser() as parser:
            repo, sections = parser.parse_repo_url(
                "https://github.com/fastapi/fastapi"
            )
        
        assert repo.owner == "fastapi"
        assert repo.name == "fastapi"
        assert len(sections) >= 1


class TestSyncGitHubRepo:
    """Tests for sync_github_repo convenience function."""
    
    @respx.mock
    def test_sync_github_repo(self):
        """Test sync convenience function."""
        # Mock repo info
        respx.get("https://api.github.com/repos/test/repo").mock(
            return_value=Response(
                200,
                json={
                    "owner": {"login": "test"},
                    "name": "repo",
                    "description": "Test repo",
                    "default_branch": "main",
                    "html_url": "https://github.com/test/repo",
                    "topics": [],
                    "language": "Python",
                    "stargazers_count": 100,
                },
                headers={
                    "x-ratelimit-remaining": "100",
                    "x-ratelimit-limit": "5000",
                    "x-ratelimit-reset": "0",
                },
            )
        )
        
        # Mock readme
        readme_content = "# Test\n\nTest content."
        encoded = base64.b64encode(readme_content.encode()).decode()
        respx.get("https://api.github.com/repos/test/repo/readme").mock(
            return_value=Response(
                200,
                json={"content": encoded},
                headers={
                    "x-ratelimit-remaining": "99",
                    "x-ratelimit-limit": "5000",
                    "x-ratelimit-reset": "0",
                },
            )
        )
        
        # Mock docs listing - both paths
        respx.get("https://api.github.com/repos/test/repo/contents/docs").mock(
            return_value=Response(404)
        )
        respx.get("https://api.github.com/repos/test/repo/contents/").mock(
            return_value=Response(
                200,
                json=[],
                headers={
                    "x-ratelimit-remaining": "98",
                    "x-ratelimit-limit": "5000",
                    "x-ratelimit-reset": "0",
                },
            )
        )
        
        repo, sections = sync_github_repo("https://github.com/test/repo")
        
        assert repo.owner == "test"
        assert repo.name == "repo"


class TestGitHubIntegration:
    """Integration tests with real database."""
    
    def test_project_creation_from_github_data(self, test_session: Session):
        """Test creating a project from parsed GitHub data."""
        # Simulate data that would come from GitHub parser
        github_repo = GitHubRepo(
            owner="test",
            name="integration-repo",
            description="Integration test repo",
            html_url="https://github.com/test/integration-repo",
            language="Python",
            stars=500,
        )
        
        # Create project from GitHub data
        project = Project(
            name=github_repo.full_name,
            description=github_repo.description,
            repository_url=github_repo.html_url,
            github_owner=github_repo.owner,
            github_repo=github_repo.name,
            github_stars=github_repo.stars,
            github_language=github_repo.language,
        )
        
        test_session.add(project)
        test_session.commit()
        test_session.refresh(project)
        
        # Verify in database
        db_project = test_session.get(Project, project.id)
        assert db_project is not None
        assert db_project.name == "test/integration-repo"
        assert db_project.github_stars == 500
    
    def test_document_sections_creation(self, test_session: Session):
        """Test creating document sections from parsed content."""
        # Create project first
        project = Project(name="test/docs-project")
        test_session.add(project)
        test_session.commit()
        test_session.refresh(project)
        
        # Create sections like the parser would
        sections = [
            DocumentSection(
                project_id=project.id,
                title="README",
                content="# Test\n\nTest content.",
                level=DocumentationLevel.OVERVIEW,
                section_type="readme",
                source_file="README.md",
                order=0,
            ),
            DocumentSection(
                project_id=project.id,
                title="Installation",
                content="```pip install test```",
                level=DocumentationLevel.DETAILED,
                section_type="setup",
                source_file="README.md",
                order=1,
            ),
        ]
        
        for section in sections:
            test_session.add(section)
        test_session.commit()
        
        # Verify in database
        db_sections = test_session.exec(
            select(DocumentSection).where(DocumentSection.project_id == project.id)
        ).all()
        assert len(db_sections) == 2
        assert db_sections[0].title == "README"
        assert db_sections[1].title == "Installation"
    
    def test_query_seeded_projects(self, seeded_session: Session):
        """Test querying pre-seeded projects."""
        # Query all projects
        projects = seeded_session.exec(select(Project)).all()
        assert len(projects) == 3
        
        # Find specific project
        fastapi = seeded_session.exec(
            select(Project).where(Project.github_owner == "fastapi")
        ).first()
        assert fastapi is not None
        assert fastapi.github_stars == 70000
    
    def test_query_seeded_sections(self, seeded_session: Session):
        """Test querying pre-seeded document sections."""
        # Get FastAPI project
        fastapi = seeded_session.exec(
            select(Project).where(Project.name == "test/fastapi")
        ).first()
        
        # Query its sections
        sections = seeded_session.exec(
            select(DocumentSection).where(DocumentSection.project_id == fastapi.id)
        ).all()
        
        assert len(sections) == 2
        assert any(s.section_type == "readme" for s in sections)
        assert any(s.section_type == "setup" for s in sections)
    
    def test_project_update_on_sync(self, test_session: Session):
        """Test updating project data on re-sync."""
        from datetime import datetime, timezone
        
        # Create initial project
        project = Project(
            name="test/sync-project",
            github_owner="test",
            github_repo="sync-project",
            github_stars=100,
        )
        test_session.add(project)
        test_session.commit()
        test_session.refresh(project)
        
        original_id = project.id
        
        # Simulate re-sync with updated data
        project.github_stars = 150
        project.last_synced_at = datetime.now(timezone.utc)
        test_session.add(project)
        test_session.commit()
        
        # Verify update
        db_project = test_session.get(Project, original_id)
        assert db_project.github_stars == 150
        assert db_project.last_synced_at is not None
    
    def test_unsynced_projects_query(self, seeded_session: Session):
        """Test finding projects that need syncing."""
        # Find projects without last_synced_at
        unsynced = seeded_session.exec(
            select(Project).where(Project.last_synced_at == None)  # noqa: E711
        ).all()
        
        assert len(unsynced) == 1
        assert unsynced[0].github_repo == "unsynced-repo"
