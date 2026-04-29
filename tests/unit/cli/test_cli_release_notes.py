from __future__ import annotations

from typing import TYPE_CHECKING

from invoke_helper import invoke

from releez import cli
from releez.errors import ReleezError
from releez.version_tags import AliasVersions

if TYPE_CHECKING:
    from pathlib import Path
    from unittest.mock import MagicMock

    from pytest_mock import MockerFixture


def _mock_settings(
    mocker: MockerFixture,
    *,
    projects: list[MagicMock],
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
        'releez.subapps.release_notes.ReleezSettings',
        return_value=mock_settings,
    )
    return mock_settings


def test_cli_release_notes_stdout(
    mocker: MockerFixture,
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / 'repo'
    repo_root.mkdir()

    mocker.patch(
        'releez.subapps.release.open_repo',
        return_value=mocker.Mock(
            repo=mocker.MagicMock(),
            info=mocker.Mock(root=repo_root, active_branch=None),
        ),
    )
    mocker.patch(
        'releez.subapps.release_notes._resolve_release_version',
        return_value='2.3.4',
    )

    cliff = mocker.Mock()
    cliff.generate_unreleased_notes.return_value = '## 2.3.4\n\n- Change\n'
    mocker.patch('releez.subapps.release_notes.GitCliff', return_value=cliff)

    result = invoke(cli.app, ['release', 'notes'])

    assert result.exit_code == 0
    assert result.stdout == '## 2.3.4\n\n- Change\n\n'


def test_cli_release_notes_delegates_to_command_helper(
    mocker: MockerFixture,
) -> None:
    run_command = mocker.patch(
        'releez.subapps.release_notes._run_release_notes_command',
    )

    result = invoke(
        cli.app,
        [
            'release',
            'notes',
            '--project',
            'core',
            '--version-override',
            '1.2.3',
        ],
    )

    assert result.exit_code == 0
    run_command.assert_called_once()
    call_kwargs = run_command.call_args.kwargs
    options = call_kwargs['options']
    assert options.version_override == '1.2.3'
    assert call_kwargs['project_names'] == ['core']
    assert call_kwargs['all_projects'] is False


def test_cli_release_notes_writes_file(
    mocker: MockerFixture,
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / 'repo'
    repo_root.mkdir()

    mocker.patch(
        'releez.subapps.release.open_repo',
        return_value=mocker.Mock(
            repo=mocker.MagicMock(),
            info=mocker.Mock(root=repo_root, active_branch=None),
        ),
    )
    mocker.patch(
        'releez.subapps.release_notes._resolve_release_version',
        return_value='2.3.4',
    )

    cliff = mocker.Mock()
    cliff.generate_unreleased_notes.return_value = '## 2.3.4\n'
    mocker.patch('releez.subapps.release_notes.GitCliff', return_value=cliff)

    output = tmp_path / 'notes.md'
    result = invoke(cli.app, ['release', 'notes', '--output', str(output)])

    assert result.exit_code == 0
    assert output.read_text(encoding='utf-8') == '## 2.3.4\n'


def test_cli_release_notes_monorepo_requires_project_selection(
    mocker: MockerFixture,
    tmp_path: Path,
) -> None:
    mock_settings = _mock_settings(
        mocker,
        projects=[mocker.MagicMock(name='core-config')],
    )

    mocker.patch(
        'releez.subapps.release.open_repo',
        return_value=mocker.Mock(
            repo=mocker.MagicMock(),
            info=mocker.Mock(root=tmp_path, active_branch=None),
        ),
    )
    core = mocker.MagicMock(
        name='core',
        path=tmp_path / 'packages' / 'core',
        changelog_path=tmp_path / 'packages' / 'core' / 'CHANGELOG.md',
        tag_pattern=r'^core-([0-9]+\.[0-9]+\.[0-9]+)$',
        include_paths=[],
        tag_prefix='core-',
        alias_versions=AliasVersions.major,
    )
    core.name = 'core'
    core.hooks.post_changelog = []
    mock_settings.get_subprojects.return_value = [core]
    mock_settings.select_projects.side_effect = ReleezError(
        'Project selection is required in monorepo mode. Use --project <name> (repeatable) or --all.',
    )

    result = invoke(cli.app, ['release', 'notes'])

    assert result.exit_code == 1
    assert 'Project selection is required in monorepo mode' in result.output


def test_cli_release_notes_monorepo_project_scopes_git_cliff(
    mocker: MockerFixture,
    tmp_path: Path,
) -> None:
    mock_settings = _mock_settings(
        mocker,
        projects=[mocker.MagicMock(name='core-config')],
    )

    project_path = tmp_path / 'packages' / 'core'
    mocker.patch(
        'releez.subapps.release.open_repo',
        return_value=mocker.Mock(
            repo=mocker.MagicMock(),
            info=mocker.Mock(root=tmp_path, active_branch=None),
        ),
    )
    core = mocker.MagicMock(
        name='core',
        path=project_path,
        changelog_path=project_path / 'CHANGELOG.md',
        tag_pattern=r'^core-([0-9]+\.[0-9]+\.[0-9]+)$',
        include_paths=['pyproject.toml'],
        tag_prefix='core-',
        alias_versions=AliasVersions.major,
    )
    core.name = 'core'
    core.hooks.post_changelog = []
    mock_settings.get_subprojects.return_value = [core]
    mock_settings.select_projects.return_value = [core]
    mocker.patch(
        'releez.subapps.release_notes._resolve_project_release_version',
        return_value='1.2.3',
    )

    cliff = mocker.Mock()
    cliff.generate_unreleased_notes.return_value = '## 1.2.3\n\n- Change\n'
    mocker.patch('releez.subapps.release_notes.GitCliff', return_value=cliff)

    result = invoke(cli.app, ['release', 'notes', '--project', 'core'])

    assert result.exit_code == 0
    cliff.generate_unreleased_notes.assert_called_once_with(
        version='1.2.3',
        tag_pattern=r'^core-([0-9]+\.[0-9]+\.[0-9]+)$',
        include_paths=['packages/core/**', 'pyproject.toml'],
    )
    assert '## `core`' in result.stdout
