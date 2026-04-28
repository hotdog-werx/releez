from __future__ import annotations

import json
from typing import TYPE_CHECKING

from releez import cli
from releez.artifact_version import (
    ArtifactVersionInput,
    ArtifactVersionScheme,
    PrereleaseType,
)
from releez.errors import ReleezError
from releez.version_tags import AliasVersions, VersionTags

if TYPE_CHECKING:
    from collections.abc import Callable
    from unittest.mock import MagicMock

    from invoke_helper import InvokeResult
    from pytest_mock import MockerFixture


def _mock_settings(
    mocker: MockerFixture,
    *,
    projects: list[object],
) -> MagicMock:
    hooks = mocker.MagicMock(post_changelog=[])
    mock_settings = mocker.MagicMock(
        base_branch='master',
        git_remote='origin',
        pr_labels='release',
        pr_title_prefix='chore(release): ',
        changelog_path='CHANGELOG.md',
        create_pr=False,
        alias_versions=AliasVersions.none,
        hooks=hooks,
        projects=projects,
    )
    mocker.patch(
        'releez.subapps.version.ReleezSettings',
        return_value=mock_settings,
    )
    return mock_settings


def test_cli_version_artifact_builds_input_and_prints_result(
    mocker: MockerFixture,
    invoke: Callable[[object, list[str]], InvokeResult],
) -> None:
    def _fake_compute(artifact_input: ArtifactVersionInput) -> str:
        assert artifact_input.scheme == ArtifactVersionScheme.semver
        assert artifact_input.version_override == '1.2.3'
        assert artifact_input.is_full_release is True
        assert artifact_input.prerelease_type == PrereleaseType.alpha
        assert artifact_input.prerelease_number is None
        assert artifact_input.build_number is None
        return '1.2.3'

    mocker.patch(
        'releez.subapps.version.compute_artifact_version',
        side_effect=_fake_compute,
    )

    result = invoke(
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
    invoke: Callable[[object, list[str]], InvokeResult],
) -> None:
    mocker.patch(
        'releez.subapps.version.compute_artifact_version',
        return_value='1.2.3',
    )

    compute_tags = mocker.patch(
        'releez.subapps.version.compute_version_tags',
        return_value=VersionTags(exact='1.2.3', major='v1', minor='v1.2'),
    )

    result = invoke(
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


def test_cli_version_artifact_rejects_invalid_prerelease_type(
    invoke: Callable[[object, list[str]], InvokeResult],
) -> None:
    result = invoke(
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
    invoke: Callable[[object, list[str]], InvokeResult],
) -> None:
    mocker.patch(
        'releez.subapps.version.compute_artifact_version',
        return_value='1.2.3',
    )
    compute_tags = mocker.patch('releez.subapps.version.compute_version_tags')

    result = invoke(
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
    invoke: Callable[[object, list[str]], InvokeResult],
) -> None:
    """Regression guard: pep440 output with no aliases should emit plain version only."""
    mocker.patch(
        'releez.subapps.version.compute_artifact_version',
        return_value='1.2.3',
    )
    compute_tags = mocker.patch('releez.subapps.version.compute_version_tags')

    result = invoke(
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
            'none',
        ],
    )

    assert result.exit_code == 0
    assert result.stdout == '1.2.3\n'
    compute_tags.assert_not_called()


