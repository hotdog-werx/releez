"""Tests for release detect-from-branch CLI command."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from invoke_helper import invoke

from releez import cli
from releez.errors import DirtyWorkingTreeError
from releez.git_repo import DetectedRelease

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


def test_cli_release_detect_from_branch_single_repo(
    mocker: MockerFixture,
) -> None:
    mocker.patch(
        'releez.subapps.release_support.open_repo',
        return_value=mocker.Mock(
            repo=mocker.MagicMock(),
            info=mocker.MagicMock(root='/repo'),
        ),
    )
    mocker.patch(
        'releez.subapps.release_support.detect_release_from_branch',
        return_value=DetectedRelease(
            version='1.2.3',
            semver_version='1.2.3',
            project_name=None,
            branch_name='release/1.2.3',
        ),
    )

    result = invoke(
        cli.app,
        ['release', 'detect-from-branch', '--branch', 'release/1.2.3'],
    )

    assert result.exit_code == 0
    output = json.loads(result.stdout)
    assert output == {
        'version': '1.2.3',
        'semver_version': '1.2.3',
        'branch': 'release/1.2.3',
    }


def test_cli_release_detect_from_branch_monorepo(
    mocker: MockerFixture,
) -> None:
    mock_repo_info = mocker.MagicMock(root=mocker.MagicMock())

    mock_settings = mocker.MagicMock(projects=[mocker.MagicMock()])
    mock_settings.get_subprojects.return_value = [mocker.MagicMock()]
    mocker.patch(
        'releez.subapps.release_support.ReleezSettings',
        return_value=mock_settings,
    )

    mocker.patch(
        'releez.subapps.release_support.open_repo',
        return_value=mocker.Mock(repo=mocker.MagicMock(), info=mock_repo_info),
    )

    mocker.patch(
        'releez.subapps.release_support.detect_release_from_branch',
        return_value=DetectedRelease(
            version='core-1.2.3',
            semver_version='1.2.3',
            project_name='core',
            branch_name='release/core-1.2.3',
        ),
    )

    result = invoke(
        cli.app,
        ['release', 'detect-from-branch', '--branch', 'release/core-1.2.3'],
    )

    assert result.exit_code == 0
    output = json.loads(result.stdout)
    assert output == {
        'version': 'core-1.2.3',
        'semver_version': '1.2.3',
        'project': 'core',
        'branch': 'release/core-1.2.3',
    }


def test_cli_release_detect_from_branch_not_release_branch(
    mocker: MockerFixture,
) -> None:
    mocker.patch(
        'releez.subapps.release_support.open_repo',
        return_value=mocker.Mock(
            repo=mocker.MagicMock(),
            info=mocker.MagicMock(root='/repo'),
        ),
    )
    mocker.patch(
        'releez.subapps.release_support.detect_release_from_branch',
        return_value=None,
    )

    result = invoke(
        cli.app,
        ['release', 'detect-from-branch', '--branch', 'main'],
    )

    assert result.exit_code == 1
    assert 'not a release branch' in result.output


def test_cli_release_detect_from_branch_uses_current_branch(
    mocker: MockerFixture,
) -> None:
    mock_info = mocker.MagicMock(active_branch='release/1.2.3')
    mocker.patch(
        'releez.subapps.release_support.open_repo',
        return_value=mocker.Mock(repo=mocker.MagicMock(), info=mock_info),
    )

    mocker.patch(
        'releez.subapps.release_support.detect_release_from_branch',
        return_value=DetectedRelease(
            version='1.2.3',
            semver_version='1.2.3',
            project_name=None,
            branch_name='release/1.2.3',
        ),
    )

    result = invoke(cli.app, ['release', 'detect-from-branch'])

    assert result.exit_code == 0
    output = json.loads(result.stdout)
    assert output['version'] == '1.2.3'


def test_cli_release_detect_from_branch_detached_head_error(
    mocker: MockerFixture,
) -> None:
    mock_info = mocker.MagicMock(active_branch=None)
    mocker.patch(
        'releez.subapps.release_support.open_repo',
        return_value=mocker.Mock(repo=mocker.MagicMock(), info=mock_info),
    )

    result = invoke(cli.app, ['release', 'detect-from-branch'])

    assert result.exit_code == 1
    assert 'detached HEAD' in result.output


def test_cli_release_detect_from_branch_handles_releez_error(
    mocker: MockerFixture,
) -> None:
    mocker.patch(
        'releez.subapps.release_support.open_repo',
        return_value=mocker.Mock(
            repo=mocker.MagicMock(),
            info=mocker.MagicMock(root='/repo'),
        ),
    )
    mocker.patch(
        'releez.subapps.release_support.detect_release_from_branch',
        side_effect=DirtyWorkingTreeError,
    )

    result = invoke(
        cli.app,
        ['release', 'detect-from-branch', '--branch', 'release/1.2.3'],
    )

    assert result.exit_code == 1
    assert 'Working tree is not clean' in result.output
