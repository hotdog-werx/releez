from __future__ import annotations

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
        assert artifact_input.scheme == ArtifactVersionScheme.docker
        assert artifact_input.next_version_override == '1.2.3'
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
            '--next-version-override',
            '1.2.3',
            '--is-full-release',
        ],
    )

    assert result.exit_code == 0
    assert result.stdout == '1.2.3\n'


def test_cli_version_artifact_alias_tags_use_v_prefix_only_for_aliases(
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
            '--next-version-override',
            '1.2.3',
            '--is-full-release',
            '--alias-tags',
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
            '--next-version-override',
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
