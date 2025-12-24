from pytest_mock import MockerFixture
from typer.testing import CliRunner

from releez import cli
from releez.version_tags import VersionTags


def test_cli_release_tag_calls_git_helpers(mocker: MockerFixture) -> None:
    runner = CliRunner()

    repo = object()
    mocker.patch('releez.cli.open_repo', return_value=(repo, object()))
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
            '--version',
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


def test_cli_release_tag_no_v_prefix(mocker: MockerFixture) -> None:
    runner = CliRunner()
    repo = object()

    mocker.patch('releez.cli.open_repo', return_value=(repo, object()))
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
            '--version',
            '2.3.4',
            '--alias-tags',
            'major',
            '--no-v-prefix',
        ],
    )

    assert result.exit_code == 0
    compute_version_tags.assert_called_once_with(version='2.3.4', prefix='')
    assert result.stdout == '2.3.4\n2\n'
