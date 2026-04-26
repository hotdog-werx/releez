from __future__ import annotations

from pathlib import Path  # noqa: TC003
from typing import TYPE_CHECKING, Annotated

import typer

if TYPE_CHECKING:
    from releez.settings import ReleezSettings
    from releez.subproject import SubProject

from releez.cliff import GitCliff
from releez.git_repo import open_repo
from releez.utils import (
    handle_releez_errors,
    resolve_changelog_path,
)

changelog_app = typer.Typer(help='Changelog utilities.')


def _run_single_repo_regenerate(
    *,
    changelog_path: str,
    repo_root: Path,
) -> None:
    """Run changelog regeneration in single-repo mode."""
    changelog = resolve_changelog_path(changelog_path, repo_root)
    cliff = GitCliff(repo_root=repo_root)
    cliff.regenerate_changelog(changelog_path=changelog)
    typer.secho(f'✓ Regenerated changelog: {changelog}', fg=typer.colors.GREEN)


def _run_project_regenerate(
    *,
    project: SubProject,
    repo_root: Path,
) -> None:
    """Regenerate changelog for a single project."""
    cliff = GitCliff(repo_root=repo_root)
    cliff.regenerate_changelog(
        changelog_path=project.changelog_path,
        tag_pattern=project.tag_pattern,
        include_paths=project.include_paths,
    )
    typer.secho(
        f'✓ [{project.name}] Regenerated changelog: {project.changelog_path}',
        fg=typer.colors.GREEN,
    )


@changelog_app.command('regenerate')
@handle_releez_errors
def changelog_regenerate(
    ctx: typer.Context,
    *,
    changelog_path: Annotated[
        str,
        typer.Option(
            '--changelog-path',
            help='Path to the changelog file (single-repo only).',
            show_default=True,
        ),
    ] = 'CHANGELOG.md',
    project_names: Annotated[
        list[str] | None,
        typer.Option(
            '--project',
            help='Project name(s) to regenerate changelog for (repeatable, monorepo only).',
            show_default=False,
        ),
    ] = None,
    all_projects: Annotated[
        bool,
        typer.Option(
            '--all',
            help='Regenerate changelog for all configured projects (monorepo only).',
            show_default=True,
        ),
    ] = False,
) -> None:
    """Regenerate the full changelog from git history."""
    settings: ReleezSettings = ctx.obj
    settings.validate_project_flags(
        project_names=project_names or [],
        all_projects=all_projects,
    )

    ctx_repo = open_repo()
    repo_root = ctx_repo.info.root

    if not settings.is_monorepo:
        _run_single_repo_regenerate(
            changelog_path=changelog_path,
            repo_root=repo_root,
        )
        return

    resolved = settings.select_projects(
        repo_root=repo_root,
        project_names=project_names or [],
        all_projects=all_projects,
    )
    for project in resolved:
        _run_project_regenerate(
            project=project,
            repo_root=repo_root,
        )
