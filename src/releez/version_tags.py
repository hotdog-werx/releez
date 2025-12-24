import re
from dataclasses import dataclass
from enum import StrEnum

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


_RELEASE_VERSION_RE = re.compile(
    r'^(?P<major>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)\.(?P<patch>0|[1-9]\d*)$',
)


def compute_version_tags(*, version: str, prefix: str = '') -> VersionTags:
    """Compute exact/major/minor tags for a full release version.

    Args:
        version: The full release version (`x.y.z`), optionally prefixed with `v`.
        prefix: Prefix to apply to alias tags (major/minor), e.g. `v`.

    Returns:
        The computed tag strings.

    Raises:
        InvalidReleaseVersionError: If the version is not a full `x.y.z` release.
    """
    normalized = version.strip().removeprefix('v')

    match = _RELEASE_VERSION_RE.match(normalized)
    if not match:
        raise InvalidReleaseVersionError(version)

    major = int(match.group('major'))
    minor = int(match.group('minor'))

    return VersionTags(
        exact=normalized,
        major=f'{prefix}{major}',
        minor=f'{prefix}{major}.{minor}',
    )


def select_tags(*, tags: VersionTags, aliases: AliasTags) -> list[str]:
    """Select which tags to output/publish given an alias level."""
    if aliases == AliasTags.none:
        return [tags.exact]
    if aliases == AliasTags.major:
        return [tags.exact, tags.major]
    return [tags.exact, tags.major, tags.minor]
