from __future__ import annotations

from typing import TYPE_CHECKING

from typer.testing import CliRunner

from releez import cli
from releez.version_tags import AliasVersions

if TYPE_CHECKING:
    from pathlib import Path

    import pytest
    from pytest_mock import MockerFixture


def _mock_repo_context(
    mocker: MockerFixture,
    *,
    repo_root: Path,
) -> None:
    mocker.patch(
        'releez.cli.open_repo',
        return_value=(mocker.MagicMock(), mocker.MagicMock(root=repo_root)),
    )


def _mock_settings(
    mocker: MockerFixture,
    *,
    projects: list[object],
) -> None:
    hooks = mocker.MagicMock(post_changelog=[], changelog_format=None)
    mocker.patch(
        'releez.cli.ReleezSettings',
        return_value=mocker.MagicMock(
            base_branch='master',
            git_remote='origin',
            pr_labels='release',
            pr_title_prefix='chore(release): ',
            changelog_path='CHANGELOG.md',
            create_pr=False,
            run_changelog_format=False,
            alias_versions=AliasVersions.none,
            hooks=hooks,
            projects=projects,
        ),
    )


def test_cli_release_start_passes_version_override(
    mocker: MockerFixture,
    tmp_path: Path,
) -> None:
    runner = CliRunner()
    _mock_repo_context(mocker, repo_root=tmp_path)

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


def test_cli_release_start_delegates_to_command_helper(
    mocker: MockerFixture,
    tmp_path: Path,
) -> None:
    runner = CliRunner()
    _mock_repo_context(mocker, repo_root=tmp_path)

    run_command = mocker.patch('releez.cli._run_release_start_command')
    result = runner.invoke(
        cli.app,
        [
            'release',
            'start',
            '--dry-run',
            '--project',
            'core',
            '--all',
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
    assert call_kwargs['all_projects'] is True


def test_cli_release_start_defaults_version_override_to_none(
    mocker: MockerFixture,
    tmp_path: Path,
) -> None:
    runner = CliRunner()
    _mock_repo_context(mocker, repo_root=tmp_path)

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
    _mock_repo_context(mocker, repo_root=tmp_path)

    monkeypatch.setenv(
        'RELEEZ_HOOKS__CHANGELOG_FORMAT',
        '["dprint", "fmt", "{changelog}"]',
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
    _mock_repo_context(mocker, repo_root=tmp_path)

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


def test_cli_release_start_monorepo_requires_explicit_project_selection(
    mocker: MockerFixture,
    tmp_path: Path,
) -> None:
    """In monorepo mode, release start must fail without --project or --all."""
    runner = CliRunner()
    _mock_repo_context(mocker, repo_root=tmp_path)
    _mock_settings(mocker, projects=[mocker.MagicMock(name='core-config')])

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

    mocker.patch('releez.cli.SubProject.from_config', return_value=project)
    start_release = mocker.patch('releez.cli.start_release')

    result = runner.invoke(cli.app, ['release', 'start', '--dry-run'])

    assert result.exit_code == 1
    assert '--project' in result.output or '--all' in result.output
    start_release.assert_not_called()


def test_cli_release_start_monorepo_with_project_flag(
    mocker: MockerFixture,
    tmp_path: Path,
) -> None:
    """In monorepo mode, release start succeeds when --project is specified."""
    runner = CliRunner()
    _mock_repo_context(mocker, repo_root=tmp_path)
    _mock_settings(mocker, projects=[mocker.MagicMock(name='core-config')])

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

    mocker.patch('releez.cli.SubProject.from_config', return_value=project)

    start_release = mocker.patch(
        'releez.cli.start_release',
        return_value=mocker.Mock(
            version='core-1.2.3',
            release_notes_markdown='notes',
            release_branch=None,
            pr_url=None,
        ),
    )

    result = runner.invoke(
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
    tmp_path: Path,
) -> None:
    runner = CliRunner()
    _mock_repo_context(mocker, repo_root=tmp_path)
    _mock_settings(
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

    mocker.patch('releez.cli.SubProject.from_config', side_effect=[core, ui])
    start_release = mocker.patch('releez.cli.start_release')

    result = runner.invoke(
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
