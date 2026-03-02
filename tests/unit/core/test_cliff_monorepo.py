from __future__ import annotations

from typing import TYPE_CHECKING

from git import Repo

from releez.cliff import GitCliff

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def test_compute_next_version_with_tag_pattern(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test computing next version with custom tag pattern.

    Args:
        tmp_path: pytest fixture for temporary directory.
        monkeypatch: pytest fixture for patching.
    """
    monkeypatch.chdir(tmp_path)
    repo = Repo.init(tmp_path)

    # Create initial commit and tag with prefix
    (tmp_path / 'file.txt').write_text('initial')
    repo.index.add(['file.txt'])
    repo.index.commit('feat: initial commit')
    repo.create_tag('core-1.0.0')

    # Create another commit
    (tmp_path / 'file.txt').write_text('updated')
    repo.index.add(['file.txt'])
    repo.index.commit('feat: update file')

    # Test with custom tag pattern
    cliff = GitCliff(repo_root=tmp_path)
    version = cliff.compute_next_version(
        bump='auto',
        tag_pattern=r'^core-([0-9]+\.[0-9]+\.[0-9]+)$',
    )

    # Should compute next version based on core- tags
    assert version == 'core-1.1.0'


def test_compute_next_version_with_include_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test computing next version with path filtering."""
    monkeypatch.chdir(tmp_path)
    repo = Repo.init(tmp_path)

    # Setup project structure
    core_dir = tmp_path / 'packages' / 'core'
    ui_dir = tmp_path / 'packages' / 'ui'
    core_dir.mkdir(parents=True)
    ui_dir.mkdir(parents=True)

    # Initial commit and tag
    (core_dir / 'main.py').write_text('core v1')
    (ui_dir / 'index.js').write_text('ui v1')
    repo.index.add(['packages/core/main.py', 'packages/ui/index.js'])
    repo.index.commit('feat: initial commit')
    repo.create_tag('core-1.0.0')

    # Change only UI (should NOT affect core version)
    (ui_dir / 'index.js').write_text('ui v2')
    repo.index.add(['packages/ui/index.js'])
    repo.index.commit('feat(ui): update ui')

    # Test with path filtering - should find no changes in core path
    cliff = GitCliff(repo_root=tmp_path)
    version = cliff.compute_next_version(
        bump='auto',
        tag_pattern=r'^core-([0-9]+\.[0-9]+\.[0-9]+)$',
        include_paths=['packages/core/**'],
    )

    # Should still be 1.0.0 since no core changes
    assert version == 'core-1.0.0'


def test_compute_next_version_with_multiple_include_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test computing next version with multiple path filters."""
    monkeypatch.chdir(tmp_path)
    repo = Repo.init(tmp_path)

    # Setup project structure
    core_dir = tmp_path / 'packages' / 'core'
    core_dir.mkdir(parents=True)

    # Initial commit and tag
    (core_dir / 'main.py').write_text('core v1')
    (tmp_path / 'pyproject.toml').write_text(
        '[tool.releez]\nbase-branch = "main"',
    )
    repo.index.add(['packages/core/main.py', 'pyproject.toml'])
    repo.index.commit('feat: initial commit')
    repo.create_tag('core-1.0.0')

    # Change root config (monitored via include_paths)
    (tmp_path / 'pyproject.toml').write_text(
        '[tool.releez]\nbase-branch = "develop"',
    )
    repo.index.add(['pyproject.toml'])
    repo.index.commit('feat: update config')

    # Test with multiple include paths
    cliff = GitCliff(repo_root=tmp_path)
    version = cliff.compute_next_version(
        bump='auto',
        tag_pattern=r'^core-([0-9]+\.[0-9]+\.[0-9]+)$',
        include_paths=['packages/core/**', 'pyproject.toml'],
    )

    # Should bump to 1.1.0 due to pyproject.toml change
    assert version == 'core-1.1.0'


def test_generate_unreleased_notes_with_tag_pattern(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test generating release notes with custom tag pattern."""
    monkeypatch.chdir(tmp_path)
    repo = Repo.init(tmp_path)

    # Create initial commit and tag
    (tmp_path / 'file.txt').write_text('initial')
    repo.index.add(['file.txt'])
    repo.index.commit('feat: initial commit')
    repo.create_tag('ui-1.0.0')

    # Create another commit
    (tmp_path / 'file.txt').write_text('updated')
    repo.index.add(['file.txt'])
    repo.index.commit('feat: update file')

    # Generate release notes with custom pattern
    cliff = GitCliff(repo_root=tmp_path)
    notes = cliff.generate_unreleased_notes(
        version='ui-1.1.0',
        tag_pattern=r'^ui-([0-9]+\.[0-9]+\.[0-9]+)$',
    )

    # Should contain the feat commit (git-cliff capitalizes)
    assert 'Update file' in notes or 'update file' in notes


def test_prepend_to_changelog_with_include_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test prepending to changelog with path filtering."""
    monkeypatch.chdir(tmp_path)
    repo = Repo.init(tmp_path)

    # Setup project structure
    core_dir = tmp_path / 'packages' / 'core'
    core_dir.mkdir(parents=True)

    # Initial commit and tag
    (core_dir / 'main.py').write_text('core v1')
    repo.index.add(['packages/core/main.py'])
    repo.index.commit('feat: initial commit')
    repo.create_tag('core-1.0.0')

    # Create another commit in core
    (core_dir / 'main.py').write_text('core v2')
    repo.index.add(['packages/core/main.py'])
    repo.index.commit('feat(core): update core')

    # Create changelog file
    changelog_path = core_dir / 'CHANGELOG.md'
    changelog_path.write_text('# Changelog\n\n')

    # Prepend with path filtering
    cliff = GitCliff(repo_root=tmp_path)
    cliff.prepend_to_changelog(
        version='core-1.1.0',
        changelog_path=changelog_path,
        tag_pattern=r'^core-([0-9]+\.[0-9]+\.[0-9]+)$',
        include_paths=['packages/core/**'],
    )

    # Check changelog was updated
    changelog_content = changelog_path.read_text()
    assert 'core-1.1.0' in changelog_content or '1.1.0' in changelog_content
    assert 'Update core' in changelog_content or 'update core' in changelog_content


def test_generate_unreleased_notes_with_include_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test generating release notes with path filtering."""
    monkeypatch.chdir(tmp_path)
    repo = Repo.init(tmp_path)

    # Setup two project directories
    core_dir = tmp_path / 'packages' / 'core'
    ui_dir = tmp_path / 'packages' / 'ui'
    core_dir.mkdir(parents=True)
    ui_dir.mkdir(parents=True)

    # Initial commit and tag
    (core_dir / 'main.py').write_text('core v1')
    (ui_dir / 'index.js').write_text('ui v1')
    repo.index.add(['packages/core/main.py', 'packages/ui/index.js'])
    repo.index.commit('feat: initial commit')
    repo.create_tag('core-1.0.0')

    # Change only core
    (core_dir / 'main.py').write_text('core v2')
    repo.index.add(['packages/core/main.py'])
    repo.index.commit('feat(core): update core module')

    # Generate notes with path filtering scoped to core
    cliff = GitCliff(repo_root=tmp_path)
    notes = cliff.generate_unreleased_notes(
        version='core-1.1.0',
        tag_pattern=r'^core-([0-9]+\.[0-9]+\.[0-9]+)$',
        include_paths=['packages/core/**'],
    )

    # Should include the core commit in notes
    assert 'core-1.1.0' in notes or '1.1.0' in notes


def test_regenerate_changelog_with_include_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test regenerating full changelog with path filtering."""
    monkeypatch.chdir(tmp_path)
    repo = Repo.init(tmp_path)

    # Setup project directory
    core_dir = tmp_path / 'packages' / 'core'
    core_dir.mkdir(parents=True)

    # Initial commit and tag
    (core_dir / 'main.py').write_text('core v1')
    repo.index.add(['packages/core/main.py'])
    repo.index.commit('feat: initial core commit')
    repo.create_tag('core-1.0.0')

    # Another commit
    (core_dir / 'main.py').write_text('core v2')
    repo.index.add(['packages/core/main.py'])
    repo.index.commit('feat(core): add feature')
    repo.create_tag('core-1.1.0')

    # Create changelog path
    changelog_path = core_dir / 'CHANGELOG.md'

    # Regenerate with path filtering
    cliff = GitCliff(repo_root=tmp_path)
    cliff.regenerate_changelog(
        changelog_path=changelog_path,
        tag_pattern=r'^core-([0-9]+\.[0-9]+\.[0-9]+)$',
        include_paths=['packages/core/**'],
    )

    changelog_content = changelog_path.read_text()
    assert 'core-1.0.0' in changelog_content or '1.0.0' in changelog_content
    assert 'core-1.1.0' in changelog_content or '1.1.0' in changelog_content
