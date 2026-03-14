from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, cast

import pytest
import typer
from click.core import ParameterSource
from semver import VersionInfo

from releez import cli
from releez.cli import MaintenanceContext
from releez.errors import ReleezError
from releez.release import StartReleaseResult

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


def _make_start_options() -> cli._ReleaseStartOptions:
    return cli._ReleaseStartOptions(
        bump='auto',
        version_override=None,
        run_changelog_format=False,
        changelog_format_cmd=None,
        create_pr=False,
        dry_run=True,
        base='master',
        remote='origin',
        labels=['release'],
        title_prefix='chore(release): ',
        changelog_path='CHANGELOG.md',
        github_token=None,
    )


def test_root_merges_into_existing_default_map(
    mocker: MockerFixture,
) -> None:
    """Regression guard: root callback must merge, not clobber, an existing default map."""
    hooks = SimpleNamespace(changelog_format=['fmt'])
    settings = SimpleNamespace(
        base_branch='master',
        git_remote='origin',
        pr_labels='release',
        pr_title_prefix='chore(release): ',
        changelog_path='CHANGELOG.md',
        create_pr=False,
        run_changelog_format=False,
        alias_versions=cli.AliasVersions.none,
        hooks=hooks,
        maintenance_branch_regex=r'^support/(?P<major>\d+)\.x$',
    )
    mocker.patch('releez.cli.ReleezSettings', return_value=settings)

    ctx = cast(
        'typer.Context',
        SimpleNamespace(default_map={'existing': {'keep': True}}, obj=None),
    )
    cli._root(ctx=ctx)

    assert ctx.obj is settings
    default_map = cast('dict[str, object]', ctx.default_map)
    assert default_map['existing'] == {'keep': True}
    assert 'release' in default_map


def test_selected_projects_from_names_deduplicates_repeated_names(
    mocker: MockerFixture,
) -> None:
    """Regression guard: repeated --project values should resolve to one target project."""
    project = mocker.MagicMock(name='core')
    project.name = 'core'

    selected = cli._selected_projects_from_names(
        subprojects=[project],
        project_names=['core', 'core'],
    )

    assert selected == [project]


def test_resolve_target_projects_single_repo_returns_none(
    mocker: MockerFixture,
) -> None:
    mocker.patch('releez.cli._build_subprojects_list', return_value=[])

    result = cli._resolve_target_projects(
        repo=mocker.MagicMock(),
        repo_root=Path('/repo'),
        settings=mocker.MagicMock(),
        project_names=[],
        all_projects=False,
        base_branch='master',
        require_explicit_selection=False,
    )

    assert result is None


def test_resolve_target_projects_autodetects_changed(
    mocker: MockerFixture,
) -> None:
    project = mocker.MagicMock()
    project.name = 'core'
    mocker.patch('releez.cli._build_subprojects_list', return_value=[project])
    detect_changed = mocker.patch(
        'releez.cli._detect_changed_project_targets',
        return_value=[project],
    )

    result = cli._resolve_target_projects(
        repo=mocker.MagicMock(),
        repo_root=Path('/repo'),
        settings=mocker.MagicMock(),
        project_names=[],
        all_projects=False,
        base_branch='master',
        require_explicit_selection=False,
    )

    assert result == [project]
    detect_changed.assert_called_once()


def test_create_and_push_selected_tags_splits_exact_and_alias(
    mocker: MockerFixture,
) -> None:
    repo = mocker.MagicMock()
    create_tags = mocker.patch('releez.cli.create_tags')
    push_tags = mocker.patch('releez.cli.push_tags')

    cli._create_and_push_selected_tags(
        repo=repo,
        remote='origin',
        selected_tags=['1.2.3', 'v1', 'v1.2'],
    )

    assert create_tags.call_args_list == [
        mocker.call(repo, tags=['1.2.3'], force=False),
        mocker.call(repo, tags=['v1', 'v1.2'], force=True),
    ]
    assert push_tags.call_args_list == [
        mocker.call(repo, remote_name='origin', tags=['1.2.3'], force=False),
        mocker.call(
            repo,
            remote_name='origin',
            tags=['v1', 'v1.2'],
            force=True,
        ),
    ]


def test_run_monorepo_release_start_exits_when_any_project_fails(
    mocker: MockerFixture,
) -> None:
    core = mocker.MagicMock(name='core')
    core.name = 'core'
    ui = mocker.MagicMock(name='ui')
    ui.name = 'ui'
    mocker.patch(
        'releez.cli._run_project_release_start',
        side_effect=[True, False],
    )
    exit_with_code = mocker.patch(
        'releez.cli._exit_with_code',
        side_effect=typer.Exit(code=1),
    )

    with pytest.raises(typer.Exit):
        cli._run_monorepo_release_start(
            options=_make_start_options(),
            target_projects=[core, ui],
            repo_root=Path('/repo'),
        )

    exit_with_code.assert_called_once()


