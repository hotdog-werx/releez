from __future__ import annotations

from pathlib import Path  # noqa: TC003
from typing import TYPE_CHECKING, Annotated

from cyclopts import Parameter

from releez.cli_utils import _resolve_release_version
from releez.settings import ReleezSettings
from releez.subapps.release import (
    ProjectSelection,
    _alias_versions_for_project,
    _emit_or_write_output,
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
        aliases=options.alias_versions or AliasVersions.none,
    )
    lines = ['## `releez` release preview', '']
    lines.extend(
        _render_preview_section(title=None, version=version_str, tags=tags),
    )
    return '\n'.join(lines)


def _build_release_preview_markdown_monorepo(
    *,
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
    settings: ReleezSettings,
    options: _ReleasePreviewOptions,
    project_names: list[str],
    all_projects: bool,
) -> None:
    resolved = _resolve_project_targets_for_command(
        settings=settings,
        project_names=project_names,
        all_projects=all_projects,
    )
    _require_single_project_override_scope(
        version_override=options.version_override,
        target_projects=resolved.target_projects,
        action_label='previewing',
    )

    resolved_options = options.resolve(settings)
    maintenance_ctx = _maintenance_context(
        branch=resolved.active_branch,
        regex=settings.effective_maintenance_branch_regex,
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
            options=resolved_options,
            repo_root=resolved.repo_root,
            tag_pattern=tag_pattern,
        )
    else:
        markdown = _build_release_preview_markdown_monorepo(
            options=options,  # raw options: per-project alias_versions fallback applies
            repo_root=resolved.repo_root,
            projects=resolved.target_projects,
        )

    _emit_or_write_output(output=options.output, content=markdown)


@release_app.command
@handle_releez_errors
def preview(
    options: Annotated[_ReleasePreviewOptions, Parameter(name='*')] | None = None,
    selection: Annotated[ProjectSelection, Parameter(name='*')] | None = None,
) -> None:
    """Preview the version and tags that would be published."""
    if options is None:
        options = _ReleasePreviewOptions()
    if selection is None:
        selection = ProjectSelection()
    settings = ReleezSettings()
    _run_release_preview_command(
        settings=settings,
        options=options,
        project_names=selection.project_names,
        all_projects=selection.all_projects,
    )
