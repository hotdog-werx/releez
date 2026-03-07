from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, NoReturn, cast

import typer
from click.core import ParameterSource

from releez import __version__
from releez.artifact_version import (
    ArtifactVersionInput,
    ArtifactVersionScheme,
    PrereleaseType,
    compute_artifact_version,
)
from releez.cliff import GitCliff, GitCliffBump
from releez.errors import (
    ChangelogFormatCommandRequiredError,
    ReleezError,
)
from releez.git_repo import (
    DetectedRelease,
    create_tags,
    detect_changed_projects,
    detect_release_from_branch,
    fetch,
    open_repo,
    push_tags,
)
from releez.release import StartReleaseInput, StartReleaseResult, start_release
from releez.settings import ReleezSettings
from releez.subapps import changelog_app
from releez.subproject import SubProject
from releez.version_tags import AliasVersions, compute_version_tags, select_tags

if TYPE_CHECKING:
    from git import Repo

app = typer.Typer(help='CLI tool for helping to manage release processes.')
release_app = typer.Typer(help='Release workflows (changelog + branch + PR).')
version_app = typer.Typer(help='Version utilities for CI/artifacts.')
projects_app = typer.Typer(help='Monorepo project utilities.')


def _version_callback(*, value: bool) -> None:
    """Print version and exit when --version flag is passed.

    Args:
        value: True if --version was passed.
    """
    if value:
        typer.echo(f'releez {__version__}')
        raise typer.Exit(0)


@app.callback()
def _root(
    ctx: typer.Context,
    *,
    _version: Annotated[
        bool,
        typer.Option(
            '--version',
            help="Show the application's version and exit.",
            callback=_version_callback,
            is_eager=True,
        ),
    ] = False,
) -> None:
    settings = ReleezSettings()
    ctx.obj = settings

    default_map: dict[str, object] = {}
    default_map['release'] = {
        'start': {
            'base': settings.base_branch,
            'remote': settings.git_remote,
            'labels': settings.pr_labels,
            'title_prefix': settings.pr_title_prefix,
            'changelog_path': settings.changelog_path,
            'create_pr': settings.create_pr,
            'run_changelog_format': settings.run_changelog_format,
            'changelog_format_cmd': settings.hooks.changelog_format,
        },
        'tag': {
            'remote': settings.git_remote,
            'alias_versions': settings.alias_versions,
        },
        'preview': {
            'alias_versions': settings.alias_versions,
        },
    }
    default_map['version'] = {
        'artifact': {
            'alias_versions': settings.alias_versions,
        },
    }
    default_map['changelog'] = {
        'regenerate': {
            'changelog_path': settings.changelog_path,
            'run_changelog_format': settings.run_changelog_format,
            'changelog_format_cmd': settings.hooks.changelog_format,
        },
    }

    if ctx.default_map is None:
        ctx.default_map = default_map
    else:
        ctx.default_map = {
            **ctx.default_map,
            **default_map,
        }


@dataclass(frozen=True)
class _VersionArtifactArgs:
    """CLI arguments for the `version artifact` command."""

    scheme: ArtifactVersionScheme
    version_override: str | None
    is_full_release: bool
    prerelease_type: PrereleaseType
    prerelease_number: int | None
    build_number: int | None


def _build_artifact_version_input(
    *,
    args: _VersionArtifactArgs,
) -> ArtifactVersionInput:
    """Convert CLI args dataclass to ArtifactVersionInput.

    Args:
        args: CLI arguments for the version artifact command.

    Returns:
        Input dataclass for compute_artifact_version.
    """
    return ArtifactVersionInput(
        scheme=args.scheme,
        version_override=args.version_override,
        is_full_release=args.is_full_release,
        prerelease_type=args.prerelease_type,
        prerelease_number=args.prerelease_number,
        build_number=args.build_number,
    )


