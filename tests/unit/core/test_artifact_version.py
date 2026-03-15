from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from releez.artifact_version import (
    ArtifactVersionInput,
    ArtifactVersionScheme,
    PrereleaseType,
    compute_artifact_version,
)
from releez.errors import (
    BuildNumberRequiredError,
    PrereleaseNumberRequiredError,
)

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


def test_compute_artifact_version_full_release_uses_override() -> None:
    artifact_input = ArtifactVersionInput(
        scheme=ArtifactVersionScheme.docker,
        version_override='1.2.3',
        is_full_release=True,
        prerelease_type=PrereleaseType.alpha,
        prerelease_number=None,
        build_number=None,
    )

    assert compute_artifact_version(artifact_input) == '1.2.3'


@pytest.mark.parametrize(
    ('scheme', 'expected'),
    [
        (
            ArtifactVersionScheme.docker,
            '0.1.0-alpha123-456',
        ),
        (
            ArtifactVersionScheme.semver,
            '0.1.0-alpha123+456',
        ),
        (
            ArtifactVersionScheme.pep440,
            '0.1.0a123.dev456',
        ),
    ],
)
def test_compute_artifact_version_prerelease_formats(
    scheme: ArtifactVersionScheme,
    expected: str,
) -> None:
    artifact_input = ArtifactVersionInput(
        scheme=scheme,
        version_override='0.1.0',
        is_full_release=False,
        prerelease_type=PrereleaseType.alpha,
        prerelease_number=123,
        build_number=456,
    )

    assert compute_artifact_version(artifact_input) == expected


def test_compute_artifact_version_requires_build_number_for_prerelease() -> None:
    artifact_input = ArtifactVersionInput(
        scheme=ArtifactVersionScheme.docker,
        version_override='0.1.0',
        is_full_release=False,
        prerelease_type=PrereleaseType.beta,
        prerelease_number=1,
        build_number=None,
    )

    with pytest.raises(BuildNumberRequiredError):
        compute_artifact_version(artifact_input)


def test_compute_artifact_version_requires_prerelease_number_for_prerelease() -> None:
    artifact_input = ArtifactVersionInput(
        scheme=ArtifactVersionScheme.docker,
        version_override='0.1.0',
        is_full_release=False,
        prerelease_type=PrereleaseType.rc,
        prerelease_number=None,
        build_number=456,
    )

    with pytest.raises(PrereleaseNumberRequiredError):
        compute_artifact_version(artifact_input)


def test_compute_artifact_version_calls_compute_next_version_when_no_override(
    mocker: MockerFixture,
) -> None:
    """When version_override is None, _compute_next_version() is called to derive it."""
    mock_info = mocker.Mock(root='/repo')
    mocker.patch(
        'releez.artifact_version.open_repo',
        return_value=mocker.Mock(info=mock_info),
    )
    mock_cliff = mocker.Mock()
    mock_cliff.compute_next_version.return_value = '3.0.0'
    mocker.patch('releez.artifact_version.GitCliff', return_value=mock_cliff)

    artifact_input = ArtifactVersionInput(
        scheme=ArtifactVersionScheme.semver,
        version_override=None,
        is_full_release=True,
        prerelease_type=PrereleaseType.alpha,
        prerelease_number=None,
        build_number=None,
    )

    assert compute_artifact_version(artifact_input) == '3.0.0'
    mock_cliff.compute_next_version.assert_called_once_with(bump='auto')
