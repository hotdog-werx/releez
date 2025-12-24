from collections.abc import Sequence
from pathlib import Path


class ReleezError(RuntimeError):
    """Base error for Releez."""


class MissingCliError(ReleezError):
    """Raised when a required CLI executable is missing."""

    cli_names: list[str]

    def __init__(self, cli_names: str | Sequence[str]) -> None:
        self.cli_names = [cli_names] if isinstance(cli_names, str) else list(cli_names)
        if len(self.cli_names) == 1:
            message = f'Required CLI {self.cli_names[0]!r} is not installed or not on PATH.'
        else:
            joined = ', '.join(repr(name) for name in self.cli_names)
            message = f'Required CLIs {joined} are not installed or not on PATH.'
        super().__init__(message)


class ExternalCommandError(ReleezError):
    """Raised when an external command returns a non-zero status."""

    args: list[str]
    returncode: int
    stderr: str

    def __init__(
        self,
        *,
        args: Sequence[str],
        returncode: int,
        stderr: str | None = None,
    ) -> None:
        self.args = list(args)
        self.returncode = returncode
        self.stderr = (stderr or '').strip()

        cmd = ' '.join(self.args)
        message = f'Command failed ({self.returncode}): {cmd}'
        if self.stderr:
            message = f'{message}\n{self.stderr}'
        super().__init__(message)


class GitRepoRootResolveError(ReleezError):
    """Raised when the git repository root cannot be determined."""

    def __init__(self) -> None:
        super().__init__('Failed to resolve git repository root.')


class DirtyWorkingTreeError(ReleezError):
    """Raised when the working tree is not clean."""

    def __init__(self) -> None:
        super().__init__(
            'Working tree is not clean. Commit or stash changes before running.',
        )


class GitRemoteNotFoundError(ReleezError):
    """Raised when a configured git remote does not exist."""

    remote_name: str

    def __init__(self, remote_name: str) -> None:
        self.remote_name = remote_name
        super().__init__(f'Remote {remote_name!r} does not exist.')


class GitRemoteBranchNotFoundError(ReleezError):
    """Raised when a remote branch does not exist."""

    ref: str

    def __init__(self, *, remote_name: str, branch: str) -> None:
        self.ref = f'{remote_name}/{branch}'
        super().__init__(f'Remote branch {self.ref!r} does not exist.')


class GitBranchExistsError(ReleezError):
    """Raised when attempting to create a branch that already exists."""

    branch: str

    def __init__(self, branch: str) -> None:
        self.branch = branch
        super().__init__(f'Local branch {branch!r} already exists.')


class GitCliffVersionComputeError(ReleezError):
    """Raised when git-cliff cannot compute the next version."""

    def __init__(self) -> None:
        super().__init__('Failed to compute next version via git-cliff.')


class ChangelogNotFoundError(ReleezError):
    """Raised when the changelog file is missing."""

    changelog_path: Path

    def __init__(self, changelog_path: Path) -> None:
        self.changelog_path = changelog_path
        super().__init__(f'Changelog file does not exist: {changelog_path}')


class GitHubTokenRequiredError(ReleezError):
    """Raised when a GitHub token is required but not provided."""

    def __init__(self) -> None:
        super().__init__(
            'GitHub token is required to create a PR; pass --github-token or set GITHUB_TOKEN.',
        )


class GitRemoteUrlRequiredError(ReleezError):
    """Raised when a remote URL is needed but missing."""

    remote_name: str

    def __init__(self, remote_name: str) -> None:
        self.remote_name = remote_name
        super().__init__(
            f'Remote URL is required to create a PR; ensure remote {remote_name!r} exists.',
        )


class InvalidGitHubRemoteError(ReleezError):
    """Raised when a remote URL cannot be mapped to a GitHub repo."""

    remote_url: str

    def __init__(self, remote_url: str) -> None:
        self.remote_url = remote_url
        super().__init__(
            f'Could not infer GitHub repo from remote URL: {remote_url}\n'
            'Use an origin remote pointing at github.com (SSH or HTTPS).',
        )


class MissingGitHubDependencyError(ReleezError):
    """Raised when PyGithub is not available but PR creation was requested."""

    def __init__(self) -> None:
        super().__init__(
            'PyGithub is required for PR creation but is not available.',
        )


class BuildNumberRequiredError(ReleezError):
    """Raised when a prerelease build is missing a build number."""

    def __init__(self) -> None:
        super().__init__(
            'Build number is required for prerelease builds; pass --build-number or set RELEEZ_BUILD_NUMBER.',
        )


class PrereleaseNumberRequiredError(ReleezError):
    """Raised when a prerelease build is missing a prerelease number."""

    def __init__(self) -> None:
        super().__init__(
            'Prerelease number is required for prerelease builds; '
            'pass --prerelease-number or set RELEEZ_PRERELEASE_NUMBER.',
        )


class InvalidReleaseVersionError(ReleezError):
    """Raised when a version is not a full release `x.y.z`."""

    version: str

    def __init__(self, version: str) -> None:
        self.version = version
        super().__init__(
            f'Expected a full release version like `2.3.4`; got {version!r}.',
        )


class AliasTagsRequireFullReleaseError(ReleezError):
    """Raised when alias tags are requested for a non-full-release build."""

    def __init__(self) -> None:
        super().__init__(
            'Alias tags are only supported for full releases (use --is-full-release).',
        )


class GitTagExistsError(ReleezError):
    """Raised when attempting to create a tag that already exists."""

    tag: str

    def __init__(self, tag: str) -> None:
        self.tag = tag
        super().__init__(
            f'Git tag already exists: {tag!r} (use --force to update).',
        )


class InvalidPrereleaseTypeError(ReleezError):
    """Raised when a prerelease type is invalid for the chosen scheme."""

    prerelease_type: str
    scheme: str

    def __init__(self, prerelease_type: str, *, scheme: str) -> None:
        self.prerelease_type = prerelease_type
        self.scheme = scheme
        super().__init__(
            f'Prerelease type {prerelease_type!r} is not supported for scheme {scheme!r}.',
        )
