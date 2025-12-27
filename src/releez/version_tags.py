from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from semver import VersionInfo

from releez.errors import InvalidReleaseVersionError


class AliasTags(StrEnum):
    """Which alias tags to include in addition to the exact version."""

    none = 'none'
    major = 'major'
    minor = 'minor'


@dataclass(frozen=True)
class VersionTags:
    """Computed tags for a release version.

    Attributes:
        exact: The exact version tag (e.g. `2.3.4`).
        major: The major tag (e.g. `v2`).
        minor: The major.minor tag (e.g. `v2.3`).
    """

    exact: str
    major: str
    minor: str


def compute_version_tags(*, version: str) -> VersionTags:
    """Compute exact/major/minor tags for a full release version.

    Args:
        version: The full release version (`x.y.z`).

    Returns:
        The computed tag strings.

    Raises:
        InvalidReleaseVersionError: If the version is not a full `x.y.z` release.
    """
    normalized = version.strip().removeprefix('v')

    try:
        parsed = VersionInfo.parse(normalized)
    except ValueError as exc:
        raise InvalidReleaseVersionError(version) from exc

    if parsed.prerelease is not None or parsed.build is not None:
        raise InvalidReleaseVersionError(version)

    return VersionTags(
        exact=normalized,
        major=f'v{parsed.major}',
        minor=f'v{parsed.major}.{parsed.minor}',
    )


def select_tags(*, tags: VersionTags, aliases: AliasTags) -> list[str]:
    """Select which tags to output/publish given an alias level."""
    if aliases == AliasTags.none:
        return [tags.exact]
    if aliases == AliasTags.major:
        return [tags.exact, tags.major]
    return [tags.exact, tags.major, tags.minor]
