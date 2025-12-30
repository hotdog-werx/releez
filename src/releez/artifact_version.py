from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from releez.cliff import GitCliff
from releez.errors import (
    BuildNumberRequiredError,
    PrereleaseNumberRequiredError,
)
from releez.git_repo import open_repo


class ArtifactVersionScheme(StrEnum):
    """Output scheme for artifact versions."""

    semver = 'semver'
    docker = 'docker'
    pep440 = 'pep440'


class PrereleaseType(StrEnum):
    """Supported prerelease types.

    These are deliberately limited so we can reliably map to PEP 440.
    """

    alpha = 'alpha'
    beta = 'beta'
    rc = 'rc'


@dataclass(frozen=True)
class ArtifactVersionInput:
    """Inputs for computing an artifact version.

    Attributes:
        scheme: Output scheme for the artifact version.
        version_override: If set, use this instead of computing via git-cliff.
        is_full_release: If true, output a full release version without prerelease markers.
        prerelease_type: Prerelease label (e.g. alpha, beta, rc).
        prerelease_number: Optional prerelease number (e.g. PR number for alpha123).
        build_number: Build identifier for prerelease builds.
    """

    scheme: ArtifactVersionScheme
    version_override: str | None
    is_full_release: bool
    prerelease_type: PrereleaseType
    prerelease_number: int | None
    build_number: int | None


_PEP440_PRERELEASE_MARKERS: dict[PrereleaseType, str] = {
    PrereleaseType.alpha: 'a',
    PrereleaseType.beta: 'b',
    PrereleaseType.rc: 'rc',
}


def compute_artifact_version(artifact_input: ArtifactVersionInput) -> str:
    """Compute an artifact version string.

    Args:
        artifact_input: The inputs for computing the version.

    Returns:
        The version string to apply to the artifact.

    Raises:
        BuildNumberRequiredError: If a prerelease build is missing a build number.
        ReleezError: If git or git-cliff are unavailable, or git-cliff fails.
    """
    next_version = artifact_input.version_override or _compute_next_version()
    if artifact_input.is_full_release:
        return next_version

    if artifact_input.build_number is None:
        raise BuildNumberRequiredError

    prerelease_type = artifact_input.prerelease_type.value
    prerelease_number = artifact_input.prerelease_number
    if prerelease_number is None:
        raise PrereleaseNumberRequiredError
    if artifact_input.scheme == ArtifactVersionScheme.semver:
        return f'{next_version}-{prerelease_type}{prerelease_number}+{artifact_input.build_number}'
    if artifact_input.scheme == ArtifactVersionScheme.docker:
        return f'{next_version}-{prerelease_type}{prerelease_number}-{artifact_input.build_number}'
    return _pep440_version(
        next_version=next_version,
        prerelease_type=artifact_input.prerelease_type,
        prerelease_number=prerelease_number,
        build_number=artifact_input.build_number,
    )


def _compute_next_version() -> str:
    _, info = open_repo()
    cliff = GitCliff(repo_root=info.root)
    return cliff.compute_next_version(bump='auto')


def _pep440_version(
    *,
    next_version: str,
    prerelease_type: PrereleaseType,
    prerelease_number: int | None,
    build_number: int,
) -> str:
    marker = _PEP440_PRERELEASE_MARKERS[prerelease_type]
    return f'{next_version}{marker}{prerelease_number}.dev{build_number}'
