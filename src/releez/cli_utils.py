from __future__ import annotations

from typing import TYPE_CHECKING

from semver import VersionInfo

from releez.cliff import GitCliff
from releez.console import err_console
from releez.errors import InvalidReleaseVersionError

if TYPE_CHECKING:
    from pathlib import Path

    from releez.subproject import SubProject


def _exit(message: str | None = None) -> SystemExit:
    if message is not None:
        err_console.print(message, style='bold red', markup=False)
    return SystemExit(1)


def _project_relative_glob(*, project: SubProject, repo_root: Path) -> str:
    rel_path = project.path.relative_to(repo_root)
    return f'{rel_path.as_posix()}/**'


def _project_include_paths(
    *,
    project: SubProject,
    repo_root: Path,
) -> list[str]:
    return [
        _project_relative_glob(project=project, repo_root=repo_root),
        *project.include_paths,
    ]


def _resolve_release_version(
    *,
    repo_root: Path,
    version_override: str | None,
    tag_pattern: str | None = None,
    include_paths: list[str] | None = None,
    tag_prefix: str = '',
) -> VersionInfo:
    """Resolve release version from override or git-cliff, parsed as VersionInfo.

    When tag_prefix is given, git-cliff may return the full tag (e.g. "core-1.1.0")
    for prefixed tag patterns; the prefix is stripped before semver parsing.
    """
    if version_override is not None:
        raw = version_override
    else:
        cliff = GitCliff(repo_root=repo_root)
        raw = cliff.compute_next_version(
            bump='auto',
            tag_pattern=tag_pattern,
            include_paths=include_paths,
        )
    if tag_prefix and raw.startswith(tag_prefix):
        raw = raw.removeprefix(tag_prefix)
    try:
        return VersionInfo.parse(raw)
    except ValueError as exc:
        raise InvalidReleaseVersionError(raw) from exc
