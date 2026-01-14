from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from typer.testing import CliRunner

from releez import cli
from releez.git_repo import RepoContext, RepoInfo
from releez.version_tags import VersionTags

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


def test_cli_release_tag_calls_git_helpers(mocker: MockerFixture) -> None:
    runner = CliRunner()

    repo = object()
    repo_info = RepoInfo(
        root=Path.cwd(),
        remote_url='',
        active_branch='feature/test',
    )
    mocker.patch(
        'releez.cli.open_repo',
        return_value=RepoContext(repo=repo, info=repo_info),
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


def test_cli_release_tag_defaults_to_git_cliff(
    mocker: MockerFixture,
    tmp_path: Path,
) -> None:
    runner = CliRunner()

    repo = object()
    repo_info = RepoInfo(
        root=tmp_path,
        remote_url='',
        active_branch='feature/test',
    )
    mocker.patch(
        'releez.cli.open_repo',
        return_value=RepoContext(repo=repo, info=repo_info),
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
    )
    create_tags.assert_called_once_with(repo, tags=['2.3.4'], force=False)
    push_tags.assert_called_once_with(
        repo,
        remote_name='origin',
        tags=['2.3.4'],
        force=False,
    )
    assert result.stdout == '2.3.4\n'
