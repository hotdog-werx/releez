from __future__ import annotations

from typing import TYPE_CHECKING

from typer.testing import CliRunner

from releez import cli
from releez.version_tags import AliasVersions

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture


def _mock_settings(
    mocker: MockerFixture,
    *,
    projects: list[object],
) -> None:
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


def test_cli_release_notes_stdout(
    mocker: MockerFixture,
    tmp_path: Path,
) -> None:
    runner = CliRunner()
    repo_root = tmp_path / 'repo'
    repo_root.mkdir()

    mocker.patch(
        'releez.cli.open_repo',
        return_value=(object(), mocker.Mock(root=repo_root)),
    )
    mocker.patch('releez.cli._resolve_release_version', return_value='2.3.4')

    cliff = mocker.Mock()
    cliff.generate_unreleased_notes.return_value = '## 2.3.4\n\n- Change\n'
    mocker.patch('releez.cli.GitCliff', return_value=cliff)

    result = runner.invoke(cli.app, ['release', 'notes'])

    assert result.exit_code == 0
    assert result.stdout == '## 2.3.4\n\n- Change\n\n'


def test_cli_release_notes_delegates_to_command_helper(
    mocker: MockerFixture,
) -> None:
    runner = CliRunner()
    run_command = mocker.patch('releez.cli._run_release_notes_command')

    result = runner.invoke(
        cli.app,
        [
            'release',
            'notes',
            '--project',
            'core',
            '--all',
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
    assert call_kwargs['all_projects'] is True


def test_cli_release_notes_writes_file(
    mocker: MockerFixture,
    tmp_path: Path,
) -> None:
    runner = CliRunner()
    repo_root = tmp_path / 'repo'
    repo_root.mkdir()

    mocker.patch(
        'releez.cli.open_repo',
        return_value=(object(), mocker.Mock(root=repo_root)),
    )
    mocker.patch('releez.cli._resolve_release_version', return_value='2.3.4')

    cliff = mocker.Mock()
    cliff.generate_unreleased_notes.return_value = '## 2.3.4\n'
    mocker.patch('releez.cli.GitCliff', return_value=cliff)

    output = tmp_path / 'notes.md'
    result = runner.invoke(
        cli.app,
        ['release', 'notes', '--output', str(output)],
    )

    assert result.exit_code == 0
    assert output.read_text(encoding='utf-8') == '## 2.3.4\n'


def test_cli_release_notes_monorepo_requires_project_selection(
    mocker: MockerFixture,
    tmp_path: Path,
) -> None:
    runner = CliRunner()
    _mock_settings(mocker, projects=[mocker.MagicMock(name='core-config')])

    mocker.patch(
        'releez.cli.open_repo',
        return_value=(mocker.MagicMock(), mocker.Mock(root=tmp_path)),
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
    mocker.patch('releez.cli.SubProject.from_config', return_value=core)

    result = runner.invoke(cli.app, ['release', 'notes'])

    assert result.exit_code == 1
    assert 'Project selection is required in monorepo mode' in result.output


def test_cli_release_notes_monorepo_project_scopes_git_cliff(
    mocker: MockerFixture,
    tmp_path: Path,
) -> None:
    runner = CliRunner()
    _mock_settings(mocker, projects=[mocker.MagicMock(name='core-config')])

    project_path = tmp_path / 'packages' / 'core'
    mocker.patch(
        'releez.cli.open_repo',
        return_value=(mocker.MagicMock(), mocker.Mock(root=tmp_path)),
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
    mocker.patch('releez.cli.SubProject.from_config', return_value=core)
    mocker.patch('releez.cli._resolve_release_version', return_value='1.2.3')

    cliff = mocker.Mock()
    cliff.generate_unreleased_notes.return_value = '## 1.2.3\n\n- Change\n'
    mocker.patch('releez.cli.GitCliff', return_value=cliff)

    result = runner.invoke(cli.app, ['release', 'notes', '--project', 'core'])

    assert result.exit_code == 0
    cliff.generate_unreleased_notes.assert_called_once_with(
        version='1.2.3',
        tag_pattern=r'^core-([0-9]+\.[0-9]+\.[0-9]+)$',
        include_paths=['packages/core/**', 'pyproject.toml'],
    )
    assert '## `core`' in result.stdout
