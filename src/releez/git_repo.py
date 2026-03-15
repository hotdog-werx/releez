from __future__ import annotations

import re
import typing
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

if typing.TYPE_CHECKING:
    from releez.subproject import SubProject

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


def _build_commit_to_tags_map(
    repo: Repo,
    compiled_pattern: re.Pattern[str],
) -> dict[str, list[str]]:
    """Build mapping of commit SHA to matching tag names.

    Args:
        repo: Git repository.
        compiled_pattern: Compiled regex to match tag names.

    Returns:
        Dict mapping commit SHA to list of matching tag names on that commit.
    """
    commit_to_tags: dict[str, list[str]] = {}
    for tag in repo.tags:
        if compiled_pattern.match(tag.name):
            sha = tag.commit.hexsha
            if sha not in commit_to_tags:
                commit_to_tags[sha] = []
            commit_to_tags[sha].append(tag.name)
    return commit_to_tags


def _find_tag_by_topology(
    repo: Repo,
    commit_to_tags: dict[str, list[str]],
) -> str | None:
    """Find latest tag by walking commit history from HEAD.

    More reliable than date-based sorting when tags are created in
    rapid succession and share the same timestamp.

    Args:
        repo: Git repository.
        commit_to_tags: Mapping of commit SHA to tag names.

    Returns:
        Most recent tag name, or None if iteration fails.
    """
    try:
        for commit in repo.iter_commits():
            if commit.hexsha in commit_to_tags:
                tags = commit_to_tags[commit.hexsha]
                tags.sort(reverse=True)
                return tags[0]
    except Exception:  # noqa: BLE001
        # Fallback to date-based sorting if commit iteration fails
        return None
    return None


def _find_tag_by_date(
    repo: Repo,
    compiled_pattern: re.Pattern[str],
) -> str | None:
    """Find latest tag by commit date (fallback for topology failure).

    Args:
        repo: Git repository.
        compiled_pattern: Compiled regex to match tag names.

    Returns:
        Most recently committed tag name, or None if no tags match.
    """
    all_tags = [(tag, tag.commit.committed_datetime) for tag in repo.tags if compiled_pattern.match(tag.name)]
    if all_tags:
        all_tags.sort(key=lambda x: x[1], reverse=True)
        return all_tags[0][0].name
    return None


def find_latest_tag_matching_pattern(repo: Repo, *, pattern: str) -> str | None:
    r"""Find the latest tag matching the given regex pattern.

    Args:
        repo: Git repository.
        pattern: Regex pattern to match tags (e.g., '^core-([0-9]+\.[0-9]+\.[0-9]+)$').

    Returns:
        The most recent tag name matching the pattern, or None if no tags match.
    """
    compiled_pattern = re.compile(pattern)
    commit_to_tags = _build_commit_to_tags_map(repo, compiled_pattern)

    if not commit_to_tags:
        return None

    # Try topology-based search first, fallback to date-based
    return _find_tag_by_topology(repo, commit_to_tags) or _find_tag_by_date(
        repo,
        compiled_pattern,
    )


def _has_commits_for_path(repo: Repo, range_spec: str, path: str) -> bool:
    """Check if any commits touched the given path.

    Args:
        repo: Git repository.
        range_spec: Git range specification (e.g., "tag..HEAD").
        path: File or directory path to check.

    Returns:
        True if commits exist for the path, False otherwise.
    """
    try:
        commits = repo.git.log(range_spec, '--format=%H', '--', path)
        return bool(commits.strip())
    except GitCommandError:
        return False


def _project_has_changes(
    repo: Repo,
    project: SubProject,
    base_branch: str,
) -> bool:
    """Check if a project has unreleased changes.

    Args:
        repo: Git repository.
        project: SubProject to check.
        base_branch: Base branch to compare against.

    Returns:
        True if project has unreleased changes, False otherwise.
    """
    range_spec = _get_range_spec(repo, project, base_branch)
    paths = _get_monitored_paths(project, repo)

    return any(_has_commits_for_path(repo, range_spec, path) for path in paths)


def detect_changed_projects(
    *,
    repo: Repo,
    base_branch: str,
    projects: list[SubProject],
) -> list[SubProject]:
    """Detect which projects have unreleased changes.

    For each project:
    1. Find latest tag matching its tag pattern
    2. Check if commits since that tag touched monitored paths
    3. Monitored paths = project.path + project.include_paths

    Args:
        repo: Git repository.
        base_branch: Base branch to compare against.
        projects: SubProject instances to check.

    Returns:
        Projects with unreleased changes.
    """
    return [p for p in projects if _project_has_changes(repo, p, base_branch)]


