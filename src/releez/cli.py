from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, cast

import typer
from semver import VersionInfo

from releez.artifact_version import (
    ArtifactVersionInput,
    ArtifactVersionScheme,
    PrereleaseType,
    compute_artifact_version,
)
from releez.cliff import GitCliff, GitCliffBump
from releez.errors import (
    ChangelogFormatCommandRequiredError,
    InvalidMaintenanceBranchRegexError,
    InvalidReleaseVersionError,
    MaintenanceBranchMajorMismatchError,
    ReleezError,
)
from releez.git_repo import create_tags, fetch, open_repo, push_tags
from releez.release import StartReleaseInput, start_release
from releez.settings import ReleezSettings
from releez.subapps import changelog_app
from releez.version_tags import AliasVersions, compute_version_tags, select_tags

app = typer.Typer(help='CLI tool for helping to manage release processes.')
release_app = typer.Typer(help='Release workflows (changelog + branch + PR).')
version_app = typer.Typer(help='Version utilities for CI/artifacts.')


@app.callback()
def _root(ctx: typer.Context) -> None:
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
            'maintenance_branch_regex': settings.maintenance_branch_regex,
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


def _maintenance_major(
    *,
    branch: str | None,
    regex: str,
) -> int | None:
    if branch is None:
        return None
    try:
        pattern = re.compile(regex)
    except re.error as exc:
        raise InvalidMaintenanceBranchRegexError(
            regex,
            reason=str(exc),
        ) from exc

    # Expect a named "major" capture group from the branch regex.
    match = pattern.match(branch)
    if not match:
        return None
    try:
        major_value = match.group('major')
    except IndexError as exc:
        raise InvalidMaintenanceBranchRegexError(
            regex,
            reason='missing named capture group "major"',
        ) from exc
    try:
        return int(major_value)
    except ValueError as exc:
        raise InvalidMaintenanceBranchRegexError(
            regex,
            reason=f'invalid major value {major_value!r}',
        ) from exc


def _maintenance_tag_pattern(major: int) -> str:
    return rf'^{major}\\.[0-9]+\\.[0-9]+$'


@dataclass(frozen=True)
class MaintenanceContext:
    """Context derived from branch naming for maintenance releases.

    Attributes:
        branch: Branch name used for detection (None if detached).
        major: Maintenance line major version, or None if not on a maintenance branch.
        tag_pattern: git-cliff tag regex for scoping versions on maintenance branches.
    """

    branch: str | None
    major: int | None
    tag_pattern: str | None

    @property
    def is_maintenance(self) -> bool:
        """Return True if the branch matches the maintenance pattern."""
        return self.major is not None

    def ensure_version_matches(self, version: VersionInfo) -> None:
        """Ensure a computed version does not escape the maintenance major."""
        if self.major is None:
            return
        if version.major != self.major:
            raise MaintenanceBranchMajorMismatchError(
                branch=self.branch or '<detached>',
                major=self.major,
                version=str(version),
            )


def _maintenance_context(
    *,
    branch: str | None,
    regex: str,
) -> MaintenanceContext:
    major = _maintenance_major(branch=branch, regex=regex)
    tag_pattern = _maintenance_tag_pattern(major) if major is not None else None
    return MaintenanceContext(
        branch=branch,
        major=major,
        tag_pattern=tag_pattern,
    )


@dataclass(frozen=True)
class _VersionArtifactArgs:
    """CLI arguments for the `version artifact` command."""

    scheme: ArtifactVersionScheme
    version_override: str | None
    is_full_release: bool
    prerelease_type: PrereleaseType
    prerelease_number: int | None
    build_number: int | None


@dataclass(frozen=True)
class _ReleaseStartContext:
    """Derived context for release start.

    Attributes:
        repo_root: Root directory of the repository.
        active_branch: Current branch name (None if detached).
        base_branch: Target base branch for the release PR.
        maintenance: Maintenance branch context for scoping versions.
        version_for_check: Precomputed version used for validation/confirmation.
    """

    repo_root: Path
    active_branch: str | None
    base_branch: str
    maintenance: MaintenanceContext
    version_for_check: VersionInfo | None


@dataclass(frozen=True)
class _ReleaseStartArgs:
    """CLI arguments for `release start`."""

    bump: GitCliffBump
    version_override: str | None
    base_branch: str
    maintenance_branch_regex: str
    dry_run: bool
    non_interactive: bool
    remote: str
    labels: str
    title_prefix: str
    changelog_path: str
    run_changelog_format: bool
    changelog_format_cmd: list[str] | None
    create_pr: bool
    github_token: str | None


