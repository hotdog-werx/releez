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
from releez.errors import ReleezError
from releez.version_tags import AliasVersions, VersionTags

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


def _mock_settings(mocker: MockerFixture, *, projects: list[object]) -> None:
    hooks = mocker.MagicMock(post_changelog=[], changelog_format=None)
    mocker.patch(
        'releez.cli.ReleezSettings',
        return_value=mocker.MagicMock(
            base_branch='master',
            git_remote='origin',
            pr_labels='release',
            pr_title_prefix='chore(release): ',
            changelog_path='CHANGELOG.md',
            create_pr=False,
            run_changelog_format=False,
            alias_versions=AliasVersions.none,
            hooks=hooks,
            projects=projects,
        ),
    )


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


def test_cli_version_artifact_pep440_without_aliases(
    mocker: MockerFixture,
) -> None:
    """Regression guard: pep440 output with no aliases should emit plain version only."""
    runner = CliRunner()
    mocker.patch('releez.cli.compute_artifact_version', return_value='1.2.3')
    compute_tags = mocker.patch('releez.cli.compute_version_tags')
    secho = mocker.patch('releez.cli.typer.secho')

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
        ],
    )

    assert result.exit_code == 0
    assert result.stdout == '1.2.3\n'
    compute_tags.assert_not_called()
    secho.assert_not_called()


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


def test_cli_version_artifact_with_project_includes_metadata_in_json(
    mocker: MockerFixture,
) -> None:
    """Test --project adds release_version and project keys to JSON output."""
    runner = CliRunner()

    mock_project = mocker.MagicMock()
    mock_project.name = 'core'
    mock_project.tag_prefix = 'core-'
    mock_project.tag_pattern = '^core-([0-9]+\\.[0-9]+\\.[0-9]+)$'
    mock_project.include_paths = []

    _mock_settings(mocker, projects=[mocker.MagicMock()])
    mocker.patch(
        'releez.cli.open_repo',
        return_value=(mocker.MagicMock(), mocker.Mock(root='/repo')),
    )
    mocker.patch(
        'releez.cli._build_subprojects_list',
        return_value=[mock_project],
    )
    mocker.patch('releez.cli._resolve_release_version', return_value='0.2.0')
    mocker.patch(
        'releez.cli.compute_artifact_version',
        return_value='0.2.0-beta1+5',
    )

    result = runner.invoke(
        cli.app,
        [
            'version',
            'artifact',
            '--project',
            'core',
            '--prerelease-type',
            'beta',
            '--prerelease-number',
            '1',
            '--build-number',
            '5',
        ],
    )

    assert result.exit_code == 0
    output = json.loads(result.stdout)
    assert output['project'] == 'core'
    assert output['release_version'] == 'core-0.2.0'
    assert 'semver' in output
    assert 'docker' in output
    assert 'pep440' in output


def test_cli_version_artifact_with_project_uses_project_scoped_version_resolution(
    mocker: MockerFixture,
) -> None:
    """Test --project passes tag_pattern and include_paths to _resolve_release_version."""
    runner = CliRunner()

    mock_project = mocker.MagicMock()
    mock_project.name = 'core'
    mock_project.tag_prefix = 'core-'
    mock_project.tag_pattern = '^core-([0-9]+\\.[0-9]+\\.[0-9]+)$'
    mock_project.path = mocker.MagicMock()
    mock_project.include_paths = ['pyproject.toml']

    _mock_settings(mocker, projects=[mocker.MagicMock()])
    mocker.patch(
        'releez.cli.open_repo',
        return_value=(mocker.MagicMock(), mocker.Mock(root='/repo')),
    )
    mocker.patch(
        'releez.cli._build_subprojects_list',
        return_value=[mock_project],
    )
    resolve = mocker.patch(
        'releez.cli._resolve_release_version',
        return_value='0.2.0',
    )
    mocker.patch(
        'releez.cli.compute_artifact_version',
        return_value='0.2.0-rc1+3',
    )
    mocker.patch(
        'releez.cli._project_include_paths',
        return_value=['packages/core/**', 'pyproject.toml'],
    )

    result = runner.invoke(
        cli.app,
        [
            'version',
            'artifact',
            '--project',
            'core',
            '--prerelease-type',
            'rc',
            '--prerelease-number',
            '1',
            '--build-number',
            '3',
        ],
    )

    assert result.exit_code == 0
    resolve.assert_called_once_with(
        repo_root='/repo',
        version_override=None,
        tag_pattern='^core-([0-9]+\\.[0-9]+\\.[0-9]+)$',
        include_paths=['packages/core/**', 'pyproject.toml'],
    )


