from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, cast

import pytest
import typer

from releez import cli

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
    )
    emit_output.assert_called_once_with(output=None, content='preview')
