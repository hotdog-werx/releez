from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

import typer
from click.core import ParameterSource

from releez.cli_utils import (
    _exit,
    _project_include_paths,
    _resolve_release_version,
)
from releez.cliff import GitCliff, GitCliffBump
from releez.errors import ChangelogFormatCommandRequiredError, ReleezError
from releez.git_repo import (
    create_tags,
    fetch,
    open_repo,
    push_tags,
)
from releez.release import StartReleaseInput, StartReleaseResult, start_release
from releez.subapps.release_maintenance import (
    MaintenanceContext,
    _maintenance_context,
    _monorepo_maintenance_context,
    _validate_maintenance_version,
)
from releez.utils import handle_releez_errors
from releez.version_tags import AliasVersions, compute_version_tags, select_tags

if TYPE_CHECKING:
    from git import Repo
    from semver import VersionInfo

    from releez.settings import ReleezSettings
    from releez.subproject import SubProject

release_app = typer.Typer(help='Release workflows (changelog + branch + PR).')


# ---------------------------------------------------------------------------
# Shared infrastructure
# ---------------------------------------------------------------------------


def _raise_changelog_format_command_required() -> None:
    """Raise ChangelogFormatCommandRequiredError.

    Extracted to reduce cyclomatic complexity in callers.
    """
    raise ChangelogFormatCommandRequiredError


def _project_changelog_path(
    *,
    project: SubProject,
    repo_root: Path,
) -> str:
    return project.changelog_path.relative_to(repo_root).as_posix()


def _project_names_csv(projects: list[SubProject]) -> str:
    return ', '.join(project.name for project in projects)


def _resolve_target_projects(
    *,
    repo_root: Path,
    settings: ReleezSettings,
    project_names: list[str],
    all_projects: bool,
) -> list[SubProject] | None:
    """Resolve project targets for monorepo-aware commands.

    Returns None for single-repo mode, or a concrete project list in monorepo mode.
    """
    if not settings.is_monorepo:
        settings.validate_project_flags(
            project_names=project_names,
            all_projects=all_projects,
        )
        return None
    return settings.select_projects(
        repo_root=repo_root,
        project_names=project_names,
        all_projects=all_projects,
    )


@dataclass(frozen=True)
class _ResolvedProjectTargets:
    settings: ReleezSettings
    repo: Repo
    repo_root: Path
    target_projects: list[SubProject] | None
    active_branch: str | None = None


def _resolve_project_targets_for_command(
    *,
    ctx: typer.Context,
    project_names: list[str],
    all_projects: bool,
) -> _ResolvedProjectTargets:
    settings: ReleezSettings = ctx.obj
    ctx_repo = open_repo()
    repo, info = ctx_repo.repo, ctx_repo.info
    target_projects = _resolve_target_projects(
        repo_root=info.root,
        settings=settings,
        project_names=project_names,
        all_projects=all_projects,
    )
    return _ResolvedProjectTargets(
        settings=settings,
        repo=repo,
        repo_root=info.root,
        target_projects=target_projects,
        active_branch=info.active_branch,
    )


def _require_single_project_override_scope(
    *,
    version_override: str | None,
    target_projects: list[SubProject] | None,
    action_label: str,
) -> None:
    if version_override is None or target_projects is None:
        return
    if len(target_projects) <= 1:
        return
    raise _exit(
        message=f'--version-override can only be used when {action_label} a single project.',
    )


def _normalize_project_names(project_names: list[str] | None) -> list[str]:
    return project_names or []


def _comma_separated_labels(labels: str) -> list[str]:
    return labels.split(',') if labels else []


def _resolve_project_release_version(
    *,
    repo_root: Path,
    version_override: str | None,
    project: SubProject,
) -> VersionInfo:
    return _resolve_release_version(
        repo_root=repo_root,
        version_override=version_override,
        tag_pattern=project.tag_pattern,
        include_paths=_project_include_paths(
            project=project,
            repo_root=repo_root,
        ),
        tag_prefix=project.tag_prefix,
    )


