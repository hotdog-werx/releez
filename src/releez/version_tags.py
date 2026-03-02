from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from semver import VersionInfo

from releez.errors import InvalidReleaseVersionError


class AliasVersions(StrEnum):
    """Which alias versions to include in addition to the exact version."""

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


def compute_version_tags(*, version: str, tag_prefix: str = '') -> VersionTags:
    """Compute exact/major/minor tags for a full release version.

    Args:
        version: The full release version (`x.y.z`).
        tag_prefix: Optional prefix for tags (e.g., "core-" creates "core-1.2.3").

    Returns:
        The computed tag strings with prefix applied.

    Raises:
        InvalidReleaseVersionError: If the version is not a full `x.y.z` release.

    Examples:
        >>> compute_version_tags(version='1.2.3')
        VersionTags(exact='1.2.3', major='v1', minor='v1.2')
        >>> compute_version_tags(version='1.2.3', tag_prefix='core-')
        VersionTags(exact='core-1.2.3', major='core-v1', minor='core-v1.2')
    """
    normalized = version.strip().removeprefix('v')

    try:
        parsed = VersionInfo.parse(normalized)
    except ValueError as exc:
        raise InvalidReleaseVersionError(version) from exc

    if parsed.prerelease is not None or parsed.build is not None:
        raise InvalidReleaseVersionError(version)

    return VersionTags(
        exact=f'{tag_prefix}{normalized}',
        major=f'{tag_prefix}v{parsed.major}',
        minor=f'{tag_prefix}v{parsed.major}.{parsed.minor}',
    )


def select_tags(*, tags: VersionTags, aliases: AliasVersions) -> list[str]:
    """Select which version aliases to output/publish given an alias level."""
    if aliases == AliasVersions.none:
        return [tags.exact]
    if aliases == AliasVersions.major:
        return [tags.exact, tags.major]
    return [tags.exact, tags.major, tags.minor]