def test_cli_version_artifact_ignores_alias_versions_for_prerelease(
    mocker: MockerFixture,
    invoke: Callable[[object, list[str]], InvokeResult],
) -> None:
    mocker.patch(
        'releez.subapps.version.compute_artifact_version',
        return_value='1.2.3-alpha1-2',
    )
    compute_tags = mocker.patch('releez.subapps.version.compute_version_tags')

    result = invoke(
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
    invoke: Callable[[object, list[str]], InvokeResult],
) -> None:
    def _fake_compute(artifact_input: ArtifactVersionInput) -> str:
        if artifact_input.scheme == ArtifactVersionScheme.semver:
            return '1.2.3-alpha123+456'
        if artifact_input.scheme == ArtifactVersionScheme.docker:
            return '1.2.3-alpha123-456'
        return '1.2.3a123.dev456'  # pep440

    mocker.patch(
        'releez.subapps.version.compute_artifact_version',
        side_effect=_fake_compute,
    )

    result = invoke(
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
    invoke: Callable[[object, list[str]], InvokeResult],
) -> None:
    mocker.patch(
        'releez.subapps.version.compute_artifact_version',
        return_value='1.2.3',
    )
    mocker.patch(
        'releez.subapps.version.compute_version_tags',
        return_value=VersionTags(exact='1.2.3', major='v1', minor='v1.2'),
    )

    result = invoke(
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
    invoke: Callable[[object, list[str]], InvokeResult],
) -> None:
    mocker.patch(
        'releez.subapps.version.compute_artifact_version',
        return_value='1.2.3',
    )

    result = invoke(
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
    output = json.loads(result.stdout)
    assert output == {
        'semver': ['1.2.3'],
        'docker': ['1.2.3'],
        'pep440': ['1.2.3'],
    }


def test_cli_version_artifact_with_project_includes_metadata_in_json(
    mocker: MockerFixture,
    invoke: Callable[[object, list[str]], InvokeResult],
) -> None:
    mock_project = mocker.MagicMock()
    mock_project.name = 'core'
    mock_project.tag_prefix = 'core-'
    mock_project.tag_pattern = '^core-([0-9]+\\.[0-9]+\\.[0-9]+)$'
    mock_project.include_paths = []

    mock_settings = _mock_settings(mocker, projects=[mocker.MagicMock()])
    mock_settings.get_subprojects.return_value = [mock_project]
    mocker.patch(
        'releez.subapps.version.open_repo',
        return_value=mocker.Mock(
            repo=mocker.MagicMock(),
            info=mocker.Mock(root='/repo'),
        ),
    )
    mocker.patch(
        'releez.subapps.version._resolve_release_version',
        return_value='0.2.0',
    )
    mocker.patch(
        'releez.subapps.version.compute_artifact_version',
        return_value='0.2.0-beta1+5',
    )

    result = invoke(
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
    invoke: Callable[[object, list[str]], InvokeResult],
) -> None:
    mock_project = mocker.MagicMock()
    mock_project.name = 'core'
    mock_project.tag_prefix = 'core-'
    mock_project.tag_pattern = '^core-([0-9]+\\.[0-9]+\\.[0-9]+)$'
    mock_project.path = mocker.MagicMock()
    mock_project.include_paths = ['pyproject.toml']

    mock_settings = _mock_settings(mocker, projects=[mocker.MagicMock()])
    mock_settings.get_subprojects.return_value = [mock_project]
    mocker.patch(
        'releez.subapps.version.open_repo',
        return_value=mocker.Mock(
            repo=mocker.MagicMock(),
            info=mocker.Mock(root='/repo'),
        ),
    )
    resolve = mocker.patch(
        'releez.subapps.version._resolve_release_version',
        return_value='0.2.0',
    )
    mocker.patch(
        'releez.subapps.version.compute_artifact_version',
        return_value='0.2.0-rc1+3',
    )
    mocker.patch(
        'releez.subapps.version._project_include_paths',
        return_value=['packages/core/**', 'pyproject.toml'],
    )

    result = invoke(
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
        tag_prefix='core-',
    )


def test_cli_version_artifact_with_unknown_project_exits_with_error(
    mocker: MockerFixture,
    invoke: Callable[[object, list[str]], InvokeResult],
) -> None:
    mock_project = mocker.MagicMock()
    mock_project.name = 'core'

    mock_settings = _mock_settings(mocker, projects=[mocker.MagicMock()])
    mock_settings.get_subprojects.return_value = [mock_project]
    mocker.patch(
        'releez.subapps.version.open_repo',
        return_value=mocker.Mock(
            repo=mocker.MagicMock(),
            info=mocker.Mock(root='/repo'),
        ),
    )

    result = invoke(
        cli.app,
        ['version', 'artifact', '--project', 'nonexistent'],
    )

    assert result.exit_code == 1
    assert 'nonexistent' in result.output


def test_cli_version_artifact_with_project_no_projects_configured_exits_with_error(
    mocker: MockerFixture,
    invoke: Callable[[object, list[str]], InvokeResult],
) -> None:
    mock_settings = _mock_settings(mocker, projects=[])
    mock_settings.get_subprojects.return_value = []
    mocker.patch(
        'releez.subapps.version.open_repo',
        return_value=mocker.Mock(
            repo=mocker.MagicMock(),
            info=mocker.Mock(root='/repo'),
        ),
    )

    result = invoke(cli.app, ['version', 'artifact', '--project', 'core'])

    assert result.exit_code == 1
    assert 'No projects configured' in result.output


def test_cli_version_artifact_with_project_version_override_skips_resolution(
    mocker: MockerFixture,
    invoke: Callable[[object, list[str]], InvokeResult],
) -> None:
    mock_project = mocker.MagicMock()
    mock_project.name = 'core'
    mock_project.tag_prefix = 'core-'
    mock_project.tag_pattern = '^core-([0-9]+\\.[0-9]+\\.[0-9]+)$'
    mock_project.include_paths = []

    mock_settings = _mock_settings(mocker, projects=[mocker.MagicMock()])
    mock_settings.get_subprojects.return_value = [mock_project]
    mocker.patch(
        'releez.subapps.version.open_repo',
        return_value=mocker.Mock(
            repo=mocker.MagicMock(),
            info=mocker.Mock(root='/repo'),
        ),
    )
    resolve = mocker.patch('releez.subapps.version._resolve_release_version')
    mocker.patch(
        'releez.subapps.version.compute_artifact_version',
        return_value='1.0.0',
    )

    result = invoke(
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
    invoke: Callable[[object, list[str]], InvokeResult],
) -> None:
    """In monorepo mode, version artifact must fail without --project."""
    _mock_settings(mocker, projects=[mocker.MagicMock()])

    result = invoke(
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
    invoke: Callable[[object, list[str]], InvokeResult],
) -> None:
    """Regression guard: version-artifact command must surface ReleezError as exit code 1."""
    mocker.patch(
        'releez.subapps.version.compute_artifact_version',
        side_effect=ReleezError('broken'),
    )

    result = invoke(
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
