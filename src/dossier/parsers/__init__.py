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

__all__ = [
    "AutoLinker",
    "BaseParser",
    "BatchResult",
    "GitHubClient",
    "GitHubParser",
    "GitHubRepo",
    "LinkStats",
    "MarkdownParser",
    "ParserRegistry",
    "RateLimitInfo",
    "sync_github_repo",
]
