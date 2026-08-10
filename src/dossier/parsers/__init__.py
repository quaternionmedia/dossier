"""Documentation parsers for Dossier."""

from .autolinker import AutoLinker, LinkStats
from .base import BaseParser, MarkdownParser, ParserRegistry
from .github import (
    BatchResult,
    GitHubClient,
    GitHubParser,
    GitHubRepo,
    RateLimitInfo,
    sync_github_repo,
)
from .governance import (
    DocumentUnavailable,
    GovernanceDocument,
    HarnessDocument,
    load_governance,
    load_harness,
)

__all__ = [
    "AutoLinker",
    "BaseParser",
    "BatchResult",
    "DocumentUnavailable",
    "GitHubClient",
    "GitHubParser",
    "GitHubRepo",
    "GovernanceDocument",
    "HarnessDocument",
    "LinkStats",
    "load_governance",
    "load_harness",
    "MarkdownParser",
    "ParserRegistry",
    "RateLimitInfo",
    "sync_github_repo",
]
