from dataclasses import dataclass
from typing import Annotated

import typer

from releez.artifact_version import (
    ArtifactVersionInput,
    ArtifactVersionScheme,
    PrereleaseType,
    compute_artifact_version,
)
from releez.cliff import GitCliffBump
from releez.errors import AliasTagsRequireFullReleaseError, ReleezError
from releez.git_repo import create_tags, open_repo, push_tags
from releez.release import StartReleaseInput, start_release
from releez.version_tags import AliasTags, compute_version_tags, select_tags

app = typer.Typer(help='CLI tool for helping to manage release processes.')
release_app = typer.Typer(help='Release workflows (changelog + branch + PR).')
version_app = typer.Typer(help='Version utilities for CI/artifacts.')


@app.callback()
def _root() -> None:
    return


@dataclass(frozen=True)
class _VersionArtifactArgs:
    """CLI arguments for the `version artifact` command."""

    scheme: ArtifactVersionScheme
    next_version_override: str | None
    is_full_release: bool
    prerelease_type: PrereleaseType
    prerelease_number: int | None
    build_number: int | None


def _build_artifact_version_input(
    *,
    args: _VersionArtifactArgs,
) -> ArtifactVersionInput:
    return ArtifactVersionInput(
        scheme=args.scheme,
        next_version_override=args.next_version_override,
        is_full_release=args.is_full_release,
        prerelease_type=args.prerelease_type,
        prerelease_number=args.prerelease_number,
        build_number=args.build_number,
    )


def _emit_artifact_version_output(
    *,
    artifact_version: str,
    is_full_release: bool,
    alias_tags: AliasTags,
    v_prefix: bool,
) -> None:
    if alias_tags == AliasTags.none:
        typer.echo(artifact_version)
        return

    if not is_full_release:
        raise AliasTagsRequireFullReleaseError

    prefix = 'v' if v_prefix else ''
    tags = compute_version_tags(version=artifact_version, prefix=prefix)
    for tag in select_tags(tags=tags, aliases=alias_tags):
        typer.echo(tag)


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
    create_pr: Annotated[
        bool,
        typer.Option(
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
            envvar='RELEEZ_BASE_BRANCH',
            help='Base branch for the release PR.',
            show_default=True,
        ),
    ] = 'master',
    remote: Annotated[
        str,
        typer.Option(
            envvar='RELEEZ_GIT_REMOTE',
            help='Remote name to use.',
            show_default=True,
        ),
    ] = 'origin',
    labels: Annotated[
        str,
        typer.Option(
            envvar='RELEEZ_PR_LABELS',
            help='Comma-separated label(s) to add to the PR (repeatable).',
            show_default=True,
        ),
    ] = 'release',
    title_prefix: Annotated[
        str,
        typer.Option(
            envvar='RELEEZ_PR_TITLE_PREFIX',
            help='Prefix for PR title.',
            show_default=True,
        ),
    ] = 'chore(release): ',
    changelog: Annotated[
        str,
        typer.Option(
            envvar='RELEEZ_CHANGELOG_PATH',
            help='Changelog file to prepend to.',
            show_default=True,
        ),
    ] = 'CHANGELOG.md',
    github_token: Annotated[
        str | None,
        typer.Option(
            envvar='GITHUB_TOKEN',
            help='GitHub token for PR creation (or set GITHUB_TOKEN).',
            show_default=False,
        ),
    ] = None,
) -> None:
    """Start a release branch and update the changelog.

    Computes the next version using git-cliff, prepends the changelog, commits and pushes a
    `release/<version>` branch, and optionally opens a GitHub PR.

    Args:
        bump: Bump mode for git-cliff.
        create_pr: If true, create a GitHub pull request.
        dry_run: If true, do not modify the repo; just output version and notes.
        base: Base branch for the release PR.
        remote: Remote name to use.
        labels: Comma-separated labels to add to the PR.
        title_prefix: Prefix for PR title.
        changelog: Changelog file to prepend to.
        github_token: GitHub token for PR creation.

    Raises:
        typer.Exit: If an error occurs during release processing.
    """
    try:
        release_input = StartReleaseInput(
            bump=bump,
            base_branch=base,
            remote_name=remote,
            labels=labels.split(',') if labels else [],
            title_prefix=title_prefix,
            changelog_path=changelog,
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
        ArtifactVersionScheme,
        typer.Option(
            help='Output scheme for the artifact version.',
            show_default=True,
            case_sensitive=False,
        ),
    ] = ArtifactVersionScheme.docker,
    is_full_release: Annotated[
        bool,
        typer.Option(
            envvar=[
                'RELEEZ_IS_FULL_RELEASE',
                'RELEEZE_IS_FULL_RELEASE',
                'IS_RELEASE_BUILD',
            ],
            help='If true, output a full release version without prerelease markers.',
            show_default=True,
        ),
    ] = False,
    prerelease_type: Annotated[
        PrereleaseType,
        typer.Option(
            envvar=[
                'RELEEZ_PRERELEASE_TYPE',
                'RELEEZE_PRERELEASE_TYPE',
                'PRERELEASE_TYPE',
            ],
            help='Prerelease label (alpha, beta, rc).',
            show_default=True,
            case_sensitive=False,
        ),
    ] = PrereleaseType.alpha,
    prerelease_number: Annotated[
        int | None,
        typer.Option(
            envvar=[
                'RELEEZ_PRERELEASE_NUMBER',
                'RELEEZE_PRERELEASE_NUMBER',
            ],
            help='Optional prerelease number (e.g. PR number for alpha123).',
            show_default=False,
        ),
    ] = None,
    build_number: Annotated[
        int | None,
        typer.Option(
            envvar=['RELEEZ_BUILD_NUMBER', 'BUILD_NUMBER'],
            help='Build number for prerelease builds.',
            show_default=False,
        ),
    ] = None,
    next_version_override: Annotated[
        str | None,
        typer.Option(
            '--next-version-override',
            '--next-version',
            envvar=[
                'RELEEZ_NEXT_VERSION_OVERRIDE',
                'NEXT_VERSION',
                '__GIT_CLIFF_NEXT_VERSION',
            ],
            help='Override next version instead of computing via git-cliff.',
            show_default=False,
        ),
    ] = None,
    alias_tags: Annotated[
        AliasTags,
        typer.Option(
            '--alias-tags',
            help='For full releases, also output major/minor tags.',
            show_default=True,
            case_sensitive=False,
        ),
    ] = AliasTags.none,
    v_prefix: Annotated[
        bool,
        typer.Option(
            '--v-prefix/--no-v-prefix',
            help='Prefix alias tags with `v` (v2, v2.3).',
            show_default=True,
        ),
    ] = True,
) -> None:
    """Compute an artifact version string."""
    try:
        artifact_args = _VersionArtifactArgs(
            scheme=scheme,
            next_version_override=next_version_override,
            is_full_release=is_full_release,
            prerelease_type=prerelease_type,
            prerelease_number=prerelease_number,
            build_number=build_number,
        )
        artifact_input = _build_artifact_version_input(args=artifact_args)
        artifact_version = compute_artifact_version(artifact_input)
        _emit_artifact_version_output(
            artifact_version=artifact_version,
            is_full_release=is_full_release,
            alias_tags=alias_tags,
            v_prefix=v_prefix,
        )
    except ReleezError as exc:
        typer.secho(str(exc), err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1) from exc


