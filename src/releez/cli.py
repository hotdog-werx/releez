from __future__ import annotations

from cyclopts import App

from releez import __version__
from releez.subapps import (
    changelog_app,
    projects_app,
    release_app,
    validate_app,
    version_app,
)

app = App(
    name='releez',
    help='CLI tool for helping to manage release processes.',
    version=f'releez {__version__}',
)
app.command(release_app)
app.command(version_app)
app.command(changelog_app)
app.command(projects_app)
app.command(validate_app)


def main() -> None:
    """Main entry point for the CLI."""
    app()
