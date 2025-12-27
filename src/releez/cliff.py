from __future__ import annotations

import os
import shutil
import sysconfig
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from releez.errors import GitCliffVersionComputeError, MissingCliError
from releez.process import run_checked

GIT_CLIFF_BIN = 'git-cliff'
GIT_CLIFF_IGNORE_TAGS = 'v*'

GitCliffBump = Literal['major', 'minor', 'patch', 'auto']


@dataclass(frozen=True)
class ReleaseNotes:
    """Generated release notes from git-cliff."""

    version: str
    markdown: str


def _git_cliff_base_cmd() -> list[str]:
    scripts_dir = sysconfig.get_path('scripts')
    if scripts_dir:
        scripts_path = Path(scripts_dir)
        candidates = [GIT_CLIFF_BIN]
        if os.name == 'nt':  # pragma: no cover
            candidates = [
                f'{GIT_CLIFF_BIN}.exe',
                f'{GIT_CLIFF_BIN}.cmd',
                f'{GIT_CLIFF_BIN}.bat',
                GIT_CLIFF_BIN,
            ]
        for name in candidates:
            exe = scripts_path / name
            if exe.is_file():
                return [str(exe)]

    if shutil.which(GIT_CLIFF_BIN):
        return [GIT_CLIFF_BIN]
    raise MissingCliError(GIT_CLIFF_BIN)


def _bump_args(bump: GitCliffBump) -> list[str]:
    if bump == 'auto':
        return ['--bump']
    return ['--bump', bump]


class GitCliff:
    """Typed wrapper around the git-cliff CLI."""

    def __init__(self, *, repo_root: Path) -> None:
        self._repo_root = repo_root
        self._cmd = _git_cliff_base_cmd()

    def compute_next_version(self, *, bump: GitCliffBump) -> str:
        """Compute the next version using git-cliff.

        Args:
            bump: The bump mode for git-cliff.

        Returns:
            The computed next version.

        Raises:
            MissingCliError: If `git-cliff` is not available.
            ExternalCommandError: If git-cliff fails.
            GitCliffVersionComputeError: If git-cliff returns an empty version.
        """
        version = run_checked(
            [
                *self._cmd,
                '--unreleased',
                '--bumped-version',
                '--ignore-tags',
                GIT_CLIFF_IGNORE_TAGS,
                *_bump_args(bump),
            ],
            cwd=self._repo_root,
        ).strip()
        if not version:
            raise GitCliffVersionComputeError
        return version

    def generate_unreleased_notes(
        self,
        *,
        version: str,
    ) -> str:
        """Generate the unreleased section as markdown.

        Args:
            version: The version to tag the release notes.

        Returns:
            The generated markdown content.

        Raises:
            MissingCliError: If `git-cliff` is not available.
            ExternalCommandError: If git-cliff fails.
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            out_path = Path(tmp_dir) / 'RELEASE_NOTES.md'
            run_checked(
                [
                    *self._cmd,
                    '--unreleased',
                    '--strip',
                    'all',
                    '--tag',
                    version,
                    '--ignore-tags',
                    GIT_CLIFF_IGNORE_TAGS,
                    '--output',
                    str(out_path),
                ],
                cwd=self._repo_root,
                capture_stdout=False,
            )
            return out_path.read_text(encoding='utf-8')

    def prepend_to_changelog(
        self,
        *,
        version: str,
        changelog_path: Path,
    ) -> None:
        """Prepend the unreleased section to the changelog file.

        Args:
            version: The version to tag the release notes.
            changelog_path: The path to the changelog file.

        Raises:
            MissingCliError: If `git-cliff` is not available.
            ExternalCommandError: If git-cliff fails.
        """
        run_checked(
            [
                *self._cmd,
                '-v',
                '--unreleased',
                '--tag',
                version,
                '--ignore-tags',
                GIT_CLIFF_IGNORE_TAGS,
                '--prepend',
                str(changelog_path),
            ],
            cwd=self._repo_root,
            capture_stdout=False,
        )