@release_app.command('tag')
def release_tag(
    *,
    version: Annotated[
        str,
        typer.Option(
            '--version',
            help='Full release version to tag (x.y.z).',
            show_default=False,
        ),
    ],
    alias_tags: Annotated[
        AliasTags,
        typer.Option(
            '--alias-tags',
            help='Also create major/minor tags (v2, v2.3).',
            show_default=True,
            case_sensitive=False,
        ),
    ] = AliasTags.none,
    v_prefix: Annotated[
        bool,
        typer.Option(
            '--v-prefix/--no-v-prefix',
            help='Prefix alias tags with `v` (v2, v2.3).',
            show_default=True,
        ),
    ] = True,
    remote: Annotated[
        str,
        typer.Option(
            '--remote',
            help='Remote to push tags to.',
            show_default=True,
        ),
    ] = 'origin',
    force: Annotated[
        bool,
        typer.Option(
            '--force',
            help='Overwrite existing tags (required to move tags like v2).',
            show_default=True,
        ),
    ] = False,
) -> None:
    """Create git tag(s) for a release and push them."""
    try:
        repo, _info = open_repo()
        prefix = 'v' if v_prefix else ''
        tags = compute_version_tags(version=version, prefix=prefix)
        selected = select_tags(tags=tags, aliases=alias_tags)
        create_tags(repo, tags=selected, force=force)
        push_tags(
            repo,
            remote_name=remote,
            tags=selected,
            force=force,
        )
    except ReleezError as exc:
        typer.secho(str(exc), err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1) from exc

    for tag in selected:
        typer.echo(tag)


def main() -> None:
    """Main entry point for the CLI."""
    app()


app.add_typer(release_app, name='release')
app.add_typer(version_app, name='version')
