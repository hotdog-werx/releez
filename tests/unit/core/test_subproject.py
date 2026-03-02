from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from releez.settings import ProjectConfig, ReleezHooks, ReleezSettings
from releez.subproject import (
    MonorepoValidationError,
    SubProject,
    generate_tag_pattern,
    validate_projects,
)
from releez.version_tags import AliasVersions

if TYPE_CHECKING:
    from pathlib import Path


def test_generate_tag_pattern_with_prefix() -> None:
    """Test tag pattern generation with various prefixes."""
    assert generate_tag_pattern('core-') == r'^core-([0-9]+\.[0-9]+\.[0-9]+)$'
    assert generate_tag_pattern('ui-') == r'^ui-([0-9]+\.[0-9]+\.[0-9]+)$'
    assert generate_tag_pattern('api/v2-') == r'^api/v2-([0-9]+\.[0-9]+\.[0-9]+)$'


def test_generate_tag_pattern_without_prefix() -> None:
    """Test tag pattern generation without prefix (single-repo mode)."""
    assert generate_tag_pattern('') == r'^([0-9]+\.[0-9]+\.[0-9]+)$'


def test_generate_tag_pattern_invalid_characters() -> None:
    """Test that invalid characters in tag prefix raise an error."""
    with pytest.raises(MonorepoValidationError, match='Invalid tag prefix'):
        generate_tag_pattern('core@')

    with pytest.raises(MonorepoValidationError, match='Invalid tag prefix'):
        generate_tag_pattern('ui!')

    with pytest.raises(MonorepoValidationError, match='Invalid tag prefix'):
        generate_tag_pattern('api#v2-')


