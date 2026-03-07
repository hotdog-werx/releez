from __future__ import annotations

import os
import re
import shutil
import sysconfig
import tempfile
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import tomli_w

from releez.errors import (
    ExternalCommandError,
    GitCliffVersionComputeError,
    MissingCliError,
)
from releez.process import run_checked

GIT_CLIFF_BIN = 'git-cliff'
GIT_CLIFF_TAG_PATTERN = '^[0-9]+\\.[0-9]+\\.[0-9]+$'

GitCliffBump = Literal['major', 'minor', 'patch', 'auto']


@dataclass(frozen=True)
class ReleaseNotes:
    """Generated release notes from git-cliff."""

    version: str
    markdown: str


@dataclass(frozen=True)
class CommitValidationResult:
    """Result of validating a commit message against the project's cliff.toml parsers."""

    valid: bool
    reason: str


def _build_validation_config(cliff_toml_path: Path) -> dict[str, object]:
    """Build a cliff.toml config dict suitable for commit message validation.

    Reads the project's cliff.toml and applies three overrides to [git]:
      - filter_unconventional = False  (non-conventional commits reach parsers)
      - fail_on_unmatched_commit = True (unmatched commit → non-zero exit)
      - removes catch-all parsers (message = ".*") so they don't swallow invalid msgs

    Returns the modified config dict (ready for tomli_w.dumps()).
    """
    with cliff_toml_path.open('rb') as f:
        config: dict[str, object] = tomllib.load(f)

    git = config.setdefault('git', {})
    if not isinstance(git, dict):
        msg = f'Expected [git] to be a table, got {type(git).__name__}'
        raise TypeError(msg)
    git['filter_unconventional'] = False
    git['fail_on_unmatched_commit'] = True
    parsers = git.get('commit_parsers', [])
    if not isinstance(parsers, list):
        msg = f'Expected commit_parsers to be an array, got {type(parsers).__name__}'
        raise TypeError(msg)
    git['commit_parsers'] = [p for p in parsers if p.get('message') != '.*']
    return config


def _git_cliff_base_cmd() -> list[str]:
    """Resolve the git-cliff executable path.

    Prefers the scripts directory of the current Python environment so that
    the correct git-cliff version is used when multiple are on PATH.

    Returns:
        Command list with absolute path to git-cliff, or ["git-cliff"] as fallback.

    Raises:
        MissingCliError: If git-cliff cannot be found anywhere.
    """
    scripts_dir = sysconfig.get_path('scripts')
    if scripts_dir:
        scripts_path = Path(scripts_dir)
        # On Windows, try platform-specific extensions before the bare name
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

    # Fall back to PATH lookup if not found in scripts dir
    if shutil.which(GIT_CLIFF_BIN):
        return [GIT_CLIFF_BIN]
    raise MissingCliError(GIT_CLIFF_BIN)


def _bump_args(bump: GitCliffBump) -> list[str]:
    """Build git-cliff --bump arguments.

    Args:
        bump: Bump mode. "auto" lets git-cliff decide; others pass the value explicitly.

    Returns:
        List of CLI arguments for the bump mode.
    """
    if bump == 'auto':
        return ['--bump']
    return ['--bump', bump]


_NO_RELEASES_PATTERN = re.compile(
    r'No releases found, using (\S+) as the next version',
)


def _extract_no_releases_default(stderr: str) -> str:
    """Return git-cliff's intended default version when no tags match the pattern.

    git-cliff warns "No releases found, using 0.1.0 as the next version" and then
    fails because 0.1.0 doesn't satisfy a prefixed tag pattern like ^core-(…)$.
    We recover the intended version from the warning so callers get 0.1.0 rather
    than a hard failure.
    """
    match = _NO_RELEASES_PATTERN.search(stderr)
    return match.group(1) if match else ''


