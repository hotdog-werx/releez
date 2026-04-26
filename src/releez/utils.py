from __future__ import annotations

import functools
import typing
from pathlib import Path
from typing import ParamSpec, TypeVar

import typer

from releez.errors import ReleezError
from releez.process import run_checked

if typing.TYPE_CHECKING:
    from collections.abc import Callable, Mapping

_P = ParamSpec('_P')
_R = TypeVar('_R')


def handle_releez_errors(func: Callable[_P, _R]) -> Callable[_P, _R]:
    """Decorator that catches ReleezError and exits with a formatted error message."""

    @functools.wraps(func)
    def wrapper(*args: _P.args, **kwargs: _P.kwargs) -> _R:
        try:
            return func(*args, **kwargs)
        except ReleezError as exc:
            typer.secho(str(exc), err=True, fg=typer.colors.RED)
            raise typer.Exit(code=1) from exc

    return wrapper


def resolve_changelog_path(changelog_path: str, repo_root: Path) -> Path:
    """Resolve the changelog path relative to the repo root.

    Args:
        changelog_path: Path to the changelog file (absolute or relative).
        repo_root: Root directory of the git repository.

    Returns:
        The resolved absolute path to the changelog.
    """
    changelog = Path(changelog_path)
    if not changelog.is_absolute():
        changelog = repo_root / changelog
    if not changelog.exists():
        changelog.touch()  # Create an empty changelog if it doesn't exist
    return changelog


def run_post_changelog_hooks(
    *,
    hooks: list[list[str]],
    repo_root: Path,
    template_vars: Mapping[str, str],
) -> None:
    """Run post-changelog hooks with template variable substitution.

    Args:
        hooks: List of command argv lists to run in order.
        repo_root: Root directory to run commands from.
        template_vars: Template variables to substitute (e.g. {"version": "1.2.3"}).

    Raises:
        ExternalCommandError: If any hook command fails.
    """
    for hook_cmd in hooks:
        # Substitute template variables in each argument
        cmd = [arg.format(**template_vars) if '{' in arg else arg for arg in hook_cmd]
        run_checked(cmd, cwd=repo_root, capture_stdout=False)