def test_subproject_from_config_basic(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test SubProject creation from basic config."""
    # Setup directory structure
    monkeypatch.chdir(tmp_path)
    project_dir = tmp_path / 'packages' / 'core'
    project_dir.mkdir(parents=True)

    config = ProjectConfig(
        name='core',
        path='packages/core',
        tag_prefix='core-',
    )
    settings = ReleezSettings()

    subproject = SubProject.from_config(config, tmp_path, settings)

    assert subproject.name == 'core'
    assert subproject.path == project_dir
    assert subproject.changelog_path == project_dir / 'CHANGELOG.md'
    assert subproject.tag_prefix == 'core-'
    assert subproject.tag_pattern == r'^core-([0-9]+\.[0-9]+\.[0-9]+)$'
    assert subproject.alias_versions == AliasVersions.none  # From global settings
    assert subproject.include_paths == []


def test_subproject_from_config_with_include_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test SubProject creation with include_paths."""
    monkeypatch.chdir(tmp_path)
    project_dir = tmp_path / 'packages' / 'core'
    project_dir.mkdir(parents=True)

    # Create files that will be in include_paths
    (tmp_path / 'pyproject.toml').write_text('[tool.releez]\n')
    (tmp_path / 'uv.lock').write_text('# lockfile\n')

    config = ProjectConfig(
        name='core',
        path='packages/core',
        tag_prefix='core-',
        include_paths=['pyproject.toml', 'uv.lock'],
    )
    settings = ReleezSettings()

    subproject = SubProject.from_config(config, tmp_path, settings)

    assert subproject.include_paths == ['pyproject.toml', 'uv.lock']


def test_subproject_from_config_override_alias_versions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that project can override global alias_versions."""
    monkeypatch.chdir(tmp_path)
    project_dir = tmp_path / 'packages' / 'core'
    project_dir.mkdir(parents=True)

    config = ProjectConfig(
        name='core',
        path='packages/core',
        tag_prefix='core-',
        alias_versions=AliasVersions.major,
    )
    settings = ReleezSettings(alias_versions=AliasVersions.minor)

    subproject = SubProject.from_config(config, tmp_path, settings)

    assert subproject.alias_versions == AliasVersions.major  # Overridden


def test_subproject_from_config_merges_hooks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that project hooks are merged with global hooks."""
    monkeypatch.chdir(tmp_path)
    project_dir = tmp_path / 'packages' / 'core'
    project_dir.mkdir(parents=True)

    global_hooks = ReleezHooks(
        post_changelog=[['prettier', '--write', '{changelog}']],
    )
    project_hooks = ReleezHooks(
        post_changelog=[['uv', 'version', '{version}']],
    )

    config = ProjectConfig(
        name='core',
        path='packages/core',
        tag_prefix='core-',
        hooks=project_hooks,
    )
    settings = ReleezSettings(hooks=global_hooks)

    subproject = SubProject.from_config(config, tmp_path, settings)

    # Should have both global and project hooks
    assert len(subproject.hooks.post_changelog) == 2
    assert subproject.hooks.post_changelog[0] == [
        'prettier',
        '--write',
        '{changelog}',
    ]
    assert subproject.hooks.post_changelog[1] == ['uv', 'version', '{version}']


def test_subproject_from_config_project_path_not_found(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test error when project path doesn't exist."""
    monkeypatch.chdir(tmp_path)

    config = ProjectConfig(
        name='core',
        path='packages/core',  # Doesn't exist
        tag_prefix='core-',
    )
    settings = ReleezSettings()

    with pytest.raises(MonorepoValidationError, match='does not exist'):
        SubProject.from_config(config, tmp_path, settings)


def test_subproject_from_config_project_path_not_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test error when project path is a file, not a directory."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / 'not_a_dir').write_text('file')

    config = ProjectConfig(
        name='core',
        path='not_a_dir',
        tag_prefix='core-',
    )
    settings = ReleezSettings()

    with pytest.raises(MonorepoValidationError, match='not a directory'):
        SubProject.from_config(config, tmp_path, settings)


def test_subproject_from_config_project_path_outside_repo(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test error when project path is outside repository."""
    monkeypatch.chdir(tmp_path)
    outside_dir = tmp_path.parent / 'outside'
    outside_dir.mkdir()

    config = ProjectConfig(
        name='core',
        path=str(outside_dir),  # Absolute path outside repo
        tag_prefix='core-',
    )
    settings = ReleezSettings()

    with pytest.raises(MonorepoValidationError, match='outside repository'):
        SubProject.from_config(config, tmp_path, settings)


def test_subproject_from_config_changelog_dir_not_found(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test error when changelog directory doesn't exist."""
    monkeypatch.chdir(tmp_path)
    project_dir = tmp_path / 'packages' / 'core'
    project_dir.mkdir(parents=True)

    config = ProjectConfig(
        name='core',
        path='packages/core',
        changelog_path='nonexistent/CHANGELOG.md',  # Directory doesn't exist
        tag_prefix='core-',
    )
    settings = ReleezSettings()

    with pytest.raises(
        MonorepoValidationError,
        match='changelog directory does not exist',
    ):
        SubProject.from_config(config, tmp_path, settings)


def test_subproject_from_config_include_path_not_found_is_allowed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-existent include paths are allowed — they simply match no commits."""
    monkeypatch.chdir(tmp_path)
    project_dir = tmp_path / 'packages' / 'core'
    project_dir.mkdir(parents=True)

    config = ProjectConfig(
        name='core',
        path='packages/core',
        tag_prefix='core-',
        include_paths=['nonexistent.toml'],
    )
    settings = ReleezSettings()

    # Should not raise — missing file just matches no commits
    subproject = SubProject.from_config(config, tmp_path, settings)
    assert subproject.include_paths == ['nonexistent.toml']


def test_subproject_from_config_include_path_outside_repo(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test error when include_path is outside repository."""
    monkeypatch.chdir(tmp_path)
    project_dir = tmp_path / 'packages' / 'core'
    project_dir.mkdir(parents=True)

    outside_file = tmp_path.parent / 'outside.toml'
    outside_file.write_text('')

    config = ProjectConfig(
        name='core',
        path='packages/core',
        tag_prefix='core-',
        include_paths=[str(outside_file)],
    )
    settings = ReleezSettings()

    with pytest.raises(
        MonorepoValidationError,
        match='include-path is outside repository',
    ):
        SubProject.from_config(config, tmp_path, settings)


def test_validate_projects_no_duplicates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test validation passes with no duplicate names or prefixes."""
    monkeypatch.chdir(tmp_path)

    # Create projects
    (tmp_path / 'core').mkdir()
    (tmp_path / 'ui').mkdir()

    projects = [
        SubProject(
            name='core',
            path=tmp_path / 'core',
            changelog_path=tmp_path / 'core' / 'CHANGELOG.md',
            tag_prefix='core-',
            tag_pattern=r'^core-([0-9]+\.[0-9]+\.[0-9]+)$',
            alias_versions=AliasVersions.none,
            hooks=ReleezSettings().hooks,
            include_paths=[],
        ),
        SubProject(
            name='ui',
            path=tmp_path / 'ui',
            changelog_path=tmp_path / 'ui' / 'CHANGELOG.md',
            tag_prefix='ui-',
            tag_pattern=r'^ui-([0-9]+\.[0-9]+\.[0-9]+)$',
            alias_versions=AliasVersions.none,
            hooks=ReleezSettings().hooks,
            include_paths=[],
        ),
    ]

    # Should not raise
    validate_projects(projects)


def test_validate_projects_duplicate_names(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test validation fails with duplicate project names."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / 'core1').mkdir()
    (tmp_path / 'core2').mkdir()

    projects = [
        SubProject(
            name='core',  # Duplicate
            path=tmp_path / 'core1',
            changelog_path=tmp_path / 'core1' / 'CHANGELOG.md',
            tag_prefix='core1-',
            tag_pattern=r'^core1-([0-9]+\.[0-9]+\.[0-9]+)$',
            alias_versions=AliasVersions.none,
            hooks=ReleezSettings().hooks,
            include_paths=[],
        ),
        SubProject(
            name='core',  # Duplicate
            path=tmp_path / 'core2',
            changelog_path=tmp_path / 'core2' / 'CHANGELOG.md',
            tag_prefix='core2-',
            tag_pattern=r'^core2-([0-9]+\.[0-9]+\.[0-9]+)$',
            alias_versions=AliasVersions.none,
            hooks=ReleezSettings().hooks,
            include_paths=[],
        ),
    ]

    with pytest.raises(
        MonorepoValidationError,
        match='Duplicate project names',
    ):
        validate_projects(projects)


def test_validate_projects_duplicate_tag_prefixes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test validation fails with duplicate tag prefixes."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / 'core1').mkdir()
    (tmp_path / 'core2').mkdir()

    projects = [
        SubProject(
            name='core1',
            path=tmp_path / 'core1',
            changelog_path=tmp_path / 'core1' / 'CHANGELOG.md',
            tag_prefix='core-',  # Duplicate
            tag_pattern=r'^core-([0-9]+\.[0-9]+\.[0-9]+)$',
            alias_versions=AliasVersions.none,
            hooks=ReleezSettings().hooks,
            include_paths=[],
        ),
        SubProject(
            name='core2',
            path=tmp_path / 'core2',
            changelog_path=tmp_path / 'core2' / 'CHANGELOG.md',
            tag_prefix='core-',  # Duplicate
            tag_pattern=r'^core-([0-9]+\.[0-9]+\.[0-9]+)$',
            alias_versions=AliasVersions.none,
            hooks=ReleezSettings().hooks,
            include_paths=[],
        ),
    ]

    with pytest.raises(MonorepoValidationError, match='Duplicate tag prefixes'):
        validate_projects(projects)


def test_validate_projects_overlapping_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test validation fails when project paths overlap."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / 'packages').mkdir()
    (tmp_path / 'packages' / 'core').mkdir()

    projects = [
        SubProject(
            name='parent',
            path=tmp_path / 'packages',  # Parent
            changelog_path=tmp_path / 'packages' / 'CHANGELOG.md',
            tag_prefix='parent-',
            tag_pattern=r'^parent-([0-9]+\.[0-9]+\.[0-9]+)$',
            alias_versions=AliasVersions.none,
            hooks=ReleezSettings().hooks,
            include_paths=[],
        ),
        SubProject(
            name='child',
            path=tmp_path / 'packages' / 'core',  # Child
            changelog_path=tmp_path / 'packages' / 'core' / 'CHANGELOG.md',
            tag_prefix='child-',
            tag_pattern=r'^child-([0-9]+\.[0-9]+\.[0-9]+)$',
            alias_versions=AliasVersions.none,
            hooks=ReleezSettings().hooks,
            include_paths=[],
        ),
    ]

    with pytest.raises(MonorepoValidationError, match='Project paths overlap'):
        validate_projects(projects)


def test_validate_projects_overlapping_paths_reverse_order(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test validation fails when child path is listed before parent path.

    Exercises the reverse overlap check (path1.relative_to(path2)).

    Args:
        tmp_path: pytest fixture for temporary directory.
        monkeypatch: pytest fixture for patching.
    """
    monkeypatch.chdir(tmp_path)
    (tmp_path / 'packages').mkdir()
    (tmp_path / 'packages' / 'core').mkdir()

    # Child listed first, parent second — triggers the reverse check
    projects = [
        SubProject(
            name='child',
            path=tmp_path / 'packages' / 'core',
            changelog_path=tmp_path / 'packages' / 'core' / 'CHANGELOG.md',
            tag_prefix='child-',
            tag_pattern=r'^child-([0-9]+\.[0-9]+\.[0-9]+)$',
            alias_versions=AliasVersions.none,
            hooks=ReleezSettings().hooks,
            include_paths=[],
        ),
        SubProject(
            name='parent',
            path=tmp_path / 'packages',
            changelog_path=tmp_path / 'packages' / 'CHANGELOG.md',
            tag_prefix='parent-',
            tag_pattern=r'^parent-([0-9]+\.[0-9]+\.[0-9]+)$',
            alias_versions=AliasVersions.none,
            hooks=ReleezSettings().hooks,
            include_paths=[],
        ),
    ]

    with pytest.raises(MonorepoValidationError, match='Project paths overlap'):
        validate_projects(projects)


def test_validate_projects_empty_list(tmp_path: Path) -> None:
    """Test validation passes with empty project list."""
    # Should not raise
    validate_projects([])
