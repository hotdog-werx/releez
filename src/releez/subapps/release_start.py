from __future__ import annotations

from pathlib import Path  # noqa: TC003
from typing import TYPE_CHECKING, Annotated

from cyclopts import Parameter
from rich.prompt import Confirm

from releez.cli_utils import (
    _exit,
    _project_include_paths,
    _resolve_release_version,
)
from releez.console import console, err_console
from releez.errors import ReleezError
from releez.release import StartReleaseInput, StartReleaseResult, start_release
from releez.settings import ReleezSettings
from releez.subapps.release import (
    ProjectSelection,
    ReleaseStartOptions,
    _project_changelog_path,
    _require_single_project_override_scope,
    _resolve_project_release_version,
    _resolve_project_targets_for_command,
    release_app,
)
from releez.subapps.release_maintenance import (
    MaintenanceContext,
    _maintenance_context,
    _monorepo_maintenance_context,
)
from releez.utils import handle_releez_errors

if TYPE_CHECKING:
    from semver import VersionInfo

    from releez.subproject import SubProject


# ---------------------------------------------------------------------------
# Release start helpers
# ---------------------------------------------------------------------------


def _confirm_release_start(
    *,
    options: ReleaseStartOptions,
    version: VersionInfo,
    active_branch: str,
) -> None:
    """Show a confirmation prompt before starting a release.

    Raises:
        SystemExit: If the user declines.
    """
    console.print('Release summary:', style='blue')
    console.print(f'  Current branch : {active_branch}', markup=False)
    console.print(f'  Base branch    : {options.base}', markup=False)
    console.print(f'  Version        : {version}', markup=False)
    console.print(f'  Release branch : release/{version}', markup=False)
    console.print(f'  Create PR      : {options.create_pr}', markup=False)
    console.print(f'  Changelog      : {options.changelog_path}', markup=False)
    console.print(f'  Dry run        : {options.dry_run}', markup=False)
    if not Confirm.ask('Proceed?'):
        raise SystemExit(1)


def _build_release_start_input_single_repo(
    *,
    options: ReleaseStartOptions,
    settings: ReleezSettings,
    maintenance_ctx: MaintenanceContext | None = None,
) -> StartReleaseInput:
    base_branch = maintenance_ctx.branch if maintenance_ctx else (options.base or settings.base_branch)
    return StartReleaseInput(
        bump=options.bump,
        version_override=options.version_override,
        base_branch=base_branch,
        remote_name=options.remote or settings.git_remote,
        labels=options.labels_list,
        title_prefix=options.title_prefix or settings.pr_title_prefix,
        changelog_path=options.changelog_path or settings.changelog_path,
        post_changelog_hooks=settings.hooks.post_changelog or None,
        create_pr=options.create_pr if options.create_pr is not None else settings.create_pr,
        github_token=options.github_token,
        dry_run=options.dry_run,
        maintenance_tag_pattern=maintenance_ctx.tag_pattern if maintenance_ctx else None,
    )


def _build_release_start_input_project(
    *,
    options: ReleaseStartOptions,
    settings: ReleezSettings,
    project: SubProject,
    repo_root: Path,
    maintenance_ctx: MaintenanceContext | None = None,
) -> StartReleaseInput:
    base_branch = maintenance_ctx.branch if maintenance_ctx else (options.base or settings.base_branch)
    return StartReleaseInput(
        bump=options.bump,
        version_override=options.version_override,
        base_branch=base_branch,
        remote_name=options.remote or settings.git_remote,
        labels=options.labels_list,
        title_prefix=options.title_prefix or settings.pr_title_prefix,
        changelog_path=_project_changelog_path(
            project=project,
            repo_root=repo_root,
        ),
        post_changelog_hooks=project.hooks.post_changelog or None,
        create_pr=options.create_pr if options.create_pr is not None else settings.create_pr,
        github_token=options.github_token,
        dry_run=options.dry_run,
        project_name=project.name,
        include_paths=_project_include_paths(
            project=project,
            repo_root=repo_root,
        ),
        project_path=project.path,
        tag_prefix=project.tag_prefix,
        maintenance_tag_pattern=maintenance_ctx.tag_pattern if maintenance_ctx else None,
    )


def _emit_release_start_result(
    *,
    result: StartReleaseResult,
    dry_run: bool,
    project_name: str | None = None,
) -> None:
    prefix = f'[{project_name}] ' if project_name else ''
    console.print(
        f'{prefix}Next version: {result.version}',
        style='green',
        markup=False,
    )
    if dry_run:
        console.print(result.release_notes_markdown, markup=False)
        return
    console.print(
        f'{prefix}Release branch: {result.release_branch}',
        markup=False,
    )
    if result.pr_url:
        console.print(f'{prefix}PR created: {result.pr_url}', markup=False)


def _run_single_repo_release_start(  # noqa: PLR0913
    *,
    options: ReleaseStartOptions,
    settings: ReleezSettings,
    repo_root: Path,
    active_branch: str | None,
    non_interactive: bool,
    maintenance_branch_regex: str,
) -> None:
    maintenance_ctx = _maintenance_context(
        branch=active_branch,
        regex=maintenance_branch_regex,
    )
    release_input = _build_release_start_input_single_repo(
        options=options,
        settings=settings,
        maintenance_ctx=maintenance_ctx,
    )

    if maintenance_ctx:
        version = _resolve_release_version(
            repo_root=repo_root,
            version_override=options.version_override,
            tag_pattern=maintenance_ctx.tag_pattern,
        )
        maintenance_ctx.ensure_version_matches(version)
        if not non_interactive and not options.dry_run:
            _confirm_release_start(
                options=options,
                version=version,
                active_branch=maintenance_ctx.branch,
            )

    result = start_release(release_input)
    _emit_release_start_result(
        result=result,
        dry_run=options.dry_run,
    )


