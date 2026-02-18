from __future__ import annotations

from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

from git import Repo
from git.exc import GitCommandError, GitCommandNotFound

from releez.errors import (
    DirtyWorkingTreeError,
    GitBranchExistsError,
    GitRemoteBranchNotFoundError,
    GitRemoteNotFoundError,
    GitRepoRootResolveError,
    GitTagExistsError,
    MissingCliError,
)

GIT_BIN = 'git'


@dataclass(frozen=True)
class RepoInfo:
    """Information about a Git repository.

    Attributes:
        root: The root path of the repository.
        remote_url: The URL of the 'origin' remote.
        active_branch: The name of the currently active branch, or None if in
            detached HEAD state.
    """

    root: Path
    remote_url: str
    active_branch: str | None


@dataclass(frozen=True)
class RepoContext:
    """Bundle a repository with its derived metadata.

    Attributes:
        repo: The GitPython repository instance.
        info: Derived repository metadata (root, remote, active branch).
    """

    repo: Repo
    info: RepoInfo


def open_repo(*, cwd: Path | None = None) -> RepoContext:
    """Open a Git repository and gather information about it.

    Args:
        cwd: The working directory to start searching for the repository.

    Returns:
        A RepoContext containing the Repo object and RepoInfo dataclass.

    Raises:
        MissingCliError: If the `git` CLI is not available.
        GitRepoRootResolveError: If the repository root cannot be determined.
    """
    repo = Repo(cwd or Path.cwd(), search_parent_directories=True)
    try:
        root = Path(
            repo.working_tree_dir or repo.git.rev_parse('--show-toplevel'),
        )
    except GitCommandNotFound as exc:  # pragma: no cover
        raise MissingCliError(GIT_BIN) from exc
    except GitCommandError as exc:  # pragma: no cover
        raise GitRepoRootResolveError from exc

    # Not all repos have an origin remote; default to empty string.
    remote_url = ''
    with suppress(AttributeError, IndexError):
        remote_url = repo.remotes.origin.url

    active_branch: str | None
    try:
        active_branch = repo.active_branch.name
    except TypeError:
        active_branch = None  # detached HEAD

    info = RepoInfo(
        root=root,
        remote_url=remote_url,
        active_branch=active_branch,
    )
    return RepoContext(repo=repo, info=info)


def ensure_clean(repo: Repo) -> None:
    """Ensure the repository working tree is clean.

    Args:
        repo: The Git repository.

    Raises:
        DirtyWorkingTreeError: If the repository has uncommitted changes.
    """
    if repo.is_dirty(untracked_files=True):
        raise DirtyWorkingTreeError


def fetch(repo: Repo, *, remote_name: str) -> None:
    """Fetch updates from the remote (including tags).

    Args:
        repo: The Git repository.
        remote_name: The remote name to fetch from.

    Raises:
        GitRemoteNotFoundError: If the remote does not exist.
    """
    try:
        _ = repo.remotes[remote_name]
    except IndexError as exc:
        raise GitRemoteNotFoundError(remote_name) from exc
    repo.git.fetch(remote_name, '--tags', '--prune')


def checkout_remote_branch(
    repo: Repo,
    *,
    remote_name: str,
    branch: str,
) -> None:
    """Check out the given remote branch as a detached HEAD.

    Args:
        repo: The Git repository.
        remote_name: The remote name.
        branch: The branch name on the remote.

    Raises:
        MissingCliError: If the `git` CLI is not available.
        GitRemoteBranchNotFoundError: If the remote branch does not exist.
    """
    ref = f'{remote_name}/{branch}'
    try:
        repo.git.rev_parse('--verify', ref)
    except GitCommandNotFound as exc:  # pragma: no cover
        raise MissingCliError(GIT_BIN) from exc
    except GitCommandError as exc:
        raise GitRemoteBranchNotFoundError(
            remote_name=remote_name,
            branch=branch,
        ) from exc
    repo.git.checkout(ref)


def create_and_checkout_branch(repo: Repo, *, name: str) -> None:
    """Create and check out a new local branch.

    Args:
        repo: The Git repository.
        name: The new branch name.

    Raises:
        MissingCliError: If the `git` CLI is not available.
        GitBranchExistsError: If the local branch already exists.
    """
    try:
        repo.git.rev_parse('--verify', name)
    except GitCommandNotFound as exc:  # pragma: no cover
        raise MissingCliError(GIT_BIN) from exc
    except GitCommandError:
        repo.git.checkout('-b', name)
        return

    raise GitBranchExistsError(name)


def commit_file(repo: Repo, *, path: Path, message: str) -> None:
    """Stage and commit a file with the given message.

    Args:
        repo: The Git repository.
        path: The path to the file to stage and commit.
        message: The commit message.
    """
    root = Path(repo.working_tree_dir or '.').resolve()
    abs_path = path.resolve()
    try:
        rel_path = abs_path.relative_to(root)
        pathspec = str(rel_path)
    except ValueError:
        pathspec = str(abs_path)
    repo.index.add([pathspec])
    repo.index.commit(message)


def push_set_upstream(repo: Repo, *, remote_name: str, branch: str) -> None:
    """Push a branch and set upstream on the remote.

    Args:
        repo: The Git repository.
        remote_name: The remote name to push to.
        branch: The branch to push.
    """
    repo.git.push('-u', remote_name, branch)


def create_tags(repo: Repo, *, tags: list[str], force: bool) -> None:
    """Create git tags pointing at HEAD.

    Args:
        repo: The Git repository.
        tags: The tag names to create.
        force: If true, overwrite existing tags.

    Raises:
        GitTagExistsError: If a tag exists and force is false.
    """
    existing = {t.name for t in repo.tags}
    for tag in tags:
        if tag in existing and not force:
            raise GitTagExistsError(tag)
        if force:
            repo.git.tag('-f', tag)
        else:
            repo.create_tag(tag)


def push_tags(
    repo: Repo,
    *,
    remote_name: str,
    tags: list[str],
    force: bool,
) -> None:
    """Push git tags to a remote.

    Args:
        repo: The Git repository.
        remote_name: The remote to push to.
        tags: The tag names to push.
        force: If true, force-update tags on the remote.
    """
    if not tags:
        return
    if force:
        repo.git.push('--force', remote_name, *tags)
        return
    repo.git.push(remote_name, *tags)
