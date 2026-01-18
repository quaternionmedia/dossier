"""GitHub repository parser for Dossier.

This module provides functionality to:
- Fetch repository information from GitHub API
- Clone/sync repositories locally
- Parse documentation from GitHub repos
- Intelligent batching with retry and rate limit handling
"""

import base64
import re
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Callable, TypeVar, Generator
from urllib.parse import urlparse

import httpx

from dossier.models import DocumentationLevel, DocumentSection
from dossier.parsers.base import MarkdownParser


T = TypeVar("T")


@dataclass
class RateLimitInfo:
    """GitHub API rate limit information."""
    
    limit: int = 60
    remaining: int = 60
    reset_at: float = 0.0
    
    @classmethod
    def from_headers(cls, headers: httpx.Headers) -> "RateLimitInfo":
        """Parse rate limit info from response headers."""
        return cls(
            limit=int(headers.get("x-ratelimit-limit", 60)),
            remaining=int(headers.get("x-ratelimit-remaining", 60)),
            reset_at=float(headers.get("x-ratelimit-reset", 0)),
        )
    
    @property
    def is_exhausted(self) -> bool:
        """Check if rate limit is exhausted."""
        return self.remaining <= 0
    
    @property
    def seconds_until_reset(self) -> float:
        """Seconds until rate limit resets."""
        return max(0, self.reset_at - time.time())


@dataclass
class BatchResult:
    """Result of a batch sync operation."""
    
    synced: list[str] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)  # (name, error)
    skipped: list[str] = field(default_factory=list)
    rate_limited: bool = False
    
    @property
    def total_processed(self) -> int:
        return len(self.synced) + len(self.failed) + len(self.skipped)
    
    def __str__(self) -> str:
        parts = [f"Synced: {len(self.synced)}"]
        if self.failed:
            parts.append(f"Failed: {len(self.failed)}")
        if self.skipped:
            parts.append(f"Skipped: {len(self.skipped)}")
        if self.rate_limited:
            parts.append("(rate limited)")
        return " | ".join(parts)


