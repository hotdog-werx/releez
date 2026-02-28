from __future__ import annotations

from typing import TYPE_CHECKING

from git import Repo

from releez.git_repo import (
    detect_changed_projects,
    find_latest_tag_matching_pattern,
    get_changed_files_per_project,
)
from releez.settings import ReleezSettings
from releez.subproject import SubProject
from releez.version_tags import AliasVersions

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def test_find_latest_tag_matching_pattern_no_tags(tmp_path: Path) -> None:
    """Test finding tag when no tags exist."""
    repo = Repo.init(tmp_path)
    result = find_latest_tag_matching_pattern(
        repo,
        pattern=r'^core-([0-9]+\.[0-9]+\.[0-9]+)$',
    )
    assert result is None


def test_find_latest_tag_matching_pattern_no_matching_tags(
    tmp_path: Path,
) -> None:
    """Test finding tag when tags exist but none match pattern."""
    repo = Repo.init(tmp_path)

    # Create a commit
    (tmp_path / 'file.txt').write_text('content')
    repo.index.add(['file.txt'])
    repo.index.commit('initial commit')

    # Create tags that don't match pattern
    repo.create_tag('ui-1.0.0')
    repo.create_tag('v1.2.3')

    result = find_latest_tag_matching_pattern(
        repo,
        pattern=r'^core-([0-9]+\.[0-9]+\.[0-9]+)$',
    )
    assert result is None


def test_find_latest_tag_matching_pattern_finds_latest(tmp_path: Path) -> None:
    """Test finding the most recent tag matching pattern."""
    repo = Repo.init(tmp_path)

    # Create first commit and tag
    (tmp_path / 'file1.txt').write_text('v1')
    repo.index.add(['file1.txt'])
    repo.index.commit('commit 1')
    repo.create_tag('core-1.0.0')

    # Create second commit and tag
    (tmp_path / 'file2.txt').write_text('v2')
    repo.index.add(['file2.txt'])
    repo.index.commit('commit 2')
    repo.create_tag('core-1.1.0')

    # Create third commit and tag
    (tmp_path / 'file3.txt').write_text('v3')
    repo.index.add(['file3.txt'])
    repo.index.commit('commit 3')
    repo.create_tag('core-2.0.0')

    # Also add some non-matching tags
    repo.create_tag('ui-1.0.0')

    result = find_latest_tag_matching_pattern(
        repo,
        pattern=r'^core-([0-9]+\.[0-9]+\.[0-9]+)$',
    )
    assert result == 'core-2.0.0'


