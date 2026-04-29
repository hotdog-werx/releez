from __future__ import annotations

import pathlib
from typing import TYPE_CHECKING

import pytest
from git import Repo

from releez.errors import GitBranchExistsError, InvalidSupportBranchCommitError
from releez.git_repo import (
    create_branch_from_ref,
    find_all_major_versions,
    validate_commit_for_major,
)

if TYPE_CHECKING:
    from pathlib import Path


def _make_commit(repo: Repo, path: Path, message: str) -> None:
    """Create a file, stage it, and commit."""
    p = pathlib.Path(str(path))
    p.write_text(message)
    repo.index.add([p.name])
    repo.index.commit(message)


class TestFindAllMajorVersions:
    def test_empty_repo_returns_empty(self, tmp_path: Path) -> None:
        """No tags → empty list."""
        repo = Repo.init(tmp_path)
        assert find_all_major_versions(repo, tag_prefix='') == []

    def test_no_matching_tags_returns_empty(self, tmp_path: Path) -> None:
        """Tags that don't match the semver pattern are ignored."""
        repo = Repo.init(tmp_path)
        _make_commit(repo, tmp_path / 'f.txt', 'init')
        repo.create_tag('not-a-version')
        repo.create_tag('v1.0.0')  # has 'v' prefix, won't match bare pattern
        assert find_all_major_versions(repo, tag_prefix='') == []

    def test_single_major(self, tmp_path: Path) -> None:
        repo = Repo.init(tmp_path)
        _make_commit(repo, tmp_path / 'f.txt', 'init')
        repo.create_tag('1.0.0')
        repo.create_tag('1.1.0')
        repo.create_tag('1.2.0')
        assert find_all_major_versions(repo, tag_prefix='') == [1]

    def test_multiple_majors_sorted(self, tmp_path: Path) -> None:
        repo = Repo.init(tmp_path)
        _make_commit(repo, tmp_path / 'f.txt', 'init')
        repo.create_tag('1.0.0')
        repo.create_tag('2.0.0')
        repo.create_tag('3.0.0')
        assert find_all_major_versions(repo, tag_prefix='') == [1, 2, 3]

    def test_with_prefix_matches_prefix_only(self, tmp_path: Path) -> None:
        """Only tags with the given prefix are counted."""
        repo = Repo.init(tmp_path)
        _make_commit(repo, tmp_path / 'f.txt', 'init')
        repo.create_tag('core-1.0.0')
        repo.create_tag('core-2.0.0')
        repo.create_tag('ui-1.0.0')  # different prefix, ignored
        repo.create_tag('3.0.0')  # no prefix, ignored
        assert find_all_major_versions(repo, tag_prefix='core-') == [1, 2]

    def test_with_prefix_empty_when_no_match(self, tmp_path: Path) -> None:
        repo = Repo.init(tmp_path)
        _make_commit(repo, tmp_path / 'f.txt', 'init')
        repo.create_tag('1.0.0')
        repo.create_tag('2.0.0')
        assert find_all_major_versions(repo, tag_prefix='core-') == []


class TestCreateBranchFromRef:
    def test_creates_branch_at_given_commit(self, tmp_path: Path) -> None:
        repo = Repo.init(tmp_path)
        _make_commit(repo, tmp_path / 'a.txt', 'first')
        first_sha = repo.head.commit.hexsha
        _make_commit(repo, tmp_path / 'b.txt', 'second')
        repo.create_tag('1.0.0')

        create_branch_from_ref(repo, name='support/1.x', ref=first_sha)

        assert 'support/1.x' in [b.name for b in repo.branches]
        assert repo.active_branch.name == 'support/1.x'
        assert repo.head.commit.hexsha == first_sha

    def test_creates_branch_from_tag(self, tmp_path: Path) -> None:
        repo = Repo.init(tmp_path)
        _make_commit(repo, tmp_path / 'a.txt', 'v1')
        repo.create_tag('1.0.0')
        _make_commit(repo, tmp_path / 'b.txt', 'v2')
        repo.create_tag('2.0.0')

        tag_sha = repo.tags[0].commit.hexsha
        create_branch_from_ref(repo, name='support/1.x', ref='1.0.0')

        assert repo.active_branch.name == 'support/1.x'
        assert repo.head.commit.hexsha == tag_sha

    def test_raises_if_branch_already_exists(self, tmp_path: Path) -> None:
        repo = Repo.init(tmp_path)
        _make_commit(repo, tmp_path / 'a.txt', 'init')
        repo.create_head('support/1.x')

        with pytest.raises(GitBranchExistsError, match=r'support/1\.x'):
            create_branch_from_ref(repo, name='support/1.x', ref='HEAD')


class TestValidateCommitForMajor:
    def test_exact_tag_commit_is_valid(self, tmp_path: Path) -> None:
        repo = Repo.init(tmp_path)
        _make_commit(repo, tmp_path / 'a.txt', 'v1')
        repo.create_tag('1.4.0')
        tag_sha = repo.tags[0].commit.hexsha

        result = validate_commit_for_major(
            repo,
            commit_ref=tag_sha,
            latest_tag='1.4.0',
            major=1,
        )
        assert result == tag_sha

    def test_ancestor_commit_is_valid(self, tmp_path: Path) -> None:
        repo = Repo.init(tmp_path)
        _make_commit(repo, tmp_path / 'a.txt', 'first')
        ancestor_sha = repo.head.commit.hexsha
        _make_commit(repo, tmp_path / 'b.txt', 'second')
        repo.create_tag('1.4.0')

        result = validate_commit_for_major(
            repo,
            commit_ref=ancestor_sha,
            latest_tag='1.4.0',
            major=1,
        )
        assert result == ancestor_sha

    def test_non_ancestor_commit_raises(self, tmp_path: Path) -> None:
        """A commit not in the ancestry of the latest tag is invalid."""
        repo = Repo.init(tmp_path)
        _make_commit(repo, tmp_path / 'a.txt', 'base')
        base_sha = repo.head.commit.hexsha

        # Create 1.x branch and tag
        repo.create_head('branch-1x', base_sha).checkout()
        _make_commit(repo, tmp_path / 'b.txt', 'v1 work')
        repo.create_tag('1.4.0')

        # Go back to base and create unrelated commit
        repo.git.checkout(base_sha, detach=True)
        _make_commit(repo, tmp_path / 'c.txt', 'unrelated')
        unrelated_sha = repo.head.commit.hexsha

        with pytest.raises(InvalidSupportBranchCommitError, match=r'1\.4\.0'):
            validate_commit_for_major(
                repo,
                commit_ref=unrelated_sha,
                latest_tag='1.4.0',
                major=1,
            )

    def test_unresolvable_ref_raises(self, tmp_path: Path) -> None:
        repo = Repo.init(tmp_path)
        _make_commit(repo, tmp_path / 'a.txt', 'init')
        repo.create_tag('1.4.0')

        with pytest.raises(InvalidSupportBranchCommitError, match='deadbeef'):
            validate_commit_for_major(
                repo,
                commit_ref='deadbeef' * 5,
                latest_tag='1.4.0',
                major=1,
            )