# Language to file extensions/encoding mapping (based on GitHub Linguist)
LANGUAGE_INFO: dict[str, dict[str, str]] = {
    "Python": {"extensions": ".py, .pyw, .pyi, .pyx", "encoding": "UTF-8"},
    "JavaScript": {"extensions": ".js, .mjs, .cjs, .jsx", "encoding": "UTF-8"},
    "TypeScript": {"extensions": ".ts, .tsx, .mts, .cts", "encoding": "UTF-8"},
    "Java": {"extensions": ".java", "encoding": "UTF-8"},
    "C": {"extensions": ".c, .h", "encoding": "UTF-8"},
    "C++": {"extensions": ".cpp, .cc, .cxx, .hpp, .hh, .h", "encoding": "UTF-8"},
    "C#": {"extensions": ".cs, .csx", "encoding": "UTF-8"},
    "Go": {"extensions": ".go", "encoding": "UTF-8"},
    "Rust": {"extensions": ".rs", "encoding": "UTF-8"},
    "Ruby": {"extensions": ".rb, .rbw, .rake, .gemspec", "encoding": "UTF-8"},
    "PHP": {"extensions": ".php, .phtml, .php3, .php4, .php5", "encoding": "UTF-8"},
    "Swift": {"extensions": ".swift", "encoding": "UTF-8"},
    "Kotlin": {"extensions": ".kt, .kts", "encoding": "UTF-8"},
    "Scala": {"extensions": ".scala, .sc", "encoding": "UTF-8"},
    "Shell": {"extensions": ".sh, .bash, .zsh, .fish", "encoding": "UTF-8"},
    "PowerShell": {"extensions": ".ps1, .psm1, .psd1", "encoding": "UTF-8"},
    "Perl": {"extensions": ".pl, .pm, .pod, .t", "encoding": "UTF-8"},
    "R": {"extensions": ".r, .R, .Rmd", "encoding": "UTF-8"},
    "Lua": {"extensions": ".lua", "encoding": "UTF-8"},
    "Dart": {"extensions": ".dart", "encoding": "UTF-8"},
    "Elixir": {"extensions": ".ex, .exs", "encoding": "UTF-8"},
    "Erlang": {"extensions": ".erl, .hrl", "encoding": "UTF-8"},
    "Haskell": {"extensions": ".hs, .lhs", "encoding": "UTF-8"},
    "Clojure": {"extensions": ".clj, .cljs, .cljc, .edn", "encoding": "UTF-8"},
    "F#": {"extensions": ".fs, .fsi, .fsx", "encoding": "UTF-8"},
    "OCaml": {"extensions": ".ml, .mli", "encoding": "UTF-8"},
    "Julia": {"extensions": ".jl", "encoding": "UTF-8"},
    "Nim": {"extensions": ".nim, .nims", "encoding": "UTF-8"},
    "Zig": {"extensions": ".zig", "encoding": "UTF-8"},
    "V": {"extensions": ".v", "encoding": "UTF-8"},
    "Crystal": {"extensions": ".cr", "encoding": "UTF-8"},
    "HTML": {"extensions": ".html, .htm, .xhtml", "encoding": "UTF-8"},
    "CSS": {"extensions": ".css", "encoding": "UTF-8"},
    "SCSS": {"extensions": ".scss", "encoding": "UTF-8"},
    "Sass": {"extensions": ".sass", "encoding": "UTF-8"},
    "Less": {"extensions": ".less", "encoding": "UTF-8"},
    "Vue": {"extensions": ".vue", "encoding": "UTF-8"},
    "Svelte": {"extensions": ".svelte", "encoding": "UTF-8"},
    "Astro": {"extensions": ".astro", "encoding": "UTF-8"},
    "JSON": {"extensions": ".json, .jsonc", "encoding": "UTF-8"},
    "YAML": {"extensions": ".yml, .yaml", "encoding": "UTF-8"},
    "TOML": {"extensions": ".toml", "encoding": "UTF-8"},
    "XML": {"extensions": ".xml, .xsd, .xsl", "encoding": "UTF-8"},
    "Markdown": {"extensions": ".md, .markdown, .mdown", "encoding": "UTF-8"},
    "reStructuredText": {"extensions": ".rst", "encoding": "UTF-8"},
    "AsciiDoc": {"extensions": ".adoc, .asciidoc", "encoding": "UTF-8"},
    "TeX": {"extensions": ".tex, .sty, .cls", "encoding": "UTF-8"},
    "SQL": {"extensions": ".sql", "encoding": "UTF-8"},
    "GraphQL": {"extensions": ".graphql, .gql", "encoding": "UTF-8"},
    "Dockerfile": {"extensions": "Dockerfile", "encoding": "UTF-8"},
    "Makefile": {"extensions": "Makefile, .mk", "encoding": "UTF-8"},
    "CMake": {"extensions": "CMakeLists.txt, .cmake", "encoding": "UTF-8"},
    "Nix": {"extensions": ".nix", "encoding": "UTF-8"},
    "Terraform": {"extensions": ".tf, .tfvars", "encoding": "UTF-8"},
    "HCL": {"extensions": ".hcl", "encoding": "UTF-8"},
    "Jupyter Notebook": {"extensions": ".ipynb", "encoding": "UTF-8"},
    "Objective-C": {"extensions": ".m, .mm", "encoding": "UTF-8"},
    "Assembly": {"extensions": ".asm, .s", "encoding": "ASCII"},
    "WebAssembly": {"extensions": ".wat, .wasm", "encoding": "Binary"},
    "Batchfile": {"extensions": ".bat, .cmd", "encoding": "CP1252"},
    "Visual Basic": {"extensions": ".vb, .vbs", "encoding": "UTF-8"},
    "MATLAB": {"extensions": ".m, .mat", "encoding": "UTF-8"},
    "Fortran": {"extensions": ".f, .f90, .f95, .for", "encoding": "UTF-8"},
    "COBOL": {"extensions": ".cob, .cbl", "encoding": "EBCDIC/UTF-8"},
    "Groovy": {"extensions": ".groovy, .gvy", "encoding": "UTF-8"},
    "Tcl": {"extensions": ".tcl", "encoding": "UTF-8"},
    "Prolog": {"extensions": ".pl, .pro", "encoding": "UTF-8"},
    "Scheme": {"extensions": ".scm, .ss", "encoding": "UTF-8"},
    "Common Lisp": {"extensions": ".lisp, .lsp, .cl", "encoding": "UTF-8"},
    "Emacs Lisp": {"extensions": ".el", "encoding": "UTF-8"},
    "Vim Script": {"extensions": ".vim", "encoding": "UTF-8"},
    "Vimscript": {"extensions": ".vim", "encoding": "UTF-8"},
    "AWK": {"extensions": ".awk", "encoding": "UTF-8"},
    "Sed": {"extensions": ".sed", "encoding": "UTF-8"},
    "Protocol Buffer": {"extensions": ".proto", "encoding": "UTF-8"},
    "Thrift": {"extensions": ".thrift", "encoding": "UTF-8"},
    "Cap'n Proto": {"extensions": ".capnp", "encoding": "UTF-8"},
    "Roff": {"extensions": ".1, .2, .3, .man", "encoding": "UTF-8"},
    "Smarty": {"extensions": ".tpl", "encoding": "UTF-8"},
    "Jinja": {"extensions": ".j2, .jinja, .jinja2", "encoding": "UTF-8"},
    "Mako": {"extensions": ".mako", "encoding": "UTF-8"},
    "EJS": {"extensions": ".ejs", "encoding": "UTF-8"},
    "Pug": {"extensions": ".pug, .jade", "encoding": "UTF-8"},
    "Handlebars": {"extensions": ".hbs, .handlebars", "encoding": "UTF-8"},
    "Mustache": {"extensions": ".mustache", "encoding": "UTF-8"},
    "Liquid": {"extensions": ".liquid", "encoding": "UTF-8"},
    "CoffeeScript": {"extensions": ".coffee", "encoding": "UTF-8"},
    "LiveScript": {"extensions": ".ls", "encoding": "UTF-8"},
    "Elm": {"extensions": ".elm", "encoding": "UTF-8"},
    "PureScript": {"extensions": ".purs", "encoding": "UTF-8"},
    "ReasonML": {"extensions": ".re, .rei", "encoding": "UTF-8"},
    "Solidity": {"extensions": ".sol", "encoding": "UTF-8"},
    "Vyper": {"extensions": ".vy", "encoding": "UTF-8"},
    "Move": {"extensions": ".move", "encoding": "UTF-8"},
    "Cairo": {"extensions": ".cairo", "encoding": "UTF-8"},
    "GLSL": {"extensions": ".glsl, .vert, .frag", "encoding": "UTF-8"},
    "HLSL": {"extensions": ".hlsl, .fx", "encoding": "UTF-8"},
    "WGSL": {"extensions": ".wgsl", "encoding": "UTF-8"},
    "Metal": {"extensions": ".metal", "encoding": "UTF-8"},
    "CUDA": {"extensions": ".cu, .cuh", "encoding": "UTF-8"},
    "OpenCL": {"extensions": ".cl", "encoding": "UTF-8"},
}


