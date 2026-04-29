from __future__ import annotations

from pathlib import Path  # noqa: TC003
from typing import TYPE_CHECKING, Annotated

from cyclopts import Parameter

from releez.cli_utils import _resolve_release_version
from releez.console import console
from releez.git_repo import create_tags, fetch, push_tags
from releez.settings import ReleezSettings
from releez.subapps.release import (
    ProjectSelection,
    _alias_versions_for_project,
    _project_semver_version,
    _ReleaseTagOptions,
    _require_single_project_override_scope,
    _resolve_project_release_version,
    _resolve_project_targets_for_command,
    release_app,
)
from releez.subapps.release_maintenance import (
    _maintenance_context,
    _validate_maintenance_version,
)
from releez.utils import handle_releez_errors
from releez.version_tags import AliasVersions, compute_version_tags, select_tags

if TYPE_CHECKING:
    from git import Repo

    from releez.subproject import SubProject


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
    push_tags(repo, remote_name=remote, tags=alias_only_tags, force=True)


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
    return select_tags(
        tags=tags,
        aliases=options.alias_versions or AliasVersions.none,
    )


def _selected_tags_for_project(
    *,
    repo_root: Path,
    options: _ReleaseTagOptions,
    project: SubProject,
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
        console.print(f'{prefix}{tag}', markup=False)


def _run_release_tag_command(
    *,
    settings: ReleezSettings,
    options: _ReleaseTagOptions,
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
        action_label='tagging',
    )

    resolved_options = options.resolve(settings)
    effective_remote = resolved_options.remote or settings.git_remote
    maintenance_ctx = _maintenance_context(
        branch=resolved.active_branch,
        regex=settings.effective_maintenance_branch_regex,
    )
    fetch(resolved.repo, remote_name=effective_remote)
    if resolved.target_projects is None:
        selected = _selected_tags_for_single_repo(
            repo_root=resolved.repo_root,
            options=resolved_options,
            tag_pattern=maintenance_ctx.tag_pattern if maintenance_ctx else None,
        )
        if maintenance_ctx:
            _validate_maintenance_version(
                version=selected[0],
                maintenance_ctx=maintenance_ctx,
            )
        _create_and_push_selected_tags(
            repo=resolved.repo,
            remote=effective_remote,
            selected_tags=selected,
        )
        _emit_tags(selected_tags=selected)
        return

    for project in resolved.target_projects:
        selected = _selected_tags_for_project(
            repo_root=resolved.repo_root,
            options=options,  # raw options: per-project alias_versions fallback applies
            project=project,
        )
        _create_and_push_selected_tags(
            repo=resolved.repo,
            remote=effective_remote,
            selected_tags=selected,
        )
        _emit_tags(selected_tags=selected, project_name=project.name)


@release_app.command
@handle_releez_errors
def tag(
    options: Annotated[_ReleaseTagOptions, Parameter(name='*')] | None = None,
    selection: Annotated[ProjectSelection, Parameter(name='*')] | None = None,
) -> None:
    """Tag a release commit and push the tags to the remote."""
    if options is None:
        options = _ReleaseTagOptions()
    if selection is None:
        selection = ProjectSelection()
    settings = ReleezSettings()
    _run_release_tag_command(
        settings=settings,
        options=options,
        project_names=selection.project_names,
        all_projects=selection.all_projects,
    )
