from __future__ import annotations

from typing import TYPE_CHECKING

from git import Repo
from semver import VersionInfo
from typer.testing import CliRunner

from releez import cli
from releez.git_repo import RepoContext, RepoInfo

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture


def test_cli_release_notes_stdout(
    mocker: MockerFixture,
    tmp_path: Path,
) -> None:
    runner = CliRunner()
    repo_root = tmp_path / 'repo'
    repo_root.mkdir()

    repo_info = RepoInfo(
        root=repo_root,
        remote_url='',
        active_branch='feature/test',
    )
    mocker.patch(
        'releez.cli.open_repo',
        return_value=RepoContext(repo=mocker.Mock(spec=Repo), info=repo_info),
    )
    mocker.patch(
        'releez.cli._resolve_release_version',
        return_value=VersionInfo.parse('2.3.4'),
    )

    cliff = mocker.Mock()
    cliff.generate_unreleased_notes.return_value = '## 2.3.4\n\n- Change\n'
    mocker.patch('releez.cli.GitCliff', return_value=cliff)

    result = runner.invoke(cli.app, ['release', 'notes'])

    assert result.exit_code == 0
    assert result.stdout == '## 2.3.4\n\n- Change\n\n'


def test_cli_release_notes_writes_file(
    mocker: MockerFixture,
    tmp_path: Path,
) -> None:
    runner = CliRunner()
    repo_root = tmp_path / 'repo'
    repo_root.mkdir()

    repo_info = RepoInfo(
        root=repo_root,
        remote_url='',
        active_branch='feature/test',
    )
    mocker.patch(
        'releez.cli.open_repo',
        return_value=RepoContext(repo=mocker.Mock(spec=Repo), info=repo_info),
    )
    mocker.patch(
        'releez.cli._resolve_release_version',
        return_value=VersionInfo.parse('2.3.4'),
    )

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