@dataclass
class GitHubRepo:
    """Represents a GitHub repository."""
    
    owner: str
    name: str
    description: Optional[str] = None
    default_branch: str = "main"
    html_url: Optional[str] = None
    topics: list[str] | None = None
    language: Optional[str] = None
    stars: int = 0
    
    @property
    def full_name(self) -> str:
        """Return owner/name format."""
        return f"{self.owner}/{self.name}"
    
    @classmethod
    def from_url(cls, url: str) -> "GitHubRepo":
        """Parse a GitHub URL into a GitHubRepo object."""
        # Handle various GitHub URL formats
        # https://github.com/owner/repo
        # https://github.com/owner/repo.git
        # git@github.com:owner/repo.git
        
        if url.startswith("git@"):
            # SSH format: git@github.com:owner/repo.git
            match = re.match(r"git@github\.com:([^/]+)/(.+?)(?:\.git)?$", url)
            if match:
                return cls(owner=match.group(1), name=match.group(2))
        else:
            # HTTPS format
            parsed = urlparse(url)
            path_parts = parsed.path.strip("/").replace(".git", "").split("/")
            if len(path_parts) >= 2:
                return cls(owner=path_parts[0], name=path_parts[1])
        
        raise ValueError(f"Unable to parse GitHub URL: {url}")


