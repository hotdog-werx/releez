from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import typer
from click.core import ParameterSource

from releez.cli_utils import (
    _exit,
    _project_include_paths,
    _resolve_release_version,
)
from releez.cliff import GitCliffBump  # noqa: TC001
from releez.git_repo import open_repo

if TYPE_CHECKING:
    from git import Repo
    from semver import VersionInfo

    from releez.settings import ReleezSettings
    from releez.subproject import SubProject
    from releez.version_tags import AliasVersions

release_app = typer.Typer(help='Release workflows (changelog + branch + PR).')


# ---------------------------------------------------------------------------
# Shared infrastructure
# ---------------------------------------------------------------------------


def _project_changelog_path(
    *,
    project: SubProject,
    repo_root: Path,
) -> str:
    return project.changelog_path.relative_to(repo_root).as_posix()


def _project_names_csv(projects: list[SubProject]) -> str:
    return ', '.join(project.name for project in projects)


def _resolve_target_projects(
    *,
    repo_root: Path,
    settings: ReleezSettings,
    project_names: list[str],
    all_projects: bool,
) -> list[SubProject] | None:
    """Resolve project targets for monorepo-aware commands.

    Returns None for single-repo mode, or a concrete project list in monorepo mode.
    """
    if not settings.is_monorepo:
        settings.validate_project_flags(
            project_names=project_names,
            all_projects=all_projects,
        )
        return None
    return settings.select_projects(
        repo_root=repo_root,
        project_names=project_names,
        all_projects=all_projects,
    )


@dataclass(frozen=True)
class _ResolvedProjectTargets:
    settings: ReleezSettings
    repo: Repo
    repo_root: Path
    target_projects: list[SubProject] | None
    active_branch: str | None = None


def _resolve_project_targets_for_command(
    *,
    ctx: typer.Context,
    project_names: list[str],
    all_projects: bool,
) -> _ResolvedProjectTargets:
    settings: ReleezSettings = ctx.obj
    ctx_repo = open_repo()
    repo, info = ctx_repo.repo, ctx_repo.info
    target_projects = _resolve_target_projects(
        repo_root=info.root,
        settings=settings,
        project_names=project_names,
        all_projects=all_projects,
    )
    return _ResolvedProjectTargets(
        settings=settings,
        repo=repo,
        repo_root=info.root,
        target_projects=target_projects,
        active_branch=info.active_branch,
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
    raise _exit(
        message=f'--version-override can only be used when {action_label} a single project.',
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
) -> VersionInfo:
    return _resolve_release_version(
        repo_root=repo_root,
        version_override=version_override,
        tag_pattern=project.tag_pattern,
        include_paths=_project_include_paths(
            project=project,
            repo_root=repo_root,
        ),
        tag_prefix=project.tag_prefix,
    )


def _project_semver_version(
    *,
    project: SubProject,  # noqa: ARG001
    version: VersionInfo,
) -> str:
    return str(version)


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


# ---------------------------------------------------------------------------
# Options dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _ReleaseStartOptions:
    bump: GitCliffBump
    version_override: str | None
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
