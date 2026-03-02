from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from typer.testing import CliRunner

from releez import cli
from releez.version_tags import AliasVersions, VersionTags

if TYPE_CHECKING:
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


def test_cli_release_tag_calls_git_helpers(mocker: MockerFixture) -> None:
    runner = CliRunner()

    repo = object()
    mocker.patch(
        'releez.cli.open_repo',
        return_value=(repo, mocker.Mock(root=Path.cwd())),
    )
    mocker.patch('releez.cli.fetch')
    mocker.patch(
        'releez.cli.compute_version_tags',
        return_value=VersionTags(exact='2.3.4', major='v2', minor='v2.3'),
    )
    mocker.patch('releez.cli.select_tags', return_value=['2.3.4', 'v2', 'v2.3'])
    create_tags = mocker.patch('releez.cli.create_tags')
    push_tags = mocker.patch('releez.cli.push_tags')

    result = runner.invoke(
        cli.app,
        [
            'release',
            'tag',
            '--version-override',
            '2.3.4',
            '--alias-versions',
            'minor',
        ],
    )

    assert result.exit_code == 0
    assert create_tags.call_args_list == [
        mocker.call(repo, tags=['2.3.4'], force=False),
        mocker.call(repo, tags=['v2', 'v2.3'], force=True),
    ]
    assert push_tags.call_args_list == [
        mocker.call(repo, remote_name='origin', tags=['2.3.4'], force=False),
        mocker.call(
            repo,
            remote_name='origin',
            tags=['v2', 'v2.3'],
            force=True,
        ),
    ]
    assert result.stdout == '2.3.4\nv2\nv2.3\n'


def test_cli_release_tag_delegates_to_command_helper(
    mocker: MockerFixture,
) -> None:
    runner = CliRunner()
    run_command = mocker.patch('releez.cli._run_release_tag_command')

    result = runner.invoke(
        cli.app,
        [
            'release',
            'tag',
            '--project',
            'core',
            '--all',
            '--version-override',
            '1.2.3',
            '--alias-versions',
            'major',
            '--remote',
            'upstream',
        ],
    )

    assert result.exit_code == 0
    run_command.assert_called_once()
    call_kwargs = run_command.call_args.kwargs
    options = call_kwargs['options']
    assert options.version_override == '1.2.3'
    assert options.alias_versions == AliasVersions.major
    assert options.remote == 'upstream'
    assert call_kwargs['project_names'] == ['core']
    assert call_kwargs['all_projects'] is True


def test_cli_release_tag_defaults_to_git_cliff(
    mocker: MockerFixture,
    tmp_path: Path,
) -> None:
    runner = CliRunner()

    repo = object()
    mocker.patch(
        'releez.cli.open_repo',
        return_value=(repo, mocker.Mock(root=tmp_path)),
    )
    mocker.patch('releez.cli.fetch')

    cliff = mocker.Mock()
    cliff.compute_next_version.return_value = '2.3.4'
    mocker.patch('releez.cli.GitCliff', return_value=cliff)

    mocker.patch(
        'releez.cli.compute_version_tags',
        return_value=VersionTags(exact='2.3.4', major='v2', minor='v2.3'),
    )
    mocker.patch('releez.cli.select_tags', return_value=['2.3.4'])
    create_tags = mocker.patch('releez.cli.create_tags')
    push_tags = mocker.patch('releez.cli.push_tags')

    result = runner.invoke(cli.app, ['release', 'tag'])

    assert result.exit_code == 0
    cliff.compute_next_version.assert_called_once_with(
        bump='auto',
        tag_pattern=None,
        include_paths=None,
    )
    create_tags.assert_called_once_with(repo, tags=['2.3.4'], force=False)
    push_tags.assert_called_once_with(
        repo,
        remote_name='origin',
        tags=['2.3.4'],
        force=False,
    )
    assert result.stdout == '2.3.4\n'


def test_cli_release_tag_monorepo_requires_project_selection(
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

    result = runner.invoke(cli.app, ['release', 'tag'])

    assert result.exit_code == 1
    assert 'Project selection is required in monorepo mode' in result.output


def test_cli_release_tag_monorepo_project_uses_prefix_and_scope(
    mocker: MockerFixture,
    tmp_path: Path,
) -> None:
    runner = CliRunner()
    _mock_settings(mocker, projects=[mocker.MagicMock(name='core-config')])

    repo = object()
    project_path = tmp_path / 'packages' / 'core'
    mocker.patch(
        'releez.cli.open_repo',
        return_value=(repo, mocker.Mock(root=tmp_path)),
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

    mocker.patch('releez.cli.fetch')
    resolve_release_version = mocker.patch(
        'releez.cli._resolve_release_version',
        return_value='1.2.3',
    )
    create_tags = mocker.patch('releez.cli.create_tags')
    push_tags = mocker.patch('releez.cli.push_tags')

    result = runner.invoke(cli.app, ['release', 'tag', '--project', 'core'])

    assert result.exit_code == 0
    resolve_release_version.assert_called_once_with(
        repo_root=tmp_path,
        version_override=None,
        tag_pattern=r'^core-([0-9]+\.[0-9]+\.[0-9]+)$',
        include_paths=['packages/core/**', 'pyproject.toml'],
    )
    assert create_tags.call_args_list == [
        mocker.call(repo, tags=['core-1.2.3'], force=False),
        mocker.call(repo, tags=['core-v1'], force=True),
    ]
    assert push_tags.call_args_list == [
        mocker.call(
            repo,
            remote_name='origin',
            tags=['core-1.2.3'],
            force=False,
        ),
        mocker.call(repo, remote_name='origin', tags=['core-v1'], force=True),
    ]
    assert result.stdout == '[core] core-1.2.3\n[core] core-v1\n'
