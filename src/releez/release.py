from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from git import Repo

from releez.cliff import GitCliff, GitCliffBump
from releez.errors import (
    ChangelogNotFoundError,
    GitHubTokenRequiredError,
    GitRemoteUrlRequiredError,
)
from releez.git_repo import (
    checkout_remote_branch,
    commit_file,
    create_and_checkout_branch,
    ensure_clean,
    fetch,
    open_repo,
    push_set_upstream,
)
from releez.github import PullRequestCreateRequest, create_pull_request


@dataclass(frozen=True)
class StartReleaseResult:
    """Result of starting a release.

    Attributes:
        version: The computed next version.
        release_notes_markdown: The generated release notes markdown.
        release_branch: The created release branch, or None in dry-run mode.
        pr_url: The created PR URL, or None if not created.
    """

    version: str
    release_notes_markdown: str
    release_branch: str | None
    pr_url: str | None


@dataclass(frozen=True)
class StartReleaseInput:
    """Inputs for starting a release.

    Attributes:
        bump: Bump mode for git-cliff.
        base_branch: Base branch for the release PR.
        remote_name: Remote name to use.
        labels: Labels to add to the PR.
        title_prefix: Prefix for PR title / commit message.
        changelog_path: Changelog file to prepend to.
        create_pr: If true, create a GitHub pull request.
        github_token: GitHub token for PR creation.
        dry_run: If true, do not modify the repo; just output version and notes.
    """

    bump: GitCliffBump
    base_branch: str
    remote_name: str
    labels: list[str]
    title_prefix: str
    changelog_path: str
    create_pr: bool
    github_token: str | None
    dry_run: bool


@dataclass(frozen=True)
class _MaybeCreatePullRequestInput:
    """Inputs for optionally creating a pull request.

    Attributes:
        create_pr: If true, create a GitHub pull request.
        github_token: GitHub token for PR creation.
        remote_name: Remote name used to infer the repo URL.
        base_branch: The base branch for the PR.
        head_branch: The head branch for the PR.
        title: The PR title.
        body: The PR body.
        labels: Labels to add to the PR.
    """

    create_pr: bool
    github_token: str | None
    remote_name: str
    base_branch: str
    head_branch: str
    title: str
    body: str
    labels: list[str]


def _maybe_create_pull_request(
    *,
    repo: Repo,
    pr_input: _MaybeCreatePullRequestInput,
) -> str | None:
    if not pr_input.create_pr:
        return None
    if not pr_input.github_token:
        raise GitHubTokenRequiredError

    remote_url = repo.remotes[pr_input.remote_name].url
    if not remote_url:
        raise GitRemoteUrlRequiredError(pr_input.remote_name)

    request = PullRequestCreateRequest(
        remote_url=remote_url,
        token=pr_input.github_token,
        base=pr_input.base_branch,
        head=pr_input.head_branch,
        title=pr_input.title,
        body=pr_input.body,
        labels=pr_input.labels,
    )
    pr = create_pull_request(request)
    return pr.url


def start_release(
    release_input: StartReleaseInput,
) -> StartReleaseResult:
    """Start a release.

    Args:
        release_input: The input parameters for starting the release.

    Returns:
        The version, release notes, and (if created) branch/PR details.

    Raises:
        ReleezError: If a release step fails (git, git-cliff, or GitHub).
    """
    repo, info = open_repo()
    ensure_clean(repo)
    fetch(repo, remote_name=release_input.remote_name)

    cliff = GitCliff(repo_root=info.root)
    if not release_input.dry_run:
        checkout_remote_branch(
            repo,
            remote_name=release_input.remote_name,
            branch=release_input.base_branch,
        )

    version = cliff.compute_next_version(bump=release_input.bump)
    notes = cliff.generate_unreleased_notes(version=version)

    if release_input.dry_run:
        return StartReleaseResult(
            version=version,
            release_notes_markdown=notes,
            release_branch=None,
            pr_url=None,
        )

    release_branch = f'release/{version}'
    create_and_checkout_branch(repo, name=release_branch)

    changelog = Path(release_input.changelog_path)
    if not changelog.is_absolute():
        changelog = info.root / changelog
    if not changelog.exists():
        raise ChangelogNotFoundError(changelog)

    cliff.prepend_to_changelog(version=version, changelog_path=changelog)
    commit_file(
        repo,
        path=changelog,
        message=f'{release_input.title_prefix}{version}',
    )

    push_set_upstream(
        repo,
        remote_name=release_input.remote_name,
        branch=release_branch,
    )

    pr_url = _maybe_create_pull_request(
        repo=repo,
        pr_input=_MaybeCreatePullRequestInput(
            create_pr=release_input.create_pr,
            github_token=release_input.github_token,
            remote_name=release_input.remote_name,
            base_branch=release_input.base_branch,
            head_branch=release_branch,
            title=f'{release_input.title_prefix}{version}',
            body=notes,
            labels=release_input.labels,
        ),
    )

    return StartReleaseResult(
        version=version,
        release_notes_markdown=notes,
        release_branch=release_branch,
        pr_url=pr_url,
    )
