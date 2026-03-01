from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from git import Repo

from releez.cliff import GitCliff, GitCliffBump
from releez.errors import (
    ChangelogFormatCommandRequiredError,
    GitHubTokenRequiredError,
    GitRemoteUrlRequiredError,
)
from releez.git_repo import (
    checkout_remote_branch,
    create_and_checkout_branch,
    ensure_clean,
    fetch,
    open_repo,
    push_set_upstream,
)
from releez.github import PullRequestCreateRequest, create_pull_request
from releez.utils import (
    resolve_changelog_path,
    run_changelog_formatter,
    run_post_changelog_hooks,
)


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
        version_override: Override the computed next version.
        base_branch: Base branch for the release PR.
        remote_name: Remote name to use.
        labels: Labels to add to the PR.
        title_prefix: Prefix for PR title / commit message.
        changelog_path: Changelog file to prepend to.
        post_changelog_hooks: List of hooks to run after changelog generation.
            Hooks run automatically if provided.
        run_changelog_format: (DEPRECATED) Use post_changelog_hooks instead.
        changelog_format_cmd: (DEPRECATED) Use post_changelog_hooks instead.
        create_pr: If true, create a GitHub pull request.
        github_token: GitHub token for PR creation.
        dry_run: If true, do not modify the repo; just output version and notes.
        project_name: Optional project name for monorepo support.
        tag_pattern: Optional tag pattern for git-cliff (monorepo).
        include_paths: Optional path filters for git-cliff (monorepo).
        project_path: Optional project directory path for selective staging (monorepo).
        tag_prefix: Optional tag prefix (e.g. "core-") used to strip the prefix from
            the hook {version} variable, so hooks always receive bare semver.
    """

    bump: GitCliffBump
    version_override: str | None
    base_branch: str
    remote_name: str
    labels: list[str]
    title_prefix: str
    changelog_path: str
    post_changelog_hooks: list[list[str]] | None
    run_changelog_format: bool
    changelog_format_cmd: list[str] | None
    create_pr: bool
    github_token: str | None
    dry_run: bool
    # Monorepo support
    project_name: str | None = None
    tag_pattern: str | None = None
    include_paths: list[str] | None = None
    project_path: Path | None = None
    tag_prefix: str = ''


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
    """Create pull request if requested.

    Args:
        repo: Git repository.
        pr_input: Pull request configuration.

    Returns:
        Pull request URL if created, None otherwise.

    Raises:
        GitHubTokenRequiredError: If PR creation requested but no token provided.
        GitRemoteUrlRequiredError: If remote URL cannot be determined.
    """
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


def _resolve_release_version(
    *,
    cliff: GitCliff,
    release_input: StartReleaseInput,
) -> str:
    """Resolve release version from override or git-cliff computation.

    Args:
        cliff: git-cliff wrapper instance.
        release_input: Release configuration.

    Returns:
        Version string to use for the release.
    """
    if release_input.version_override is not None:
        return release_input.version_override
    return cliff.compute_next_version(
        bump=release_input.bump,
        tag_pattern=release_input.tag_pattern,
        include_paths=release_input.include_paths,
    )


def _format_changelog_if_requested(
    *,
    repo_root: Path,
    changelog_path: Path,
    release_input: StartReleaseInput,
) -> None:
    """DEPRECATED: Use _run_post_changelog_hooks_if_requested instead."""
    if not release_input.run_changelog_format:  # pragma: no cover
        return
    if not release_input.changelog_format_cmd:
        raise ChangelogFormatCommandRequiredError
    run_changelog_formatter(
        changelog_path=changelog_path,
        repo_root=repo_root,
        changelog_format_cmd=release_input.changelog_format_cmd,
    )


def _run_post_changelog_hooks_if_requested(
    *,
    repo_root: Path,
    changelog_path: Path,
    version: str,
    release_input: StartReleaseInput,
) -> None:
    """Run post-changelog hooks if configured.

    Hooks run automatically if post_changelog_hooks is provided.
    Falls back to legacy changelog_format_cmd if needed.

    Provides template variables to hooks:
      {version}         Bare semver (e.g. "1.2.3"), tag prefix stripped.
      {project_version} Full project version as tagged (e.g. "core-1.2.3").
      {changelog}       Absolute path to the changelog file.

    Args:
        repo_root: Repository root directory.
        changelog_path: Path to changelog file.
        version: Release version string (may include tag prefix, e.g. "core-1.2.3").
        release_input: Release configuration.
    """
    # New hooks take precedence - run automatically if defined
    if release_input.post_changelog_hooks:
        semver_version = version.removeprefix(release_input.tag_prefix)
        template_vars = {
            'version': semver_version,
            'project_version': version,
            'changelog': str(changelog_path),
        }
        run_post_changelog_hooks(
            hooks=release_input.post_changelog_hooks,
            repo_root=repo_root,
            template_vars=template_vars,
        )
        return

    # Legacy fallback
    if release_input.run_changelog_format:
        _format_changelog_if_requested(
            repo_root=repo_root,
            changelog_path=changelog_path,
            release_input=release_input,
        )


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

    version = _resolve_release_version(cliff=cliff, release_input=release_input)
    notes = cliff.generate_unreleased_notes(
        version=version,
        tag_pattern=release_input.tag_pattern,
        include_paths=release_input.include_paths,
    )

    if release_input.dry_run:
        return StartReleaseResult(
            version=version,
            release_notes_markdown=notes,
            release_branch=None,
            pr_url=None,
        )

    release_branch = f'release/{version}'
    create_and_checkout_branch(repo, name=release_branch)

    changelog = resolve_changelog_path(
        changelog_path=release_input.changelog_path,
        repo_root=info.root,
    )
    cliff.prepend_to_changelog(
        version=version,
        changelog_path=changelog,
        tag_pattern=release_input.tag_pattern,
        include_paths=release_input.include_paths,
    )
    _run_post_changelog_hooks_if_requested(
        repo_root=info.root,
        changelog_path=changelog,
        version=version,
        release_input=release_input,
    )

    # Stage files: for monorepo, only stage project files; otherwise stage all
    if release_input.project_path:
        # Monorepo: selective staging - only project directory
        rel_project_path = release_input.project_path.relative_to(info.root)
        repo.git.add(rel_project_path.as_posix())
    else:
        # Single repo: stage all modified/new files
        repo.git.add('-A')
    repo.index.commit(message=f'{release_input.title_prefix}{version}')

    push_set_upstream(
        repo,
        remote_name=release_input.remote_name,
        branch=release_branch,
    )

    # Add project-specific label for monorepo releases
    pr_labels = list(release_input.labels)
    if release_input.project_name:
        pr_labels.append(f'release:{release_input.project_name}')

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
            labels=pr_labels,
        ),
    )

    return StartReleaseResult(
        version=version,
        release_notes_markdown=notes,
        release_branch=release_branch,
        pr_url=pr_url,
    )
