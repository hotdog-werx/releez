from __future__ import annotations

from typing import TYPE_CHECKING

from releez import cli
from releez.errors import ReleezError
from releez.version_tags import AliasVersions

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path
    from unittest.mock import MagicMock

    from invoke_helper import InvokeResult
    from pytest_mock import MockerFixture


def _mock_repo_context(
    mocker: MockerFixture,
    *,
    repo_root: Path,
) -> None:
    mocker.patch(
        'releez.subapps.release.open_repo',
        return_value=mocker.Mock(
            repo=mocker.MagicMock(),
            info=mocker.MagicMock(root=repo_root, active_branch=None),
        ),
    )


def _mock_settings(
    mocker: MockerFixture,
    *,
    projects: list[object],
) -> MagicMock:
    hooks = mocker.MagicMock(post_changelog=[])
    mock_settings = mocker.MagicMock(
        base_branch='master',
        git_remote='origin',
        pr_labels='release',
        pr_title_prefix='chore(release): ',
        changelog_path='CHANGELOG.md',
        create_pr=False,
        alias_versions=AliasVersions.none,
        hooks=hooks,
        projects=projects,
    )
    mocker.patch(
        'releez.subapps.release_start.ReleezSettings',
        return_value=mock_settings,
    )
    return mock_settings


def test_cli_release_start_passes_version_override(
    mocker: MockerFixture,
    invoke: Callable[[object, list[str]], InvokeResult],
    tmp_path: Path,
) -> None:
    _mock_repo_context(mocker, repo_root=tmp_path)

    start_release = mocker.patch(
        'releez.subapps.release_start.start_release',
        return_value=mocker.Mock(
            version='1.2.3',
            release_notes_markdown='notes',
            release_branch=None,
            pr_url=None,
        ),
    )

    result = invoke(
        cli.app,
        ['release', 'start', '--dry-run', '--version-override', '1.2.3'],
    )

    assert result.exit_code == 0
    release_input = start_release.call_args.args[0]
    assert release_input.version_override == '1.2.3'


def test_cli_release_start_delegates_to_command_helper(
    mocker: MockerFixture,
    invoke: Callable[[object, list[str]], InvokeResult],
    tmp_path: Path,
) -> None:
    _mock_repo_context(mocker, repo_root=tmp_path)

    run_command = mocker.patch(
        'releez.subapps.release_start._run_release_start_command',
    )
    result = invoke(
        cli.app,
        [
            'release',
            'start',
            '--dry-run',
            '--project',
            'core',
            '--version-override',
            '1.2.3',
        ],
    )

    assert result.exit_code == 0
    run_command.assert_called_once()
    call_kwargs = run_command.call_args.kwargs
    options = call_kwargs['options']
    assert options.version_override == '1.2.3'
    assert options.dry_run is True
    assert call_kwargs['project_names'] == ['core']
    assert call_kwargs['all_projects'] is False


def test_cli_release_start_defaults_version_override_to_none(
    mocker: MockerFixture,
    invoke: Callable[[object, list[str]], InvokeResult],
    tmp_path: Path,
) -> None:
    _mock_repo_context(mocker, repo_root=tmp_path)

    start_release = mocker.patch(
        'releez.subapps.release_start.start_release',
        return_value=mocker.Mock(
            version='1.2.3',
            release_notes_markdown='notes',
            release_branch=None,
            pr_url=None,
        ),
    )

    result = invoke(cli.app, ['release', 'start', '--dry-run'])

    assert result.exit_code == 0
    release_input = start_release.call_args.args[0]
    assert release_input.version_override is None


def test_cli_release_start_monorepo_requires_explicit_project_selection(
    mocker: MockerFixture,
    invoke: Callable[[object, list[str]], InvokeResult],
    tmp_path: Path,
) -> None:
    """In monorepo mode, release start must fail without --project or --all."""
    _mock_repo_context(mocker, repo_root=tmp_path)
    mock_settings = _mock_settings(
        mocker,
        projects=[mocker.MagicMock(name='core-config')],
    )

    project_path = tmp_path / 'packages' / 'core'
    project_path.mkdir(parents=True)
    project = mocker.MagicMock(
        spec=[
            'name',
            'path',
            'changelog_path',
            'tag_pattern',
            'include_paths',
            'tag_prefix',
            'hooks',
        ],
    )
    project.name = 'core'

    mock_settings.get_subprojects.return_value = [project]
    mock_settings.select_projects.side_effect = ReleezError(
        'Project selection is required in monorepo mode. Use --project <name> (repeatable) or --all.',
    )
    start_release = mocker.patch('releez.subapps.release_start.start_release')

    result = invoke(cli.app, ['release', 'start', '--dry-run'])

    assert result.exit_code == 1
    assert '--project' in result.output or '--all' in result.output
    start_release.assert_not_called()