def _project_semver_version(
    *,
    project: SubProject,  # noqa: ARG001
    version: VersionInfo,
) -> str:
    return str(version)


def _alias_versions_for_project(
    *,
    ctx: typer.Context,
    cli_alias_versions: AliasVersions,
    project: SubProject,
) -> AliasVersions:
    source = ctx.get_parameter_source('alias_versions')
    if source == ParameterSource.COMMANDLINE:
        return cli_alias_versions
    return project.alias_versions


# ---------------------------------------------------------------------------
# Options dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _ReleaseStartOptions:
    bump: GitCliffBump
    version_override: str | None
    run_changelog_format: bool
    changelog_format_cmd: list[str] | None
    create_pr: bool
    dry_run: bool
    base: str
    remote: str
    labels: list[str]
    title_prefix: str
    changelog_path: str
    github_token: str | None


@dataclass(frozen=True)
class _ReleaseTagOptions:
    version_override: str | None
    alias_versions: AliasVersions
    remote: str


@dataclass(frozen=True)
class _ReleasePreviewOptions:
    version_override: str | None
    alias_versions: AliasVersions
    output: Path | None


@dataclass(frozen=True)
class _ReleaseNotesOptions:
    version_override: str | None
    output: Path | None


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
# Release tag helpers
# ---------------------------------------------------------------------------


def _create_and_push_selected_tags(
    *,
    repo: Repo,
    remote: str,
    selected_tags: list[str],
) -> None:
    exact_tags = selected_tags[:1]
    alias_only_tags = selected_tags[1:]

    create_tags(repo, tags=exact_tags, force=False)
    push_tags(repo, remote_name=remote, tags=exact_tags, force=False)

    if not alias_only_tags:
        return

    create_tags(repo, tags=alias_only_tags, force=True)
    push_tags(
        repo,
        remote_name=remote,
        tags=alias_only_tags,
        force=True,
    )


def _selected_tags_for_single_repo(
    *,
    repo_root: Path,
    options: _ReleaseTagOptions,
    tag_pattern: str | None = None,
) -> list[str]:
    version = _resolve_release_version(
        repo_root=repo_root,
        version_override=options.version_override,
        tag_pattern=tag_pattern,
    )
    tags = compute_version_tags(version=str(version))
    return select_tags(tags=tags, aliases=options.alias_versions)


def _selected_tags_for_project(
    *,
    repo_root: Path,
    options: _ReleaseTagOptions,
    project: SubProject,
    ctx: typer.Context,
) -> list[str]:
    version = _resolve_project_release_version(
        repo_root=repo_root,
        version_override=options.version_override,
        project=project,
    )
    semver_version = _project_semver_version(project=project, version=version)
    tags = compute_version_tags(
        version=semver_version,
        tag_prefix=project.tag_prefix,
    )
    aliases = _alias_versions_for_project(
        ctx=ctx,
        cli_alias_versions=options.alias_versions,
        project=project,
    )
    return select_tags(tags=tags, aliases=aliases)


def _emit_tags(
    *,
    selected_tags: list[str],
    project_name: str | None = None,
) -> None:
    prefix = f'[{project_name}] ' if project_name else ''
    for tag in selected_tags:
        typer.echo(f'{prefix}{tag}')


