from __future__ import annotations

import json
from typing import TYPE_CHECKING, Annotated

from cyclopts import App, Parameter
from pydantic import BaseModel

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
from releez.console import console, err_console
from releez.git_repo import open_repo
from releez.settings import ReleezSettings
from releez.utils import handle_releez_errors
from releez.version_tags import AliasVersions, compute_version_tags, select_tags

if TYPE_CHECKING:
    from releez.subproject import SubProject

version_app = App(name='version', help='Version utilities for CI/artifacts.')


class PrereleaseOptions(BaseModel):
    """Prerelease version options."""

    prerelease_type: Annotated[
        PrereleaseType,
        Parameter(
            help='Prerelease label (alpha, beta, rc).',
            show_default=True,
        ),
    ] = PrereleaseType.alpha
    prerelease_number: Annotated[
        int | None,
        Parameter(
            help='Optional prerelease number (e.g. PR number for alpha123).',
            show_default=False,
        ),
    ] = None
    build_number: Annotated[
        int | None,
        Parameter(
            help='Build number for prerelease builds.',
            show_default=False,
        ),
    ] = None


def _build_artifact_version_input(
    *,
    scheme: ArtifactVersionScheme,
    version_override: str | None,
    is_full_release: bool,
    prerelease: PrereleaseOptions,
) -> ArtifactVersionInput:
    return ArtifactVersionInput(
        scheme=scheme,
        version_override=version_override,
        is_full_release=is_full_release,
        prerelease_type=prerelease.prerelease_type,
        prerelease_number=prerelease.prerelease_number,
        build_number=prerelease.build_number,
    )


def _emit_all_artifact_versions_json(  # noqa: PLR0913
    *,
    version_override: str | None,
    is_full_release: bool,
    prerelease: PrereleaseOptions,
    alias_versions: AliasVersions,
    project_name: str | None = None,
    tag_prefix: str = '',
) -> None:
    result: dict[str, list[str] | str] = {}

    for scheme_value in ArtifactVersionScheme:
        artifact_input = _build_artifact_version_input(
            scheme=scheme_value,
            version_override=version_override,
            is_full_release=is_full_release,
            prerelease=prerelease,
        )
        artifact_version = compute_artifact_version(artifact_input)

        if scheme_value == ArtifactVersionScheme.pep440 or alias_versions == AliasVersions.none or not is_full_release:
            result[scheme_value.value] = [artifact_version]
        else:
            tags = compute_version_tags(version=artifact_version)
            result[scheme_value.value] = select_tags(
                tags=tags,
                aliases=alias_versions,
            )

    if project_name is not None and version_override is not None:
        result['release_version'] = f'{tag_prefix}{version_override}'
        result['project'] = project_name

    console.print(json.dumps(result, indent=2), markup=False)


def _emit_artifact_version_output(
    *,
    artifact_version: str,
    scheme: ArtifactVersionScheme,
    is_full_release: bool,
    alias_versions: AliasVersions,
) -> None:
    if scheme == ArtifactVersionScheme.pep440:
        if alias_versions != AliasVersions.none:
            err_console.print(
                'Note: --alias-versions is ignored for --scheme pep440.',
                style='yellow',
            )
        console.print(artifact_version, markup=False)
        return

    if alias_versions == AliasVersions.none:
        console.print(artifact_version, markup=False)
        return

    if not is_full_release:
        err_console.print(
            'Note: --alias-versions is only applied for full releases; ignoring because --is-full-release is not set.',
            style='yellow',
        )
        console.print(artifact_version, markup=False)
        return

    tags = compute_version_tags(version=artifact_version)
    for tag in select_tags(tags=tags, aliases=alias_versions):
        console.print(tag, markup=False)


def _find_project_for_artifact(
    *,
    subprojects: list[SubProject],
    project_name: str,
) -> SubProject:
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


@version_app.command
@handle_releez_errors
def artifact(  # noqa: PLR0913
    prerelease: Annotated[PrereleaseOptions, Parameter(name='*')] | None = None,
    *,
    scheme: Annotated[
        ArtifactVersionScheme | None,
        Parameter(
            '--scheme',
            help='Output scheme. If not specified, outputs all schemes as JSON.',
            show_default=False,
        ),
    ] = None,
    is_full_release: Annotated[
        bool,
        Parameter(
            help='If true, output a full release version without prerelease markers.',
            show_default=True,
        ),
    ] = False,
    version_override: Annotated[
        str | None,
        Parameter(
            '--version-override',
            help='Override version instead of computing via git-cliff.',
            show_default=False,
        ),
    ] = None,
    alias_versions: Annotated[
        AliasVersions | None,
        Parameter(
            '--alias-versions',
            help='Alias tags for full releases (major/minor). [default: from config alias-versions; fallback: none]',
            show_default=False,
        ),
    ] = None,
    project_name: Annotated[
        str | None,
        Parameter(
            '--project',
            help='Project name for monorepo version detection (monorepo only).',
            show_default=False,
        ),
    ] = None,
) -> None:
    """Compute an artifact version string."""
    if prerelease is None:
        prerelease = PrereleaseOptions()
    settings = ReleezSettings()
    resolved_alias_versions = alias_versions if alias_versions is not None else settings.alias_versions
    resolved_tag_prefix, resolved_version_override = _resolve_artifact_project_context(
        settings=settings,
        project_name=project_name,
        version_override=version_override,
    )

    if scheme is None:
        _emit_all_artifact_versions_json(
            version_override=resolved_version_override,
            is_full_release=is_full_release,
            prerelease=prerelease,
            alias_versions=resolved_alias_versions,
            project_name=project_name,
            tag_prefix=resolved_tag_prefix,
        )
        return

    artifact_input = _build_artifact_version_input(
        scheme=scheme,
        version_override=resolved_version_override,
        is_full_release=is_full_release,
        prerelease=prerelease,
    )
    artifact_version = compute_artifact_version(artifact_input)
    _emit_artifact_version_output(
        artifact_version=artifact_version,
        scheme=scheme,
        is_full_release=is_full_release,
        alias_versions=resolved_alias_versions,
    )
