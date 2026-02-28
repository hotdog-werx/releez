"""Tests for detect_release_from_branch function."""

from __future__ import annotations

from typing import TYPE_CHECKING

from releez.git_repo import detect_release_from_branch
from releez.settings import ReleezSettings
from releez.subproject import SubProject

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def test_detect_release_from_branch_single_repo(tmp_path: Path) -> None:
    """Test detecting release from single-repo branch.

    Args:
        tmp_path: pytest fixture for temporary directory.
    """
    detected = detect_release_from_branch(
        branch_name='release/1.2.3',
        projects=[],
    )

    assert detected is not None
    assert detected.version == '1.2.3'
    assert detected.project_name is None
    assert detected.branch_name == 'release/1.2.3'


def test_detect_release_from_branch_not_release_branch(tmp_path: Path) -> None:
    """Test that non-release branches return None.

    Args:
        tmp_path: pytest fixture for temporary directory.
    """
    detected = detect_release_from_branch(
        branch_name='main',
        projects=[],
    )

    assert detected is None


def test_detect_release_from_branch_feature_branch(tmp_path: Path) -> None:
    """Test that feature branches return None.

    Args:
        tmp_path: pytest fixture for temporary directory.
    """
    detected = detect_release_from_branch(
        branch_name='feature/my-feature',
        projects=[],
    )

    assert detected is None


def test_detect_release_from_branch_monorepo_with_prefix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test detecting release from monorepo branch with tag prefix.

    Args:
        tmp_path: pytest fixture for temporary directory.
        monkeypatch: pytest fixture for patching.
    """
    # Create mock project
    project_dir = tmp_path / 'packages' / 'core'
    project_dir.mkdir(parents=True)
    changelog_dir = project_dir
    changelog_dir.mkdir(exist_ok=True)

    # Create SubProject with tag prefix
    subproject = SubProject(
        name='core',
        path=project_dir,
        changelog_path=project_dir / 'CHANGELOG.md',
        tag_prefix='core-',
        tag_pattern=r'^core-([0-9]+\.[0-9]+\.[0-9]+)$',
        alias_versions=ReleezSettings().alias_versions,
        hooks=ReleezSettings().hooks,
        include_paths=[],
    )

    detected = detect_release_from_branch(
        branch_name='release/core-1.2.3',
        projects=[subproject],
    )

    assert detected is not None
    assert detected.version == 'core-1.2.3'
    assert detected.project_name == 'core'
    assert detected.branch_name == 'release/core-1.2.3'


def test_detect_release_from_branch_monorepo_multiple_projects(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test detecting release with multiple projects configured.

    Args:
        tmp_path: pytest fixture for temporary directory.
        monkeypatch: pytest fixture for patching.
    """
    # Create mock projects
    core_dir = tmp_path / 'packages' / 'core'
    ui_dir = tmp_path / 'packages' / 'ui'
    core_dir.mkdir(parents=True)
    ui_dir.mkdir(parents=True)

    core_project = SubProject(
        name='core',
        path=core_dir,
        changelog_path=core_dir / 'CHANGELOG.md',
        tag_prefix='core-',
        tag_pattern=r'^core-([0-9]+\.[0-9]+\.[0-9]+)$',
        alias_versions=ReleezSettings().alias_versions,
        hooks=ReleezSettings().hooks,
        include_paths=[],
    )

    ui_project = SubProject(
        name='ui',
        path=ui_dir,
        changelog_path=ui_dir / 'CHANGELOG.md',
        tag_prefix='ui-',
        tag_pattern=r'^ui-([0-9]+\.[0-9]+\.[0-9]+)$',
        alias_versions=ReleezSettings().alias_versions,
        hooks=ReleezSettings().hooks,
        include_paths=[],
    )

    # Test detecting core release
    detected = detect_release_from_branch(
        branch_name='release/core-1.2.3',
        projects=[core_project, ui_project],
    )

    assert detected is not None
    assert detected.version == 'core-1.2.3'
    assert detected.project_name == 'core'

    # Test detecting ui release
    detected = detect_release_from_branch(
        branch_name='release/ui-4.5.6',
        projects=[core_project, ui_project],
    )

    assert detected is not None
    assert detected.version == 'ui-4.5.6'
    assert detected.project_name == 'ui'


def test_detect_release_from_branch_monorepo_no_matching_prefix(
    tmp_path: Path,
) -> None:
    """Test release branch with no matching project prefix.

    Args:
        tmp_path: pytest fixture for temporary directory.
    """
    core_dir = tmp_path / 'packages' / 'core'
    core_dir.mkdir(parents=True)

    core_project = SubProject(
        name='core',
        path=core_dir,
        changelog_path=core_dir / 'CHANGELOG.md',
        tag_prefix='core-',
        tag_pattern=r'^core-([0-9]+\.[0-9]+\.[0-9]+)$',
        alias_versions=ReleezSettings().alias_versions,
        hooks=ReleezSettings().hooks,
        include_paths=[],
    )

    # Release branch without matching prefix
    detected = detect_release_from_branch(
        branch_name='release/1.2.3',
        projects=[core_project],
    )

    assert detected is not None
    assert detected.version == '1.2.3'
    assert detected.project_name is None  # No matching project
