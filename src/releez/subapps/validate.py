from __future__ import annotations

from cyclopts import App

from releez.cliff import GitCliff
from releez.console import console, err_console
from releez.git_repo import open_repo

validate_app = App(
    name='validate',
    help='Validate commit messages against cliff.toml rules.',
)


@validate_app.command
def commit_message(
    message: str,
) -> None:
    """Check if a commit message matches a configured commit parser.

    Exits 0 if valid, 1 if the message does not match any parser.
    Useful for validating PR titles before merge.

    Parameters
    ----------
    message
        Commit message to validate.
    """
    repo_info = open_repo().info
    result = GitCliff(repo_root=repo_info.root).validate_commit_message(message)
    if result.valid:
        console.print(f'✓ {result.reason}', style='green')
    else:
        err_console.print(f'✗ {result.reason}', style='bold red', markup=False)
        raise SystemExit(1)
