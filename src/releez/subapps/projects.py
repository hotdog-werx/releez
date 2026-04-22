from __future__ import annotations

import json
from typing import TYPE_CHECKING, Annotated

import typer

from releez.git_repo import detect_changed_projects, open_repo
from releez.utils import handle_releez_errors

if TYPE_CHECKING:
    from releez.settings import ReleezSettings
    from releez.subproject import SubProject

projects_app = typer.Typer(help='Monorepo project utilities.')


def _output_changed_projects(
    changed: list[SubProject],
    format_output: str,
) -> None:
    """Output changed projects in the requested format.

    Args:
        changed: Projects with unreleased changes.
        format_output: Output format, "json" or "text".
    """
    if format_output == 'json':
        # include key matches GitHub Actions matrix strategy format
        output = {
            'projects': [p.name for p in changed],
            'include': [{'project': p.name} for p in changed],
        }
        typer.echo(json.dumps(output, indent=2))
    elif not changed:
        typer.secho(
            'No projects have unreleased changes.',
            fg=typer.colors.GREEN,
        )
    else:
        typer.secho(
            f'Projects with unreleased changes ({len(changed)}):',
            fg=typer.colors.BLUE,
            bold=True,
        )
        for project in changed:
            typer.echo(f'  • {project.name}')


@projects_app.command('list')
def projects_list(ctx: typer.Context) -> None:
    """List configured monorepo projects."""
    settings: ReleezSettings = ctx.obj

    if not settings.projects:
        typer.secho(
            'No projects configured. This is a single-repo setup.',
            fg=typer.colors.YELLOW,
        )
        return

    typer.secho(
        f'Configured projects ({len(settings.projects)}):',
        fg=typer.colors.BLUE,
        bold=True,
    )
    for project_config in settings.projects:
        typer.echo(f'  • {project_config.name}')
        typer.echo(f'    Path: {project_config.path}')
        typer.echo(f'    Tag prefix: {project_config.tag_prefix or "(none)"}')
        typer.echo(f'    Changelog: {project_config.changelog_path}')
        if project_config.include_paths:
            typer.echo(
                f'    Include paths: {", ".join(project_config.include_paths)}',
            )
        typer.echo()


@projects_app.command('changed')
@handle_releez_errors
def projects_changed(
    ctx: typer.Context,
    *,
    format_output: Annotated[
        str,
        typer.Option(
            '--format',
            help='Output format: text or json',
            show_default=True,
        ),
    ] = 'text',
    base: Annotated[
        str | None,
        typer.Option(
            '--base',
            help='Base branch to compare against (defaults to configured base-branch)',
            show_default=False,
        ),
    ] = None,
) -> None:
    """Detect projects that have unreleased changes."""
    settings: ReleezSettings = ctx.obj

    if not settings.projects:
        typer.secho(
            'No projects configured. This is a single-repo setup.',
            err=True,
            fg=typer.colors.YELLOW,
        )
        raise typer.Exit(code=1)

    ctx_repo = open_repo()
    repo, info = ctx_repo.repo, ctx_repo.info
    base_branch = base or settings.base_branch

    subprojects = settings.get_subprojects(repo_root=info.root)

    changed = detect_changed_projects(
        repo=repo,
        base_branch=base_branch,
        projects=subprojects,
    )
    _output_changed_projects(changed, format_output)


@projects_app.command('info')
def projects_info(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument(help='Project name')],
) -> None:
    """Show configuration details for one project."""
    settings: ReleezSettings = ctx.obj

    if not settings.projects:
        typer.secho(
            'No projects configured. This is a single-repo setup.',
            err=True,
            fg=typer.colors.YELLOW,
        )
        raise typer.Exit(code=1)

    # Find the project
    project_config = next(
        (p for p in settings.projects if p.name == name),
        None,
    )
    if not project_config:
        typer.secho(
            f'Project "{name}" not found.',
            err=True,
            fg=typer.colors.RED,
        )
        available = ', '.join(p.name for p in settings.projects)
        typer.secho(f'Available projects: {available}', err=True)
        raise typer.Exit(code=1)

    # Display detailed info
    typer.secho(
        f'Project: {project_config.name}',
        fg=typer.colors.BLUE,
        bold=True,
    )
    typer.echo(f'  Path: {project_config.path}')
    typer.echo(f'  Tag prefix: {project_config.tag_prefix or "(none)"}')
    typer.echo(f'  Changelog: {project_config.changelog_path}')
    typer.echo(
        f'  Alias versions: {project_config.alias_versions or settings.alias_versions}',
    )

    if project_config.include_paths:
        typer.echo('  Include paths:')
        for path in project_config.include_paths:
            typer.echo(f'    - {path}')

    if project_config.hooks.post_changelog:
        typer.echo('  Post-changelog hooks:')
        for hook in project_config.hooks.post_changelog:
            typer.echo(f'    - {" ".join(hook)}')
