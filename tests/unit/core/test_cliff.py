from __future__ import annotations

from typing import TYPE_CHECKING

import releez.cliff

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


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
