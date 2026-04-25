from __future__ import annotations

from pathlib import Path  # noqa: TC003
from typing import TYPE_CHECKING, Annotated

import typer

from releez.cli_utils import (
    _resolve_release_version,
)
from releez.git_repo import (
    create_tags,
    fetch,
    push_tags,
)
from releez.subapps.release import (
    _alias_versions_for_project,
    _normalize_project_names,
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
