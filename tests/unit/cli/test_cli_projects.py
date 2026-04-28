"""Tests for the `projects` CLI subcommand group."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from releez import cli
from releez.errors import DirtyWorkingTreeError

if TYPE_CHECKING:
    from collections.abc import Callable

    from invoke_helper import InvokeResult
    from pytest_mock import MockerFixture


def test_projects_list_no_projects(
    mocker: MockerFixture,
    invoke: Callable[[object, list[str]], InvokeResult],
) -> None:
    mocker.patch(
        'releez.subapps.projects.ReleezSettings',
        return_value=mocker.MagicMock(projects=[]),
    )

    result = invoke(cli.app, ['projects', 'list'])

    assert result.exit_code == 0
    assert 'single-repo' in result.output


def test_projects_list_with_projects(
    mocker: MockerFixture,
    invoke: Callable[[object, list[str]], InvokeResult],
) -> None:
    core_config = mocker.MagicMock(
        name='core',
        path='packages/core',
        tag_prefix='core-',
        changelog_path='packages/core/CHANGELOG.md',
        include_paths=['pyproject.toml'],
    )
    core_config.name = 'core'

    mocker.patch(
        'releez.subapps.projects.ReleezSettings',
        return_value=mocker.MagicMock(projects=[core_config]),
    )

    result = invoke(cli.app, ['projects', 'list'])

    assert result.exit_code == 0
    assert 'core' in result.output


def test_projects_list_with_projects_no_include_paths(
    mocker: MockerFixture,
    invoke: Callable[[object, list[str]], InvokeResult],
) -> None:
    core_config = mocker.MagicMock(
        path='packages/core',
        tag_prefix='core-',
        changelog_path='packages/core/CHANGELOG.md',
        include_paths=[],
    )
    core_config.name = 'core'

    mocker.patch(
        'releez.subapps.projects.ReleezSettings',
        return_value=mocker.MagicMock(projects=[core_config]),
    )

    result = invoke(cli.app, ['projects', 'list'])

    assert result.exit_code == 0
    assert 'core' in result.output


def test_projects_changed_no_projects_configured(
    mocker: MockerFixture,
    invoke: Callable[[object, list[str]], InvokeResult],
) -> None:
    mocker.patch(
        'releez.subapps.projects.ReleezSettings',
        return_value=mocker.MagicMock(projects=[]),
    )

    result = invoke(cli.app, ['projects', 'changed'])

    assert result.exit_code == 1
    assert 'single-repo' in result.output


def test_projects_changed_text_output_with_changes(
    mocker: MockerFixture,
    invoke: Callable[[object, list[str]], InvokeResult],
) -> None:
    mock_project = mocker.MagicMock()
    mock_project.name = 'core'

    mock_info = mocker.MagicMock()
    mock_info.root = mocker.MagicMock()

    mock_settings = mocker.MagicMock(
        projects=[mocker.MagicMock()],
        base_branch='main',
    )
    mock_settings.get_subprojects.return_value = [mock_project]
    mocker.patch(
        'releez.subapps.projects.ReleezSettings',
        return_value=mock_settings,
    )
    mocker.patch(
        'releez.subapps.projects.open_repo',
        return_value=mocker.Mock(repo=mocker.MagicMock(), info=mock_info),
    )
    mocker.patch(
        'releez.subapps.projects.detect_changed_projects',
        return_value=[mock_project],
    )

    result = invoke(cli.app, ['projects', 'changed'])

    assert result.exit_code == 0
    assert 'core' in result.output


def test_projects_changed_text_output_no_changes(
    mocker: MockerFixture,
    invoke: Callable[[object, list[str]], InvokeResult],
) -> None:
    mock_info = mocker.MagicMock()
    mock_info.root = mocker.MagicMock()

    mock_settings = mocker.MagicMock(
        projects=[mocker.MagicMock()],
        base_branch='main',
    )
    mock_settings.get_subprojects.return_value = [mocker.MagicMock()]
    mocker.patch(
        'releez.subapps.projects.ReleezSettings',
        return_value=mock_settings,
    )
    mocker.patch(
        'releez.subapps.projects.open_repo',
        return_value=mocker.Mock(repo=mocker.MagicMock(), info=mock_info),
    )
    mocker.patch(
        'releez.subapps.projects.detect_changed_projects',
        return_value=[],
    )

    result = invoke(cli.app, ['projects', 'changed'])

    assert result.exit_code == 0
    assert 'No projects' in result.output


def test_projects_changed_json_output(
    mocker: MockerFixture,
    invoke: Callable[[object, list[str]], InvokeResult],
) -> None:
    mock_project = mocker.MagicMock()
    mock_project.name = 'core'

    mock_info = mocker.MagicMock()
    mock_info.root = mocker.MagicMock()

    mock_settings = mocker.MagicMock(
        projects=[mocker.MagicMock()],
        base_branch='main',
    )
    mock_settings.get_subprojects.return_value = [mock_project]
    mocker.patch(
        'releez.subapps.projects.ReleezSettings',
        return_value=mock_settings,
    )
    mocker.patch(
        'releez.subapps.projects.open_repo',
        return_value=mocker.Mock(repo=mocker.MagicMock(), info=mock_info),
    )
    mocker.patch(
        'releez.subapps.projects.detect_changed_projects',
        return_value=[mock_project],
    )

    result = invoke(cli.app, ['projects', 'changed', '--format', 'json'])

    assert result.exit_code == 0
    output = json.loads(result.stdout)
    assert output == {
        'projects': ['core'],
        'include': [{'project': 'core'}],
    }


def test_projects_changed_with_custom_base(
    mocker: MockerFixture,
    invoke: Callable[[object, list[str]], InvokeResult],
) -> None:
    mock_info = mocker.MagicMock()
    mock_info.root = mocker.MagicMock()

    mock_settings = mocker.MagicMock(
        projects=[mocker.MagicMock()],
        base_branch='main',
    )
    mock_settings.get_subprojects.return_value = [mocker.MagicMock()]
    mocker.patch(
        'releez.subapps.projects.ReleezSettings',
        return_value=mock_settings,
    )
    mocker.patch(
        'releez.subapps.projects.open_repo',
        return_value=mocker.Mock(repo=mocker.MagicMock(), info=mock_info),
    )
    mock_detect = mocker.patch(
        'releez.subapps.projects.detect_changed_projects',
        return_value=[],
    )

    result = invoke(cli.app, ['projects', 'changed', '--base', 'develop'])

    assert result.exit_code == 0
    mock_detect.assert_called_once()
    call_kwargs = mock_detect.call_args.kwargs
    assert call_kwargs['base_branch'] == 'develop'


def test_projects_changed_handles_releez_error(
    mocker: MockerFixture,
    invoke: Callable[[object, list[str]], InvokeResult],
) -> None:
    mock_info = mocker.MagicMock()
    mock_info.root = mocker.MagicMock()

    mock_settings = mocker.MagicMock(
        projects=[mocker.MagicMock()],
        base_branch='main',
    )
    mock_settings.get_subprojects.return_value = [mocker.MagicMock()]
    mocker.patch(
        'releez.subapps.projects.ReleezSettings',
        return_value=mock_settings,
    )
    mocker.patch(
        'releez.subapps.projects.open_repo',
        return_value=mocker.Mock(repo=mocker.MagicMock(), info=mock_info),
    )
    mocker.patch(
        'releez.subapps.projects.detect_changed_projects',
        side_effect=DirtyWorkingTreeError,
    )

    result = invoke(cli.app, ['projects', 'changed'])

    assert result.exit_code == 1
    assert 'Working tree is not clean' in result.output


def test_projects_info_no_projects_configured(
    mocker: MockerFixture,
    invoke: Callable[[object, list[str]], InvokeResult],
) -> None:
    mocker.patch(
        'releez.subapps.projects.ReleezSettings',
        return_value=mocker.MagicMock(projects=[]),
    )

    result = invoke(cli.app, ['projects', 'info', 'core'])

    assert result.exit_code == 1
    assert 'single-repo' in result.output


def test_projects_info_project_not_found(
    mocker: MockerFixture,
    invoke: Callable[[object, list[str]], InvokeResult],
) -> None:
    existing = mocker.MagicMock()
    existing.name = 'ui'

    mocker.patch(
        'releez.subapps.projects.ReleezSettings',
        return_value=mocker.MagicMock(projects=[existing]),
    )

    result = invoke(cli.app, ['projects', 'info', 'core'])

    assert result.exit_code == 1
    assert '"core" not found' in result.output
    assert 'ui' in result.output


def test_projects_info_valid_project(
    mocker: MockerFixture,
    invoke: Callable[[object, list[str]], InvokeResult],
) -> None:
    project_config = mocker.MagicMock(
        path='packages/core',
        tag_prefix='core-',
        changelog_path='packages/core/CHANGELOG.md',
        alias_versions=None,
        include_paths=['pyproject.toml'],
    )
    project_config.name = 'core'
    project_config.hooks.post_changelog = []

    mocker.patch(
        'releez.subapps.projects.ReleezSettings',
        return_value=mocker.MagicMock(
            projects=[project_config],
            alias_versions='none',
        ),
    )

    result = invoke(cli.app, ['projects', 'info', 'core'])

    assert result.exit_code == 0
    assert 'core' in result.output
    assert 'pyproject.toml' in result.output


def test_projects_info_with_post_changelog_hooks(
    mocker: MockerFixture,
    invoke: Callable[[object, list[str]], InvokeResult],
) -> None:
    project_config = mocker.MagicMock(
        path='packages/core',
        tag_prefix='core-',
        changelog_path='packages/core/CHANGELOG.md',
        alias_versions=None,
        include_paths=[],
    )
    project_config.name = 'core'
    project_config.hooks.post_changelog = [
        ['prettier', '--write', '{changelog}'],
    ]

    mocker.patch(
        'releez.subapps.projects.ReleezSettings',
        return_value=mocker.MagicMock(
            projects=[project_config],
            alias_versions='none',
        ),
    )

    result = invoke(cli.app, ['projects', 'info', 'core'])

    assert result.exit_code == 0
    assert 'prettier' in result.output
