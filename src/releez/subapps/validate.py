from __future__ import annotations

from typing import Annotated

import typer

from releez.cliff import GitCliff
from releez.git_repo import open_repo

validate_app = typer.Typer(
    help='Validate commit messages against cliff.toml rules.',
)


@validate_app.command('commit-message')
def validate_commit_message(
    message: Annotated[str, typer.Argument(help='Commit message to validate.')],
) -> None:
    """Check if a commit message matches a configured commit parser.

    Exits 0 if valid, 1 if the message does not match any parser.
    Useful for validating PR titles before merge.
    """
    repo_info = open_repo().info
    result = GitCliff(repo_root=repo_info.root).validate_commit_message(message)
    if result.valid:
        typer.secho(f'✓ {result.reason}', fg=typer.colors.GREEN)
    else:
        typer.secho(f'✗ {result.reason}', err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1)