def _emit_all_artifact_versions_json(  # noqa: PLR0913
    *,
    version_override: str | None,
    is_full_release: bool,
    prerelease_type: PrereleaseType,
    prerelease_number: int | None,
    build_number: int | None,
    alias_versions: AliasVersions,
    project_name: str | None = None,
    tag_prefix: str = '',
) -> None:
    """Emit all artifact version schemes as JSON.

    Outputs JSON with keys for each scheme (semver, docker, pep440)
    and values as arrays of version strings including aliases.

    For each scheme, computes the version string and any alias versions
    (if full release). PEP440 never includes aliases. Prerelease builds
    never include aliases regardless of scheme.

    When project_name is provided, also emits "release_version" (the full
    prefixed tag, e.g. "core-0.2.0") and "project" keys in the JSON output.

    Args:
        version_override: Version to use instead of computing from git-cliff.
        is_full_release: Whether this is a full release (no prerelease markers).
        prerelease_type: Prerelease label (alpha, beta, rc).
        prerelease_number: Prerelease number.
        build_number: Build identifier for prereleases.
        alias_versions: Alias version strategy (none, major, minor).
        project_name: Project name for monorepo releases.
        tag_prefix: Tag prefix for the project (e.g. "core-").
    """
    result: dict[str, list[str] | str] = {}

    for scheme_value in ArtifactVersionScheme:
        artifact_args = _VersionArtifactArgs(
            scheme=scheme_value,
            version_override=version_override,
            is_full_release=is_full_release,
            prerelease_type=prerelease_type,
            prerelease_number=prerelease_number,
            build_number=build_number,
        )
        artifact_input = _build_artifact_version_input(args=artifact_args)
        artifact_version = compute_artifact_version(artifact_input)

        # Get the list of versions for this scheme
        if scheme_value == ArtifactVersionScheme.pep440:
            # PEP440 doesn't support alias versions
            result[scheme_value.value] = [artifact_version]
        elif alias_versions == AliasVersions.none or not is_full_release:
            # No aliases requested or not a full release
            result[scheme_value.value] = [artifact_version]
        else:
            # Full release with alias versions (semver/docker)
            tags = compute_version_tags(version=artifact_version)
            result[scheme_value.value] = select_tags(
                tags=tags,
                aliases=alias_versions,
            )

    if project_name is not None and version_override is not None:
        result['release_version'] = f'{tag_prefix}{version_override}'
        result['project'] = project_name

    typer.echo(json.dumps(result, indent=2))


def _emit_artifact_version_output(
    *,
    artifact_version: str,
    scheme: ArtifactVersionScheme,
    is_full_release: bool,
    alias_versions: AliasVersions,
) -> None:
    """Emit artifact version(s) to stdout with warnings for invalid combinations.

    Prints one version per line. For alias versions, prints each alias
    on a separate line. Warns to stderr if alias options are inapplicable.

    Args:
        artifact_version: Computed version string.
        scheme: Output scheme (semver, docker, pep440).
        is_full_release: Whether this is a full release.
        alias_versions: Alias version strategy.
    """
    if scheme == ArtifactVersionScheme.pep440:
        if alias_versions != AliasVersions.none:
            typer.secho(
                'Note: --alias-versions is ignored for --scheme pep440.',
                err=True,
                fg=typer.colors.YELLOW,
            )
        typer.echo(artifact_version)
        return

    if alias_versions == AliasVersions.none:
        typer.echo(artifact_version)
        return

    if not is_full_release:
        typer.secho(
            'Note: --alias-versions is only applied for full releases; ignoring because --is-full-release is not set.',
            err=True,
            fg=typer.colors.YELLOW,
        )
        typer.echo(artifact_version)
        return

    tags = compute_version_tags(version=artifact_version)
    for tag in select_tags(tags=tags, aliases=alias_versions):
        typer.echo(tag)


def _resolve_release_version(
    *,
    repo_root: Path,
    version_override: str | None,
    tag_pattern: str | None = None,
    include_paths: list[str] | None = None,
) -> str:
    """Resolve release version from override or git-cliff."""
    if version_override is not None:
        return version_override
    cliff = GitCliff(repo_root=repo_root)
    return cliff.compute_next_version(
        bump='auto',
        tag_pattern=tag_pattern,
        include_paths=include_paths,
    )


def _raise_changelog_format_command_required() -> None:
    """Raise ChangelogFormatCommandRequiredError.

    Extracted to reduce cyclomatic complexity in callers.
    """
    raise ChangelogFormatCommandRequiredError


