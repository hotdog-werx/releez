from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

import releez.cliff
from releez.errors import ExternalCommandError

if TYPE_CHECKING:
    from pathlib import Path


def test_git_cliff_base_cmd_prefers_current_env_scripts_dir(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    scripts_dir = tmp_path / 'scripts'
    scripts_dir.mkdir()

    exe_name = 'git-cliff.exe' if releez.cliff.os.name == 'nt' else 'git-cliff'
    exe_path = scripts_dir / exe_name
    exe_path.write_text('#!/bin/sh\necho ok\n', encoding='utf-8')

    monkeypatch.setattr(
        releez.cliff.sysconfig,
        'get_path',
        lambda _: str(scripts_dir),
    )
    monkeypatch.setattr(releez.cliff.shutil, 'which', lambda _: None)

    assert releez.cliff._git_cliff_base_cmd() == [str(exe_path)]


def test_git_cliff_base_cmd_falls_back_to_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(releez.cliff.sysconfig, 'get_path', lambda _: None)
    monkeypatch.setattr(
        releez.cliff.shutil,
        'which',
        lambda _: '/usr/bin/git-cliff',
    )

    assert releez.cliff._git_cliff_base_cmd() == ['git-cliff']


def test_prepend_to_changelog_skips_include_paths_when_empty(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured_cmd: list[str] = []

    def _fake_run_checked(
        cmd: list[str],
        *,
        cwd: Path,
        capture_stdout: bool = True,
    ) -> str:
        captured_cmd.extend(cmd)
        assert cwd == tmp_path
        assert capture_stdout is False
        return ''

    monkeypatch.setattr(
        releez.cliff,
        '_git_cliff_base_cmd',
        lambda: ['git-cliff'],
    )
    monkeypatch.setattr(releez.cliff, 'run_checked', _fake_run_checked)

    cliff = releez.cliff.GitCliff(repo_root=tmp_path)
    cliff.prepend_to_changelog(
        version='1.2.3',
        changelog_path=tmp_path / 'CHANGELOG.md',
        include_paths=[],
    )

    assert '--include-path' not in captured_cmd


def test_regenerate_changelog_skips_include_paths_when_empty(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured_cmd: list[str] = []

    def _fake_run_checked(
        cmd: list[str],
        *,
        cwd: Path,
        capture_stdout: bool = True,
    ) -> str:
        captured_cmd.extend(cmd)
        assert cwd == tmp_path
        assert capture_stdout is False
        return ''

    monkeypatch.setattr(
        releez.cliff,
        '_git_cliff_base_cmd',
        lambda: ['git-cliff'],
    )
    monkeypatch.setattr(releez.cliff, 'run_checked', _fake_run_checked)

    cliff = releez.cliff.GitCliff(repo_root=tmp_path)
    cliff.regenerate_changelog(
        changelog_path=tmp_path / 'CHANGELOG.md',
        include_paths=[],
    )

    assert '--include-path' not in captured_cmd


def test_compute_next_version_falls_back_when_no_matching_tags(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Unit: compute_next_version recovers git-cliff's default when no tags match the pattern.

    git-cliff warns "No releases found, using 0.1.0 as the next version" and then
    errors because 0.1.0 doesn't satisfy a prefixed tag pattern like ^core-(…)$.
    We parse the intended version from the warning and return it instead of failing.
    """
    git_cliff_stderr = (
        'WARN  git_cliff_core::config > No releases found, using 0.1.0 as the next version\n'
        'ERROR git_cliff              > Changelog error: '
        '`Next version (0.1.0) does not match the tag pattern: ^core-([0-9]+\\.[0-9]+\\.[0-9]+)$`'
    )

    def _raise_no_releases(
        cmd: list[str],
        *,
        cwd: object,
        capture_stdout: bool = True,
    ) -> str:
        raise ExternalCommandError(
            cmd_args=cmd,
            returncode=1,
            stderr=git_cliff_stderr,
        )

    monkeypatch.setattr(
        releez.cliff,
        '_git_cliff_base_cmd',
        lambda: ['git-cliff'],
    )
    monkeypatch.setattr(releez.cliff, 'run_checked', _raise_no_releases)

    cliff = releez.cliff.GitCliff(repo_root=tmp_path)
    version = cliff.compute_next_version(
        bump='auto',
        tag_pattern=r'^core-([0-9]+\.[0-9]+\.[0-9]+)$',
    )

    assert version == '0.1.0'


def test_compute_next_version_reraises_unrelated_external_errors(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Unit: unrelated git-cliff failures are not swallowed by the no-releases fallback."""

    def _raise_other_error(
        cmd: list[str],
        *,
        cwd: object,
        capture_stdout: bool = True,
    ) -> str:
        raise ExternalCommandError(
            cmd_args=cmd,
            returncode=1,
            stderr='some other git-cliff error',
        )

    monkeypatch.setattr(
        releez.cliff,
        '_git_cliff_base_cmd',
        lambda: ['git-cliff'],
    )
    monkeypatch.setattr(releez.cliff, 'run_checked', _raise_other_error)

    cliff = releez.cliff.GitCliff(repo_root=tmp_path)
    with pytest.raises(ExternalCommandError):
        cliff.compute_next_version(bump='auto')