def _run_release_tag_command(
    *,
    ctx: typer.Context,
    options: _ReleaseTagOptions,
    project_names: list[str],
    all_projects: bool,
) -> None:
    resolved = _resolve_project_targets_for_command(
        ctx=ctx,
        project_names=project_names,
        all_projects=all_projects,
    )
    _require_single_project_override_scope(
        version_override=options.version_override,
        target_projects=resolved.target_projects,
        action_label='tagging',
    )

    maintenance_ctx = _maintenance_context(
        branch=resolved.active_branch,
        regex=resolved.settings.effective_maintenance_branch_regex,
    )
    fetch(resolved.repo, remote_name=options.remote)
    if resolved.target_projects is None:
        selected = _selected_tags_for_single_repo(
            repo_root=resolved.repo_root,
            options=options,
            tag_pattern=maintenance_ctx.tag_pattern if maintenance_ctx else None,
        )
        if maintenance_ctx:
            _validate_maintenance_version(
                version=selected[0],
                maintenance_ctx=maintenance_ctx,
            )
        _create_and_push_selected_tags(
            repo=resolved.repo,
            remote=options.remote,
            selected_tags=selected,
        )
        _emit_tags(selected_tags=selected)
        return

    for project in resolved.target_projects:
        selected = _selected_tags_for_project(
            repo_root=resolved.repo_root,
            options=options,
            project=project,
            ctx=ctx,
        )
        _create_and_push_selected_tags(
            repo=resolved.repo,
            remote=options.remote,
            selected_tags=selected,
        )
        _emit_tags(selected_tags=selected, project_name=project.name)


# ---------------------------------------------------------------------------
# Release preview helpers
# ---------------------------------------------------------------------------


def _render_preview_section(
    *,
    title: str | None,
    version: str,
    tags: list[str],
) -> list[str]:
    heading = [f'### `{title}`', ''] if title else []
    return [
        *heading,
        f'- Version: `{version}`',
        '- Tags:',
        *[f'  - `{tag}`' for tag in tags],
        '',
    ]


def _build_release_preview_markdown_single_repo(
    *,
    options: _ReleasePreviewOptions,
    repo_root: Path,
    tag_pattern: str | None = None,
) -> str:
    version = _resolve_release_version(
        repo_root=repo_root,
        version_override=options.version_override,
        tag_pattern=tag_pattern,
    )
    version_str = str(version)
    tags = select_tags(
        tags=compute_version_tags(version=version_str),
        aliases=options.alias_versions,
    )
    lines = ['## `releez` release preview', '']
    lines.extend(
        _render_preview_section(
            title=None,
            version=version_str,
            tags=tags,
        ),
    )
    return '\n'.join(lines)


def _build_release_preview_markdown_monorepo(
    *,
    ctx: typer.Context,
    options: _ReleasePreviewOptions,
    repo_root: Path,
    projects: list[SubProject],
) -> str:
    lines = ['## `releez` release preview', '']
    for project in projects:
        version = _resolve_project_release_version(
            repo_root=repo_root,
            version_override=options.version_override,
            project=project,
        )
        semver_version = _project_semver_version(
            project=project,
            version=version,
        )
        tags = select_tags(
            tags=compute_version_tags(
                version=semver_version,
                tag_prefix=project.tag_prefix,
            ),
            aliases=_alias_versions_for_project(
                ctx=ctx,
                cli_alias_versions=options.alias_versions,
                project=project,
            ),
        )
        lines.extend(
            _render_preview_section(
                title=project.name,
                version=tags[0],
                tags=tags,
            ),
        )
    return '\n'.join(lines)


def _emit_or_write_output(
    *,
    output: Path | None,
    content: str,
) -> None:
    if output is None:
        typer.echo(content)
        return
    output_path = Path(output)
    output_path.write_text(content, encoding='utf-8')


