"""Tests for release detect-from-branch CLI command."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from typer.testing import CliRunner

from releez import cli
from releez.git_repo import DetectedRelease

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


def test_cli_release_detect_from_branch_single_repo(
    mocker: MockerFixture,
) -> None:
    """Test detecting release from single-repo branch.

    Args:
        mocker: pytest-mock fixture for creating mocks.
    """
    runner = CliRunner()

    mocker.patch(
        'releez.cli.ReleezSettings',
        return_value=mocker.MagicMock(projects=[]),
    )

    mocker.patch(
        'releez.cli.detect_release_from_branch',
        return_value=DetectedRelease(
            version='1.2.3',
            project_name=None,
            branch_name='release/1.2.3',
        ),
    )

    result = runner.invoke(
        cli.app,
        ['release', 'detect-from-branch', '--branch', 'release/1.2.3'],
    )

    assert result.exit_code == 0
    output = json.loads(result.stdout)
    assert output == {
        'version': '1.2.3',
        'branch': 'release/1.2.3',
    }


def test_cli_release_detect_from_branch_monorepo(
    mocker: MockerFixture,
) -> None:
    """Test detecting release from monorepo branch.

    Args:
        mocker: pytest-mock fixture for creating mocks.
    """
    runner = CliRunner()

    mock_repo_info = mocker.MagicMock(root=mocker.MagicMock())

    mocker.patch(
        'releez.cli.ReleezSettings',
        return_value=mocker.MagicMock(projects=[mocker.MagicMock()]),
    )

    mocker.patch(
        'releez.cli.open_repo',
        return_value=(mocker.MagicMock(), mock_repo_info),
    )
    mocker.patch(
        'releez.cli.SubProject.from_config',
        return_value=mocker.MagicMock(),
    )

    mocker.patch(
        'releez.cli.detect_release_from_branch',
        return_value=DetectedRelease(
            version='core-1.2.3',
            project_name='core',
            branch_name='release/core-1.2.3',
        ),
    )

    result = runner.invoke(
        cli.app,
        ['release', 'detect-from-branch', '--branch', 'release/core-1.2.3'],
    )

    assert result.exit_code == 0
    output = json.loads(result.stdout)
    assert output == {
        'version': 'core-1.2.3',
        'project': 'core',
        'branch': 'release/core-1.2.3',
    }


def test_cli_release_detect_from_branch_not_release_branch(
    mocker: MockerFixture,
) -> None:
    """Test error when branch is not a release branch.

    Args:
        mocker: pytest-mock fixture for creating mocks.
    """
    runner = CliRunner()

    mocker.patch(
        'releez.cli.ReleezSettings',
        return_value=mocker.MagicMock(projects=[]),
    )

    mocker.patch('releez.cli.detect_release_from_branch', return_value=None)

    result = runner.invoke(
        cli.app,
        ['release', 'detect-from-branch', '--branch', 'main'],
    )

    assert result.exit_code == 1
    assert 'not a release branch' in result.output


def test_cli_release_detect_from_branch_uses_current_branch(
    mocker: MockerFixture,
) -> None:
    """Test using current branch when --branch not specified.

    Args:
        mocker: pytest-mock fixture for creating mocks.
    """
    runner = CliRunner()

    mocker.patch(
        'releez.cli.ReleezSettings',
        return_value=mocker.MagicMock(projects=[]),
    )

    mock_info = mocker.MagicMock(active_branch='release/1.2.3')
    mocker.patch(
        'releez.cli.open_repo',
        return_value=(mocker.MagicMock(), mock_info),
    )

    mocker.patch(
        'releez.cli.detect_release_from_branch',
        return_value=DetectedRelease(
            version='1.2.3',
            project_name=None,
            branch_name='release/1.2.3',
        ),
    )

    result = runner.invoke(cli.app, ['release', 'detect-from-branch'])

    assert result.exit_code == 0
    output = json.loads(result.stdout)
    assert output['version'] == '1.2.3'


def test_cli_release_detect_from_branch_detached_head_error(
    mocker: MockerFixture,
) -> None:
    """Test error when in detached HEAD state without --branch.

    Args:
        mocker: pytest-mock fixture for creating mocks.
    """
    runner = CliRunner()

    mocker.patch(
        'releez.cli.ReleezSettings',
        return_value=mocker.MagicMock(projects=[]),
    )

    mock_info = mocker.MagicMock(active_branch=None)
    mocker.patch(
        'releez.cli.open_repo',
        return_value=(mocker.MagicMock(), mock_info),
    )

    result = runner.invoke(cli.app, ['release', 'detect-from-branch'])

    assert result.exit_code == 1
    assert 'detached HEAD' in result.output
