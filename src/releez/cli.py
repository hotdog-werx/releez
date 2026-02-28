from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

import typer

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
from releez.release import StartReleaseInput, start_release
from releez.settings import ReleezSettings
from releez.subapps import changelog_app
from releez.subproject import SubProject
from releez.version_tags import AliasVersions, compute_version_tags, select_tags

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
) -> None:
    """Emit all artifact version schemes as JSON.

    Outputs JSON with keys for each scheme (semver, docker, pep440)
    and values as arrays of version strings including aliases.

    For each scheme, computes the version string and any alias versions
    (if full release). PEP440 never includes aliases. Prerelease builds
    never include aliases regardless of scheme.

    Args:
        version_override: Version to use instead of computing from git-cliff.
        is_full_release: Whether this is a full release (no prerelease markers).
        prerelease_type: Prerelease label (alpha, beta, rc).
        prerelease_number: Prerelease number.
        build_number: Build identifier for prereleases.
        alias_versions: Alias version strategy (none, major, minor).
    """
    result: dict[str, list[str]] = {}

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
) -> str:
    """Resolve release version from override or git-cliff.

    Args:
        repo_root: Repository root directory.
        version_override: Explicit version to use, or None to compute.

    Returns:
        Version string to use for the release.
    """
    if version_override is not None:
        return version_override
    cliff = GitCliff(repo_root=repo_root)
    return cliff.compute_next_version(bump='auto')


def _raise_changelog_format_command_required() -> None:
    """Raise ChangelogFormatCommandRequiredError.

    Extracted to reduce cyclomatic complexity in callers.
    """
    raise ChangelogFormatCommandRequiredError


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
    github_token: Annotated[
        str | None,
        typer.Option(
            envvar=['RELEEZ_GITHUB_TOKEN', 'GITHUB_TOKEN'],
            help='GitHub token for PR creation (prefer RELEEZ_GITHUB_TOKEN; falls back to GITHUB_TOKEN).',
            show_default=False,
        ),
    ] = None,
) -> None:
    """Start a release branch and update the changelog.

    Computes the next version using git-cliff, prepends the changelog, commits and pushes a
    `release/<version>` branch, and optionally opens a GitHub PR.

    Post-changelog hooks from config are automatically run if configured.

    Args:
        ctx: Typer context (injected automatically).
        bump: Bump mode for git-cliff.
        version_override: Override the computed next version.
        run_changelog_format: (DEPRECATED) If true, run changelog formatter.
        changelog_format_cmd: (DEPRECATED) Override changelog formatter argv.
        create_pr: If true, create a GitHub pull request.
        dry_run: If true, do not modify the repo; just output version and notes.
        base: Base branch for the release PR.
        remote: Remote name to use.
        labels: Comma-separated labels to add to the PR.
        title_prefix: Prefix for PR title.
        changelog_path: Changelog file to prepend to.
        github_token: GitHub token for PR creation.

    Raises:
        typer.Exit: If an error occurs during release processing.
    """
    try:
        if run_changelog_format and not changelog_format_cmd:
            _raise_changelog_format_command_required()

        # Get configured hooks from settings
        settings: ReleezSettings = ctx.obj
        post_changelog_hooks = settings.hooks.post_changelog or None

        release_input = StartReleaseInput(
            bump=bump,
            version_override=version_override,
            base_branch=base,
            remote_name=remote,
            labels=labels.split(',') if labels else [],
            title_prefix=title_prefix,
            changelog_path=changelog_path,
            post_changelog_hooks=post_changelog_hooks,
            run_changelog_format=run_changelog_format,
            changelog_format_cmd=changelog_format_cmd,
            create_pr=create_pr,
            github_token=github_token,
            dry_run=dry_run,
        )
        result = start_release(release_input)
    except ReleezError as exc:
        typer.secho(str(exc), err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1) from exc
    except Exception as exc:  # pragma: no cover
        typer.secho(f'Unexpected error: {exc}', err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1) from exc

    typer.secho(f'Next version: {result.version}', fg=typer.colors.GREEN)
    if dry_run:
        typer.echo(result.release_notes_markdown)
        return

    typer.echo(f'Release branch: {result.release_branch}')
    if result.pr_url:
        typer.echo(f'PR created: {result.pr_url}')