class GitHubClient:
    """Client for interacting with GitHub API with rate limit handling."""
    
    BASE_URL = "https://api.github.com"
    
    def __init__(
        self,
        token: Optional[str] = None,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        respect_rate_limit: bool = True,
    ):
        """Initialize GitHub client.
        
        Args:
            token: Optional GitHub personal access token for higher rate limits
                   and access to private repositories.
            max_retries: Maximum number of retries for failed requests.
            retry_delay: Base delay between retries (exponential backoff).
            respect_rate_limit: If True, wait when rate limited instead of failing.
        """
        self.token = token
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.respect_rate_limit = respect_rate_limit
        self._client: Optional[httpx.Client] = None
        self._rate_limit = RateLimitInfo()
    
    @property
    def client(self) -> httpx.Client:
        """Get or create HTTP client."""
        if self._client is None:
            headers = {
                "Accept": "application/vnd.github.v3+json",
                "User-Agent": "Dossier-Documentation-Tool",
            }
            if self.token:
                headers["Authorization"] = f"Bearer {self.token}"
            self._client = httpx.Client(
                base_url=self.BASE_URL,
                headers=headers,
                timeout=30.0,
                follow_redirects=True,
            )
        return self._client
    
    @property
    def rate_limit(self) -> RateLimitInfo:
        """Current rate limit info."""
        return self._rate_limit
    
    def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            self._client.close()
            self._client = None
    
    def __enter__(self) -> "GitHubClient":
        return self
    
    def __exit__(self, *args) -> None:
        self.close()
    
    def _request_with_retry(
        self,
        method: str,
        url: str,
        **kwargs,
    ) -> httpx.Response:
        """Make a request with retry and rate limit handling.
        
        Args:
            method: HTTP method
            url: Request URL
            **kwargs: Additional arguments for httpx
            
        Returns:
            HTTP response
            
        Raises:
            httpx.HTTPStatusError: If request fails after retries
        """
        last_error: Optional[Exception] = None
        
        for attempt in range(self.max_retries + 1):
            try:
                # Check rate limit before making request
                if self._rate_limit.is_exhausted and self.respect_rate_limit:
                    wait_time = self._rate_limit.seconds_until_reset + 1
                    if wait_time > 0 and wait_time < 900:  # Max 15 min wait
                        time.sleep(wait_time)
                
                response = self.client.request(method, url, **kwargs)
                
                # Update rate limit info
                self._rate_limit = RateLimitInfo.from_headers(response.headers)
                
                # Handle rate limit response
                if response.status_code == 403:
                    if "rate limit" in response.text.lower():
                        if self.respect_rate_limit:
                            wait_time = self._rate_limit.seconds_until_reset + 1
                            if wait_time > 0 and wait_time < 900:
                                time.sleep(wait_time)
                                continue
                        raise httpx.HTTPStatusError(
                            f"Rate limit exceeded. Resets in {self._rate_limit.seconds_until_reset:.0f}s",
                            request=response.request,
                            response=response,
                        )
                
                # Handle server errors with retry
                if response.status_code >= 500:
                    response.raise_for_status()
                
                return response
                
            except (httpx.ConnectError, httpx.ReadTimeout, httpx.HTTPStatusError) as e:
                last_error = e
                if attempt < self.max_retries:
                    delay = self.retry_delay * (2 ** attempt)  # Exponential backoff
                    time.sleep(delay)
                    continue
                raise
        
        if last_error:
            raise last_error
        raise RuntimeError("Request failed without error")
    
    def get(self, url: str, **kwargs) -> httpx.Response:
        """Make GET request with retry handling."""
        response = self._request_with_retry("GET", url, **kwargs)
        response.raise_for_status()
        return response
    
    def get_repo(self, owner: str, name: str) -> GitHubRepo:
        """Fetch repository information.
        
        Args:
            owner: Repository owner (user or organization)
            name: Repository name
            
        Returns:
            GitHubRepo with repository details
            
        Raises:
            httpx.HTTPStatusError: If repository not found or API error
        """
        response = self.get(f"/repos/{owner}/{name}")
        data = response.json()
        
        return GitHubRepo(
            owner=data["owner"]["login"],
            name=data["name"],
            description=data.get("description"),
            default_branch=data.get("default_branch", "main"),
            html_url=data.get("html_url"),
            topics=data.get("topics", []),
            language=data.get("language"),
            stars=data.get("stargazers_count", 0),
        )
    
    def get_repo_from_url(self, url: str) -> GitHubRepo:
        """Fetch repository information from a GitHub URL.
        
        Args:
            url: GitHub repository URL
            
        Returns:
            GitHubRepo with repository details
        """
        parsed = GitHubRepo.from_url(url)
        return self.get_repo(parsed.owner, parsed.name)
    
    def get_readme(self, owner: str, name: str) -> Optional[str]:
        """Fetch repository README content.
        
        Args:
            owner: Repository owner
            name: Repository name
            
        Returns:
            README content as string, or None if not found
        """
        try:
            response = self.get(f"/repos/{owner}/{name}/readme")
            data = response.json()
            
            # README is base64 encoded
            content = data.get("content", "")
            if content:
                return base64.b64decode(content).decode("utf-8")
            return None
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise
    
    def list_docs_files(
        self,
        owner: str,
        name: str,
        path: str = "",
        branch: Optional[str] = None,
    ) -> list[dict]:
        """List documentation files in a repository path.
        
        Args:
            owner: Repository owner
            name: Repository name
            path: Path within repository (default: root)
            branch: Branch name (default: repository default)
            
        Returns:
            List of file info dicts with 'name', 'path', 'type', 'download_url'
        """
        params = {}
        if branch:
            params["ref"] = branch
            
        try:
            response = self.get(
                f"/repos/{owner}/{name}/contents/{path}",
                params=params,
            )
            contents = response.json()
            
            # Handle single file response
            if isinstance(contents, dict):
                contents = [contents]
            
            # Filter for documentation files
            doc_extensions = {".md", ".markdown", ".rst", ".txt"}
            doc_files = []
            
            for item in contents:
                if item["type"] == "file":
                    ext = Path(item["name"]).suffix.lower()
                    if ext in doc_extensions:
                        doc_files.append(item)
                elif item["type"] == "dir" and item["name"].lower() in {"docs", "doc", "documentation"}:
                    # Recursively get docs from documentation directories
                    doc_files.extend(
                        self.list_docs_files(owner, name, item["path"], branch)
                    )
            
            return doc_files
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return []
            raise
    
    def get_file_content(self, owner: str, name: str, path: str) -> Optional[str]:
        """Fetch file content from repository.
        
        Args:
            owner: Repository owner
            name: Repository name
            path: File path within repository
            
        Returns:
            File content as string, or None if not found
        """
        try:
            response = self.get(f"/repos/{owner}/{name}/contents/{path}")
            data = response.json()
            
            content = data.get("content", "")
            if content:
                return base64.b64decode(content).decode("utf-8")
            return None
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise
    
    def search_repos(
        self,
        query: str,
        sort: str = "stars",
        order: str = "desc",
        per_page: int = 10,
    ) -> list[GitHubRepo]:
        """Search for repositories.
        
        Args:
            query: Search query (GitHub search syntax)
            sort: Sort field ('stars', 'forks', 'updated')
            order: Sort order ('asc' or 'desc')
            per_page: Number of results (max 100)
            
        Returns:
            List of matching GitHubRepo objects
        """
        response = self.get(
            "/search/repositories",
            params={
                "q": query,
                "sort": sort,
                "order": order,
                "per_page": min(per_page, 100),
            },
        )
        data = response.json()
        
        repos = []
        for item in data.get("items", []):
            repos.append(
                GitHubRepo(
                    owner=item["owner"]["login"],
                    name=item["name"],
                    description=item.get("description"),
                    default_branch=item.get("default_branch", "main"),
                    html_url=item.get("html_url"),
                    topics=item.get("topics", []),
                    language=item.get("language"),
                    stars=item.get("stargazers_count", 0),
                )
            )
        
        return repos

    def list_user_repos(
        self,
        username: str,
        repo_type: str = "owner",
        sort: str = "updated",
        per_page: int = 100,
    ) -> list[GitHubRepo]:
        """List repositories for a user.
        
        Args:
            username: GitHub username
            repo_type: Type filter ('all', 'owner', 'member')
            sort: Sort field ('created', 'updated', 'pushed', 'full_name')
            per_page: Number of results per page (max 100)
            
        Returns:
            List of GitHubRepo objects
        """
        repos = []
        page = 1
        
        while True:
            response = self.get(
                f"/users/{username}/repos",
                params={
                    "type": repo_type,
                    "sort": sort,
                    "per_page": min(per_page, 100),
                    "page": page,
                },
            )
            data = response.json()
            
            if not data:
                break
            
            for item in data:
                repos.append(
                    GitHubRepo(
                        owner=item["owner"]["login"],
                        name=item["name"],
                        description=item.get("description"),
                        default_branch=item.get("default_branch", "main"),
                        html_url=item.get("html_url"),
                        topics=item.get("topics", []),
                        language=item.get("language"),
                        stars=item.get("stargazers_count", 0),
                    )
                )
            
            # Check if we got all repos
            if len(data) < per_page:
                break
            page += 1
        
        return repos

    def list_org_repos(
        self,
        org: str,
        repo_type: str = "all",
        sort: str = "updated",
        per_page: int = 100,
    ) -> list[GitHubRepo]:
        """List repositories for an organization.
        
        Args:
            org: GitHub organization name
            repo_type: Type filter ('all', 'public', 'private', 'forks', 'sources', 'member')
            sort: Sort field ('created', 'updated', 'pushed', 'full_name')
            per_page: Number of results per page (max 100)
            
        Returns:
            List of GitHubRepo objects
        """
        repos = []
        page = 1
        
        while True:
            response = self.get(
                f"/orgs/{org}/repos",
                params={
                    "type": repo_type,
                    "sort": sort,
                    "per_page": min(per_page, 100),
                    "page": page,
                },
            )
            data = response.json()
            
            if not data:
                break
            
            for item in data:
                repos.append(
                    GitHubRepo(
                        owner=item["owner"]["login"],
                        name=item["name"],
                        description=item.get("description"),
                        default_branch=item.get("default_branch", "main"),
                        html_url=item.get("html_url"),
                        topics=item.get("topics", []),
                        language=item.get("language"),
                        stars=item.get("stargazers_count", 0),
                    )
                )
            
            if len(data) < per_page:
                break
            page += 1
        
        return repos

    def get_authenticated_user(self) -> dict:
        """Get the authenticated user's information.
        
        Returns:
            User information dict
            
        Raises:
            httpx.HTTPStatusError: If not authenticated
        """
        response = self.get("/user")
        return response.json()
    
    def check_rate_limit(self) -> RateLimitInfo:
        """Check current rate limit status.
        
        Returns:
            RateLimitInfo with current limits
        """
        response = self.get("/rate_limit")
        data = response.json()
        core = data.get("resources", {}).get("core", {})
        return RateLimitInfo(
            limit=core.get("limit", 60),
            remaining=core.get("remaining", 60),
            reset_at=core.get("reset", 0),
        )

    def get_contributors(
        self,
        owner: str,
        name: str,
        per_page: int = 30,
        max_contributors: int = 100,
    ) -> list[dict]:
        """Fetch repository contributors.
        
        Args:
            owner: Repository owner
            name: Repository name
            per_page: Number per page (max 100)
            max_contributors: Maximum total to fetch
            
        Returns:
            List of contributor dicts with login, avatar_url, contributions, html_url
        """
        contributors = []
        page = 1
        
        while len(contributors) < max_contributors:
            try:
                response = self.get(
                    f"/repos/{owner}/{name}/contributors",
                    params={"per_page": min(per_page, 100), "page": page},
                )
                data = response.json()
                
                if not data:
                    break
                
                for item in data:
                    contributors.append({
                        "username": item.get("login"),
                        "avatar_url": item.get("avatar_url"),
                        "contributions": item.get("contributions", 0),
                        "profile_url": item.get("html_url"),
                    })
                
                if len(data) < per_page:
                    break
                page += 1
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 404:
                    break
                raise
        
        return contributors[:max_contributors]

    def get_issues(
        self,
        owner: str,
        name: str,
        state: str = "open",
        per_page: int = 30,
        max_issues: int = 100,
    ) -> list[dict]:
        """Fetch repository issues.
        
        Args:
            owner: Repository owner
            name: Repository name
            state: Issue state ('open', 'closed', 'all')
            per_page: Number per page (max 100)
            max_issues: Maximum total to fetch
            
        Returns:
            List of issue dicts
        """
        issues = []
        page = 1
        
        while len(issues) < max_issues:
            try:
                response = self.get(
                    f"/repos/{owner}/{name}/issues",
                    params={
                        "state": state,
                        "per_page": min(per_page, 100),
                        "page": page,
                    },
                )
                data = response.json()
                
                if not data:
                    break
                
                for item in data:
                    # Skip pull requests (they appear in issues endpoint)
                    if "pull_request" in item:
                        continue
                    
                    labels = [label.get("name") for label in item.get("labels", [])]
                    issues.append({
                        "issue_number": item.get("number"),
                        "title": item.get("title"),
                        "state": item.get("state"),
                        "author": item.get("user", {}).get("login"),
                        "labels": ",".join(labels) if labels else None,
                        "issue_created_at": item.get("created_at"),
                        "issue_updated_at": item.get("updated_at"),
                    })
                
                if len(data) < per_page:
                    break
                page += 1
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 404:
                    break
                raise
        
        return issues[:max_issues]

    def get_pull_requests(
        self,
        owner: str,
        name: str,
        state: str = "all",
        per_page: int = 30,
        max_prs: int = 50,
    ) -> list[dict]:
        """Fetch repository pull requests.
        
        Args:
            owner: Repository owner
            name: Repository name
            state: PR state ('open', 'closed', 'all')
            per_page: Number per page (max 100)
            max_prs: Maximum total to fetch
            
        Returns:
            List of PR dicts
        """
        prs = []
        page = 1
        
        while len(prs) < max_prs:
            try:
                response = self.get(
                    f"/repos/{owner}/{name}/pulls",
                    params={
                        "state": state,
                        "per_page": min(per_page, 100),
                        "page": page,
                        "sort": "updated",
                        "direction": "desc",
                    },
                )
                data = response.json()
                
                if not data:
                    break
                
                for item in data:
                    labels = [label.get("name") for label in item.get("labels", [])]
                    
                    # Parse dates
                    pr_created = item.get("created_at")
                    pr_updated = item.get("updated_at")
                    pr_merged = item.get("merged_at")
                    
                    # Parse dates to datetime
                    from datetime import datetime
                    def parse_date(date_str):
                        if date_str:
                            try:
                                return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                            except (ValueError, AttributeError):
                                return None
                        return None
                    
                    prs.append({
                        "pr_number": item.get("number"),
                        "title": item.get("title"),
                        "state": "merged" if item.get("merged_at") else item.get("state"),
                        "author": item.get("user", {}).get("login"),
                        "base_branch": item.get("base", {}).get("ref"),
                        "head_branch": item.get("head", {}).get("ref"),
                        "is_draft": item.get("draft", False),
                        "is_merged": item.get("merged_at") is not None,
                        "additions": item.get("additions", 0),
                        "deletions": item.get("deletions", 0),
                        "labels": ",".join(labels) if labels else None,
                        "pr_created_at": parse_date(pr_created),
                        "pr_updated_at": parse_date(pr_updated),
                        "pr_merged_at": parse_date(pr_merged),
                    })
                
                if len(data) < per_page:
                    break
                page += 1
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 404:
                    break
                raise
        
        return prs[:max_prs]

    def get_releases(
        self,
        owner: str,
        name: str,
        per_page: int = 30,
        max_releases: int = 20,
    ) -> list[dict]:
        """Fetch repository releases and tags.
        
        Args:
            owner: Repository owner
            name: Repository name
            per_page: Number per page (max 100)
            max_releases: Maximum total to fetch
            
        Returns:
            List of release dicts
        """
        releases = []
        page = 1
        
        while len(releases) < max_releases:
            try:
                response = self.get(
                    f"/repos/{owner}/{name}/releases",
                    params={"per_page": min(per_page, 100), "page": page},
                )
                data = response.json()
                
                if not data:
                    break
                
                for item in data:
                    # Parse dates
                    from datetime import datetime
                    def parse_date(date_str):
                        if date_str:
                            try:
                                return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                            except (ValueError, AttributeError):
                                return None
                        return None
                    
                    # Truncate body to reasonable length
                    body = item.get("body", "") or ""
                    if len(body) > 500:
                        body = body[:497] + "..."
                    
                    releases.append({
                        "tag_name": item.get("tag_name"),
                        "name": item.get("name"),
                        "body": body,
                        "is_prerelease": item.get("prerelease", False),
                        "is_draft": item.get("draft", False),
                        "author": item.get("author", {}).get("login"),
                        "target_commitish": item.get("target_commitish"),
                        "release_created_at": parse_date(item.get("created_at")),
                        "release_published_at": parse_date(item.get("published_at")),
                    })
                
                if len(data) < per_page:
                    break
                page += 1
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 404:
                    break
                raise
        
        return releases[:max_releases]

    def get_branches(
        self,
        owner: str,
        name: str,
        per_page: int = 30,
        max_branches: int = 100,
    ) -> list[dict]:
        """Fetch repository branches with latest commit info.
        
        Args:
            owner: Repository owner
            name: Repository name
            per_page: Number per page (max 100)
            max_branches: Maximum total to fetch
            
        Returns:
            List of branch dicts with name, is_protected, commit info
        """
        branches = []
        page = 1
        
        # Get repo default branch
        try:
            repo_resp = self.get(f"/repos/{owner}/{name}")
            repo_data = repo_resp.json()
            default_branch = repo_data.get("default_branch", "main")
        except httpx.HTTPStatusError:
            default_branch = "main"
        
        while len(branches) < max_branches:
            try:
                response = self.get(
                    f"/repos/{owner}/{name}/branches",
                    params={"per_page": min(per_page, 100), "page": page},
                )
                data = response.json()
                
                if not data:
                    break
                
                for item in data:
                    branch_name = item.get("name", "")
                    commit = item.get("commit", {})
                    
                    # Get commit details if available
                    commit_sha = commit.get("sha")
                    commit_message = None
                    commit_author = None
                    commit_date = None
                    
                    # Try to get more commit details
                    if commit_sha:
                        try:
                            commit_resp = self.get(f"/repos/{owner}/{name}/commits/{commit_sha}")
                            commit_data = commit_resp.json()
                            commit_info = commit_data.get("commit", {})
                            commit_message = commit_info.get("message", "")
                            if commit_message:
                                commit_message = commit_message.split("\n")[0][:100]  # First line, truncated
                            author_info = commit_info.get("author", {})
                            commit_author = author_info.get("name")
                            # Parse ISO date string to datetime
                            date_str = author_info.get("date")
                            if date_str:
                                from datetime import datetime, timezone
                                try:
                                    # GitHub returns ISO format: 2024-01-15T10:30:00Z
                                    commit_date = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                                except (ValueError, AttributeError):
                                    commit_date = None
                        except httpx.HTTPStatusError:
                            pass
                    
                    branches.append({
                        "name": branch_name,
                        "is_default": branch_name == default_branch,
                        "is_protected": item.get("protected", False),
                        "commit_sha": commit_sha,
                        "commit_message": commit_message,
                        "commit_author": commit_author,
                        "commit_date": commit_date,
                    })
                
                if len(data) < per_page:
                    break
                page += 1
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 404:
                    break
                raise
        
        # Sort: default branch first, then alphabetically
        branches.sort(key=lambda x: (not x["is_default"], x["name"]))
        return branches[:max_branches]

    def get_languages(self, owner: str, name: str) -> list[dict]:
        """Fetch repository language breakdown.
        
        Args:
            owner: Repository owner
            name: Repository name
            
        Returns:
            List of language dicts with language, bytes_count, percentage,
            file_extensions, and encoding
        """
        try:
            response = self.get(f"/repos/{owner}/{name}/languages")
            data = response.json()
            
            if not data:
                return []
            
            # Calculate total bytes
            total_bytes = sum(data.values())
            
            languages = []
            for lang, bytes_count in data.items():
                percentage = (bytes_count / total_bytes * 100) if total_bytes > 0 else 0
                # Look up language info from our mapping
                lang_info = LANGUAGE_INFO.get(lang, {})
                languages.append({
                    "language": lang,
                    "bytes_count": bytes_count,
                    "percentage": round(percentage, 2),
                    "file_extensions": lang_info.get("extensions"),
                    "encoding": lang_info.get("encoding"),
                })
            
            # Sort by bytes descending
            languages.sort(key=lambda x: x["bytes_count"], reverse=True)
            return languages
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return []
            raise

    def get_dependencies(self, owner: str, name: str) -> list[dict]:
        """Fetch project dependencies from common dependency files.
        
        Parses: pyproject.toml, package.json, requirements.txt
        
        Args:
            owner: Repository owner
            name: Repository name
            
        Returns:
            List of dependency dicts with name, version_spec, dep_type, source
        """
        dependencies = []
        
        # Try pyproject.toml
        pyproject = self.get_file_content(owner, name, "pyproject.toml")
        if pyproject:
            dependencies.extend(self._parse_pyproject_toml(pyproject))
        
        # Try package.json
        package_json = self.get_file_content(owner, name, "package.json")
        if package_json:
            dependencies.extend(self._parse_package_json(package_json))
        
        # Try requirements.txt (only if no pyproject.toml)
        if not pyproject:
            requirements = self.get_file_content(owner, name, "requirements.txt")
            if requirements:
                dependencies.extend(self._parse_requirements_txt(requirements))
        
        return dependencies

    def _parse_pyproject_toml(self, content: str) -> list[dict]:
        """Parse dependencies from pyproject.toml content."""
        dependencies = []
        
        try:
            import tomllib
            data = tomllib.loads(content)
            
            # PEP 621 dependencies
            project = data.get("project", {})
            for dep in project.get("dependencies", []):
                name, version = self._parse_pep508(dep)
                dependencies.append({
                    "name": name,
                    "version_spec": version,
                    "dep_type": "runtime",
                    "source": "pyproject.toml",
                })
            
            # Optional dependencies
            for group, deps in project.get("optional-dependencies", {}).items():
                dep_type = "dev" if group in ("dev", "test", "testing") else "optional"
                for dep in deps:
                    name, version = self._parse_pep508(dep)
                    dependencies.append({
                        "name": name,
                        "version_spec": version,
                        "dep_type": dep_type,
                        "source": "pyproject.toml",
                    })
            
            # Poetry dependencies
            poetry = data.get("tool", {}).get("poetry", {})
            for dep, version in poetry.get("dependencies", {}).items():
                if dep.lower() == "python":
                    continue
                if isinstance(version, dict):
                    version = version.get("version", "*")
                dependencies.append({
                    "name": dep,
                    "version_spec": str(version),
                    "dep_type": "runtime",
                    "source": "pyproject.toml",
                })
            
            for dep, version in poetry.get("dev-dependencies", {}).items():
                if isinstance(version, dict):
                    version = version.get("version", "*")
                dependencies.append({
                    "name": dep,
                    "version_spec": str(version),
                    "dep_type": "dev",
                    "source": "pyproject.toml",
                })
            
            # uv dependencies
            uv = data.get("tool", {}).get("uv", {})
            for dep in uv.get("dependencies", []):
                name, version = self._parse_pep508(dep)
                dependencies.append({
                    "name": name,
                    "version_spec": version,
                    "dep_type": "runtime",
                    "source": "pyproject.toml",
                })
            
            for dep in uv.get("dev-dependencies", []):
                name, version = self._parse_pep508(dep)
                dependencies.append({
                    "name": name,
                    "version_spec": version,
                    "dep_type": "dev",
                    "source": "pyproject.toml",
                })
                
        except Exception:
            pass  # Silently fail on parse errors
        
        return dependencies

    def _parse_pep508(self, spec: str) -> tuple[str, Optional[str]]:
        """Parse a PEP 508 dependency specifier into name and version."""
        # Simple parsing: split on version specifiers
        import re
        match = re.match(r'^([a-zA-Z0-9_-]+(?:\[[^\]]+\])?)\s*(.*)$', spec.strip())
        if match:
            name = match.group(1).split("[")[0]  # Remove extras
            version = match.group(2).strip() or None
            return name, version
        return spec.strip(), None

    def _parse_package_json(self, content: str) -> list[dict]:
        """Parse dependencies from package.json content."""
        import json
        dependencies = []
        
        try:
            data = json.loads(content)
            
            for dep, version in data.get("dependencies", {}).items():
                dependencies.append({
                    "name": dep,
                    "version_spec": version,
                    "dep_type": "runtime",
                    "source": "package.json",
                })
            
            for dep, version in data.get("devDependencies", {}).items():
                dependencies.append({
                    "name": dep,
                    "version_spec": version,
                    "dep_type": "dev",
                    "source": "package.json",
                })
            
            for dep, version in data.get("peerDependencies", {}).items():
                dependencies.append({
                    "name": dep,
                    "version_spec": version,
                    "dep_type": "peer",
                    "source": "package.json",
                })
            
            for dep, version in data.get("optionalDependencies", {}).items():
                dependencies.append({
                    "name": dep,
                    "version_spec": version,
                    "dep_type": "optional",
                    "source": "package.json",
                })
        except json.JSONDecodeError:
            pass
        
        return dependencies

    def _parse_requirements_txt(self, content: str) -> list[dict]:
        """Parse dependencies from requirements.txt content."""
        dependencies = []
        
        for line in content.splitlines():
            line = line.strip()
            # Skip comments and empty lines
            if not line or line.startswith("#") or line.startswith("-"):
                continue
            
            name, version = self._parse_pep508(line)
            if name:
                dependencies.append({
                    "name": name,
                    "version_spec": version,
                    "dep_type": "runtime",
                    "source": "requirements.txt",
                })
        
        return dependencies