def _build_artifact_version_input(
    *,
    args: _VersionArtifactArgs,
) -> ArtifactVersionInput:
    return ArtifactVersionInput(
        scheme=args.scheme,
        version_override=args.version_override,
        is_full_release=args.is_full_release,
        prerelease_type=args.prerelease_type,
        prerelease_number=args.prerelease_number,
        build_number=args.build_number,
    )


def _emit_artifact_version_output(
    *,
    artifact_version: str,
    scheme: ArtifactVersionScheme,
    is_full_release: bool,
    alias_versions: AliasVersions,
) -> None:
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
    bump: GitCliffBump = 'auto',
    tag_pattern: str | None = None,
) -> VersionInfo:
    """Resolve the release version, defaulting to git-cliff."""
    # Parse once here so callers get a validated VersionInfo.
    if version_override is not None:
        version = version_override
    else:
        cliff = GitCliff(repo_root=repo_root)
        version = cliff.compute_next_version(
            bump=bump,
            tag_pattern=tag_pattern,
        )
    try:
        return VersionInfo.parse(version)
    except ValueError as exc:
        raise InvalidReleaseVersionError(version) from exc


def _build_release_start_context(
    *,
    bump: GitCliffBump,
    version_override: str | None,
    base_branch: str,
    maintenance_branch_regex: str,
    dry_run: bool,
) -> _ReleaseStartContext:
    repo_context = open_repo()
    info = repo_context.info
    maintenance = _maintenance_context(
        branch=info.active_branch,
        regex=maintenance_branch_regex,
    )
    # Maintenance releases use the current branch as their base.
    active_branch = info.active_branch
    # Maintenance releases should target the current branch; fall back if detached.
    if maintenance.is_maintenance and active_branch is not None:
        resolved_base = active_branch
    else:
        resolved_base = base_branch

    version_for_check: VersionInfo | None = None
    # Compute a version whenever we need to validate or confirm.
    if maintenance.is_maintenance or not dry_run:
        version_for_check = _resolve_release_version(
            repo_root=info.root,
            version_override=version_override,
            bump=bump,
            tag_pattern=maintenance.tag_pattern,
        )

    if version_for_check is not None:
        maintenance.ensure_version_matches(version_for_check)

    return _ReleaseStartContext(
        repo_root=info.root,
        active_branch=info.active_branch,
        base_branch=resolved_base,
        maintenance=maintenance,
        version_for_check=version_for_check,
    )


def _confirm_release_start(
    *,
    context: _ReleaseStartContext,
    create_pr: bool,
    changelog_path: str,
    run_changelog_format: bool,
) -> None:
    if context.version_for_check is None:
        return
    release_branch = f'release/{context.version_for_check}'
    typer.echo('Release confirmation:')
    typer.echo(f'- Current branch: {context.active_branch or "detached"}')
    typer.echo(f'- Base branch: {context.base_branch}')
    typer.echo(f'- Release version: {context.version_for_check}')
    typer.echo(f'- Release branch: {release_branch}')
    typer.echo(f'- Create PR: {create_pr}')
    typer.echo(f'- Changelog path: {changelog_path}')
    typer.echo(f'- Run changelog format: {run_changelog_format}')
    if not typer.confirm('Proceed with release?', default=False):
        typer.secho('Release cancelled.', err=True, fg=typer.colors.YELLOW)
        raise typer.Exit(code=1)


def _prepare_release_start_input(
    *,
    args: _ReleaseStartArgs,
) -> StartReleaseInput:
    if args.run_changelog_format and not args.changelog_format_cmd:
        raise ChangelogFormatCommandRequiredError

    context = _build_release_start_context(
        bump=args.bump,
        version_override=args.version_override,
        base_branch=args.base_branch,
        maintenance_branch_regex=args.maintenance_branch_regex,
        dry_run=args.dry_run,
    )

    if not args.dry_run and not args.non_interactive:
        _confirm_release_start(
            context=context,
            create_pr=args.create_pr,
            changelog_path=args.changelog_path,
            run_changelog_format=args.run_changelog_format,
        )

    effective_version_override = args.version_override
    if not args.dry_run and effective_version_override is None and context.version_for_check is not None:
        effective_version_override = str(context.version_for_check)

    return StartReleaseInput(
        bump=args.bump,
        version_override=effective_version_override,
        base_branch=context.base_branch,
        remote_name=args.remote,
        labels=args.labels.split(',') if args.labels else [],
        title_prefix=args.title_prefix,
        changelog_path=args.changelog_path,
        run_changelog_format=args.run_changelog_format,
        changelog_format_cmd=args.changelog_format_cmd,
        create_pr=args.create_pr,
        github_token=args.github_token,
        dry_run=args.dry_run,
        tag_pattern=context.maintenance.tag_pattern,
    )