class GitCliff:
    """Typed wrapper around the git-cliff CLI."""

    def __init__(self, *, repo_root: Path) -> None:
        self._repo_root = repo_root
        self._cmd = _git_cliff_base_cmd()

    def compute_next_version(
        self,
        *,
        bump: GitCliffBump,
        tag_pattern: str | None = None,
        include_paths: list[str] | None = None,
    ) -> str:
        """Compute the next version using git-cliff.

        Args:
            bump: The bump mode for git-cliff.
            tag_pattern: Optional regex pattern to match tags. Defaults to GIT_CLIFF_TAG_PATTERN.
            include_paths: Optional list of path patterns to filter commits
                (e.g., ["packages/core/**", "pyproject.toml"]).

        Returns:
            The computed next version.

        Raises:
            MissingCliError: If `git-cliff` is not available.
            ExternalCommandError: If git-cliff fails.
            GitCliffVersionComputeError: If git-cliff returns an empty version.
        """
        cmd = [
            *self._cmd,
            '--unreleased',
            '--bumped-version',
            '--tag-pattern',
            tag_pattern or GIT_CLIFF_TAG_PATTERN,
            *_bump_args(bump),
        ]

        if include_paths:
            for path in include_paths:
                cmd.extend(['--include-path', path])

        try:
            version = run_checked(cmd, cwd=self._repo_root).strip()
        except ExternalCommandError as exc:
            version = _extract_no_releases_default(exc.stderr)
            if not version:
                raise
        if not version:
            raise GitCliffVersionComputeError
        return version

    def generate_unreleased_notes(
        self,
        *,
        version: str,
        tag_pattern: str | None = None,
        include_paths: list[str] | None = None,
    ) -> str:
        """Generate the unreleased section as markdown.

        Args:
            version: The version to tag the release notes.
            tag_pattern: Optional regex pattern to match tags. Defaults to GIT_CLIFF_TAG_PATTERN.
            include_paths: Optional list of path patterns to filter commits
                (e.g., ["packages/core/**", "pyproject.toml"]).

        Returns:
            The generated markdown content.

        Raises:
            MissingCliError: If `git-cliff` is not available.
            ExternalCommandError: If git-cliff fails.
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            out_path = Path(tmp_dir) / 'RELEASE_NOTES.md'
            cmd = [
                *self._cmd,
                '--unreleased',
                '--strip',
                'all',
                '--tag',
                version,
                '--tag-pattern',
                tag_pattern or GIT_CLIFF_TAG_PATTERN,
                '--output',
                str(out_path),
            ]

            if include_paths:
                for path in include_paths:
                    cmd.extend(['--include-path', path])

            run_checked(
                cmd,
                cwd=self._repo_root,
                capture_stdout=False,
            )
            return out_path.read_text(encoding='utf-8')

    def prepend_to_changelog(
        self,
        *,
        version: str,
        changelog_path: Path,
        tag_pattern: str | None = None,
        include_paths: list[str] | None = None,
    ) -> None:
        """Prepend the unreleased section to the changelog file.

        Args:
            version: The version to tag the release notes.
            changelog_path: The path to the changelog file.
            tag_pattern: Optional regex pattern to match tags. Defaults to GIT_CLIFF_TAG_PATTERN.
            include_paths: Optional list of path patterns to filter commits
                (e.g., ["packages/core/**", "pyproject.toml"]).

        Raises:
            MissingCliError: If `git-cliff` is not available.
            ExternalCommandError: If git-cliff fails.
        """
        cmd = [
            *self._cmd,
            '-v',
            '--unreleased',
            '--tag',
            version,
            '--tag-pattern',
            tag_pattern or GIT_CLIFF_TAG_PATTERN,
            '--prepend',
            str(changelog_path),
        ]

        if include_paths:
            for path in include_paths:
                cmd.extend(['--include-path', path])

        run_checked(
            cmd,
            cwd=self._repo_root,
            capture_stdout=False,
        )

    def validate_commit_message(self, message: str) -> CommitValidationResult:
        """Check if a commit message matches a parser in the project's cliff.toml.

        Generates a temp cliff.toml from the real config with validation-safe overrides
        (fail_on_unmatched_commit=True, filter_unconventional=False, no catch-all parsers)
        and runs git-cliff --with-commit against it.

        skip=true parsers still exit 0 — e.g. chore(release): 1.2.3 is a valid PR title.
        Any non-zero exit (including git-cliff panics on unmatched commits) is invalid.
        """
        cliff_toml = self._repo_root / 'cliff.toml'
        config = _build_validation_config(cliff_toml)

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            cfg = tmp / 'cliff-validate.toml'
            cfg.write_bytes(tomli_w.dumps(config).encode())

            # Run git-cliff in a fresh git repo so real history doesn't interfere.
            # Without this, git-cliff processes all unreleased commits in the project
            # repo and any non-conventional commit (e.g. a CI merge commit from a
            # shallow checkout) causes a false failure via fail_on_unmatched_commit.
            run_checked(['git', 'init', str(tmp)], cwd=tmp)
            run_checked(
                ['git', '-C', str(tmp), 'config', 'user.email', 'x@x.x'],
            )
            run_checked(['git', '-C', str(tmp), 'config', 'user.name', 'x'])
            run_checked(
                [
                    'git',
                    '-C',
                    str(tmp),
                    'commit',
                    '--allow-empty',
                    '-m',
                    'chore: init',
                ],
            )

            try:
                run_checked(
                    [
                        *self._cmd,
                        '--unreleased',
                        '--with-commit',
                        message,
                        '--config',
                        str(cfg),
                    ],
                    cwd=tmp,
                )
                return CommitValidationResult(
                    valid=True,
                    reason='Valid: matches a commit parser',
                )
            except ExternalCommandError:
                return CommitValidationResult(
                    valid=False,
                    reason='Invalid: does not match any commit parser (expected: type(scope?): subject)',
                )

    def regenerate_changelog(
        self,
        *,
        changelog_path: Path,
        tag_pattern: str | None = None,
        include_paths: list[str] | None = None,
    ) -> None:
        """Regenerate the full changelog file from git history.

        Args:
            changelog_path: The path to the changelog file.
            tag_pattern: Optional regex pattern to match tags. Defaults to GIT_CLIFF_TAG_PATTERN.
            include_paths: Optional list of path patterns to filter commits
                (e.g., ["packages/core/**", "pyproject.toml"]).

        Raises:
            MissingCliError: If `git-cliff` is not available.
            ExternalCommandError: If git-cliff fails.
        """
        cmd = [
            *self._cmd,
            '-v',
            '--tag-pattern',
            tag_pattern or GIT_CLIFF_TAG_PATTERN,
            '--output',
            str(changelog_path),
        ]

        if include_paths:
            for path in include_paths:
                cmd.extend(['--include-path', path])

        run_checked(
            cmd,
            cwd=self._repo_root,
            capture_stdout=False,
        )