def _exit_with_message(message: str) -> NoReturn:
    typer.secho(message, err=True, fg=typer.colors.RED)
    raise typer.Exit(code=1)


def _exit_with_code() -> NoReturn:
    raise typer.Exit(code=1)


def _project_relative_glob(*, project: SubProject, repo_root: Path) -> str:
    rel_path = project.path.relative_to(repo_root)
    return f'{rel_path.as_posix()}/**'


def _project_include_paths(
    *,
    project: SubProject,
    repo_root: Path,
) -> list[str]:
    return [
        _project_relative_glob(project=project, repo_root=repo_root),
        *project.include_paths,
    ]


def _project_changelog_path(
    *,
    project: SubProject,
    repo_root: Path,
) -> str:
    return project.changelog_path.relative_to(repo_root).as_posix()


def _project_names_csv(projects: list[SubProject]) -> str:
    return ', '.join(project.name for project in projects)


def _selected_projects_from_names(
    *,
    subprojects: list[SubProject],
    project_names: list[str],
) -> list[SubProject]:
    projects_by_name = {project.name: project for project in subprojects}
    selected: list[SubProject] = []

    for name in project_names:
        project = projects_by_name.get(name)
        if project is None:
            available = ', '.join(sorted(projects_by_name))
            _exit_with_message(
                f'Unknown project "{name}". Available projects: {available}',
            )
        if project not in selected:
            selected.append(cast('SubProject', project))

    return selected


def _validate_project_selection_flags(
    *,
    project_names: list[str],
    all_projects: bool,
) -> None:
    if project_names and all_projects:
        _exit_with_message('Cannot use --project and --all together.')


def _resolve_single_repo_targets(
    *,
    project_names: list[str],
    all_projects: bool,
) -> list[SubProject] | None:
    if project_names or all_projects:
        _exit_with_message(
            'No projects are configured. Remove --project/--all or configure [tool.releez.projects].',
        )
    return None


def _resolve_explicit_project_targets(
    *,
    subprojects: list[SubProject],
    project_names: list[str],
    all_projects: bool,
) -> list[SubProject] | None:
    if project_names:
        return _selected_projects_from_names(
            subprojects=subprojects,
            project_names=project_names,
        )
    if all_projects:
        return subprojects
    return None


def _detect_changed_project_targets(
    *,
    repo: Repo,
    base_branch: str,
    subprojects: list[SubProject],
) -> list[SubProject]:
    changed = detect_changed_projects(
        repo=repo,
        base_branch=base_branch,
        projects=subprojects,
    )

    if not changed:
        typer.secho(
            'No projects with unreleased changes were detected.',
            fg=typer.colors.GREEN,
        )
        return []

    typer.secho(
        f'Detected changed projects: {_project_names_csv(changed)}',
        fg=typer.colors.BLUE,
    )
    return changed


def _resolve_target_projects(  # noqa: PLR0913
    *,
    repo: Repo,
    repo_root: Path,
    settings: ReleezSettings,
    project_names: list[str],
    all_projects: bool,
    base_branch: str,
    require_explicit_selection: bool,
) -> list[SubProject] | None:
    """Resolve project targets for monorepo-aware commands.

    Returns None for single-repo mode, or a concrete project list in monorepo mode.
    """
    subprojects = _build_subprojects_list(settings, repo_root=repo_root)

    if not subprojects:
        return _resolve_single_repo_targets(
            project_names=project_names,
            all_projects=all_projects,
        )

    _validate_project_selection_flags(
        project_names=project_names,
        all_projects=all_projects,
    )
    explicit_targets = _resolve_explicit_project_targets(
        subprojects=subprojects,
        project_names=project_names,
        all_projects=all_projects,
    )
    if explicit_targets is not None:
        return explicit_targets

    if require_explicit_selection:
        _exit_with_message(
            'Project selection is required in monorepo mode. Use --project <name> (repeatable) or --all.',
        )

    return _detect_changed_project_targets(
        repo=repo,
        base_branch=base_branch,
        subprojects=subprojects,
    )