def test_run_monorepo_release_start_no_targets_noops(
    mocker: MockerFixture,
) -> None:
    """Regression guard: empty project lists should short-circuit without side effects."""
    run_project = mocker.patch('releez.cli._run_project_release_start')
    exit_with_code = mocker.patch('releez.cli._exit_with_code')

    cli._run_monorepo_release_start(
        options=_make_start_options(),
        target_projects=[],
        repo_root=Path('/repo'),
    )

    run_project.assert_not_called()
    exit_with_code.assert_not_called()


def test_run_project_release_start_handles_releez_error(
    mocker: MockerFixture,
) -> None:
    """Regression guard: per-project release failures must be caught and reported."""
    project = mocker.MagicMock(name='core')
    project.name = 'core'
    mocker.patch(
        'releez.cli._build_release_start_input_project',
        return_value=object(),
    )
    mocker.patch('releez.cli.start_release', side_effect=ReleezError('boom'))
    secho = mocker.patch('releez.cli.typer.secho')

    ok = cli._run_project_release_start(
        options=_make_start_options(),
        project=project,
        repo_root=Path('/repo'),
    )

    assert ok is False
    secho.assert_called_once_with(
        '[core] boom',
        err=True,
        fg=typer.colors.RED,
    )


def test_emit_release_start_result_prints_pr_url_when_present(
    mocker: MockerFixture,
) -> None:
    """Regression guard: successful releases with PRs must print the PR URL."""
    echo = mocker.patch('releez.cli.typer.echo')

    cli._emit_release_start_result(
        result=StartReleaseResult(
            version='core-1.2.3',
            release_notes_markdown='notes',
            release_branch='release/core-1.2.3',
            pr_url='https://example.invalid/pr/1',
        ),
        dry_run=False,
        project_name='core',
    )

    assert echo.call_args_list == [
        mocker.call('[core] Release branch: release/core-1.2.3'),
        mocker.call('[core] PR created: https://example.invalid/pr/1'),
    ]


def test_alias_versions_for_project_prefers_cli_flag_source(
    mocker: MockerFixture,
) -> None:
    """Regression guard: explicit CLI alias flags must override project defaults."""
    ctx = cast(
        'typer.Context',
        SimpleNamespace(
            get_parameter_source=lambda _name: ParameterSource.COMMANDLINE,
        ),
    )
    project = mocker.MagicMock(alias_versions=cli.AliasVersions.major)

    resolved = cli._alias_versions_for_project(
        ctx=ctx,
        cli_alias_versions=cli.AliasVersions.minor,
        project=project,
    )

    assert resolved == cli.AliasVersions.minor


def test_run_release_preview_command_uses_single_repo_builder(
    mocker: MockerFixture,
) -> None:
    ctx = cast(
        'typer.Context',
        SimpleNamespace(obj=SimpleNamespace(base_branch='master')),
    )
    resolved = cli._ResolvedProjectTargets(
        settings=mocker.MagicMock(),
        repo=mocker.MagicMock(),
        repo_root=Path('/repo'),
        target_projects=None,
    )
    mocker.patch(
        'releez.cli._resolve_project_targets_for_command',
        return_value=resolved,
    )
    build_single = mocker.patch(
        'releez.cli._build_release_preview_markdown_single_repo',
        return_value='preview',
    )
    emit_output = mocker.patch('releez.cli._emit_or_write_output')

    cli._run_release_preview_command(
        ctx=ctx,
        options=cli._ReleasePreviewOptions(
            version_override='1.2.3',
            alias_versions=cli.AliasVersions.none,
            output=None,
        ),
        project_names=[],
        all_projects=False,
    )

    build_single.assert_called_once_with(
        options=cli._ReleasePreviewOptions(
            version_override='1.2.3',
            alias_versions=cli.AliasVersions.none,
            output=None,
        ),
        repo_root=Path('/repo'),
        tag_pattern=None,
    )
    emit_output.assert_called_once_with(output=None, content='preview')


def test_exit_with_code_raises_exit_1() -> None:
    """Regression guard: generic command failure helper must exit with code 1."""
    with pytest.raises(typer.Exit) as exc_info:
        cli._exit_with_code()
    assert exc_info.value.exit_code == 1


def test_project_names_csv_joins_names_in_order(
    mocker: MockerFixture,
) -> None:
    """Regression guard: changed-project messages should preserve project name order."""
    core = mocker.MagicMock()
    core.name = 'core'
    ui = mocker.MagicMock()
    ui.name = 'ui'

    assert cli._project_names_csv([core, ui]) == 'core, ui'


