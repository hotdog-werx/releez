"""Tests for shared Git repository operations."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from git import Repo
from git.exc import GitCommandError

from releez.git_repo import commit_staged

if TYPE_CHECKING:
    from pathlib import Path


def test_commit_staged_honors_required_signing_configuration(
    tmp_path: Path,
) -> None:
    """A required but unavailable signer fails instead of creating an unsigned commit."""
    repo = Repo.init(tmp_path)
    with repo.config_writer() as config:
        config.set_value('user', 'name', 'Test')
        config.set_value('user', 'email', 'test@example.com')

    tracked = tmp_path / 'tracked.txt'
    tracked.write_text('initial\n', encoding='utf-8')
    repo.index.add(['tracked.txt'])
    initial = repo.index.commit('initial')

    tracked.write_text('changed\n', encoding='utf-8')
    repo.index.add(['tracked.txt'])
    with repo.config_writer() as config:
        config.set_value('commit', 'gpgSign', 'true')
        config.set_value('gpg', 'format', 'openpgp')
        config.set_value('gpg', 'program', 'releez-missing-gpg-program')
        config.set_value('user', 'signingKey', 'releez-missing-signing-key')

    with pytest.raises(GitCommandError):
        commit_staged(repo, message='must be signed')

    assert repo.head.commit == initial