@dataclass(frozen=True)
class _ResolvedProjectTargets:
    settings: ReleezSettings
    repo: Repo
    repo_root: Path
    target_projects: list[SubProject] | None


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


def _resolve_project_targets_for_command(
    *,
    ctx: typer.Context,
    project_names: list[str],
    all_projects: bool,
    base_branch: str,
    require_explicit_selection: bool,
) -> _ResolvedProjectTargets:
    settings: ReleezSettings = ctx.obj
    repo, info = open_repo()
    target_projects = _resolve_target_projects(
        repo=repo,
        repo_root=info.root,
        settings=settings,
        project_names=project_names,
        all_projects=all_projects,
        base_branch=base_branch,
        require_explicit_selection=require_explicit_selection,
    )
    return _ResolvedProjectTargets(
        settings=settings,
        repo=repo,
        repo_root=info.root,
        target_projects=target_projects,
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
    _exit_with_message(
        f'--version-override can only be used when {action_label} a single project.',
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
) -> str:
    return _resolve_release_version(
        repo_root=repo_root,
        version_override=version_override,
        tag_pattern=project.tag_pattern,
        include_paths=_project_include_paths(
            project=project,
            repo_root=repo_root,
        ),
    )


def _project_semver_version(
    *,
    project: SubProject,
    version: str,
) -> str:
    if project.tag_prefix and version.startswith(project.tag_prefix):
        return version.removeprefix(project.tag_prefix)
    return version


def _build_release_start_input_single_repo(
    *,
    options: _ReleaseStartOptions,
    settings: ReleezSettings,
) -> StartReleaseInput:
    return StartReleaseInput(
        bump=options.bump,
        version_override=options.version_override,
        base_branch=options.base,
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
    )


def _build_release_start_input_project(
    *,
    options: _ReleaseStartOptions,
    project: SubProject,
    repo_root: Path,
) -> StartReleaseInput:
    return StartReleaseInput(
        bump=options.bump,
        version_override=options.version_override,
        base_branch=options.base,
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


def _run_single_repo_release_start(
    *,
    options: _ReleaseStartOptions,
    settings: ReleezSettings,
) -> None:
    release_input = _build_release_start_input_single_repo(
        options=options,
        settings=settings,
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
) -> bool:
    release_input = _build_release_start_input_project(
        options=options,
        project=project,
        repo_root=repo_root,
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


def _run_monorepo_release_start(
    *,
    options: _ReleaseStartOptions,
    target_projects: list[SubProject],
    repo_root: Path,
) -> None:
    _require_single_project_override_scope(
        version_override=options.version_override,
        target_projects=target_projects,
        action_label='releasing',
    )
    if not target_projects:
        return

    succeeded = 0
    for project in target_projects:
        if _run_project_release_start(
            options=options,
            project=project,
            repo_root=repo_root,
        ):
            succeeded += 1

    failed = len(target_projects) - succeeded
    typer.secho(
        f'Release summary: {succeeded} succeeded, {failed} failed.',
        fg=typer.colors.BLUE,
    )
    if failed:
        _exit_with_code()


def _run_release_start_command(
    *,
    ctx: typer.Context,
    options: _ReleaseStartOptions,
    project_names: list[str],
    all_projects: bool,
) -> None:
    if options.run_changelog_format and not options.changelog_format_cmd:
        _raise_changelog_format_command_required()

    resolved = _resolve_project_targets_for_command(
        ctx=ctx,
        project_names=project_names,
        all_projects=all_projects,
        base_branch=options.base,
        require_explicit_selection=True,
    )
    if resolved.target_projects is None:
        _run_single_repo_release_start(
            options=options,
            settings=resolved.settings,
        )
        return
    if not resolved.target_projects:
        _exit_with_code()

    _run_monorepo_release_start(
        options=options,
        target_projects=resolved.target_projects,
        repo_root=resolved.repo_root,
    )


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


@release_app.command('start')
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

    try:
        _run_release_start_command(
            ctx=ctx,
            options=options,
            project_names=_normalize_project_names(project_names),
            all_projects=all_projects,
        )
    except ReleezError as exc:
        typer.secho(str(exc), err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1) from exc
    except Exception as exc:  # pragma: no cover
        typer.secho(f'Unexpected error: {exc}', err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1) from exc


def _find_project_for_artifact(
    *,
    subprojects: list[SubProject],
    project_name: str,
) -> SubProject:
    """Find a SubProject by name for version artifact computation.

    Args:
        subprojects: List of configured subprojects.
        project_name: Name of the project to find.

    Returns:
        The matching SubProject.

    Raises:
        SystemExit: If the project is not found or no projects are configured.
    """
    if not subprojects:
        _exit_with_message(
            'No projects configured. Remove --project or add [[tool.releez.projects]] to config.',
        )

    for project in subprojects:
        if project.name == project_name:
            return project

    available = ', '.join(sorted(p.name for p in subprojects))
    _exit_with_message(
        f'Unknown project "{project_name}". Available: {available}',
    )


def _resolve_artifact_project_context(
    *,
    settings: ReleezSettings,
    project_name: str | None,
    version_override: str | None,
) -> tuple[str, str | None]:
    """Validate monorepo mode and resolve tag prefix and version for version artifact.

    Returns:
        (tag_prefix, resolved_version_override)
    """
    if project_name is None:
        if settings.projects:
            _exit_with_message(
                'Monorepo projects are configured. Use --project <name> to specify which project to version.',
            )
        return '', version_override

    _, info = open_repo()
    subprojects = _build_subprojects_list(settings, repo_root=info.root)
    project = _find_project_for_artifact(
        subprojects=subprojects,
        project_name=project_name,
    )
    if version_override is None:
        raw_version = _resolve_release_version(
            repo_root=info.root,
            version_override=None,
            tag_pattern=project.tag_pattern,
            include_paths=_project_include_paths(
                project=project,
                repo_root=info.root,
            ),
        )
        # git-cliff returns the full tag (e.g., "core-1.1.0") when a tag prefix is used;
        # strip it so version_override is a bare semver string for compute_artifact_version.
        version_override = _project_semver_version(
            project=project,
            version=raw_version,
        )
    return project.tag_prefix, version_override


@version_app.command('artifact')
def version_artifact(  # noqa: PLR0913
    ctx: typer.Context,
    *,
    scheme: Annotated[
        ArtifactVersionScheme | None,
        typer.Option(
            '--scheme',
            help='Output scheme for the artifact version. If not specified, outputs all schemes as JSON.',
            show_default=False,
            case_sensitive=False,
        ),
    ] = None,
    is_full_release: Annotated[
        bool,
        typer.Option(
            help='If true, output a full release version without prerelease markers.',
            show_default=True,
        ),
    ] = False,
    prerelease_type: Annotated[
        PrereleaseType,
        typer.Option(
            help='Prerelease label (alpha, beta, rc).',
            show_default=True,
            case_sensitive=False,
        ),
    ] = PrereleaseType.alpha,
    prerelease_number: Annotated[
        int | None,
        typer.Option(
            help='Optional prerelease number (e.g. PR number for alpha123).',
            show_default=False,
        ),
    ] = None,
    build_number: Annotated[
        int | None,
        typer.Option(
            help='Build number for prerelease builds.',
            show_default=False,
        ),
    ] = None,
    version_override: Annotated[
        str | None,
        typer.Option(
            '--version-override',
            help='Override version instead of computing via git-cliff.',
            show_default=False,
        ),
    ] = None,
    alias_versions: Annotated[
        AliasVersions,
        typer.Option(
            '--alias-versions',
            help='For full releases, also output major/minor tags.',
            show_default=True,
            case_sensitive=False,
        ),
    ] = AliasVersions.none,
    project_name: Annotated[
        str | None,
        typer.Option(
            '--project',
            help='Project name for monorepo version detection (monorepo only).',
            show_default=False,
        ),
    ] = None,
) -> None:
    """Compute an artifact version string."""
    try:
        settings: ReleezSettings = ctx.obj
        resolved_tag_prefix, version_override = _resolve_artifact_project_context(
            settings=settings,
            project_name=project_name,
            version_override=version_override,
        )

        if scheme is None:
            # Output all schemes as JSON
            _emit_all_artifact_versions_json(
                version_override=version_override,
                is_full_release=is_full_release,
                prerelease_type=prerelease_type,
                prerelease_number=prerelease_number,
                build_number=build_number,
                alias_versions=alias_versions,
                project_name=project_name,
                tag_prefix=resolved_tag_prefix,
            )
            return

        # Output single scheme (scheme is guaranteed non-None here)
        artifact_args = _VersionArtifactArgs(
            scheme=scheme,
            version_override=version_override,
            is_full_release=is_full_release,
            prerelease_type=prerelease_type,
            prerelease_number=prerelease_number,
            build_number=build_number,
        )
        artifact_input = _build_artifact_version_input(args=artifact_args)
        artifact_version = compute_artifact_version(artifact_input)
        _emit_artifact_version_output(
            artifact_version=artifact_version,
            scheme=scheme,
            is_full_release=is_full_release,
            alias_versions=alias_versions,
        )
    except ReleezError as exc:
        typer.secho(str(exc), err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1) from exc


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
) -> list[str]:
    version = _resolve_release_version(
        repo_root=repo_root,
        version_override=options.version_override,
    )
    tags = compute_version_tags(version=version)
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
    settings: ReleezSettings = ctx.obj
    resolved = _resolve_project_targets_for_command(
        ctx=ctx,
        project_names=project_names,
        all_projects=all_projects,
        base_branch=settings.base_branch,
        require_explicit_selection=True,
    )
    _require_single_project_override_scope(
        version_override=options.version_override,
        target_projects=resolved.target_projects,
        action_label='tagging',
    )

    fetch(resolved.repo, remote_name=options.remote)
    if resolved.target_projects is None:
        selected = _selected_tags_for_single_repo(
            repo_root=resolved.repo_root,
            options=options,
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
) -> str:
    version = _resolve_release_version(
        repo_root=repo_root,
        version_override=options.version_override,
    )
    tags = select_tags(
        tags=compute_version_tags(version=version),
        aliases=options.alias_versions,
    )
    lines = ['## `releez` release preview', '']
    lines.extend(
        _render_preview_section(
            title=None,
            version=version,
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
    settings: ReleezSettings = ctx.obj
    resolved = _resolve_project_targets_for_command(
        ctx=ctx,
        project_names=project_names,
        all_projects=all_projects,
        base_branch=settings.base_branch,
        require_explicit_selection=True,
    )
    _require_single_project_override_scope(
        version_override=options.version_override,
        target_projects=resolved.target_projects,
        action_label='previewing',
    )

    if resolved.target_projects is None:
        markdown = _build_release_preview_markdown_single_repo(
            options=options,
            repo_root=resolved.repo_root,
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


def _generate_release_notes_single_repo(
    *,
    cliff: GitCliff,
    repo_root: Path,
    version_override: str | None,
) -> str:
    version = _resolve_release_version(
        repo_root=repo_root,
        version_override=version_override,
    )
    compute_version_tags(version=version)
    return cliff.generate_unreleased_notes(version=version)


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
            version=version,
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
    settings: ReleezSettings = ctx.obj
    resolved = _resolve_project_targets_for_command(
        ctx=ctx,
        project_names=project_names,
        all_projects=all_projects,
        base_branch=settings.base_branch,
        require_explicit_selection=True,
    )
    _require_single_project_override_scope(
        version_override=options.version_override,
        target_projects=resolved.target_projects,
        action_label='generating notes for',
    )

    cliff = GitCliff(repo_root=resolved.repo_root)
    if resolved.target_projects is None:
        notes = _generate_release_notes_single_repo(
            cliff=cliff,
            repo_root=resolved.repo_root,
            version_override=options.version_override,
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


@release_app.command('tag')
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
    try:
        _run_release_tag_command(
            ctx=ctx,
            options=options,
            project_names=_normalize_project_names(project_names),
            all_projects=all_projects,
        )
    except ReleezError as exc:
        typer.secho(str(exc), err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1) from exc


@release_app.command('preview')
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
    try:
        _run_release_preview_command(
            ctx=ctx,
            options=options,
            project_names=_normalize_project_names(project_names),
            all_projects=all_projects,
        )
    except ReleezError as exc:
        typer.secho(str(exc), err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1) from exc


def _get_branch_name(branch: str | None) -> str:
    """Get branch name from parameter or detect current branch.

    Args:
        branch: Branch name from user, or None to auto-detect.

    Returns:
        Branch name to parse.

    Raises:
        typer.Exit: If in detached HEAD state without --branch.
    """
    if branch is not None:
        return branch

    _, info = open_repo()
    if info.active_branch is None:
        typer.secho(
            'Error: Not on a branch (detached HEAD). Use --branch to specify branch name.',
            err=True,
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=1)
    return info.active_branch


def _build_subprojects_list(
    settings: ReleezSettings,
    *,
    repo_root: Path,
) -> list[SubProject]:
    """Build SubProject instances from settings."""
    if not settings.projects:
        return []

    return [
        SubProject.from_config(
            config,
            repo_root=repo_root,
            global_settings=settings,
        )
        for config in settings.projects
    ]


def _format_detected_release_json(detected: DetectedRelease) -> str:
    """Format DetectedRelease as JSON string.

    Args:
        detected: Detected release information.

    Returns:
        JSON string with version, branch, and optional project.
    """
    output = {
        'version': detected.version,
        'semver_version': detected.semver_version,
        'branch': detected.branch_name,
    }
    if detected.project_name:
        output['project'] = detected.project_name
    return json.dumps(output, indent=2)


@release_app.command('detect-from-branch')
def release_detect_from_branch(
    *,
    branch: Annotated[
        str | None,
        typer.Option(
            '--branch',
            help='Branch name to parse. If not specified, uses current branch.',
            show_default=False,
        ),
    ] = None,
) -> None:
    """Detect release information from a branch name.

    Parses release branch names to extract version and project information.
    Useful for GitHub Actions workflows to detect which project is being released.

    Single repo format: release/1.2.3
    Monorepo format: release/core-1.2.3
    """
    try:
        settings = ReleezSettings()
        branch_name = _get_branch_name(branch)
        _, info = open_repo()
        subprojects = _build_subprojects_list(settings, repo_root=info.root)

        detected = detect_release_from_branch(
            branch_name=branch_name,
            projects=subprojects,
        )

        if detected is None:
            typer.secho(
                f'Error: Branch "{branch_name}" is not a release branch.',
                err=True,
                fg=typer.colors.RED,
            )
            raise typer.Exit(code=1)

        typer.echo(_format_detected_release_json(detected))

    except ReleezError as exc:
        typer.secho(str(exc), err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1) from exc


@release_app.command('notes')
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
    try:
        _run_release_notes_command(
            ctx=ctx,
            options=options,
            project_names=_normalize_project_names(project_names),
            all_projects=all_projects,
        )
    except ReleezError as exc:
        typer.secho(str(exc), err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1) from exc


@projects_app.command('list')
def projects_list(ctx: typer.Context) -> None:
    """List configured monorepo projects."""
    settings: ReleezSettings = ctx.obj

    if not settings.projects:
        typer.secho(
            'No projects configured. This is a single-repo setup.',
            fg=typer.colors.YELLOW,
        )
        return

    typer.secho(
        f'Configured projects ({len(settings.projects)}):',
        fg=typer.colors.BLUE,
        bold=True,
    )
    for project_config in settings.projects:
        typer.echo(f'  • {project_config.name}')
        typer.echo(f'    Path: {project_config.path}')
        typer.echo(f'    Tag prefix: {project_config.tag_prefix or "(none)"}')
        typer.echo(f'    Changelog: {project_config.changelog_path}')
        if project_config.include_paths:
            typer.echo(
                f'    Include paths: {", ".join(project_config.include_paths)}',
            )
        typer.echo()


def _output_changed_projects(
    changed: list[SubProject],
    format_output: str,
) -> None:
    """Output changed projects in the requested format.

    Args:
        changed: Projects with unreleased changes.
        format_output: Output format, "json" or "text".
    """
    if format_output == 'json':
        # include key matches GitHub Actions matrix strategy format
        output = {
            'projects': [p.name for p in changed],
            'include': [{'project': p.name} for p in changed],
        }
        typer.echo(json.dumps(output, indent=2))
    elif not changed:
        typer.secho(
            'No projects have unreleased changes.',
            fg=typer.colors.GREEN,
        )
    else:
        typer.secho(
            f'Projects with unreleased changes ({len(changed)}):',
            fg=typer.colors.BLUE,
            bold=True,
        )
        for project in changed:
            typer.echo(f'  • {project.name}')


@projects_app.command('changed')
def projects_changed(
    ctx: typer.Context,
    *,
    format_output: Annotated[
        str,
        typer.Option(
            '--format',
            help='Output format: text or json',
            show_default=True,
        ),
    ] = 'text',
    base: Annotated[
        str | None,
        typer.Option(
            '--base',
            help='Base branch to compare against (defaults to configured base-branch)',
            show_default=False,
        ),
    ] = None,
) -> None:
    """Detect projects that have unreleased changes."""
    try:
        settings: ReleezSettings = ctx.obj

        if not settings.projects:
            typer.secho(
                'No projects configured. This is a single-repo setup.',
                err=True,
                fg=typer.colors.YELLOW,
            )
            raise typer.Exit(code=1)

        repo, info = open_repo()
        base_branch = base or settings.base_branch

        subprojects = [
            SubProject.from_config(
                config,
                repo_root=info.root,
                global_settings=settings,
            )
            for config in settings.projects
        ]

        changed = detect_changed_projects(
            repo=repo,
            base_branch=base_branch,
            projects=subprojects,
        )
        _output_changed_projects(changed, format_output)

    except ReleezError as exc:
        typer.secho(str(exc), err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1) from exc


@projects_app.command('info')
def projects_info(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument(help='Project name')],
) -> None:
    """Show configuration details for one project."""
    settings: ReleezSettings = ctx.obj

    if not settings.projects:
        typer.secho(
            'No projects configured. This is a single-repo setup.',
            err=True,
            fg=typer.colors.YELLOW,
        )
        raise typer.Exit(code=1)

    # Find the project
    project_config = next(
        (p for p in settings.projects if p.name == name),
        None,
    )
    if not project_config:
        typer.secho(
            f'Project "{name}" not found.',
            err=True,
            fg=typer.colors.RED,
        )
        available = ', '.join(p.name for p in settings.projects)
        typer.secho(f'Available projects: {available}', err=True)
        raise typer.Exit(code=1)

    # Display detailed info
    typer.secho(
        f'Project: {project_config.name}',
        fg=typer.colors.BLUE,
        bold=True,
    )
    typer.echo(f'  Path: {project_config.path}')
    typer.echo(f'  Tag prefix: {project_config.tag_prefix or "(none)"}')
    typer.echo(f'  Changelog: {project_config.changelog_path}')
    typer.echo(
        f'  Alias versions: {project_config.alias_versions or settings.alias_versions}',
    )

    if project_config.include_paths:
        typer.echo('  Include paths:')
        for path in project_config.include_paths:
            typer.echo(f'    - {path}')

    if project_config.hooks.post_changelog:
        typer.echo('  Post-changelog hooks:')
        for hook in project_config.hooks.post_changelog:
            typer.echo(f'    - {" ".join(hook)}')


validate_app = typer.Typer(
    help='Validate commit messages against cliff.toml rules.',
)


@validate_app.command('commit-message')
def validate_commit_message(
    message: Annotated[str, typer.Argument(help='Commit message to validate.')],
) -> None:
    """Check if a commit message matches a configured commit parser.

    Exits 0 if valid, 1 if the message does not match any parser.
    Useful for validating PR titles before merge.
    """
    _, repo_info = open_repo()
    result = GitCliff(repo_root=repo_info.root).validate_commit_message(message)
    if result.valid:
        typer.secho(f'✓ {result.reason}', fg=typer.colors.GREEN)
    else:
        typer.secho(f'✗ {result.reason}', err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1)


app.add_typer(release_app, name='release')
app.add_typer(version_app, name='version')
app.add_typer(changelog_app, name='changelog')
app.add_typer(projects_app, name='projects')
app.add_typer(validate_app, name='validate')


def main() -> None:
    """Main entry point for the CLI."""
    app()