def test_detect_changed_project_targets_reports_no_changes(
    mocker: MockerFixture,
) -> None:
    """Regression guard: no changed projects should emit a green status and return empty."""
    repo = mocker.MagicMock()
    detect_changed = mocker.patch(
        'releez.cli.detect_changed_projects',
        return_value=[],
    )
    secho = mocker.patch('releez.cli.typer.secho')

    changed = cli._detect_changed_project_targets(
        repo=repo,
        base_branch='master',
        subprojects=[],
    )

    assert changed == []
    detect_changed.assert_called_once_with(
        repo=repo,
        base_branch='master',
        projects=[],
    )
    secho.assert_called_once_with(
        'No projects with unreleased changes were detected.',
        fg=typer.colors.GREEN,
    )


def test_detect_changed_project_targets_reports_detected_names(
    mocker: MockerFixture,
) -> None:
    """Regression guard: autodetect path should announce changed projects and return them."""
    repo = mocker.MagicMock()
    core = mocker.MagicMock()
    core.name = 'core'
    ui = mocker.MagicMock()
    ui.name = 'ui'
    detect_changed = mocker.patch(
        'releez.cli.detect_changed_projects',
        return_value=[core, ui],
    )
    secho = mocker.patch('releez.cli.typer.secho')

    changed = cli._detect_changed_project_targets(
        repo=repo,
        base_branch='master',
        subprojects=[core, ui],
    )

    assert changed == [core, ui]
    detect_changed.assert_called_once_with(
        repo=repo,
        base_branch='master',
        projects=[core, ui],
    )
    secho.assert_called_once_with(
        'Detected changed projects: core, ui',
        fg=typer.colors.BLUE,
    )


def test_run_release_start_command_exits_when_monorepo_targets_empty(
    mocker: MockerFixture,
) -> None:
    """Regression guard: monorepo start must exit when no changed projects are detected."""
    ctx = cast(
        'typer.Context',
        SimpleNamespace(obj=SimpleNamespace(base_branch='master')),
    )
    resolved = cli._ResolvedProjectTargets(
        settings=mocker.MagicMock(),
        repo=mocker.MagicMock(),
        repo_root=Path('/repo'),
        target_projects=[],
    )
    mocker.patch(
        'releez.cli._resolve_project_targets_for_command',
        return_value=resolved,
    )
    run_single = mocker.patch('releez.cli._run_single_repo_release_start')
    run_mono = mocker.patch('releez.cli._run_monorepo_release_start')
    exit_with_code = mocker.patch(
        'releez.cli._exit_with_code',
        side_effect=typer.Exit(code=1),
    )

    with pytest.raises(typer.Exit):
        cli._run_release_start_command(
            ctx=ctx,
            options=_make_start_options(),
            project_names=[],
            all_projects=False,
            maintenance_branch_regex=r'^support/(?P<major>\d+)\.x$',
            non_interactive=False,
        )

    exit_with_code.assert_called_once()
    run_single.assert_not_called()
    run_mono.assert_not_called()


def test_project_semver_version_strips_prefix_when_present(
    mocker: MockerFixture,
) -> None:
    """When git-cliff returns a prefixed tag (e.g. 'core-1.2.3'), the prefix is stripped."""
    project = mocker.MagicMock()
    project.tag_prefix = 'core-'

    result = cli._project_semver_version(
        project=project,
        version=VersionInfo.parse('1.2.3'),
    )
    assert result == '1.2.3'


def test_run_project_release_start_prompts_confirmation_on_maintenance_branch(
    mocker: MockerFixture,
) -> None:
    """On a maintenance branch, confirmation is shown when not dry_run and not non_interactive."""
    project = mocker.MagicMock(name='ui')
    project.name = 'ui'

    maintenance_ctx = MaintenanceContext(
        branch='support/ui-1.x',
        major=1,
        tag_pattern=r'^ui\-1\.[0-9]+\.[0-9]+$',
    )

    mocker.patch(
        'releez.cli._resolve_project_release_version',
        return_value=VersionInfo.parse('1.5.0'),
    )
    confirm = mocker.patch('releez.cli._confirm_release_start')
    mocker.patch(
        'releez.cli._build_release_start_input_project',
        return_value=object(),
    )
    mocker.patch(
        'releez.cli.start_release',
        return_value=mocker.Mock(
            version='ui-1.5.0',
            release_notes_markdown='notes',
            release_branch='release/1.5.0',
            pr_url=None,
        ),
    )
    mocker.patch('releez.cli.typer.secho')
    mocker.patch('releez.cli.typer.echo')

    options = cli._ReleaseStartOptions(
        bump='auto',
        version_override=None,
        run_changelog_format=False,
        changelog_format_cmd=None,
        create_pr=False,
        dry_run=False,
        base='master',
        remote='origin',
        labels=[],
        title_prefix='chore(release): ',
        changelog_path='CHANGELOG.md',
        github_token=None,
    )

    cli._run_project_release_start(
        options=options,
        project=project,
        repo_root=Path('/repo'),
        maintenance_ctx=maintenance_ctx,
        non_interactive=False,
    )

    confirm.assert_called_once()