def test_detect_changed_projects_no_changes_since_tag(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that project is not marked as changed when no commits since tag."""
    monkeypatch.chdir(tmp_path)
    repo = Repo.init(tmp_path)

    # Setup project structure
    core_dir = tmp_path / 'packages' / 'core'
    core_dir.mkdir(parents=True)
    (core_dir / 'main.py').write_text('print("hello")')

    # Commit and tag
    repo.index.add(['packages/core/main.py'])
    repo.index.commit('initial commit')
    repo.create_tag('core-1.0.0')

    # Create SubProject
    project = SubProject(
        name='core',
        path=core_dir,
        changelog_path=core_dir / 'CHANGELOG.md',
        tag_prefix='core-',
        tag_pattern=r'^core-([0-9]+\.[0-9]+\.[0-9]+)$',
        alias_versions=AliasVersions.none,
        hooks=ReleezSettings().hooks,
        include_paths=[],
    )

    # Detect changes
    changed = detect_changed_projects(
        repo=repo,
        base_branch='HEAD',
        projects=[project],
    )

    assert changed == []


def test_detect_changed_projects_with_changes_since_tag(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that project is marked as changed when commits exist since tag."""
    monkeypatch.chdir(tmp_path)
    repo = Repo.init(tmp_path)

    # Setup project structure
    core_dir = tmp_path / 'packages' / 'core'
    core_dir.mkdir(parents=True)
    (core_dir / 'main.py').write_text('print("hello")')

    # Initial commit and tag
    repo.index.add(['packages/core/main.py'])
    repo.index.commit('initial commit')
    repo.create_tag('core-1.0.0')

    # Make a change after the tag
    (core_dir / 'new.py').write_text('print("new")')
    repo.index.add(['packages/core/new.py'])
    repo.index.commit('add new file')

    # Create SubProject
    project = SubProject(
        name='core',
        path=core_dir,
        changelog_path=core_dir / 'CHANGELOG.md',
        tag_prefix='core-',
        tag_pattern=r'^core-([0-9]+\.[0-9]+\.[0-9]+)$',
        alias_versions=AliasVersions.none,
        hooks=ReleezSettings().hooks,
        include_paths=[],
    )

    # Detect changes
    changed = detect_changed_projects(
        repo=repo,
        base_branch='HEAD',
        projects=[project],
    )

    assert changed == [project]


def test_detect_changed_projects_no_tag_yet(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test detection when project has no tags yet (bootstrap case)."""
    monkeypatch.chdir(tmp_path)
    repo = Repo.init(tmp_path)

    # Setup project structure
    core_dir = tmp_path / 'packages' / 'core'
    core_dir.mkdir(parents=True)
    (core_dir / 'main.py').write_text('print("hello")')

    # Commit but don't create any tags
    repo.index.add(['packages/core/main.py'])
    repo.index.commit('initial commit')

    # Create SubProject
    project = SubProject(
        name='core',
        path=core_dir,
        changelog_path=core_dir / 'CHANGELOG.md',
        tag_prefix='core-',
        tag_pattern=r'^core-([0-9]+\.[0-9]+\.[0-9]+)$',
        alias_versions=AliasVersions.none,
        hooks=ReleezSettings().hooks,
        include_paths=[],
    )

    # Detect changes
    changed = detect_changed_projects(
        repo=repo,
        base_branch='HEAD',
        projects=[project],
    )

    # Should detect change since there's a commit but no tag
    assert changed == [project]


def test_detect_changed_projects_include_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that changes to include_paths trigger detection."""
    monkeypatch.chdir(tmp_path)
    repo = Repo.init(tmp_path)

    # Setup project structure
    core_dir = tmp_path / 'packages' / 'core'
    core_dir.mkdir(parents=True)
    (core_dir / 'main.py').write_text('print("hello")')
    (tmp_path / 'pyproject.toml').write_text(
        '[tool.releez]\nbase-branch = "main"',
    )

    # Initial commit and tag
    repo.index.add(['packages/core/main.py', 'pyproject.toml'])
    repo.index.commit('initial commit')
    repo.create_tag('core-1.0.0')

    # Change root pyproject.toml (which is in include_paths)
    (tmp_path / 'pyproject.toml').write_text(
        '[tool.releez]\nbase-branch = "develop"',
    )
    repo.index.add(['pyproject.toml'])
    repo.index.commit('update root pyproject')

    # Create SubProject with include_paths
    project = SubProject(
        name='core',
        path=core_dir,
        changelog_path=core_dir / 'CHANGELOG.md',
        tag_prefix='core-',
        tag_pattern=r'^core-([0-9]+\.[0-9]+\.[0-9]+)$',
        alias_versions=AliasVersions.none,
        hooks=ReleezSettings().hooks,
        include_paths=['pyproject.toml'],  # Monitor root file
    )

    # Detect changes
    changed = detect_changed_projects(
        repo=repo,
        base_branch='HEAD',
        projects=[project],
    )

    # Should detect change due to pyproject.toml modification
    assert changed == [project]


def test_detect_changed_projects_multiple_projects(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test detecting changes across multiple projects."""
    monkeypatch.chdir(tmp_path)
    repo = Repo.init(tmp_path)

    # Setup two projects
    core_dir = tmp_path / 'packages' / 'core'
    ui_dir = tmp_path / 'packages' / 'ui'
    core_dir.mkdir(parents=True)
    ui_dir.mkdir(parents=True)

    (core_dir / 'main.py').write_text('core')
    (ui_dir / 'index.js').write_text('ui')

    # Initial commit and tags
    repo.index.add(['packages/core/main.py', 'packages/ui/index.js'])
    repo.index.commit('initial commit')
    repo.create_tag('core-1.0.0')
    repo.create_tag('ui-1.0.0')

    # Change only core
    (core_dir / 'new.py').write_text('new')
    repo.index.add(['packages/core/new.py'])
    repo.index.commit('update core')

    # Create SubProjects
    core_project = SubProject(
        name='core',
        path=core_dir,
        changelog_path=core_dir / 'CHANGELOG.md',
        tag_prefix='core-',
        tag_pattern=r'^core-([0-9]+\.[0-9]+\.[0-9]+)$',
        alias_versions=AliasVersions.none,
        hooks=ReleezSettings().hooks,
        include_paths=[],
    )

    ui_project = SubProject(
        name='ui',
        path=ui_dir,
        changelog_path=ui_dir / 'CHANGELOG.md',
        tag_prefix='ui-',
        tag_pattern=r'^ui-([0-9]+\.[0-9]+\.[0-9]+)$',
        alias_versions=AliasVersions.none,
        hooks=ReleezSettings().hooks,
        include_paths=[],
    )

    # Detect changes
    changed = detect_changed_projects(
        repo=repo,
        base_branch='HEAD',
        projects=[core_project, ui_project],
    )

    # Only core should be detected
    assert changed == [core_project]


def test_get_changed_files_per_project(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test getting list of changed files per project."""
    monkeypatch.chdir(tmp_path)
    repo = Repo.init(tmp_path)

    # Setup project
    core_dir = tmp_path / 'packages' / 'core'
    core_dir.mkdir(parents=True)
    (core_dir / 'main.py').write_text('v1')
    (tmp_path / 'pyproject.toml').write_text(
        '[tool.releez]\nbase-branch = "main"',
    )

    # Initial commit and tag
    repo.index.add(['packages/core/main.py', 'pyproject.toml'])
    repo.index.commit('initial')
    repo.create_tag('core-1.0.0')

    # Make changes
    (core_dir / 'main.py').write_text('v2')
    (core_dir / 'new.py').write_text('new')
    (tmp_path / 'pyproject.toml').write_text(
        '[tool.releez]\nbase-branch = "develop"',
    )

    repo.index.add(
        ['packages/core/main.py', 'packages/core/new.py', 'pyproject.toml'],
    )
    repo.index.commit('updates')

    # Create SubProject
    project = SubProject(
        name='core',
        path=core_dir,
        changelog_path=core_dir / 'CHANGELOG.md',
        tag_prefix='core-',
        tag_pattern=r'^core-([0-9]+\.[0-9]+\.[0-9]+)$',
        alias_versions=AliasVersions.none,
        hooks=ReleezSettings().hooks,
        include_paths=['pyproject.toml'],
    )

    # Get changed files
    result = get_changed_files_per_project(
        repo=repo,
        base_branch='HEAD',
        projects=[project],
    )

    assert 'core' in result
    assert set(result['core']) == {
        'packages/core/main.py',
        'packages/core/new.py',
        'pyproject.toml',
    }


def test_get_changed_files_per_project_no_changes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test getting changed files when no changes exist."""
    monkeypatch.chdir(tmp_path)
    repo = Repo.init(tmp_path)

    # Setup project
    core_dir = tmp_path / 'packages' / 'core'
    core_dir.mkdir(parents=True)
    (core_dir / 'main.py').write_text('v1')

    # Initial commit and tag
    repo.index.add(['packages/core/main.py'])
    repo.index.commit('initial')
    repo.create_tag('core-1.0.0')

    # Create SubProject
    project = SubProject(
        name='core',
        path=core_dir,
        changelog_path=core_dir / 'CHANGELOG.md',
        tag_prefix='core-',
        tag_pattern=r'^core-([0-9]+\.[0-9]+\.[0-9]+)$',
        alias_versions=AliasVersions.none,
        hooks=ReleezSettings().hooks,
        include_paths=[],
    )

    # Get changed files
    result = get_changed_files_per_project(
        repo=repo,
        base_branch='HEAD',
        projects=[project],
    )

    assert result == {}