def _get_range_spec(repo: Repo, project: SubProject, base_branch: str) -> str:
    """Get git range specification for project.

    Args:
        repo: Git repository.
        project: SubProject to get range for.
        base_branch: Base branch name.

    Returns:
        Git range spec (e.g., "tag..HEAD" or just "HEAD").
    """
    latest_tag = find_latest_tag_matching_pattern(
        repo,
        pattern=project.tag_pattern,
    )
    return f'{latest_tag}..{base_branch}' if latest_tag else base_branch


def _get_monitored_paths(project: SubProject, repo: Repo) -> list[str]:
    """Get all paths monitored by a project.

    Args:
        project: SubProject to get paths for.
        repo: Git repository.

    Returns:
        List of paths (project path + include_paths).
    """
    rel_path = str(project.path.relative_to(Path(repo.working_tree_dir or '.')))
    return [rel_path, *project.include_paths]


def _collect_changed_files(
    repo: Repo,
    range_spec: str,
    paths: list[str],
) -> set[str]:
    """Collect changed files for given paths.

    Args:
        repo: Git repository.
        range_spec: Git range specification.
        paths: Paths to check for changes.

    Returns:
        Set of changed file paths.
    """
    changed_files = set()
    for path in paths:
        try:
            files = repo.git.diff(range_spec, '--name-only', '--', path)
            if files.strip():
                changed_files.update(files.strip().split('\n'))
        except GitCommandError:
            continue
    return changed_files


def get_changed_files_per_project(
    *,
    repo: Repo,
    base_branch: str,
    projects: list[SubProject],
) -> dict[str, list[str]]:
    """Get the list of changed files for each project.

    Args:
        repo: The Git repository.
        base_branch: The base branch to compare against.
        projects: List of SubProject instances to check.

    Returns:
        Dictionary mapping project name to list of changed file paths.
    """
    result = {}
    for project in projects:
        range_spec = _get_range_spec(repo, project, base_branch)
        paths = _get_monitored_paths(project, repo)
        changed_files = _collect_changed_files(repo, range_spec, paths)

        if changed_files:
            result[project.name] = sorted(changed_files)

    return result


@dataclass(frozen=True)
class DetectedRelease:
    """Information parsed from a release branch name.

    Attributes:
        version: Full release version string (e.g., "1.2.3" or "core-1.2.3" for monorepo).
        semver_version: Plain semver without tag prefix (e.g., "1.2.3"). Equal to version for single-repo.
        project_name: Project name for monorepo, None for single-repo.
        branch_name: Original branch name.
    """

    version: str
    semver_version: str
    project_name: str | None
    branch_name: str


def detect_release_from_branch(
    *,
    branch_name: str,
    projects: list[SubProject],
) -> DetectedRelease | None:
    """Detect release information from a branch name.

    Parses branch names in the format:
    - Single repo: "release/1.2.3"
    - Monorepo: "release/core-1.2.3" (with tag prefix)

    The function matches the version string against configured project
    tag prefixes to determine which project the release belongs to.
    If no matching prefix is found, treats it as a single-repo release.

    Args:
        branch_name: Branch name to parse.
        projects: Configured projects, empty for single-repo.

    Returns:
        Parsed release information, or None if not a release branch.

    Examples:
        >>> # Single repo
        >>> detect_release_from_branch(branch_name="release/1.2.3", projects=[])
        DetectedRelease(version="1.2.3", project_name=None, branch_name="release/1.2.3")

        >>> # Monorepo
        >>> core_project = SubProject(...)  # with tag_prefix="core-"
        >>> detect_release_from_branch(
        ...     branch_name="release/core-1.2.3",
        ...     projects=[core_project],
        ... )
        DetectedRelease(version="core-1.2.3", project_name="core", branch_name="release/core-1.2.3")
    """
    # Check if branch matches release pattern
    if not branch_name.startswith('release/'):
        return None

    # Extract version part after "release/"
    version_with_prefix = branch_name.removeprefix('release/')

    # If no projects configured, this is a single-repo release
    if not projects:
        return DetectedRelease(
            version=version_with_prefix,
            semver_version=version_with_prefix,
            project_name=None,
            branch_name=branch_name,
        )

    # Try to match against project tag prefixes
    for project in projects:
        if project.tag_prefix and version_with_prefix.startswith(
            project.tag_prefix,
        ):
            return DetectedRelease(
                version=version_with_prefix,
                semver_version=version_with_prefix.removeprefix(
                    project.tag_prefix,
                ),
                project_name=project.name,
                branch_name=branch_name,
            )

    # No matching project found - could be a single-repo release in a monorepo config
    return DetectedRelease(
        version=version_with_prefix,
        semver_version=version_with_prefix,
        project_name=None,
        branch_name=branch_name,
    )
