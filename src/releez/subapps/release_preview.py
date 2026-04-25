from __future__ import annotations

from pathlib import Path  # noqa: TC003
from typing import TYPE_CHECKING, Annotated

import typer

from releez.cli_utils import _resolve_release_version
from releez.subapps.release import (
    _alias_versions_for_project,
    _emit_or_write_output,
    _normalize_project_names,
    _project_semver_version,
    _ReleasePreviewOptions,
    _require_single_project_override_scope,
    _resolve_project_release_version,
    _resolve_project_targets_for_command,
    release_app,
)
from releez.subapps.release_maintenance import _maintenance_context
from releez.utils import handle_releez_errors
from releez.version_tags import AliasVersions, compute_version_tags, select_tags

if TYPE_CHECKING:
    from releez.subproject import SubProject


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
