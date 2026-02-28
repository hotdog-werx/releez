from __future__ import annotations

import json
from typing import TYPE_CHECKING

from typer.testing import CliRunner

from releez import cli
from releez.artifact_version import (
    ArtifactVersionInput,
    ArtifactVersionScheme,
    PrereleaseType,
)
from releez.version_tags import VersionTags

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


def test_cli_version_artifact_builds_input_and_prints_result(
    mocker: MockerFixture,
) -> None:
    runner = CliRunner()

    def _fake_compute(artifact_input: ArtifactVersionInput) -> str:
        assert artifact_input.scheme == ArtifactVersionScheme.semver
        assert artifact_input.version_override == '1.2.3'
        assert artifact_input.is_full_release is True
        assert artifact_input.prerelease_type == PrereleaseType.alpha
        assert artifact_input.prerelease_number is None
        assert artifact_input.build_number is None
        return '1.2.3'

    mocker.patch(
        'releez.cli.compute_artifact_version',
        side_effect=_fake_compute,
    )

    result = runner.invoke(
        cli.app,
        [
            'version',
            'artifact',
            '--scheme',
            'semver',
            '--version-override',
            '1.2.3',
            '--is-full-release',
            '--alias-versions',
            'none',
        ],
    )

    assert result.exit_code == 0
    assert result.stdout == '1.2.3\n'


def test_cli_version_artifact_alias_versions_use_v_prefix_only_for_aliases(
    mocker: MockerFixture,
) -> None:
    runner = CliRunner()
    mocker.patch('releez.cli.compute_artifact_version', return_value='1.2.3')

    compute_tags = mocker.patch(
        'releez.cli.compute_version_tags',
        return_value=VersionTags(exact='1.2.3', major='v1', minor='v1.2'),
    )

    result = runner.invoke(
        cli.app,
        [
            'version',
            'artifact',
            '--scheme',
            'semver',
            '--version-override',
            '1.2.3',
            '--is-full-release',
            '--alias-versions',
            'major',
        ],
    )

    assert result.exit_code == 0
    compute_tags.assert_called_once_with(version='1.2.3')
    assert result.stdout == '1.2.3\nv1\n'


def test_cli_version_artifact_rejects_invalid_prerelease_type() -> None:
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        [
            'version',
            'artifact',
            '--version-override',
            '0.1.0',
            '--prerelease-type',
            'canary',
            '--prerelease-number',
            '1',
            '--build-number',
            '2',
        ],
    )

    assert result.exit_code != 0


def test_cli_version_artifact_ignores_alias_versions_for_pep440(
    mocker: MockerFixture,
) -> None:
    runner = CliRunner()
    mocker.patch('releez.cli.compute_artifact_version', return_value='1.2.3')
    compute_tags = mocker.patch('releez.cli.compute_version_tags')

    result = runner.invoke(
        cli.app,
        [
            'version',
            'artifact',
            '--scheme',
            'pep440',
            '--version-override',
            '1.2.3',
            '--is-full-release',
            '--alias-versions',
            'major',
        ],
    )

    assert result.exit_code == 0
    assert result.stdout == '1.2.3\n'
    compute_tags.assert_not_called()


def test_cli_version_artifact_ignores_alias_versions_for_prerelease(
    mocker: MockerFixture,
) -> None:
    runner = CliRunner()
    mocker.patch(
        'releez.cli.compute_artifact_version',
        return_value='1.2.3-alpha1-2',
    )
    compute_tags = mocker.patch('releez.cli.compute_version_tags')

    result = runner.invoke(
        cli.app,
        [
            'version',
            'artifact',
            '--scheme',
            'docker',
            '--version-override',
            '1.2.3',
            '--prerelease-type',
            'alpha',
            '--prerelease-number',
            '1',
            '--build-number',
            '2',
            '--alias-versions',
            'major',
        ],
    )

    assert result.exit_code == 0
    assert result.stdout == '1.2.3-alpha1-2\n'
    compute_tags.assert_not_called()


def test_cli_version_artifact_outputs_all_schemes_as_json_when_no_scheme_specified(
    mocker: MockerFixture,
) -> None:
    """Test JSON output when --scheme is not provided.

    Args:
        mocker: pytest-mock fixture for creating mocks.
    """
    runner = CliRunner()

    # Mock compute_artifact_version to return different values for each scheme
    def _fake_compute(artifact_input: ArtifactVersionInput) -> str:
        if artifact_input.scheme == ArtifactVersionScheme.semver:
            return '1.2.3-alpha123+456'
        if artifact_input.scheme == ArtifactVersionScheme.docker:
            return '1.2.3-alpha123-456'
        return '1.2.3a123.dev456'  # pep440

    mocker.patch(
        'releez.cli.compute_artifact_version',
        side_effect=_fake_compute,
    )

    result = runner.invoke(
        cli.app,
        [
            'version',
            'artifact',
            '--version-override',
            '1.2.3',
            '--prerelease-type',
            'alpha',
            '--prerelease-number',
            '123',
            '--build-number',
            '456',
        ],
    )

    assert result.exit_code == 0
    output = json.loads(result.stdout)
    assert output == {
        'semver': ['1.2.3-alpha123+456'],
        'docker': ['1.2.3-alpha123-456'],
        'pep440': ['1.2.3a123.dev456'],
    }


def test_cli_version_artifact_json_output_with_alias_versions(
    mocker: MockerFixture,
) -> None:
    """Test JSON output includes alias versions for full releases.

    Args:
        mocker: pytest-mock fixture for creating mocks.
    """
    runner = CliRunner()
    mocker.patch('releez.cli.compute_artifact_version', return_value='1.2.3')
    mocker.patch(
        'releez.cli.compute_version_tags',
        return_value=VersionTags(exact='1.2.3', major='v1', minor='v1.2'),
    )

    result = runner.invoke(
        cli.app,
        [
            'version',
            'artifact',
            '--version-override',
            '1.2.3',
            '--is-full-release',
            '--alias-versions',
            'major',
        ],
    )

    assert result.exit_code == 0
    output = json.loads(result.stdout)
    assert output == {
        'semver': ['1.2.3', 'v1'],
        'docker': ['1.2.3', 'v1'],
        'pep440': ['1.2.3'],
    }


def test_cli_version_artifact_json_output_full_release_no_aliases(
    mocker: MockerFixture,
) -> None:
    """Test JSON output for full release without alias versions.

    Args:
        mocker: pytest-mock fixture for creating mocks.
    """
    runner = CliRunner()
    mocker.patch('releez.cli.compute_artifact_version', return_value='1.2.3')

    result = runner.invoke(
        cli.app,
        [
            'version',
            'artifact',
            '--version-override',
            '1.2.3',
            '--is-full-release',
        ],
    )

    assert result.exit_code == 0
    output = json.loads(result.stdout)
    assert output == {
        'semver': ['1.2.3'],
        'docker': ['1.2.3'],
        'pep440': ['1.2.3'],
    }
