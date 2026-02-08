from __future__ import annotations

from typing import TYPE_CHECKING

from typer.testing import CliRunner

from releez import cli
from releez.version_tags import VersionTags

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


def test_cli_version_artifact_full_release_with_no_aliases(
    mocker: MockerFixture,
) -> None:
    """Test full release with alias-versions=none outputs only the version."""
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
