from __future__ import annotations

from pathlib import Path  # noqa: TC003
from typing import TYPE_CHECKING, Annotated

import typer

if TYPE_CHECKING:
    from releez.settings import ReleezSettings
    from releez.subproject import SubProject

from releez.cliff import GitCliff
from releez.errors import ChangelogFormatCommandRequiredError
from releez.git_repo import open_repo
from releez.utils import (
    handle_releez_errors,
    resolve_changelog_path,
    run_changelog_formatter,
)

changelog_app = typer.Typer(help='Changelog utilities.')


def _run_changelog_formatter_with_message(
    *,
    changelog_path: Path,
    repo_root: Path,
    changelog_format_cmd: list[str],
) -> None:
    """Run the changelog formatter command and print success message."""
    run_changelog_formatter(
        changelog_path=changelog_path,
        repo_root=repo_root,
        changelog_format_cmd=changelog_format_cmd,
    )
    typer.secho(
        '✓ Ran changelog format hook',
        fg=typer.colors.GREEN,
    )


def _run_single_repo_regenerate(
    *,
    changelog_path: str,
    repo_root: Path,
    run_changelog_format: bool,
    changelog_format_cmd: list[str] | None,
) -> None:
    """Run changelog regeneration in single-repo mode."""
    changelog = resolve_changelog_path(changelog_path, repo_root)
    cliff = GitCliff(repo_root=repo_root)
    cliff.regenerate_changelog(changelog_path=changelog)
    typer.secho(f'✓ Regenerated changelog: {changelog}', fg=typer.colors.GREEN)
    if run_changelog_format and changelog_format_cmd:
        _run_changelog_formatter_with_message(
            changelog_path=changelog,
            repo_root=repo_root,
            changelog_format_cmd=changelog_format_cmd,
        )


def _run_project_regenerate(
    *,
    project: SubProject,
    repo_root: Path,
    run_changelog_format: bool,
    changelog_format_cmd: list[str] | None,
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
    if run_changelog_format and changelog_format_cmd:
        _run_changelog_formatter_with_message(
            changelog_path=project.changelog_path,
            repo_root=repo_root,
            changelog_format_cmd=changelog_format_cmd,
        )


@changelog_app.command('regenerate')
@handle_releez_errors
def changelog_regenerate(  # noqa: PLR0913
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
    run_changelog_format: Annotated[
        bool,
        typer.Option(
            '--run-changelog-format',
            help='Run the configured changelog formatter after regeneration.',
            show_default=True,
        ),
    ] = False,
    changelog_format_cmd: Annotated[
        list[str] | None,
        typer.Option(
            '--changelog-format-cmd',
            help='Override changelog format command argv (repeatable).',
            show_default=False,
        ),
    ] = None,
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

    if run_changelog_format and not changelog_format_cmd:
        raise ChangelogFormatCommandRequiredError

    ctx_repo = open_repo()
    repo_root = ctx_repo.info.root

    if not settings.is_monorepo:
        _run_single_repo_regenerate(
            changelog_path=changelog_path,
            repo_root=repo_root,
            run_changelog_format=run_changelog_format,
            changelog_format_cmd=changelog_format_cmd,
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
            run_changelog_format=run_changelog_format,
            changelog_format_cmd=changelog_format_cmd,
        )
