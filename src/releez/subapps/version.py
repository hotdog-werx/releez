from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Annotated

import typer

from releez.artifact_version import (
    ArtifactVersionInput,
    ArtifactVersionScheme,
    PrereleaseType,
    compute_artifact_version,
)
from releez.cli_utils import (
    _exit,
    _project_include_paths,
    _resolve_release_version,
)
from releez.git_repo import open_repo
from releez.utils import handle_releez_errors
from releez.version_tags import AliasVersions, compute_version_tags, select_tags

if TYPE_CHECKING:
    from releez.settings import ReleezSettings
    from releez.subproject import SubProject

version_app = typer.Typer(help='Version utilities for CI/artifacts.')


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
        msg = 'No projects configured. Remove --project or add [[tool.releez.projects]] to config.'
        raise _exit(msg)

    for project in subprojects:
        if project.name == project_name:
            return project

    available = ', '.join(sorted(p.name for p in subprojects))
    msg = f'Unknown project "{project_name}". Available: {available}'
    raise _exit(msg)


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
            msg = 'Monorepo projects are configured. Use --project <name> to specify which project to version.'
            raise _exit(msg)
        return '', version_override

    info = open_repo().info
    subprojects = settings.get_subprojects(repo_root=info.root)
    project = _find_project_for_artifact(
        subprojects=subprojects,
        project_name=project_name,
    )
    if version_override is None:
        version = _resolve_release_version(
            repo_root=info.root,
            version_override=None,
            tag_pattern=project.tag_pattern,
            include_paths=_project_include_paths(
                project=project,
                repo_root=info.root,
            ),
            tag_prefix=project.tag_prefix,
        )
        version_override = str(version)
    return project.tag_prefix, version_override


@version_app.command('artifact')
@handle_releez_errors
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
