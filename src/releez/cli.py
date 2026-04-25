from __future__ import annotations

from typing import Annotated

import typer

from releez import __version__
from releez.settings import ReleezSettings
from releez.subapps import (
    changelog_app,
    projects_app,
    release_app,
    validate_app,
    version_app,
)

app = typer.Typer(help='CLI tool for helping to manage release processes.')


def _version_callback(*, value: bool) -> None:
    """Print version and exit when --version flag is passed.

    Args:
        value: True if --version was passed.
    """
    if value:
        typer.echo(f'releez {__version__}')
        raise typer.Exit(0)


@app.callback()
def _root(
    ctx: typer.Context,
    *,
    _version: Annotated[
        bool,
        typer.Option(
            '--version',
            help="Show the application's version and exit.",
            callback=_version_callback,
            is_eager=True,
        ),
    ] = False,
) -> None:
    settings = ReleezSettings()
    ctx.obj = settings

    default_map: dict[str, object] = {}
    default_map['release'] = {
        'start': {
            'base': settings.base_branch,
            'remote': settings.git_remote,
            'labels': settings.pr_labels,
            'title_prefix': settings.pr_title_prefix,
            'changelog_path': settings.changelog_path,
            'create_pr': settings.create_pr,
            'run_changelog_format': settings.run_changelog_format,
            'changelog_format_cmd': settings.hooks.changelog_format,
            'maintenance_branch_regex': settings.effective_maintenance_branch_regex,
        },
        'tag': {
            'remote': settings.git_remote,
            'alias_versions': settings.alias_versions,
        },
        'preview': {
            'alias_versions': settings.alias_versions,
        },
    }
    default_map['version'] = {
        'artifact': {
            'alias_versions': settings.alias_versions,
        },
    }
    default_map['changelog'] = {
        'regenerate': {
            'changelog_path': settings.changelog_path,
            'run_changelog_format': settings.run_changelog_format,
            'changelog_format_cmd': settings.hooks.changelog_format,
        },
    }

    if ctx.default_map is None:
        ctx.default_map = default_map
    else:
        ctx.default_map = {
            **ctx.default_map,
            **default_map,
        }


app.add_typer(release_app, name='release')
app.add_typer(version_app, name='version')
app.add_typer(changelog_app, name='changelog')
app.add_typer(projects_app, name='projects')
app.add_typer(validate_app, name='validate')


def main() -> None:
    """Main entry point for the CLI."""
    app()
