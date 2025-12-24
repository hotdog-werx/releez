import re
from dataclasses import dataclass

from releez.errors import InvalidGitHubRemoteError, MissingGitHubDependencyError


@dataclass(frozen=True)
class PullRequest:
    """A minimal representation of a created GitHub pull request.

    Attributes:
        url: The PR URL.
        number: The PR number.
    """

    url: str
    number: int


@dataclass(frozen=True)
class PullRequestCreateRequest:
    """Parameters for creating a GitHub pull request.

    Attributes:
        remote_url: The git remote URL used to infer the GitHub repo.
        token: GitHub token used for authentication.
        base: The base branch for the PR.
        head: The head branch for the PR.
        title: The PR title.
        body: The PR body.
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
    r'^git@github\\.com:(?P<full>[^/]+/[^/]+?)(?:\\.git)?$',
)
_SSH_URL_RE = re.compile(
    r'^ssh://git@github\\.com/(?P<full>[^/]+/[^/]+?)(?:\\.git)?$',
)
_HTTPS_RE = re.compile(
    r'^https://github\\.com/(?P<full>[^/]+/[^/]+?)(?:\\.git)?$',
)


def _parse_github_full_name(remote_url: str) -> str:
    remote_url = remote_url.strip()
    for regex in (_SCP_SSH_RE, _SSH_URL_RE, _HTTPS_RE):
        m = regex.match(remote_url)
        if m:
            return m.group('full')
    raise InvalidGitHubRemoteError(remote_url)


def create_pull_request(request: PullRequestCreateRequest) -> PullRequest:
    """Create a GitHub pull request.

    Args:
        request: The parameters needed to create the pull request.

    Returns:
        The created PR URL and number.

    Raises:
        MissingGitHubDependencyError: If PyGithub is not installed.
        InvalidGitHubRemoteError: If the remote URL cannot be mapped to a GitHub repo.
    """
    try:
        from github import Github  # noqa: PLC0415
    except ImportError as exc:
        raise MissingGitHubDependencyError from exc

    full_name = _parse_github_full_name(request.remote_url)
    gh = Github(request.token)
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
