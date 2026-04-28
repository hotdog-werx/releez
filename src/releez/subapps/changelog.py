from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from cyclopts import App, Parameter

if TYPE_CHECKING:
    from pathlib import Path

    from releez.subproject import SubProject

from releez.cliff import GitCliff
from releez.console import console
from releez.git_repo import open_repo
from releez.settings import ReleezSettings
from releez.utils import (
    handle_releez_errors,
    resolve_changelog_path,
)

changelog_app = App(name='changelog', help='Changelog utilities.')


def _run_single_repo_regenerate(
    *,
    changelog_path: str,
    repo_root: Path,
) -> None:
    """Run changelog regeneration in single-repo mode."""
    changelog = resolve_changelog_path(changelog_path, repo_root)
    cliff = GitCliff(repo_root=repo_root)
    cliff.regenerate_changelog(changelog_path=changelog)
    console.print(f'✓ Regenerated changelog: {changelog}', style='green')


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
    console.print(
        f'✓ [{project.name}] Regenerated changelog: {project.changelog_path}',
        style='green',
    )


@changelog_app.command
@handle_releez_errors
def regenerate(
    *,
    changelog_path: Annotated[
        str | None,
        Parameter(
            '--changelog-path',
            help=(
                'Path to the changelog file (single-repo only). '
                '[default: from config changelog-path; fallback: CHANGELOG.md]'
            ),
            show_default=False,
        ),
    ] = None,
    project_names: Annotated[
        list[str],
        Parameter(
            '--project',
            help='Project name(s) to regenerate changelog for (repeatable, monorepo only).',
            show_default=False,
        ),
    ] = [],  # noqa: B006
    all_projects: Annotated[
        bool,
        Parameter(
            '--all',
            help='Regenerate changelog for all configured projects (monorepo only).',
            show_default=True,
        ),
    ] = False,
) -> None:
    """Regenerate the full changelog from git history."""
    settings = ReleezSettings()
    settings.validate_project_flags(
        project_names=project_names,
        all_projects=all_projects,
    )

    ctx_repo = open_repo()
    repo_root = ctx_repo.info.root

    # Apply config-backed default for changelog_path
    resolved_changelog_path: str = changelog_path if changelog_path is not None else settings.changelog_path

    if not settings.is_monorepo:
        _run_single_repo_regenerate(
            changelog_path=resolved_changelog_path,
            repo_root=repo_root,
        )
        return

    resolved = settings.select_projects(
        repo_root=repo_root,
        project_names=project_names,
        all_projects=all_projects,
    )
    for project in resolved:
        _run_project_regenerate(
            project=project,
            repo_root=repo_root,
        )