def _run_release_preview_command(
    *,
    ctx: typer.Context,
    options: _ReleasePreviewOptions,
    project_names: list[str],
    all_projects: bool,
) -> None:
    resolved = _resolve_project_targets_for_command(
        ctx=ctx,
        project_names=project_names,
        all_projects=all_projects,
    )
    _require_single_project_override_scope(
        version_override=options.version_override,
        target_projects=resolved.target_projects,
        action_label='previewing',
    )

    maintenance_ctx = _maintenance_context(
        branch=resolved.active_branch,
        regex=resolved.settings.effective_maintenance_branch_regex,
    )
    if resolved.target_projects is None:
        tag_pattern = maintenance_ctx.tag_pattern if maintenance_ctx else None
        if maintenance_ctx:
            version = _resolve_release_version(
                repo_root=resolved.repo_root,
                version_override=options.version_override,
                tag_pattern=tag_pattern,
            )
            maintenance_ctx.ensure_version_matches(version)
        markdown = _build_release_preview_markdown_single_repo(
            options=options,
            repo_root=resolved.repo_root,
            tag_pattern=tag_pattern,
        )
    else:
        markdown = _build_release_preview_markdown_monorepo(
            ctx=ctx,
            options=options,
            repo_root=resolved.repo_root,
            projects=resolved.target_projects,
        )

    _emit_or_write_output(
        output=options.output,
        content=markdown,
    )


# ---------------------------------------------------------------------------
# Release notes helpers
# ---------------------------------------------------------------------------


def _generate_release_notes_single_repo(
    *,
    cliff: GitCliff,
    repo_root: Path,
    version_override: str | None,
    tag_pattern: str | None = None,
) -> str:
    version = _resolve_release_version(
        repo_root=repo_root,
        version_override=version_override,
        tag_pattern=tag_pattern,
    )
    compute_version_tags(version=str(version))
    return cliff.generate_unreleased_notes(
        version=str(version),
        tag_pattern=tag_pattern,
    )


def _generate_release_notes_monorepo(
    *,
    cliff: GitCliff,
    repo_root: Path,
    version_override: str | None,
    projects: list[SubProject],
) -> str:
    sections: list[str] = []
    for project in projects:
        version = _resolve_project_release_version(
            repo_root=repo_root,
            version_override=version_override,
            project=project,
        )
        semver_version = _project_semver_version(
            project=project,
            version=version,
        )
        compute_version_tags(
            version=semver_version,
            tag_prefix=project.tag_prefix,
        )
        project_notes = cliff.generate_unreleased_notes(
            version=str(version),
            tag_pattern=project.tag_pattern,
            include_paths=_project_include_paths(
                project=project,
                repo_root=repo_root,
            ),
        )
        sections.extend(
            [
                f'## `{project.name}`',
                '',
                project_notes.strip(),
                '',
            ],
        )
    return '\n'.join(sections).rstrip() + '\n'


def _run_release_notes_command(
    *,
    ctx: typer.Context,
    options: _ReleaseNotesOptions,
    project_names: list[str],
    all_projects: bool,
) -> None:
    resolved = _resolve_project_targets_for_command(
        ctx=ctx,
        project_names=project_names,
        all_projects=all_projects,
    )
    _require_single_project_override_scope(
        version_override=options.version_override,
        target_projects=resolved.target_projects,
        action_label='generating notes for',
    )

    maintenance_ctx = _maintenance_context(
        branch=resolved.active_branch,
        regex=resolved.settings.effective_maintenance_branch_regex,
    )
    cliff = GitCliff(repo_root=resolved.repo_root)
    if resolved.target_projects is None:
        tag_pattern = maintenance_ctx.tag_pattern if maintenance_ctx else None
        if maintenance_ctx:
            version = _resolve_release_version(
                repo_root=resolved.repo_root,
                version_override=options.version_override,
                tag_pattern=tag_pattern,
            )
            maintenance_ctx.ensure_version_matches(version)
        notes = _generate_release_notes_single_repo(
            cliff=cliff,
            repo_root=resolved.repo_root,
            version_override=options.version_override,
            tag_pattern=tag_pattern,
        )
    else:
        notes = _generate_release_notes_monorepo(
            cliff=cliff,
            repo_root=resolved.repo_root,
            version_override=options.version_override,
            projects=resolved.target_projects,
        )

    _emit_or_write_output(
        output=options.output,
        content=notes,
    )


# ---------------------------------------------------------------------------
# Commands
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