@release_app.command('start')
def release_start(  # noqa: PLR0913
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
            help='Run the configured changelog formatter before committing.',
            show_default=True,
        ),
    ] = False,
    changelog_format_cmd: Annotated[
        list[str] | None,
        typer.Option(
            '--changelog-format-cmd',
            help='Override changelog format command argv (repeatable).',
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
    non_interactive: Annotated[
        bool,
        typer.Option(
            '--non-interactive',
            help='Disable confirmation prompts (useful for CI).',
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
    maintenance_branch_regex: Annotated[
        str,
        typer.Option(
            '--maintenance-branch-regex',
            help='Regex to detect maintenance branches (must include a named "major" capture).',
            show_default=True,
        ),
    ] = r'^support/(?P<major>\d+)\.x$',
) -> None:
    """Start a release branch and update the changelog.

    Computes the next version using git-cliff, prepends the changelog, commits and pushes a
    `release/<version>` branch, and optionally opens a GitHub PR.

    Args:
        bump: Bump mode for git-cliff.
        version_override: Override the computed next version.
        run_changelog_format: If true, run the configured changelog formatter before commit.
        changelog_format_cmd: Override the configured changelog formatter argv.
        create_pr: If true, create a GitHub pull request.
        dry_run: If true, do not modify the repo; just output version and notes.
        non_interactive: If true, skip confirmation prompts.
        base: Base branch for the release PR.
        remote: Remote name to use.
        labels: Comma-separated labels to add to the PR.
        title_prefix: Prefix for PR title.
        changelog_path: Changelog file to prepend to.
        github_token: GitHub token for PR creation.
        maintenance_branch_regex: Regex for detecting maintenance branches.

    Raises:
        typer.Exit: If an error occurs during release processing.
    """
    try:
        release_args = _ReleaseStartArgs(
            bump=bump,
            version_override=version_override,
            base_branch=base,
            maintenance_branch_regex=maintenance_branch_regex,
            dry_run=dry_run,
            non_interactive=non_interactive,
            remote=remote,
            labels=labels,
            title_prefix=title_prefix,
            changelog_path=changelog_path,
            run_changelog_format=run_changelog_format,
            changelog_format_cmd=changelog_format_cmd,
            create_pr=create_pr,
            github_token=github_token,
        )
        release_input = _prepare_release_start_input(args=release_args)
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
        ArtifactVersionScheme,
        typer.Option(
            '--scheme',
            help='Output scheme for the artifact version.',
            show_default=True,
            case_sensitive=False,
        ),
    ] = ArtifactVersionScheme.semver,
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
) -> None:
    """Create git tag(s) for a release and push them."""
    try:
        settings = cast('ReleezSettings', ctx.obj)
        repo_context = open_repo()
        repo = repo_context.repo
        info = repo_context.info
        maintenance = _maintenance_context(
            branch=info.active_branch,
            regex=settings.maintenance_branch_regex,
        )
        fetch(repo, remote_name=remote)
        version = _resolve_release_version(
            repo_root=info.root,
            version_override=version_override,
            tag_pattern=maintenance.tag_pattern,
        )
        maintenance.ensure_version_matches(version)
        tags = compute_version_tags(version=str(version))
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
) -> None:
    """Preview the version and tags that would be published."""
    try:
        settings = cast('ReleezSettings', ctx.obj)
        repo_context = open_repo()
        info = repo_context.info
        maintenance = _maintenance_context(
            branch=info.active_branch,
            regex=settings.maintenance_branch_regex,
        )
        version = _resolve_release_version(
            repo_root=info.root,
            version_override=version_override,
            tag_pattern=maintenance.tag_pattern,
        )
        maintenance.ensure_version_matches(version)

        computed = compute_version_tags(version=str(version))
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
) -> None:
    """Generate the new changelog section for the release."""
    try:
        settings = cast('ReleezSettings', ctx.obj)
        repo_context = open_repo()
        info = repo_context.info
        maintenance = _maintenance_context(
            branch=info.active_branch,
            regex=settings.maintenance_branch_regex,
        )
        version = _resolve_release_version(
            repo_root=info.root,
            version_override=version_override,
            tag_pattern=maintenance.tag_pattern,
        )
        maintenance.ensure_version_matches(version)
        cliff = GitCliff(repo_root=info.root)
        notes = cliff.generate_unreleased_notes(
            version=str(version),
            tag_pattern=maintenance.tag_pattern,
        )

        if output is not None:
            output_path = Path(output)
            output_path.write_text(notes, encoding='utf-8')
        else:
            typer.echo(notes)
    except ReleezError as exc:
        typer.secho(str(exc), err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1) from exc


app.add_typer(release_app, name='release')
app.add_typer(version_app, name='version')
app.add_typer(changelog_app, name='changelog')


def main() -> None:
    """Main entry point for the CLI."""
    app()
