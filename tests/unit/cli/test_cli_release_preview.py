from __future__ import annotations

from typing import TYPE_CHECKING

from typer.testing import CliRunner

from releez import cli
from releez.git_repo import RepoContext, RepoInfo

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture


def test_cli_release_preview_writes_markdown(
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
        return_value=RepoContext(repo=object(), info=repo_info),
    )

    cliff = mocker.Mock()
    cliff.compute_next_version.return_value = '2.3.4'
    mocker.patch('releez.cli.GitCliff', return_value=cliff)

    output = tmp_path / 'preview.md'
    result = runner.invoke(
        cli.app,
        [
            'release',
            'preview',
            '--alias-versions',
            'major',
            '--output',
            str(output),
        ],
    )

    assert result.exit_code == 0
    content = output.read_text(encoding='utf-8')
    assert '## `releez` release preview' in content
    assert '`2.3.4`' in content


def test_cli_release_preview_stdout(
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
        return_value=RepoContext(repo=object(), info=repo_info),
    )

    cliff = mocker.Mock()
    cliff.compute_next_version.return_value = '1.2.3'
    mocker.patch('releez.cli.GitCliff', return_value=cliff)

    result = runner.invoke(
        cli.app,
        [
            'release',
            'preview',
            '--alias-versions',
            'none',
        ],
    )

    assert result.exit_code == 0
    assert '## `releez` release preview' in result.stdout
    assert '`1.2.3`' in result.stdout