def test_cli_release_start_monorepo_with_project_flag(
    mocker: MockerFixture,
    invoke: Callable[[object, list[str]], InvokeResult],
    tmp_path: Path,
) -> None:
    """In monorepo mode, release start succeeds when --project is specified."""
    _mock_repo_context(mocker, repo_root=tmp_path)
    mock_settings = _mock_settings(
        mocker,
        projects=[mocker.MagicMock(name='core-config')],
    )

    project_path = tmp_path / 'packages' / 'core'
    project_path.mkdir(parents=True)
    project = mocker.MagicMock(
        name='core',
        path=project_path,
        changelog_path=project_path / 'CHANGELOG.md',
        tag_pattern=r'^core-([0-9]+\.[0-9]+\.[0-9]+)$',
        include_paths=['pyproject.toml'],
        tag_prefix='core-',
    )
    project.name = 'core'
    project.hooks.post_changelog = []

    mock_settings.get_subprojects.return_value = [project]
    mock_settings.select_projects.return_value = [project]

    start_release = mocker.patch(
        'releez.subapps.release_start.start_release',
        return_value=mocker.Mock(
            version='core-1.2.3',
            release_notes_markdown='notes',
            release_branch=None,
            pr_url=None,
        ),
    )

    result = invoke(
        cli.app,
        ['release', 'start', '--dry-run', '--project', 'core'],
    )

    assert result.exit_code == 0
    assert '[core] Next version: core-1.2.3' in result.output

    release_input = start_release.call_args.args[0]
    assert release_input.project_name == 'core'
    assert release_input.tag_pattern == r'^core-([0-9]+\.[0-9]+\.[0-9]+)$'
    assert release_input.changelog_path == 'packages/core/CHANGELOG.md'
    assert release_input.include_paths == ['packages/core/**', 'pyproject.toml']


def test_cli_release_start_monorepo_override_requires_single_project(
    mocker: MockerFixture,
    invoke: Callable[[object, list[str]], InvokeResult],
    tmp_path: Path,
) -> None:
    _mock_repo_context(mocker, repo_root=tmp_path)
    mock_settings = _mock_settings(
        mocker,
        projects=[
            mocker.MagicMock(name='core-config'),
            mocker.MagicMock(name='ui-config'),
        ],
    )

    core_path = tmp_path / 'packages' / 'core'
    ui_path = tmp_path / 'packages' / 'ui'
    core_path.mkdir(parents=True)
    ui_path.mkdir(parents=True)

    core = mocker.MagicMock(
        name='core',
        path=core_path,
        changelog_path=core_path / 'CHANGELOG.md',
        tag_pattern=r'^core-([0-9]+\.[0-9]+\.[0-9]+)$',
        include_paths=[],
        tag_prefix='core-',
    )
    core.name = 'core'
    core.hooks.post_changelog = []

    ui = mocker.MagicMock(
        name='ui',
        path=ui_path,
        changelog_path=ui_path / 'CHANGELOG.md',
        tag_pattern=r'^ui-([0-9]+\.[0-9]+\.[0-9]+)$',
        include_paths=[],
        tag_prefix='ui-',
    )
    ui.name = 'ui'
    ui.hooks.post_changelog = []

    mock_settings.get_subprojects.return_value = [core, ui]
    mock_settings.select_projects.return_value = [core, ui]
    start_release = mocker.patch('releez.subapps.release_start.start_release')

    result = invoke(
        cli.app,
        [
            'release',
            'start',
            '--dry-run',
            '--project',
            'core',
            '--project',
            'ui',
            '--version-override',
            'core-1.2.3',
        ],
    )

    assert result.exit_code == 1
    assert '--version-override can only be used when releasing a single project' in result.output
    start_release.assert_not_called()