@version_app.command('artifact')
def version_artifact(  # noqa: PLR0913
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
) -> None:
    """Compute an artifact version string."""
    try:
        if scheme is None:
            # Output all schemes as JSON
            _emit_all_artifact_versions_json(
                version_override=version_override,
                is_full_release=is_full_release,
                prerelease_type=prerelease_type,
                prerelease_number=prerelease_number,
                build_number=build_number,
                alias_versions=alias_versions,
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


@release_app.command('tag')
def release_tag(
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
) -> None:
    """Create git tag(s) for a release and push them."""
    try:
        repo, _info = open_repo()
        fetch(repo, remote_name=remote)
        version = _resolve_release_version(
            repo_root=_info.root,
            version_override=version_override,
        )
        tags = compute_version_tags(version=version)
        selected = select_tags(tags=tags, aliases=alias_versions)
        exact_tags = selected[:1]
        alias_only_tags = selected[1:]

        create_tags(repo, tags=exact_tags, force=False)
        push_tags(repo, remote_name=remote, tags=exact_tags, force=False)

        if alias_only_tags:
            create_tags(repo, tags=alias_only_tags, force=True)
            push_tags(
                repo,
                remote_name=remote,
                tags=alias_only_tags,
                force=True,
            )
    except ReleezError as exc:
        typer.secho(str(exc), err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1) from exc

    for tag in selected:
        typer.echo(tag)


@release_app.command('preview')
def release_preview(
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
) -> None:
    """Preview the version and tags that would be published."""
    try:
        _repo, info = open_repo()
        version = _resolve_release_version(
            repo_root=info.root,
            version_override=version_override,
        )

        computed = compute_version_tags(version=version)
        tags = select_tags(tags=computed, aliases=alias_versions)

        markdown = '\n'.join(
            [
                '## `releez` release preview',
                '',
                f'- Version: `{version}`',
                '- Tags:',
                *[f'  - `{tag}`' for tag in tags],
                '',
            ],
        )

        if output is not None:
            output_path = Path(output)
            output_path.write_text(markdown, encoding='utf-8')
        else:
            typer.echo(markdown)
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


def _build_subprojects_list(settings: ReleezSettings) -> list[SubProject]:
    """Build list of SubProjects from settings.

    Args:
        settings: Releez settings with optional projects configuration.

    Returns:
        SubProject instances, or empty list for single-repo.
    """
    if not settings.projects:
        return []

    _, repo_info = open_repo()
    return [
        SubProject.from_config(
            config,
            repo_root=repo_info.root,
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
        subprojects = _build_subprojects_list(settings)

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
) -> None:
    """Generate the new changelog section for the release."""
    try:
        _, info = open_repo()
        version = _resolve_release_version(
            repo_root=info.root,
            version_override=version_override,
        )
        cliff = GitCliff(repo_root=info.root)
        notes = cliff.generate_unreleased_notes(version=version)

        if output is not None:
            output_path = Path(output)
            output_path.write_text(notes, encoding='utf-8')
        else:
            typer.echo(notes)
    except ReleezError as exc:
        typer.secho(str(exc), err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1) from exc


@projects_app.command('list')
def projects_list(ctx: typer.Context) -> None:
    """List all configured projects in the monorepo.

    Args:
        ctx: Typer context (injected automatically).
    """
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
    """Detect which projects have unreleased changes.

    Useful for CI/CD pipelines to determine which projects need releasing.

    Args:
        ctx: Typer context (injected automatically).
        format_output: Output format (text or json).
        base: Base branch to compare against.

    Raises:
        typer.Exit: If an error occurs.
    """
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
    """Show detailed information about a specific project.

    Args:
        ctx: Typer context (injected automatically).
        name: The project name.

    Raises:
        typer.Exit: If the project is not found.
    """
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


app.add_typer(release_app, name='release')
app.add_typer(version_app, name='version')
app.add_typer(changelog_app, name='changelog')
app.add_typer(projects_app, name='projects')


def main() -> None:
    """Main entry point for the CLI."""
    app()
