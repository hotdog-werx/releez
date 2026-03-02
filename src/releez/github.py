from __future__ import annotations

import os
import re
from dataclasses import dataclass
from urllib.parse import urlparse

from releez.errors import InvalidGitHubRemoteError, MissingGitHubDependencyError


@dataclass(frozen=True)
class PullRequest:
    """A minimal representation of a created GitHub pull request.

    Attributes:
        url: PR URL.
        number: PR number.
    """

    url: str
    number: int


@dataclass(frozen=True)
class PullRequestCreateRequest:
    """Parameters for creating a GitHub pull request.

    Attributes:
        remote_url: Git remote URL used to infer the GitHub repo.
        token: GitHub token used for authentication.
        base: Base branch for the PR.
        head: Head branch for the PR.
        title: PR title.
        body: PR body.
        labels: Labels to add to the PR.
    """

    remote_url: str
    token: str
    base: str
    head: str
    title: str
    body: str
    labels: list[str]


_SCP_SSH_RE = re.compile(
    r'^git@(?P<host>[^:]+):(?P<full>[^/]+/[^/]+?)(?:\\.git)?$',
)
_SSH_URL_RE = re.compile(
    r'^ssh://git@(?P<host>[^/]+)/(?P<full>[^/]+/[^/]+?)(?:\\.git)?$',
)
_HTTPS_RE = re.compile(
    r'^https?://(?P<host>[^/]+)/(?P<full>[^/]+/[^/]+?)(?:\\.git)?$',
)


def _github_api_base_url_from_env() -> str | None:
    """Resolve GitHub API base URL from environment variables.

    Checks RELEEZ_GITHUB_API_URL / GITHUB_API_URL directly, then falls back
    to constructing an API URL from RELEEZ_GITHUB_SERVER_URL / GITHUB_SERVER_URL.
    Supports GitHub Enterprise Server by respecting custom server URLs.

    Returns:
        API base URL with trailing slash removed, or None if not configured.
    """
    api_url = os.getenv('RELEEZ_GITHUB_API_URL') or os.getenv('GITHUB_API_URL')
    if api_url:
        return api_url.rstrip('/')

    server_url = os.getenv('RELEEZ_GITHUB_SERVER_URL') or os.getenv(
        'GITHUB_SERVER_URL',
    )
    if not server_url:
        return None
    return f'{server_url.rstrip("/")}/api/v3'


def _allowed_github_hosts_from_env() -> set[str]:
    """Build set of allowed GitHub hosts from environment variables.

    Always includes "github.com". Adds additional hosts from server/API
    URL env vars to support GitHub Enterprise Server deployments.
    Handles both full URLs (parses hostname) and plain hostnames.

    Returns:
        Set of allowed hostname strings.
    """
    hosts = {'github.com'}

    for var in (
        'RELEEZ_GITHUB_SERVER_URL',
        'GITHUB_SERVER_URL',
        'RELEEZ_GITHUB_API_URL',
        'GITHUB_API_URL',
    ):
        raw = os.getenv(var)
        if not raw:
            continue
        parsed = urlparse(raw)
        if parsed.hostname:
            hosts.add(parsed.hostname)
            continue
        # allow plain host values (not URLs)
        hosts.add(raw.strip().rstrip('/'))

    return hosts


def _parse_github_full_name(remote_url: str) -> str:
    """Parse owner/repo from a git remote URL.

    Supports three URL formats:
    - SCP-style SSH: git@github.com:owner/repo.git
    - SSH URL: ssh://git@github.com/owner/repo.git
    - HTTPS: https://github.com/owner/repo.git

    Args:
        remote_url: Git remote URL to parse.

    Returns:
        Full repository name in "owner/repo" format.

    Raises:
        InvalidGitHubRemoteError: If URL format is unrecognized or host is not allowed.
    """
    # Try each URL format in order; first match wins
    remote_url = remote_url.strip()
    for regex in (_SCP_SSH_RE, _SSH_URL_RE, _HTTPS_RE):
        m = regex.match(remote_url)
        if m:
            host = m.group('host')
            if host not in _allowed_github_hosts_from_env():
                raise InvalidGitHubRemoteError(remote_url)
            full_name = m.group('full')
            if full_name.endswith('.git'):
                full_name = full_name.removesuffix('.git')
            return full_name
    raise InvalidGitHubRemoteError(remote_url)


def create_pull_request(request: PullRequestCreateRequest) -> PullRequest:
    """Create a GitHub pull request.

    Args:
        request: Parameters for creating the pull request.

    Returns:
        Created PR with URL and number.

    Raises:
        MissingGitHubDependencyError: If PyGithub is not installed.
        InvalidGitHubRemoteError: If the remote URL cannot be mapped to a GitHub repo.
    """
    try:
        from github import Github  # noqa: PLC0415
    except ImportError as exc:
        raise MissingGitHubDependencyError from exc

    full_name = _parse_github_full_name(request.remote_url)
    base_url = _github_api_base_url_from_env()
    gh = (
        Github(
            login_or_token=request.token,
            base_url=base_url,
        )
        if base_url
        else Github(request.token)
    )
    repo = gh.get_repo(full_name)
    pr = repo.create_pull(
        title=request.title,
        body=request.body,
        base=request.base,
        head=request.head,
    )
    if request.labels:
        pr.add_to_labels(*request.labels)
    return PullRequest(url=pr.html_url, number=pr.number)
