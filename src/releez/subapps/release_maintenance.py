from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from releez.errors import (
    InvalidMaintenanceBranchRegexError,
    MaintenanceBranchMajorMismatchError,
)

if TYPE_CHECKING:
    from semver import VersionInfo

    from releez.subproject import SubProject


@dataclass(frozen=True)
class MaintenanceContext:
    """Detected maintenance branch context.

    Attributes:
        branch: The maintenance branch name (e.g. "support/1.x").
        major: The major version number of the maintenance line.
        tag_pattern: The git-cliff tag pattern scoped to this major.
    """

    branch: str
    major: int
    tag_pattern: str

    def ensure_version_matches(self, version: VersionInfo) -> None:
        """Raise MaintenanceBranchMajorMismatchError if version.major != self.major."""
        if version.major != self.major:
            raise MaintenanceBranchMajorMismatchError(
                branch=self.branch,
                major=self.major,
                version=str(version),
            )


def _maintenance_major(*, branch: str, regex: str) -> int | None:
    """Extract the major version integer from a branch name via regex.

    Returns the major version if the branch matches, or None if no match.

    Raises:
        InvalidMaintenanceBranchRegexError: If the regex is invalid, missing
            the 'major' named capture group, or captures a non-integer value.
    """
    try:
        pattern = re.compile(regex)
    except re.error as exc:
        raise InvalidMaintenanceBranchRegexError(
            pattern=regex,
            reason=str(exc),
        ) from exc

    if 'major' not in pattern.groupindex:
        raise InvalidMaintenanceBranchRegexError(
            pattern=regex,
            reason='missing named capture group "major"',
        )

    match = pattern.match(branch)
    if not match:
        return None

    major_str = match.group('major')
    try:
        return int(major_str)
    except ValueError as exc:
        raise InvalidMaintenanceBranchRegexError(
            pattern=regex,
            reason=f'invalid major value {major_str!r}: must be an integer',
        ) from exc


def _maintenance_tag_pattern(major: int) -> str:
    """Return a git-cliff tag pattern scoped to a given major version."""
    return f'^{major}\\.[0-9]+\\.[0-9]+$'


def _maintenance_context(
    *,
    branch: str | None,
    regex: str,
) -> MaintenanceContext | None:
    """Detect and build a maintenance context from the current branch name.

    Returns None if branch is None or does not match the maintenance regex.
    """
    if branch is None:
        return None
    major = _maintenance_major(branch=branch, regex=regex)
    if major is None:
        return None
    return MaintenanceContext(
        branch=branch,
        major=major,
        tag_pattern=_maintenance_tag_pattern(major),
    )


def _monorepo_maintenance_tag_pattern(prefix: str, major: int) -> str:
    """Return a git-cliff tag pattern scoped to a prefix and major version."""
    return f'^{re.escape(prefix)}{major}\\.[0-9]+\\.[0-9]+$'


def _monorepo_context_from_prefix_regex(
    branch: str,
    projects: list[SubProject],
    compiled: re.Pattern[str],
) -> tuple[SubProject, MaintenanceContext] | None:
    """Detect project/major from a compiled regex containing (?P<prefix>...) and (?P<major>...) groups."""
    m = compiled.match(branch)
    if m is None:
        return None
    prefix_value = m.group('prefix') or ''
    try:
        major = int(m.group('major'))
    except (ValueError, KeyError):
        return None
    project = next((p for p in projects if p.tag_prefix == prefix_value), None)
    if project is None:
        return None
    ctx = MaintenanceContext(
        branch=branch,
        major=major,
        tag_pattern=_monorepo_maintenance_tag_pattern(
            project.tag_prefix,
            major,
        ),
    )
    return project, ctx


def _monorepo_maintenance_context(
    branch: str | None,
    projects: list[SubProject],
    *,
    regex: str,
) -> tuple[SubProject, MaintenanceContext] | None:
    r"""Detect a maintenance branch in monorepo mode.

    If ``regex`` contains a ``(?P<prefix>...)`` group, uses the global regex to
    detect both the project (by matching prefix against tag_prefix) and the major.
    Otherwise falls back to per-project patterns of the form
    ``^support/{re.escape(tag_prefix)}(?P<major>\d+)\.x$``.

    Returns the first matching (SubProject, MaintenanceContext) pair, or None.
    """
    if branch is None:
        return None
    try:
        compiled = re.compile(regex)
    except re.error:
        return None
    if 'prefix' in compiled.groupindex:
        return _monorepo_context_from_prefix_regex(branch, projects, compiled)
    for project in projects:
        if not project.tag_prefix:
            continue
        pattern = rf'^support/{re.escape(project.tag_prefix)}(?P<major>\d+)\.x$'
        match = re.match(pattern, branch)
        if match:
            major = int(match.group('major'))
            ctx = MaintenanceContext(
                branch=branch,
                major=major,
                tag_pattern=_monorepo_maintenance_tag_pattern(
                    project.tag_prefix,
                    major,
                ),
            )
            return project, ctx
    return None


def _validate_maintenance_version(
    *,
    version: str,
    maintenance_ctx: MaintenanceContext,
) -> None:
    """Validate that the release version major matches the maintenance branch.

    Raises:
        MaintenanceBranchMajorMismatchError: If the major does not match.
    """
    version_parts = version.split('.')
    try:
        version_major = int(version_parts[0])
    except (ValueError, IndexError) as exc:
        raise MaintenanceBranchMajorMismatchError(
            branch=maintenance_ctx.branch,
            major=maintenance_ctx.major,
            version=version,
        ) from exc
    if version_major != maintenance_ctx.major:
        raise MaintenanceBranchMajorMismatchError(
            branch=maintenance_ctx.branch,
            major=maintenance_ctx.major,
            version=version,
        )