class GitHubParser:
    """Parser for GitHub repository documentation."""
    
    def __init__(self, token: Optional[str] = None):
        """Initialize GitHub parser.
        
        Args:
            token: Optional GitHub personal access token
        """
        self.client = GitHubClient(token)
        self.markdown_parser = MarkdownParser()
    
    def close(self) -> None:
        """Close the GitHub client."""
        self.client.close()
    
    def __enter__(self) -> "GitHubParser":
        return self
    
    def __exit__(self, *args) -> None:
        self.close()
    
    def parse_repo(
        self,
        owner: str,
        name: str,
        project_id: int = 0,
        include_docs_folder: bool = True,
    ) -> tuple[GitHubRepo, list[DocumentSection]]:
        """Parse documentation from a GitHub repository.
        
        Args:
            owner: Repository owner
            name: Repository name
            project_id: ID of associated Dossier project
            include_docs_folder: Whether to parse docs/ folder
            
        Returns:
            Tuple of (GitHubRepo info, list of DocumentSections)
        """
        # Get repo info
        repo = self.client.get_repo(owner, name)
        sections: list[DocumentSection] = []
        
        # Parse README
        readme = self.client.get_readme(owner, name)
        if readme:
            readme_sections = self.markdown_parser.parse(
                readme,
                source_file=f"github:{repo.full_name}/README.md",
                project_id=project_id,
            )
            sections.extend(readme_sections)
        
        # Parse docs folder if requested
        if include_docs_folder:
            docs_files = self.client.list_docs_files(owner, name)
            for file_info in docs_files:
                # Skip README if already parsed
                if file_info["name"].upper().startswith("README"):
                    continue
                    
                content = self.client.get_file_content(owner, name, file_info["path"])
                if content:
                    file_sections = self.markdown_parser.parse(
                        content,
                        source_file=f"github:{repo.full_name}/{file_info['path']}",
                        project_id=project_id,
                    )
                    # Adjust order to come after README sections
                    for section in file_sections:
                        section.order += len(sections)
                    sections.extend(file_sections)
        
        return repo, sections
    
    def parse_repo_url(
        self,
        url: str,
        project_id: int = 0,
        include_docs_folder: bool = True,
    ) -> tuple[GitHubRepo, list[DocumentSection]]:
        """Parse documentation from a GitHub URL.
        
        Args:
            url: GitHub repository URL
            project_id: ID of associated Dossier project
            include_docs_folder: Whether to parse docs/ folder
            
        Returns:
            Tuple of (GitHubRepo info, list of DocumentSections)
        """
        parsed = GitHubRepo.from_url(url)
        return self.parse_repo(
            parsed.owner,
            parsed.name,
            project_id=project_id,
            include_docs_folder=include_docs_folder,
        )


def sync_github_repo(
    url: str,
    token: Optional[str] = None,
    project_id: int = 0,
) -> tuple[GitHubRepo, list[DocumentSection]]:
    """Convenience function to sync a GitHub repository.
    
    Args:
        url: GitHub repository URL
        token: Optional GitHub personal access token
        project_id: ID of associated Dossier project
        
    Returns:
        Tuple of (GitHubRepo info, list of DocumentSections)
    """
    with GitHubParser(token) as parser:
        return parser.parse_repo_url(url, project_id=project_id)
