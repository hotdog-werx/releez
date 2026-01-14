from __future__ import annotations

from typing import TYPE_CHECKING

from git import Repo
from typer.testing import CliRunner

from releez import cli
from releez.git_repo import RepoContext, RepoInfo

if TYPE_CHECKING:
    from pathlib import Path

    import pytest
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


def test_cli_release_start_run_changelog_format_uses_configured_command(
    mocker: MockerFixture,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = CliRunner()
    monkeypatch.chdir(tmp_path)

    monkeypatch.setenv(
        'RELEEZ_HOOKS__CHANGELOG_FORMAT',
        '["dprint", "fmt", "{changelog}"]',
    )

    repo_info = RepoInfo(
        root=tmp_path,
        remote_url='',
        active_branch='feature/test',
    )
    mocker.patch(
        'releez.cli.open_repo',
        return_value=RepoContext(repo=mocker.Mock(spec=Repo), info=repo_info),
    )

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
        ['release', 'start', '--dry-run', '--run-changelog-format'],
    )

    assert result.exit_code == 0
    release_input = start_release.call_args.args[0]
    assert release_input.run_changelog_format is True
    assert release_input.changelog_format_cmd == [
        'dprint',
        'fmt',
        '{changelog}',
    ]


def test_cli_release_start_run_changelog_format_requires_command(
    mocker: MockerFixture,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = CliRunner()
    monkeypatch.chdir(tmp_path)

    repo_info = RepoInfo(
        root=tmp_path,
        remote_url='',
        active_branch='feature/test',
    )
    mocker.patch(
        'releez.cli.open_repo',
        return_value=RepoContext(repo=mocker.Mock(spec=Repo), info=repo_info),
    )

    mocker.patch(
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
        ['release', 'start', '--dry-run', '--run-changelog-format'],
    )

    assert result.exit_code == 1
    assert 'no format command is configured' in result.output.lower()
