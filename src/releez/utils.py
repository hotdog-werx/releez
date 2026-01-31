from __future__ import annotations

from pathlib import Path

from releez.errors import ChangelogNotFoundError
from releez.process import run_checked


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
