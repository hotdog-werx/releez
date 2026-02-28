"""Integration tests for monorepo workflow."""

from __future__ import annotations

from typing import TYPE_CHECKING

from git import Repo

from releez.git_repo import detect_changed_projects, open_repo
from releez.settings import ReleezSettings
from releez.subproject import SubProject

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def test_monorepo_detect_and_release_workflow(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test full workflow: configure monorepo, detect changes, release a project."""
    monkeypatch.chdir(tmp_path)

    # Setup monorepo structure
    core_dir = tmp_path / 'packages' / 'core'
    ui_dir = tmp_path / 'packages' / 'ui'
    core_dir.mkdir(parents=True)
    ui_dir.mkdir(parents=True)

    # Create pyproject.toml with monorepo config
    config = """
[tool.releez]
base-branch = "main"
git-remote = "origin"

[[tool.releez.projects]]
name = "core"
path = "packages/core"
changelog-path = "CHANGELOG.md"
tag-prefix = "core-"

[[tool.releez.projects]]
name = "ui"
path = "packages/ui"
changelog-path = "CHANGELOG.md"
tag-prefix = "ui-"
"""
    (tmp_path / 'pyproject.toml').write_text(config)

    # Initialize git repo
    repo = Repo.init(tmp_path)
    repo.config_writer().set_value('user', 'name', 'Test User').release()
    repo.config_writer().set_value(
        'user',
        'email',
        'test@example.com',
    ).release()

    # Create initial commit
    (core_dir / 'main.py').write_text('print("core v1")')
    (ui_dir / 'index.js').write_text('console.log("ui v1")')
    (core_dir / 'CHANGELOG.md').write_text('# Core Changelog\n\n')
    (ui_dir / 'CHANGELOG.md').write_text('# UI Changelog\n\n')

    repo.index.add(
        [
            'packages/core/main.py',
            'packages/ui/index.js',
            'packages/core/CHANGELOG.md',
            'packages/ui/CHANGELOG.md',
            'pyproject.toml',
        ],
    )
    repo.index.commit('feat: initial commit')
    repo.create_tag('core-1.0.0')
    repo.create_tag('ui-1.0.0')

    # Make changes only to core
    (core_dir / 'main.py').write_text('print("core v2")')
    (core_dir / 'new.py').write_text('print("new feature")')
    repo.index.add(['packages/core/main.py', 'packages/core/new.py'])
    repo.index.commit('feat(core): add new feature')

    # Load settings and create SubProjects
    settings = ReleezSettings()
    assert len(settings.projects) == 2

    repo_obj, info = open_repo(cwd=tmp_path)
    subprojects = [
        SubProject.from_config(
            config,
            repo_root=info.root,
            global_settings=settings,
        )
        for config in settings.projects
    ]

    # Detect changed projects
    changed = detect_changed_projects(
        repo=repo_obj,
        base_branch='HEAD',
        projects=subprojects,
    )

    # Only core should have changed
    assert len(changed) == 1
    assert changed[0].name == 'core'
    assert changed[0].tag_prefix == 'core-'

    # Verify the SubProject was created correctly
    core_project = changed[0]
    assert core_project.path == core_dir
    assert core_project.changelog_path == core_dir / 'CHANGELOG.md'
    assert core_project.tag_pattern == r'^core-([0-9]+\.[0-9]+\.[0-9]+)$'


def test_monorepo_multiple_projects_changed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test detecting changes across multiple projects."""
    monkeypatch.chdir(tmp_path)

    # Setup monorepo
    core_dir = tmp_path / 'packages' / 'core'
    ui_dir = tmp_path / 'packages' / 'ui'
    core_dir.mkdir(parents=True)
    ui_dir.mkdir(parents=True)

    config = """
[tool.releez]
base-branch = "main"

[[tool.releez.projects]]
name = "core"
path = "packages/core"
tag-prefix = "core-"

[[tool.releez.projects]]
name = "ui"
path = "packages/ui"
tag-prefix = "ui-"
"""
    (tmp_path / 'pyproject.toml').write_text(config)

    repo = Repo.init(tmp_path)
    repo.config_writer().set_value('user', 'name', 'Test User').release()
    repo.config_writer().set_value(
        'user',
        'email',
        'test@example.com',
    ).release()

    # Initial commits and tags
    (core_dir / 'main.py').write_text('core')
    (ui_dir / 'index.js').write_text('ui')
    repo.index.add(
        ['packages/core/main.py', 'packages/ui/index.js', 'pyproject.toml'],
    )
    repo.index.commit('initial')
    repo.create_tag('core-1.0.0')
    repo.create_tag('ui-1.0.0')

    # Change both projects
    (core_dir / 'main.py').write_text('core v2')
    (ui_dir / 'index.js').write_text('ui v2')
    repo.index.add(['packages/core/main.py', 'packages/ui/index.js'])
    repo.index.commit('update both')

    # Detect changes
    settings = ReleezSettings()
    repo_obj, info = open_repo(cwd=tmp_path)
    subprojects = [
        SubProject.from_config(
            config,
            repo_root=info.root,
            global_settings=settings,
        )
        for config in settings.projects
    ]

    changed = detect_changed_projects(
        repo=repo_obj,
        base_branch='HEAD',
        projects=subprojects,
    )

    # Both should be changed
    assert len(changed) == 2
    changed_names = {p.name for p in changed}
    assert changed_names == {'core', 'ui'}


def test_monorepo_include_paths_triggers_release(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that changes to include_paths trigger project detection."""
    monkeypatch.chdir(tmp_path)

    core_dir = tmp_path / 'packages' / 'core'
    core_dir.mkdir(parents=True)

    # Core monitors root pyproject.toml
    config = """
[tool.releez]
base-branch = "main"

[[tool.releez.projects]]
name = "core"
path = "packages/core"
tag-prefix = "core-"
include-paths = ["pyproject.toml", "uv.lock"]
"""
    (tmp_path / 'pyproject.toml').write_text(config)
    (tmp_path / 'uv.lock').write_text('# lock file v1')

    repo = Repo.init(tmp_path)
    repo.config_writer().set_value('user', 'name', 'Test User').release()
    repo.config_writer().set_value(
        'user',
        'email',
        'test@example.com',
    ).release()

    # Initial commit
    (core_dir / 'main.py').write_text('core')
    repo.index.add(['packages/core/main.py', 'pyproject.toml', 'uv.lock'])
    repo.index.commit('initial')
    repo.create_tag('core-1.0.0')

    # Change only uv.lock (monitored file)
    (tmp_path / 'uv.lock').write_text('# lock file v2')
    repo.index.add(['uv.lock'])
    repo.index.commit('update lock file')

    # Detect changes
    settings = ReleezSettings()
    repo_obj, info = open_repo(cwd=tmp_path)
    subprojects = [
        SubProject.from_config(
            config,
            repo_root=info.root,
            global_settings=settings,
        )
        for config in settings.projects
    ]

    changed = detect_changed_projects(
        repo=repo_obj,
        base_branch='HEAD',
        projects=subprojects,
    )

    # Core should be detected due to uv.lock change
    assert len(changed) == 1
    assert changed[0].name == 'core'
