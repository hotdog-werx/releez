from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from releez.errors import ReleezError
from releez.settings import ProjectConfig, ReleezHooks, ReleezSettings

if TYPE_CHECKING:
    from pathlib import Path

    from releez.version_tags import AliasVersions


class MonorepoValidationError(ReleezError):
    """Error raised when monorepo configuration is invalid."""


@dataclass(frozen=True)
class SubProject:
    """Represents a subproject in a monorepo.

    Attributes:
        name: Unique project identifier.
        path: Absolute path to project directory.
        changelog_path: Absolute path to changelog file.
        tag_prefix: Git tag prefix (e.g., "core-").
        tag_pattern: Auto-generated regex for matching tags.
        alias_versions: Version alias strategy (major/minor/none).
        hooks: Per-project hooks, merged with global hooks.
        include_paths: Additional paths to monitor for changes.
    """

    name: str
    path: Path
    changelog_path: Path
    tag_prefix: str
    tag_pattern: str
    alias_versions: AliasVersions
    hooks: ReleezHooks
    include_paths: list[str]

    @staticmethod
    def from_config(
        config: ProjectConfig,
        repo_root: Path,
        global_settings: ReleezSettings,
    ) -> SubProject:
        """Create SubProject from configuration with validation.

        Validates that paths exist and are within the repository,
        generates the tag pattern from the prefix, and merges
        project-specific hooks with global hooks (global first).

        Args:
            config: Project configuration from TOML.
            repo_root: Git repository root directory.
            global_settings: Global releez settings.

        Returns:
            Validated SubProject instance.

        Raises:
            MonorepoValidationError: If configuration is invalid.
        """
        project_path = _validate_project_path(config, repo_root)
        changelog_path = _validate_changelog_path(config, project_path)
        _validate_include_paths(config, repo_root)

        tag_pattern = generate_tag_pattern(config.tag_prefix)
        merged_hooks = _merge_hooks(global_settings, config)

        return SubProject(
            name=config.name,
            path=project_path,
            changelog_path=changelog_path,
            tag_prefix=config.tag_prefix,
            tag_pattern=tag_pattern,
            alias_versions=config.alias_versions or global_settings.alias_versions,
            hooks=merged_hooks,
            include_paths=config.include_paths,
        )


def _validate_project_path(config: ProjectConfig, repo_root: Path) -> Path:
    """Validate and return project path.

    Args:
        config: Project configuration.
        repo_root: Repository root directory.

    Returns:
        Absolute project path.

    Raises:
        MonorepoValidationError: If path doesn't exist, isn't a directory, or is outside repo.
    """
    project_path = repo_root / config.path
    if not project_path.exists():
        msg = f"Project '{config.name}' path does not exist: {project_path}\nExpected directory at: {config.path}"
        raise MonorepoValidationError(msg)

    if not project_path.is_dir():
        msg = f"Project '{config.name}' path is not a directory: {project_path}"
        raise MonorepoValidationError(msg)

    try:
        project_path.relative_to(repo_root)
    except ValueError as e:
        msg = f"Project '{config.name}' path is outside repository: {project_path}\nRepository root: {repo_root}"
        raise MonorepoValidationError(msg) from e

    return project_path


def _validate_changelog_path(config: ProjectConfig, project_path: Path) -> Path:
    """Validate and return changelog path.

    Args:
        config: Project configuration.
        project_path: Absolute project path.

    Returns:
        Absolute changelog path.

    Raises:
        MonorepoValidationError: If changelog directory doesn't exist.
    """
    changelog_path = project_path / config.changelog_path
    changelog_dir = changelog_path.parent
    if not changelog_dir.exists():
        msg = (
            f"Project '{config.name}' changelog directory does not exist: "
            f'{changelog_dir}\n'
            f'Expected directory for: {config.changelog_path}'
        )
        raise MonorepoValidationError(msg)
    return changelog_path


def _validate_include_paths(config: ProjectConfig, repo_root: Path) -> None:
    """Validate include paths are within the repo.

    Non-existent paths are allowed — they simply match no commits (e.g. a lock
    file that hasn't been created yet).  Only paths that escape the repository
    root are rejected, as those would be a genuine misconfiguration.

    Args:
        config: Project configuration.
        repo_root: Repository root directory.

    Raises:
        MonorepoValidationError: If any include path is outside the repository.
    """
    for include_path in config.include_paths:
        full_include_path = repo_root / include_path
        try:
            full_include_path.relative_to(repo_root)
        except ValueError as e:
            msg = f"Project '{config.name}' include-path is outside repository: {include_path}"
            raise MonorepoValidationError(msg) from e


