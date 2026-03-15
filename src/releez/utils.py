from __future__ import annotations

import typing
from pathlib import Path

from releez.errors import ChangelogNotFoundError
from releez.process import run_checked

if typing.TYPE_CHECKING:
    from collections.abc import Mapping


def resolve_changelog_path(changelog_path: str, repo_root: Path) -> Path:
    """Resolve the changelog path relative to the repo root.

    Args:
        changelog_path: Path to the changelog file (absolute or relative).
        repo_root: Root directory of the git repository.

    Returns:
        The resolved absolute path to the changelog.

    Raises:
        ChangelogNotFoundError: If the changelog file doesn't exist.
    """
    changelog = Path(changelog_path)
    if not changelog.is_absolute():
        changelog = repo_root / changelog
    if not changelog.exists():
        raise ChangelogNotFoundError(changelog)
    return changelog


def run_changelog_formatter(
    *,
    changelog_path: Path,
    repo_root: Path,
    changelog_format_cmd: list[str],
) -> None:
    """Run the changelog formatter command.

    Args:
        changelog_path: Path to the changelog file to format.
        repo_root: Root directory to run the command from.
        changelog_format_cmd: Command argv list with optional {changelog} placeholder.
    """
    cmd = [arg.replace('{changelog}', str(changelog_path)) for arg in changelog_format_cmd]
    run_checked(cmd, cwd=repo_root, capture_stdout=False)


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