@release_app.command('tag')
@handle_releez_errors
def release_tag(  # noqa: PLR0913
    ctx: typer.Context,
    *,
    version_override: Annotated[
        str | None,
        typer.Option(
            '--version-override',
            help='Override release version to tag (x.y.z).',
            show_default=False,
        ),
    ] = None,
    alias_versions: Annotated[
        AliasVersions,
        typer.Option(
            '--alias-versions',
            help='Also create major/minor tags (v2, v2.3).',
            show_default=True,
            case_sensitive=False,
        ),
    ] = AliasVersions.none,
    remote: Annotated[
        str,
        typer.Option(
            '--remote',
            help='Remote to push tags to.',
            show_default=True,
        ),
    ] = 'origin',
    project_names: Annotated[
        list[str] | None,
        typer.Option(
            '--project',
            help='Project name to tag (repeatable, monorepo only).',
            show_default=False,
        ),
    ] = None,
    all_projects: Annotated[
        bool,
        typer.Option(
            '--all',
            help='Tag all configured projects (monorepo only).',
            show_default=True,
        ),
    ] = False,
) -> None:
    """Create git tag(s) for a release and push them."""
    options = _ReleaseTagOptions(
        version_override=version_override,
        alias_versions=alias_versions,
        remote=remote,
    )
    _run_release_tag_command(
        ctx=ctx,
        options=options,
        project_names=_normalize_project_names(project_names),
        all_projects=all_projects,
    )


@release_app.command('preview')
@handle_releez_errors
def release_preview(  # noqa: PLR0913
    ctx: typer.Context,
    *,
    version_override: Annotated[
        str | None,
        typer.Option(
            '--version-override',
            help='Override release version to preview (x.y.z).',
            show_default=False,
        ),
    ] = None,
    alias_versions: Annotated[
        AliasVersions,
        typer.Option(
            '--alias-versions',
            help='Include major/minor tags in the preview.',
            show_default=True,
            case_sensitive=False,
        ),
    ] = AliasVersions.none,
    output: Annotated[
        Path | None,
        typer.Option(
            '--output',
            help='Write markdown preview to a file instead of stdout.',
            show_default=False,
        ),
    ] = None,
    project_names: Annotated[
        list[str] | None,
        typer.Option(
            '--project',
            help='Project name to preview (repeatable, monorepo only).',
            show_default=False,
        ),
    ] = None,
    all_projects: Annotated[
        bool,
        typer.Option(
            '--all',
            help='Preview all configured projects (monorepo only).',
            show_default=True,
        ),
    ] = False,
) -> None:
    """Preview the version and tags that would be published."""
    options = _ReleasePreviewOptions(
        version_override=version_override,
        alias_versions=alias_versions,
        output=output,
    )
    _run_release_preview_command(
        ctx=ctx,
        options=options,
        project_names=_normalize_project_names(project_names),
        all_projects=all_projects,
    )


@release_app.command('notes')
@handle_releez_errors
def release_notes(
    ctx: typer.Context,
    *,
    version_override: Annotated[
        str | None,
        typer.Option(
            '--version-override',
            help='Override release version for the notes section (x.y.z).',
            show_default=False,
        ),
    ] = None,
    output: Annotated[
        Path | None,
        typer.Option(
            '--output',
            help='Write release notes to a file instead of stdout.',
            show_default=False,
        ),
    ] = None,
    project_names: Annotated[
        list[str] | None,
        typer.Option(
            '--project',
            help='Project name to render notes for (repeatable, monorepo only).',
            show_default=False,
        ),
    ] = None,
    all_projects: Annotated[
        bool,
        typer.Option(
            '--all',
            help='Generate notes for all configured projects (monorepo only).',
            show_default=True,
        ),
    ] = False,
) -> None:
    """Generate the new changelog section for the release."""
    options = _ReleaseNotesOptions(
        version_override=version_override,
        output=output,
    )
    _run_release_notes_command(
        ctx=ctx,
        options=options,
        project_names=_normalize_project_names(project_names),
        all_projects=all_projects,
    )