def _run_project_release_start(  # noqa: PLR0913
    *,
    options: ReleaseStartOptions,
    settings: ReleezSettings,
    project: SubProject,
    repo_root: Path,
    maintenance_ctx: MaintenanceContext | None = None,
    non_interactive: bool = False,
) -> bool:
    if maintenance_ctx:
        version = _resolve_project_release_version(
            repo_root=repo_root,
            version_override=options.version_override,
            project=project,
        )
        maintenance_ctx.ensure_version_matches(version)
        if not non_interactive and not options.dry_run:
            _confirm_release_start(
                options=options,
                version=version,
                active_branch=maintenance_ctx.branch,
            )

    release_input = _build_release_start_input_project(
        options=options,
        settings=settings,
        project=project,
        repo_root=repo_root,
        maintenance_ctx=maintenance_ctx,
    )
    try:
        result = start_release(release_input)
    except ReleezError as exc:
        err_console.print(
            f'[{project.name}] {exc}',
            style='bold red',
            markup=False,
        )
        return False

    _emit_release_start_result(
        result=result,
        dry_run=options.dry_run,
        project_name=project.name,
    )
    return True


def _run_monorepo_release_start(  # noqa: PLR0913
    *,
    options: ReleaseStartOptions,
    settings: ReleezSettings,
    target_projects: list[SubProject],
    repo_root: Path,
    active_branch: str | None = None,
    non_interactive: bool = False,
    maintenance_branch_regex: str,
) -> None:
    _require_single_project_override_scope(
        version_override=options.version_override,
        target_projects=target_projects,
        action_label='releasing',
    )
    if not target_projects:
        return

    monorepo_ctx = _monorepo_maintenance_context(
        active_branch,
        target_projects,
        regex=maintenance_branch_regex,
    )
    maintenance_project = monorepo_ctx[0] if monorepo_ctx else None
    maintenance_ctx = monorepo_ctx[1] if monorepo_ctx else None

    succeeded = 0
    for project in target_projects:
        ctx = maintenance_ctx if project is maintenance_project else None
        if _run_project_release_start(
            options=options,
            settings=settings,
            project=project,
            repo_root=repo_root,
            maintenance_ctx=ctx,
            non_interactive=non_interactive,
        ):
            succeeded += 1

    failed = len(target_projects) - succeeded
    console.print(
        f'Release summary: {succeeded} succeeded, {failed} failed.',
        style='blue',
    )
    if failed:
        raise _exit()


def _run_release_start_command(  # noqa: PLR0913
    *,
    settings: ReleezSettings,
    options: ReleaseStartOptions,
    project_names: list[str],
    all_projects: bool,
    maintenance_branch_regex: str,
    non_interactive: bool,
) -> None:
    resolved = _resolve_project_targets_for_command(
        settings=settings,
        project_names=project_names,
        all_projects=all_projects,
    )
    if resolved.target_projects is None:
        _run_single_repo_release_start(
            options=options,
            settings=settings,
            repo_root=resolved.repo_root,
            active_branch=resolved.active_branch,
            non_interactive=non_interactive,
            maintenance_branch_regex=maintenance_branch_regex,
        )
        return
    if not resolved.target_projects:
        raise _exit()

    _run_monorepo_release_start(
        options=options,
        settings=settings,
        target_projects=resolved.target_projects,
        repo_root=resolved.repo_root,
        active_branch=resolved.active_branch,
        non_interactive=non_interactive,
        maintenance_branch_regex=maintenance_branch_regex,
    )


# ---------------------------------------------------------------------------
# Command
# ---------------------------------------------------------------------------


_DEFAULT_START_OPTIONS = ReleaseStartOptions()
_DEFAULT_PROJECT_SELECTION = ProjectSelection()


@release_app.command
@handle_releez_errors
def start(
    options: Annotated[
        ReleaseStartOptions,
        Parameter(name='*'),
    ] = _DEFAULT_START_OPTIONS,
    selection: Annotated[
        ProjectSelection,
        Parameter(name='*'),
    ] = _DEFAULT_PROJECT_SELECTION,
    *,
    maintenance_branch_regex: Annotated[
        str | None,
        Parameter(
            '--maintenance-branch-regex',
            help='Regex to detect maintenance branches (named "major" group required). [default: from config]',
            show_default=False,
        ),
    ] = None,
    non_interactive: Annotated[
        bool,
        Parameter(
            '--non-interactive',
            help='Skip confirmation prompt (useful in CI).',
            show_default=True,
        ),
    ] = False,
) -> None:
    """Start release branch workflows for single-repo or monorepo projects."""
    settings = ReleezSettings()
    options = options.resolve(settings)
    effective_regex = maintenance_branch_regex or settings.effective_maintenance_branch_regex

    _run_release_start_command(
        settings=settings,
        options=options,
        project_names=selection.project_names,
        all_projects=selection.all_projects,
        maintenance_branch_regex=effective_regex,
        non_interactive=non_interactive,
    )
