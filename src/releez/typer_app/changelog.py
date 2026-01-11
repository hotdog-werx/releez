from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from releez.cliff import GitCliff
from releez.errors import ChangelogFormatCommandRequiredError, ReleezError
from releez.git_repo import open_repo
from releez.process import run_checked

changelog_app = typer.Typer(help='Changelog utilities.')


def _resolve_changelog_path(changelog_path: str, repo_root: Path) -> Path:
    """Resolve the changelog path relative to the repo root."""
    changelog = Path(changelog_path)
    if not changelog.is_absolute():
        changelog = repo_root / changelog
    return changelog


def _run_changelog_formatter(
    *,
    changelog_path: Path,
    repo_root: Path,
    changelog_format_cmd: list[str],
) -> None:
    """Run the changelog formatter command."""
    cmd = [arg.replace('{changelog}', str(changelog_path)) for arg in changelog_format_cmd]
    run_checked(cmd, cwd=repo_root, capture_stdout=False)
    typer.secho(
        '✓ Ran changelog format hook',
        fg=typer.colors.GREEN,
    )


@changelog_app.command('regenerate')
def changelog_regenerate(
    *,
    changelog_path: Annotated[
        str,
        typer.Option(
            '--changelog-path',
            help='Path to the changelog file.',
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
) -> None:
    """Regenerate the full changelog from git history."""
    try:
        if run_changelog_format and not changelog_format_cmd:
            raise ChangelogFormatCommandRequiredError

        _, info = open_repo()
        changelog = _resolve_changelog_path(changelog_path, info.root)

        cliff = GitCliff(repo_root=info.root)
        cliff.regenerate_changelog(changelog_path=changelog)
        typer.secho(
            f'✓ Regenerated changelog: {changelog}',
            fg=typer.colors.GREEN,
        )

        if run_changelog_format and changelog_format_cmd:
            _run_changelog_formatter(
                changelog_path=changelog,
                repo_root=info.root,
                changelog_format_cmd=changelog_format_cmd,
            )
    except ReleezError as exc:
        typer.secho(str(exc), err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1) from exc
