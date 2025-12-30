from __future__ import annotations

from typing import TYPE_CHECKING

from typer.testing import CliRunner

from releez import cli

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


def test_cli_release_start_passes_version_override(
    mocker: MockerFixture,
) -> None:
    runner = CliRunner()

    start_release = mocker.patch(
        'releez.cli.start_release',
        return_value=mocker.Mock(
            version='1.2.3',
            release_notes_markdown='notes',
            release_branch=None,
            pr_url=None,
        ),
    )

    result = runner.invoke(
        cli.app,
        [
            'release',
            'start',
            '--dry-run',
            '--version-override',
            '1.2.3',
        ],
    )

    assert result.exit_code == 0
    release_input = start_release.call_args.args[0]
    assert release_input.version_override == '1.2.3'


def test_cli_release_start_defaults_version_override_to_none(
    mocker: MockerFixture,
) -> None:
    runner = CliRunner()

    start_release = mocker.patch(
        'releez.cli.start_release',
        return_value=mocker.Mock(
            version='1.2.3',
            release_notes_markdown='notes',
            release_branch=None,
            pr_url=None,
        ),
    )

    result = runner.invoke(cli.app, ['release', 'start', '--dry-run'])

    assert result.exit_code == 0
    release_input = start_release.call_args.args[0]
    assert release_input.version_override is None
