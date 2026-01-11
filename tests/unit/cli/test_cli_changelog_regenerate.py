from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from typer.testing import CliRunner

from releez import cli
from releez.errors import MissingCliError

if TYPE_CHECKING:
    from pathlib import Path
    from unittest.mock import Mock

    from pytest_mock import MockerFixture


@pytest.fixture
def mock_changelog_setup(
    mocker: MockerFixture,
    tmp_path: Path,
) -> tuple[Path, Mock]:
    """Set up common mocks for changelog tests.

    Returns:
        Tuple of (repo_root, mocked_cliff)
    """
    repo_root = tmp_path / 'repo'
    repo_root.mkdir()

    mocker.patch(
        'releez.typer_app.changelog.open_repo',
        return_value=(object(), mocker.Mock(root=repo_root)),
    )

    cliff = mocker.Mock()
    mocker.patch('releez.typer_app.changelog.GitCliff', return_value=cliff)

    return repo_root, cliff


def test_changelog_regenerate_basic(
    mock_changelog_setup: tuple[Path, Mock],
) -> None:
    """Test basic changelog regeneration without formatting."""
    repo_root, cliff = mock_changelog_setup
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        ['changelog', 'regenerate'],
    )

    assert result.exit_code == 0
    cliff.regenerate_changelog.assert_called_once()
    call_args = cliff.regenerate_changelog.call_args
    assert call_args.kwargs['changelog_path'] == repo_root / 'CHANGELOG.md'


def test_changelog_regenerate_custom_path(
    mock_changelog_setup: tuple[Path, Mock],
) -> None:
    """Test changelog regeneration with custom path."""
    repo_root, cliff = mock_changelog_setup
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        ['changelog', 'regenerate', '--changelog-path', 'HISTORY.md'],
    )

    assert result.exit_code == 0
    cliff.regenerate_changelog.assert_called_once()
    call_args = cliff.regenerate_changelog.call_args
    assert call_args.kwargs['changelog_path'] == repo_root / 'HISTORY.md'


def test_changelog_regenerate_absolute_path(
    mock_changelog_setup: tuple[Path, Mock],
    tmp_path: Path,
) -> None:
    """Test changelog regeneration with absolute path."""
    _, cliff = mock_changelog_setup
    runner = CliRunner()
    changelog_path = tmp_path / 'custom' / 'CHANGELOG.md'

    result = runner.invoke(
        cli.app,
        ['changelog', 'regenerate', '--changelog-path', str(changelog_path)],
    )

    assert result.exit_code == 0
    cliff.regenerate_changelog.assert_called_once()
    call_args = cliff.regenerate_changelog.call_args
    assert call_args.kwargs['changelog_path'] == changelog_path


def test_changelog_regenerate_with_format(
    mock_changelog_setup: tuple[Path, Mock],
    mocker: MockerFixture,
) -> None:
    """Test changelog regeneration with formatting enabled."""
    repo_root, cliff = mock_changelog_setup
    runner = CliRunner()

    run_checked = mocker.patch('releez.typer_app.changelog.run_checked')

    result = runner.invoke(
        cli.app,
        [
            'changelog',
            'regenerate',
            '--run-changelog-format',
            '--changelog-format-cmd',
            'prettier',
            '--changelog-format-cmd',
            '--write',
            '--changelog-format-cmd',
            '{changelog}',
        ],
    )

    assert result.exit_code == 0
    cliff.regenerate_changelog.assert_called_once()
    run_checked.assert_called_once()
    call_args = run_checked.call_args
    expected_changelog = repo_root / 'CHANGELOG.md'
    assert call_args.args[0] == ['prettier', '--write', str(expected_changelog)]
    assert call_args.kwargs['cwd'] == repo_root
    assert call_args.kwargs['capture_stdout'] is False


def test_changelog_regenerate_format_without_cmd_raises_error(
    mock_changelog_setup: tuple[Path, Mock],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that enabling format without providing cmd raises error."""
    _, cliff = mock_changelog_setup
    runner = CliRunner()
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(
        cli.app,
        ['changelog', 'regenerate', '--run-changelog-format'],
    )

    assert result.exit_code == 1
    assert 'no format command is configured' in result.output.lower()
    # Verify GitCliff was not called since error happens before
    cliff.regenerate_changelog.assert_not_called()


def test_changelog_regenerate_handles_releez_error(
    mocker: MockerFixture,
    tmp_path: Path,
) -> None:
    """Test that ReleezError is properly handled and reported."""
    runner = CliRunner()
    repo_root = tmp_path / 'repo'
    repo_root.mkdir()

    mocker.patch(
        'releez.typer_app.changelog.open_repo',
        return_value=(object(), mocker.Mock(root=repo_root)),
    )

    # This test needs to raise an error during GitCliff creation,
    # so we can't use the fixture which mocks it successfully
    mocker.patch(
        'releez.typer_app.changelog.GitCliff',
        side_effect=MissingCliError('git-cliff'),
    )

    result = runner.invoke(
        cli.app,
        ['changelog', 'regenerate'],
    )

    assert result.exit_code == 1
    assert 'git-cliff' in result.output
