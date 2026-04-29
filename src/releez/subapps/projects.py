from __future__ import annotations

import json
from collections.abc import Sequence  # noqa: TC003
from typing import Annotated

from cyclopts import App, Parameter

from releez.console import console, err_console
from releez.git_repo import detect_changed_projects, open_repo
from releez.settings import ReleezSettings
from releez.subproject import SubProject  # noqa: TC001
from releez.utils import handle_releez_errors

projects_app = App(name='projects', help='Monorepo project utilities.')


def _output_changed_projects(
    changed: Sequence[SubProject],
    format_output: str,
) -> None:
    """Output changed projects in the requested format."""
    if format_output == 'json':
        output = {
            'projects': [p.name for p in changed],
            'include': [{'project': p.name} for p in changed],
        }
        console.print(json.dumps(output, indent=2), markup=False)
    elif not changed:
        console.print('No projects have unreleased changes.', style='green')
    else:
        console.print(
            f'Projects with unreleased changes ({len(changed)}):',
            style='bold blue',
        )
        for project in changed:
            console.print(f'  • {project.name}', markup=False)


@projects_app.command
def list() -> None:  # noqa: A001
    """List configured monorepo projects."""
    settings = ReleezSettings()

    if not settings.projects:
        console.print(
            'No projects configured. This is a single-repo setup.',
            style='yellow',
        )
        return

    console.print(
        f'Configured projects ({len(settings.projects)}):',
        style='bold blue',
    )
    for project_config in settings.projects:
        console.print(f'  • {project_config.name}', markup=False)
        console.print(f'    Path: {project_config.path}', markup=False)
        console.print(
            f'    Tag prefix: {project_config.tag_prefix or "(none)"}',
            markup=False,
        )
        console.print(
            f'    Changelog: {project_config.changelog_path}',
            markup=False,
        )
        if project_config.include_paths:
            console.print(
                f'    Include paths: {", ".join(project_config.include_paths)}',
                markup=False,
            )
        console.print('')


@projects_app.command
@handle_releez_errors
def changed(
    *,
    format_output: Annotated[
        str,
        Parameter(
            '--format',
            help='Output format: text or json.',
            show_default=True,
        ),
    ] = 'text',
    base: Annotated[
        str | None,
        Parameter(
            '--base',
            help='Base branch to compare against (defaults to configured base-branch).',
            show_default=False,
        ),
    ] = None,
) -> None:
    """Detect projects that have unreleased changes."""
    settings = ReleezSettings()

    if not settings.projects:
        err_console.print(
            'No projects configured. This is a single-repo setup.',
            style='yellow',
        )
        raise SystemExit(1)

    ctx_repo = open_repo()
    repo, info = ctx_repo.repo, ctx_repo.info
    base_branch = base or settings.base_branch

    subprojects = settings.get_subprojects(repo_root=info.root)
    changed_projects = detect_changed_projects(
        repo=repo,
        base_branch=base_branch,
        projects=subprojects,
    )
    _output_changed_projects(changed_projects, format_output)


@projects_app.command
def info(
    name: Annotated[str, Parameter(help='Project name.')],
) -> None:
    """Show configuration details for one project."""
    settings = ReleezSettings()

    if not settings.projects:
        err_console.print(
            'No projects configured. This is a single-repo setup.',
            style='yellow',
        )
        raise SystemExit(1)

    project_config = next(
        (p for p in settings.projects if p.name == name),
        None,
    )
    if not project_config:
        err_console.print(
            f'Project "{name}" not found.',
            style='bold red',
            markup=False,
        )
        available = ', '.join(p.name for p in settings.projects)
        err_console.print(f'Available projects: {available}', markup=False)
        raise SystemExit(1)

    console.print(
        f'Project: {project_config.name}',
        style='bold blue',
        markup=False,
    )
    console.print(f'  Path: {project_config.path}', markup=False)
    console.print(
        f'  Tag prefix: {project_config.tag_prefix or "(none)"}',
        markup=False,
    )
    console.print(f'  Changelog: {project_config.changelog_path}', markup=False)
    console.print(
        f'  Alias versions: {project_config.alias_versions or settings.alias_versions}',
        markup=False,
    )

    if project_config.include_paths:
        console.print('  Include paths:')
        for path in project_config.include_paths:
            console.print(f'    - {path}', markup=False)

    if project_config.hooks.post_changelog:
        console.print('  Post-changelog hooks:')
        for hook in project_config.hooks.post_changelog:
            console.print(f'    - {" ".join(hook)}', markup=False)
