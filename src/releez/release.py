from __future__ import annotations

import typing
from dataclasses import dataclass

if typing.TYPE_CHECKING:
    from pathlib import Path

    from git import Repo

from releez.cli_utils import _validate_semver_override
from releez.cliff import GitCliff, GitCliffBump
from releez.errors import (
    GitHubTokenRequiredError,
    GitRemoteUrlRequiredError,
)
from releez.git_repo import (
    checkout_remote_branch,
    commit_staged,
    create_and_checkout_branch,
    ensure_clean,
    fetch,
    open_repo,
    push_set_upstream,
)
from releez.github import PullRequestCreateRequest, create_pull_request
from releez.subproject import generate_tag_pattern
from releez.utils import (
    resolve_changelog_path,
    run_post_changelog_hooks,
)


@dataclass(frozen=True)
class StartReleaseResult:
    """Result of starting a release.

    Attributes:
        version (str): The computed next version.
        release_notes_markdown (str): The generated release notes markdown.
        release_branch (str | None): The created release branch, or None in
            dry-run mode.
        pr_url (str | None): The created PR URL, or None if not created.
    """

    version: str
    release_notes_markdown: str
    release_branch: str | None
    pr_url: str | None


@dataclass(frozen=True)
class StartReleaseInput:
    """Inputs for starting a release.

    Attributes:
        bump (GitCliffBump): Bump mode for git-cliff.
        version_override (str | None): Override the computed next version.
        base_branch (str): Base branch for the release PR.
        remote_name (str): Remote name to use.
        labels (list[str]): Labels to add to the PR.
        title_prefix (str): Prefix for PR title / commit message.
        changelog_path (str): Changelog file to prepend to.
        post_changelog_hooks (list[list[str]] | None): Hooks to run after changelog
            generation. Hooks run automatically if provided.
        create_pr (bool): If true, create a GitHub pull request.
        github_token (str | None): GitHub token for PR creation.
        dry_run (bool): If true, do not modify the repo; just output version and
            notes.
        project_name (str | None): Optional project name for monorepo support.
        include_paths (list[str] | None): Optional path filters for git-cliff.
        project_path (Path | None): Optional project directory path for selective
            staging.
        tag_prefix (str): Optional tag prefix used to strip the prefix from the hook
            {version} variable. The git-cliff tag pattern is derived from it.
        maintenance_tag_pattern (str | None): Optional explicit tag pattern override
            for maintenance branch releases.
    """

    bump: GitCliffBump
    version_override: str | None
    base_branch: str
    remote_name: str
    labels: list[str]
    title_prefix: str
    changelog_path: str
    post_changelog_hooks: list[list[str]] | None
    create_pr: bool
    github_token: str | None
    dry_run: bool
    # Monorepo support
    project_name: str | None = None
    include_paths: list[str] | None = None
    project_path: Path | None = None
    tag_prefix: str = ''
    maintenance_tag_pattern: str | None = None

    def __post_init__(self) -> None:
        """Validate version_override is bare semver if provided."""
        if self.version_override is not None:
            _validate_semver_override(self.version_override)

    @property
    def tag_pattern(self) -> str | None:
        """Derive git-cliff tag pattern.

        maintenance_tag_pattern takes priority (maintenance branch releases).
        Falls back to the tag_prefix-derived pattern for monorepo projects.
        Returns None for plain single-repo releases.
        """
        if self.maintenance_tag_pattern:
            return self.maintenance_tag_pattern
        return generate_tag_pattern(self.tag_prefix) if self.tag_prefix else None


@dataclass(frozen=True)
class _MaybeCreatePullRequestInput:
    """Inputs for optionally creating a pull request.

    Attributes:
        create_pr (bool): If true, create a GitHub pull request.
        github_token (str | None): GitHub token for PR creation.
        remote_name (str): Remote name used to infer the repo URL.
        base_branch (str): The base branch for the PR.
        head_branch (str): The head branch for the PR.
        title (str): The PR title.
        body (str): The PR body.
        labels (list[str]): Labels to add to the PR.
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
        repo (Repo): Git repository.
        pr_input (_MaybeCreatePullRequestInput): Pull request configuration.

    Returns:
        str | None: Pull request URL if created, None otherwise.

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
        cliff (GitCliff): git-cliff wrapper instance.
        release_input (StartReleaseInput): Release configuration.

    Returns:
        str: Version string to use for the release.
    """
    if release_input.version_override is not None:
        # Always prepend prefix: callers must pass bare semver ("1.2.3"), not "core-1.2.3".
        return f'{release_input.tag_prefix}{release_input.version_override}'
    version = cliff.compute_next_version(
        bump=release_input.bump,
        tag_pattern=release_input.tag_pattern,
        include_paths=release_input.include_paths,
    )
    # git-cliff returns bare semver (e.g. "0.1.0") when no tags match the
    # tag-pattern yet (first release of a new monorepo project). Prepend the
    # prefix so callers always receive the fully-qualified version ("core-0.1.0").
    if release_input.tag_prefix and not version.startswith(
        release_input.tag_prefix,
    ):
        version = f'{release_input.tag_prefix}{version}'
    return version


def _run_post_changelog_hooks_if_requested(
    *,
    repo_root: Path,
    changelog_path: Path,
    version: str,
    release_input: StartReleaseInput,
) -> None:
    """Run post-changelog hooks if configured.

    Provides template variables to hooks:
      {version}         Bare semver (e.g. "1.2.3"), tag prefix stripped.
      {project_version} Full project version as tagged (e.g. "core-1.2.3").
      {changelog}       Absolute path to the changelog file.

    Args:
        repo_root (Path): Repository root directory.
        changelog_path (Path): Path to changelog file.
        version (str): Release version string (may include a tag prefix).
        release_input (StartReleaseInput): Release configuration.
    """
    if not release_input.post_changelog_hooks:
        return
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


def start_release(
    release_input: StartReleaseInput,
) -> StartReleaseResult:
    """Start a release.

    Args:
        release_input (StartReleaseInput): Input parameters for starting the release.

    Returns:
        StartReleaseResult: Version, release notes, and optional branch/PR details.

    Raises:
        ReleezError: If a release step fails (git, git-cliff, or GitHub).
    """  # noqa: DOC502
    ctx = open_repo()
    repo, info = ctx.repo, ctx.info
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
    commit_staged(
        repo,
        message=f'{release_input.title_prefix}{version}',
    )

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
