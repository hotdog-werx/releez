from __future__ import annotations

from pathlib import Path  # noqa: TC003
from typing import TYPE_CHECKING, Annotated

import typer

from releez.cli_utils import (
    _exit,
    _project_include_paths,
    _resolve_release_version,
)
from releez.cliff import GitCliffBump  # noqa: TC001
from releez.errors import ReleezError
from releez.release import StartReleaseInput, StartReleaseResult, start_release
from releez.subapps.release import (
    _comma_separated_labels,
    _normalize_project_names,
    _project_changelog_path,
    _raise_changelog_format_command_required,
    _ReleaseStartOptions,
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

    from releez.settings import ReleezSettings
    from releez.subproject import SubProject


# ---------------------------------------------------------------------------
# Release start helpers
# ---------------------------------------------------------------------------


def _confirm_release_start(
    *,
    options: _ReleaseStartOptions,
    version: VersionInfo,
    active_branch: str,
) -> None:
    """Show a confirmation prompt before starting a release.

    Raises:
        typer.Abort: If the user declines.
    """
    typer.secho('Release summary:', fg=typer.colors.BLUE)
    typer.echo(f'  Current branch : {active_branch}')
    typer.echo(f'  Base branch    : {options.base}')
    typer.echo(f'  Version        : {version}')
    typer.echo(f'  Release branch : release/{version}')
    typer.echo(f'  Create PR      : {options.create_pr}')
    typer.echo(f'  Changelog      : {options.changelog_path}')
    typer.echo(f'  Dry run        : {options.dry_run}')
    typer.confirm('Proceed?', abort=True)


def _build_release_start_input_single_repo(
    *,
    options: _ReleaseStartOptions,
    settings: ReleezSettings,
    maintenance_ctx: MaintenanceContext | None = None,
) -> StartReleaseInput:
    base_branch = maintenance_ctx.branch if maintenance_ctx else options.base
    return StartReleaseInput(
        bump=options.bump,
        version_override=options.version_override,
        base_branch=base_branch,
        remote_name=options.remote,
        labels=options.labels,
        title_prefix=options.title_prefix,
        changelog_path=options.changelog_path,
        post_changelog_hooks=settings.hooks.post_changelog or None,
        run_changelog_format=options.run_changelog_format,
        changelog_format_cmd=options.changelog_format_cmd,
        create_pr=options.create_pr,
        github_token=options.github_token,
        dry_run=options.dry_run,
        maintenance_tag_pattern=maintenance_ctx.tag_pattern if maintenance_ctx else None,
    )


def _build_release_start_input_project(
    *,
    options: _ReleaseStartOptions,
    project: SubProject,
    repo_root: Path,
    maintenance_ctx: MaintenanceContext | None = None,
) -> StartReleaseInput:
    base_branch = maintenance_ctx.branch if maintenance_ctx else options.base
    return StartReleaseInput(
        bump=options.bump,
        version_override=options.version_override,
        base_branch=base_branch,
        remote_name=options.remote,
        labels=options.labels,
        title_prefix=options.title_prefix,
        changelog_path=_project_changelog_path(
            project=project,
            repo_root=repo_root,
        ),
        post_changelog_hooks=project.hooks.post_changelog or None,
        run_changelog_format=options.run_changelog_format,
        changelog_format_cmd=options.changelog_format_cmd,
        create_pr=options.create_pr,
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
    typer.secho(
        f'{prefix}Next version: {result.version}',
        fg=typer.colors.GREEN,
    )
    if dry_run:
        typer.echo(result.release_notes_markdown)
        return
    typer.echo(f'{prefix}Release branch: {result.release_branch}')
    if result.pr_url:
        typer.echo(f'{prefix}PR created: {result.pr_url}')


def _run_single_repo_release_start(  # noqa: PLR0913
    *,
    options: _ReleaseStartOptions,
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


def _run_project_release_start(
    *,
    options: _ReleaseStartOptions,
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
        project=project,
        repo_root=repo_root,
        maintenance_ctx=maintenance_ctx,
    )
    try:
        result = start_release(release_input)
    except ReleezError as exc:
        typer.secho(
            f'[{project.name}] {exc}',
            err=True,
            fg=typer.colors.RED,
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
    options: _ReleaseStartOptions,
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
            project=project,
            repo_root=repo_root,
            maintenance_ctx=ctx,
            non_interactive=non_interactive,
        ):
            succeeded += 1

    failed = len(target_projects) - succeeded
    typer.secho(
        f'Release summary: {succeeded} succeeded, {failed} failed.',
        fg=typer.colors.BLUE,
    )
    if failed:
        raise _exit()


def _run_release_start_command(  # noqa: PLR0913
    *,
    ctx: typer.Context,
    options: _ReleaseStartOptions,
    project_names: list[str],
    all_projects: bool,
    maintenance_branch_regex: str,
    non_interactive: bool,
) -> None:
    if options.run_changelog_format and not options.changelog_format_cmd:
        _raise_changelog_format_command_required()

    resolved = _resolve_project_targets_for_command(
        ctx=ctx,
        project_names=project_names,
        all_projects=all_projects,
    )
    if resolved.target_projects is None:
        _run_single_repo_release_start(
            options=options,
            settings=resolved.settings,
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
        target_projects=resolved.target_projects,
        repo_root=resolved.repo_root,
        active_branch=resolved.active_branch,
        non_interactive=non_interactive,
        maintenance_branch_regex=maintenance_branch_regex,
    )


# ---------------------------------------------------------------------------
# Command
# ---------------------------------------------------------------------------


@release_app.command('start')
@handle_releez_errors
def release_start(  # noqa: PLR0913
    ctx: typer.Context,
    *,
    bump: Annotated[
        GitCliffBump,
        typer.Option(
            help='Bump mode passed to git-cliff.',
            show_default=True,
            case_sensitive=False,
        ),
    ] = 'auto',
    version_override: Annotated[
        str | None,
        typer.Option(
            '--version-override',
            help='Override version instead of computing via git-cliff.',
            show_default=False,
        ),
    ] = None,
    run_changelog_format: Annotated[
        bool,
        typer.Option(
            '--run-changelog-format',
            help='(DEPRECATED) Use post-changelog hooks instead.',
            show_default=True,
        ),
    ] = False,
    changelog_format_cmd: Annotated[
        list[str] | None,
        typer.Option(
            '--changelog-format-cmd',
            help='(DEPRECATED: use --post-changelog-hook) Override changelog format command argv (repeatable).',
            show_default=False,
        ),
    ] = None,
    create_pr: Annotated[
        bool,
        typer.Option(
            '--create-pr/--no-create-pr',
            help='Create a GitHub PR (requires token).',
            show_default=True,
        ),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option(
            help='Compute version and notes without changing the repo.',
        ),
    ] = False,
    base: Annotated[
        str,
        typer.Option(
            help='Base branch for the release PR.',
            show_default=True,
        ),
    ] = 'master',
    remote: Annotated[
        str,
        typer.Option(
            help='Remote name to use.',
            show_default=True,
        ),
    ] = 'origin',
    labels: Annotated[
        str,
        typer.Option(
            help='Comma-separated label(s) to add to the PR (repeatable).',
            show_default=True,
        ),
    ] = 'release',
    title_prefix: Annotated[
        str,
        typer.Option(
            help='Prefix for PR title.',
            show_default=True,
        ),
    ] = 'chore(release): ',
    changelog_path: Annotated[
        str,
        typer.Option(
            '--changelog-path',
            '--changelog',
            help='Changelog file to prepend to.',
            show_default=True,
        ),
    ] = 'CHANGELOG.md',
    project_names: Annotated[
        list[str] | None,
        typer.Option(
            '--project',
            help='Project name to release (repeatable, monorepo only).',
            show_default=False,
        ),
    ] = None,
    all_projects: Annotated[
        bool,
        typer.Option(
            '--all',
            help='Release all configured projects (monorepo only).',
            show_default=True,
        ),
    ] = False,
    github_token: Annotated[
        str | None,
        typer.Option(
            envvar=['RELEEZ_GITHUB_TOKEN', 'GITHUB_TOKEN'],
            help='GitHub token for PR creation (prefer RELEEZ_GITHUB_TOKEN; falls back to GITHUB_TOKEN).',
            show_default=False,
        ),
    ] = None,
    maintenance_branch_regex: Annotated[
        str,
        typer.Option(
            '--maintenance-branch-regex',
            help='Regex to detect maintenance branches (must have a named "major" capture group).',
            show_default=True,
        ),
    ] = r'^support/(?P<major>\d+)\.x$',
    non_interactive: Annotated[
        bool,
        typer.Option(
            '--non-interactive',
            help='Skip confirmation prompt (useful in CI).',
            show_default=True,
        ),
    ] = False,
) -> None:
    """Start release branch workflows for single-repo or monorepo projects."""
    options = _ReleaseStartOptions(
        bump=bump,
        version_override=version_override,
        run_changelog_format=run_changelog_format,
        changelog_format_cmd=changelog_format_cmd,
        create_pr=create_pr,
        dry_run=dry_run,
        base=base,
        remote=remote,
        labels=_comma_separated_labels(labels),
        title_prefix=title_prefix,
        changelog_path=changelog_path,
        github_token=github_token,
    )

    _run_release_start_command(
        ctx=ctx,
        options=options,
        project_names=_normalize_project_names(project_names),
        all_projects=all_projects,
        maintenance_branch_regex=maintenance_branch_regex,
        non_interactive=non_interactive,
    )