def _merge_hooks(
    global_settings: ReleezSettings,
    config: ProjectConfig,
) -> ReleezHooks:
    """Merge global and project-specific hooks.

    Args:
        global_settings: Global releez settings.
        config: Project configuration.

    Returns:
        Merged hooks with global hooks first, then project hooks.
    """
    return ReleezHooks(
        post_changelog=[
            *global_settings.hooks.post_changelog,
            *config.hooks.post_changelog,
        ],
    )


def generate_tag_pattern(tag_prefix: str) -> str:
    r"""Generate regex pattern for git tags with the given prefix.

    Args:
        tag_prefix: Tag prefix (e.g., "core-", "ui-", or "" for no prefix).

    Returns:
        Regex pattern like "^core-([0-9]+\.[0-9]+\.[0-9]+)$"

    Raises:
        MonorepoValidationError: If tag_prefix contains invalid characters.

    Examples:
        >>> generate_tag_pattern("core-")
        '^core-([0-9]+\\.[0-9]+\\.[0-9]+)$'
        >>> generate_tag_pattern("")
        '^([0-9]+\\.[0-9]+\\.[0-9]+)$'
    """
    # Validate prefix: only alphanumeric, dash, underscore, slash
    if tag_prefix and not re.match(r'^[a-zA-Z0-9_/-]*$', tag_prefix):
        msg = f"Invalid tag prefix '{tag_prefix}'. Only alphanumeric, dash, underscore, and slash characters allowed."
        raise MonorepoValidationError(msg)

    # Generate pattern (no escaping needed - git-cliff expects raw regex)
    return f'^{tag_prefix}([0-9]+\\.[0-9]+\\.[0-9]+)$'


def _check_duplicate_names(projects: list[SubProject]) -> None:
    """Check for duplicate project names.

    Args:
        projects: SubProject instances to validate.

    Raises:
        MonorepoValidationError: If duplicate names found.
    """
    names = [p.name for p in projects]
    duplicates = {name for name in names if names.count(name) > 1}
    if duplicates:
        msg = f'Duplicate project names found: {", ".join(sorted(duplicates))}'
        raise MonorepoValidationError(msg)


def _check_duplicate_prefixes(projects: list[SubProject]) -> None:
    """Check for duplicate tag prefixes.

    Args:
        projects: SubProject instances to validate.

    Raises:
        MonorepoValidationError: If duplicate prefixes found.
    """
    prefixes = [p.tag_prefix for p in projects]
    duplicate_prefixes = {prefix for prefix in prefixes if prefix and prefixes.count(prefix) > 1}
    if duplicate_prefixes:
        msg = (
            f'Duplicate tag prefixes found: {", ".join(sorted(duplicate_prefixes))}\n'
            f'Each project must have a unique tag prefix to avoid tag collisions.'
        )
        raise MonorepoValidationError(msg)


def _check_overlapping_paths(paths: list[tuple[str, Path]]) -> None:
    """Check if any project paths overlap.

    Args:
        paths: List of (project_name, project_path) tuples.

    Raises:
        MonorepoValidationError: If any paths overlap.
    """
    for i, (name1, path1) in enumerate(paths):
        for name2, path2 in paths[i + 1 :]:
            # Check if path1 is a parent of path2 or vice versa
            try:
                path2.relative_to(path1)
                msg = f"Project paths overlap: '{name1}' ({path1}) contains '{name2}' ({path2})"
                raise MonorepoValidationError(msg)
            except ValueError:
                pass

            try:
                path1.relative_to(path2)
                msg = f"Project paths overlap: '{name2}' ({path2}) contains '{name1}' ({path1})"
                raise MonorepoValidationError(msg)
            except ValueError:
                pass


def validate_projects(projects: list[SubProject]) -> None:
    """Validate that projects don't have conflicts.

    Args:
        projects: List of SubProject instances to validate.

    Raises:
        MonorepoValidationError: If projects have duplicate names, tag prefixes,
            or overlapping paths.
    """
    if not projects:
        return

    _check_duplicate_names(projects)
    _check_duplicate_prefixes(projects)

    paths = [(p.name, p.path) for p in projects]
    _check_overlapping_paths(paths)