def test_cli_version_artifact_with_unknown_project_exits_with_error(
    mocker: MockerFixture,
) -> None:
    """Test --project with an unknown name exits with code 1."""
    runner = CliRunner()

    mock_project = mocker.MagicMock()
    mock_project.name = 'core'

    _mock_settings(mocker, projects=[mocker.MagicMock()])
    mocker.patch(
        'releez.cli.open_repo',
        return_value=(mocker.MagicMock(), mocker.Mock(root='/repo')),
    )
    mocker.patch(
        'releez.cli._build_subprojects_list',
        return_value=[mock_project],
    )

    result = runner.invoke(
        cli.app,
        ['version', 'artifact', '--project', 'nonexistent'],
    )

    assert result.exit_code == 1
    assert 'nonexistent' in result.output


def test_cli_version_artifact_with_project_no_projects_configured_exits_with_error(
    mocker: MockerFixture,
) -> None:
    """Test --project when no projects are configured exits with code 1."""
    runner = CliRunner()

    _mock_settings(mocker, projects=[])
    mocker.patch(
        'releez.cli.open_repo',
        return_value=(mocker.MagicMock(), mocker.Mock(root='/repo')),
    )
    mocker.patch('releez.cli._build_subprojects_list', return_value=[])

    result = runner.invoke(
        cli.app,
        ['version', 'artifact', '--project', 'core'],
    )

    assert result.exit_code == 1
    assert 'No projects configured' in result.output


def test_cli_version_artifact_with_project_version_override_skips_resolution(
    mocker: MockerFixture,
) -> None:
    """Test --project with --version-override skips git-cliff resolution."""
    runner = CliRunner()

    mock_project = mocker.MagicMock()
    mock_project.name = 'core'
    mock_project.tag_prefix = 'core-'
    mock_project.tag_pattern = '^core-([0-9]+\\.[0-9]+\\.[0-9]+)$'
    mock_project.include_paths = []

    _mock_settings(mocker, projects=[mocker.MagicMock()])
    mocker.patch(
        'releez.cli.open_repo',
        return_value=(mocker.MagicMock(), mocker.Mock(root='/repo')),
    )
    mocker.patch(
        'releez.cli._build_subprojects_list',
        return_value=[mock_project],
    )
    resolve = mocker.patch('releez.cli._resolve_release_version')
    mocker.patch('releez.cli.compute_artifact_version', return_value='1.0.0')

    result = runner.invoke(
        cli.app,
        [
            'version',
            'artifact',
            '--project',
            'core',
            '--version-override',
            '1.0.0',
            '--is-full-release',
        ],
    )

    assert result.exit_code == 0
    resolve.assert_not_called()
    output = json.loads(result.stdout)
    assert output['release_version'] == 'core-1.0.0'


def test_cli_version_artifact_requires_project_in_monorepo_mode(
    mocker: MockerFixture,
) -> None:
    """In monorepo mode, version artifact must fail without --project."""
    runner = CliRunner()
    _mock_settings(mocker, projects=[mocker.MagicMock()])

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

    assert result.exit_code == 1
    assert '--project' in result.output


def test_cli_version_artifact_handles_releez_error(
    mocker: MockerFixture,
) -> None:
    """Regression guard: version-artifact command must surface ReleezError as exit code 1."""
    runner = CliRunner()
    mocker.patch(
        'releez.cli.compute_artifact_version',
        side_effect=ReleezError('broken'),
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
        ],
    )

    assert result.exit_code == 1
    assert 'broken' in result.output
