from pathlib import Path

from pytest_mock import MockerFixture
from typer.testing import CliRunner

from releez import cli
from releez.version_tags import VersionTags


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
            '--alias-tags',
            'minor',
        ],
    )

    assert result.exit_code == 0
    create_tags.assert_called_once_with(
        repo,
        tags=['2.3.4', 'v2', 'v2.3'],
        force=False,
    )
    push_tags.assert_called_once_with(
        repo,
        remote_name='origin',
        tags=['2.3.4', 'v2', 'v2.3'],
        force=False,
    )
    assert result.stdout == '2.3.4\nv2\nv2.3\n'


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
    cliff.compute_next_version.assert_called_once_with(bump='auto')
    create_tags.assert_called_once_with(repo, tags=['2.3.4'], force=False)
    push_tags.assert_called_once_with(
        repo,
        remote_name='origin',
        tags=['2.3.4'],
        force=False,
    )
    assert result.stdout == '2.3.4\n'


def test_cli_release_tag_no_v_prefix(mocker: MockerFixture) -> None:
    runner = CliRunner()
    repo = object()

    mocker.patch(
        'releez.cli.open_repo',
        return_value=(repo, mocker.Mock(root=Path.cwd())),
    )
    mocker.patch('releez.cli.fetch')
    compute_version_tags = mocker.patch(
        'releez.cli.compute_version_tags',
        return_value=VersionTags(exact='2.3.4', major='2', minor='2.3'),
    )
    mocker.patch('releez.cli.select_tags', return_value=['2.3.4', '2'])
    mocker.patch('releez.cli.create_tags')
    mocker.patch('releez.cli.push_tags')

    result = runner.invoke(
        cli.app,
        [
            'release',
            'tag',
            '--version-override',
            '2.3.4',
            '--alias-tags',
            'major',
            '--no-v-prefix',
        ],
    )

    assert result.exit_code == 0
    compute_version_tags.assert_called_once_with(version='2.3.4', prefix='')
    assert result.stdout == '2.3.4\n2\n'
