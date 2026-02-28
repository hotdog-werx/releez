"""CLI integration tests that exercise real git repositories and command flows."""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING

from git import Repo
from typer.testing import CliRunner

from releez import cli
from releez.release import StartReleaseInput, start_release

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def _init_repo(tmp_path: Path) -> Repo:
    repo = Repo.init(tmp_path)
    repo.config_writer().set_value('user', 'name', 'Test User').release()
    repo.config_writer().set_value(
        'user',
        'email',
        'test@example.com',
    ).release()
    if repo.active_branch.name != 'master':
        repo.git.branch('-M', 'master')
    return repo


def _add_origin_remote(repo: Repo, tmp_path: Path) -> Path:
    remote_path = tmp_path.parent / f'{tmp_path.name}-origin.git'
    Repo.init(remote_path, bare=True)
    repo.create_remote('origin', str(remote_path))
    repo.git.push('-u', 'origin', 'master')
    return remote_path


def _init_two_project_monorepo_repo(
    tmp_path: Path,
    *,
    alias_versions: str | None = None,
) -> tuple[Repo, Path, Path]:
    core_dir = tmp_path / 'packages' / 'core'
    ui_dir = tmp_path / 'packages' / 'ui'
    core_dir.mkdir(parents=True)
    ui_dir.mkdir(parents=True)

    core_alias = f'\nalias-versions = "{alias_versions}"' if alias_versions else ''
    ui_alias = f'\nalias-versions = "{alias_versions}"' if alias_versions else ''
    (tmp_path / 'pyproject.toml').write_text(
        f"""
[tool.releez]
base-branch = "master"
git-remote = "origin"
create-pr = false

[[tool.releez.projects]]
name = "core"
path = "packages/core"
changelog-path = "CHANGELOG.md"
tag-prefix = "core-"{core_alias}

[[tool.releez.projects]]
name = "ui"
path = "packages/ui"
changelog-path = "CHANGELOG.md"
tag-prefix = "ui-"{ui_alias}
""".strip(),
        encoding='utf-8',
    )

    (core_dir / 'CHANGELOG.md').write_text(
        '# Core Changelog\n\n',
        encoding='utf-8',
    )
    (ui_dir / 'CHANGELOG.md').write_text('# UI Changelog\n\n', encoding='utf-8')
    (core_dir / 'main.py').write_text('print("core v1")\n', encoding='utf-8')
    (ui_dir / 'main.py').write_text('print("ui v1")\n', encoding='utf-8')

    repo = _init_repo(tmp_path)
    repo.index.add(
        [
            'packages/core/CHANGELOG.md',
            'packages/core/main.py',
            'packages/ui/CHANGELOG.md',
            'packages/ui/main.py',
            'pyproject.toml',
        ],
    )
    repo.index.commit('feat: initial monorepo state')
    repo.create_tag('core-1.0.0')
    repo.create_tag('ui-1.0.0')

    return repo, core_dir, ui_dir


def test_cli_projects_changed_integration_with_real_repo(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test `projects changed` against a real monorepo checkout."""
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()

    core_dir = tmp_path / 'packages' / 'core'
    ui_dir = tmp_path / 'packages' / 'ui'
    core_dir.mkdir(parents=True)
    ui_dir.mkdir(parents=True)

    (tmp_path / 'pyproject.toml').write_text(
        """
[tool.releez]
base-branch = "master"
create-pr = false

[[tool.releez.projects]]
name = "core"
path = "packages/core"
tag-prefix = "core-"

[[tool.releez.projects]]
name = "ui"
path = "packages/ui"
tag-prefix = "ui-"
""".strip(),
        encoding='utf-8',
    )

    repo = _init_repo(tmp_path)
    (core_dir / 'main.py').write_text('print("core v1")\n', encoding='utf-8')
    (ui_dir / 'index.js').write_text('console.log("ui v1")\n', encoding='utf-8')
    repo.index.add(
        ['packages/core/main.py', 'packages/ui/index.js', 'pyproject.toml'],
    )
    repo.index.commit('feat: initial monorepo state')
    repo.create_tag('core-1.0.0')
    repo.create_tag('ui-1.0.0')

    (core_dir / 'main.py').write_text('print("core v2")\n', encoding='utf-8')
    repo.index.add(['packages/core/main.py'])
    repo.index.commit('feat(core): add feature')

    result = runner.invoke(
        cli.app,
        ['projects', 'changed', '--format', 'json', '--base', 'HEAD'],
    )

    assert result.exit_code == 0
    output = json.loads(result.stdout)
    assert output['projects'] == ['core']
    assert all(project != 'ui' for project in output['projects'])


def test_cli_release_detect_from_branch_integration_with_projects_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test `release detect-from-branch` with real monorepo config and repo."""
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()

    core_dir = tmp_path / 'packages' / 'core'
    core_dir.mkdir(parents=True)

    (tmp_path / 'pyproject.toml').write_text(
        """
[tool.releez]
base-branch = "master"
create-pr = false

[[tool.releez.projects]]
name = "core"
path = "packages/core"
changelog-path = "CHANGELOG.md"
tag-prefix = "core-"
""".strip(),
        encoding='utf-8',
    )
    (core_dir / 'CHANGELOG.md').write_text('# Changelog\n\n', encoding='utf-8')
    (core_dir / 'main.py').write_text('print("hello")\n', encoding='utf-8')

    repo = _init_repo(tmp_path)
    repo.index.add(
        [
            'packages/core/CHANGELOG.md',
            'packages/core/main.py',
            'pyproject.toml',
        ],
    )
    repo.index.commit('feat(core): initial commit')

    result = runner.invoke(
        cli.app,
        ['release', 'detect-from-branch', '--branch', 'release/core-1.2.3'],
    )

    assert result.exit_code == 0
    output = json.loads(result.stdout)
    assert output['version'] == 'core-1.2.3'
    assert output['project'] == 'core'
    assert output['branch'] == 'release/core-1.2.3'


def test_cli_release_start_dry_run_integration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test dry-run release start via CLI against a real repository."""
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()

    (tmp_path / 'pyproject.toml').write_text(
        """
[tool.releez]
base-branch = "master"
git-remote = "origin"
create-pr = false
""".strip(),
        encoding='utf-8',
    )
    (tmp_path / 'CHANGELOG.md').write_text('# Changelog\n\n', encoding='utf-8')
    (tmp_path / 'app.py').write_text('print("v1")\n', encoding='utf-8')

    repo = _init_repo(tmp_path)
    repo.index.add(['CHANGELOG.md', 'app.py', 'pyproject.toml'])
    repo.index.commit('feat: initial release')
    repo.create_tag('1.0.0')

    (tmp_path / 'app.py').write_text('print("v2")\n', encoding='utf-8')
    repo.index.add(['app.py'])
    repo.index.commit('feat: add new capability')

    _add_origin_remote(repo, tmp_path)

    result = runner.invoke(
        cli.app,
        [
            'release',
            'start',
            '--dry-run',
            '--no-create-pr',
            '--version-override',
            '1.1.0',
        ],
    )

    assert result.exit_code == 0
    assert 'Next version:' in result.output
    assert '1.1.0' in result.output
    assert 'Release branch:' not in result.output
    assert repo.active_branch.name == 'master'


def test_cli_release_start_creates_and_pushes_release_branch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test non-dry-run release start creates and pushes release branch via CLI."""
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()

    (tmp_path / 'pyproject.toml').write_text(
        """
[tool.releez]
base-branch = "master"
git-remote = "origin"
create-pr = false
""".strip(),
        encoding='utf-8',
    )
    (tmp_path / 'CHANGELOG.md').write_text('# Changelog\n\n', encoding='utf-8')
    (tmp_path / 'app.py').write_text('print("v1")\n', encoding='utf-8')

    repo = _init_repo(tmp_path)
    repo.index.add(['CHANGELOG.md', 'app.py', 'pyproject.toml'])
    repo.index.commit('feat: initial release')
    repo.create_tag('1.0.0')

    (tmp_path / 'app.py').write_text('print("v2")\n', encoding='utf-8')
    repo.index.add(['app.py'])
    repo.index.commit('feat: ship feature')

    _add_origin_remote(repo, tmp_path)

    result = runner.invoke(
        cli.app,
        ['release', 'start', '--no-create-pr', '--version-override', '1.1.0'],
    )

    assert result.exit_code == 0
    assert 'Next version:' in result.output
    assert 'Release branch:' in result.output
    assert 'release/1.1.0' in result.output
    assert 'release/1.1.0' in {branch.name for branch in repo.branches}

    pushed = repo.git.ls_remote('--heads', 'origin', 'release/1.1.0')
    assert 'refs/heads/release/1.1.0' in pushed


def test_cli_release_start_monorepo_project_creates_project_branch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test `release start --project` runs a real scoped monorepo release."""
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()

    core_dir = tmp_path / 'packages' / 'core'
    ui_dir = tmp_path / 'packages' / 'ui'
    core_dir.mkdir(parents=True)
    ui_dir.mkdir(parents=True)

    (tmp_path / 'pyproject.toml').write_text(
        """
[tool.releez]
base-branch = "master"
git-remote = "origin"
create-pr = false

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
""".strip(),
        encoding='utf-8',
    )
    (core_dir / 'CHANGELOG.md').write_text(
        '# Core Changelog\n\n',
        encoding='utf-8',
    )
    (ui_dir / 'CHANGELOG.md').write_text('# UI Changelog\n\n', encoding='utf-8')
    (core_dir / 'main.py').write_text('print("core v1")\n', encoding='utf-8')
    (ui_dir / 'main.py').write_text('print("ui v1")\n', encoding='utf-8')

    repo = _init_repo(tmp_path)
    repo.index.add(
        [
            'packages/core/CHANGELOG.md',
            'packages/core/main.py',
            'packages/ui/CHANGELOG.md',
            'packages/ui/main.py',
            'pyproject.toml',
        ],
    )
    repo.index.commit('feat: initial monorepo state')
    repo.create_tag('core-1.0.0')
    repo.create_tag('ui-1.0.0')

    (core_dir / 'main.py').write_text('print("core v2")\n', encoding='utf-8')
    repo.index.add(['packages/core/main.py'])
    repo.index.commit('feat(core): new feature')
    _add_origin_remote(repo, tmp_path)

    result = runner.invoke(
        cli.app,
        [
            'release',
            'start',
            '--project',
            'core',
            '--no-create-pr',
            '--version-override',
            'core-1.1.0',
        ],
    )

    assert result.exit_code == 0
    assert '[core] Next version: core-1.1.0' in result.output
    assert '[core] Release branch: release/core-1.1.0' in result.output
    assert 'release/core-1.1.0' in {branch.name for branch in repo.branches}
    pushed = repo.git.ls_remote('--heads', 'origin', 'release/core-1.1.0')
    assert 'refs/heads/release/core-1.1.0' in pushed


def test_cli_release_start_monorepo_autodetects_multiple_projects(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test monorepo `release start` auto-detects and releases all changed projects."""
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()

    core_dir = tmp_path / 'packages' / 'core'
    ui_dir = tmp_path / 'packages' / 'ui'
    core_dir.mkdir(parents=True)
    ui_dir.mkdir(parents=True)

    (tmp_path / 'pyproject.toml').write_text(
        """
[tool.releez]
base-branch = "master"
git-remote = "origin"
create-pr = false

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
""".strip(),
        encoding='utf-8',
    )
    (core_dir / 'CHANGELOG.md').write_text(
        '# Core Changelog\n\n',
        encoding='utf-8',
    )
    (ui_dir / 'CHANGELOG.md').write_text('# UI Changelog\n\n', encoding='utf-8')
    (core_dir / 'main.py').write_text('print("core v1")\n', encoding='utf-8')
    (ui_dir / 'main.py').write_text('print("ui v1")\n', encoding='utf-8')

    repo = _init_repo(tmp_path)
    repo.index.add(
        [
            'packages/core/CHANGELOG.md',
            'packages/core/main.py',
            'packages/ui/CHANGELOG.md',
            'packages/ui/main.py',
            'pyproject.toml',
        ],
    )
    repo.index.commit('feat: initial monorepo state')
    repo.create_tag('core-1.0.0')
    repo.create_tag('ui-1.0.0')

    (core_dir / 'main.py').write_text('print("core v2")\n', encoding='utf-8')
    repo.index.add(['packages/core/main.py'])
    repo.index.commit('feat(core): new feature')
    (ui_dir / 'main.py').write_text('print("ui v2")\n', encoding='utf-8')
    repo.index.add(['packages/ui/main.py'])
    repo.index.commit('feat(ui): new feature')
    _add_origin_remote(repo, tmp_path)

    result = runner.invoke(
        cli.app,
        ['release', 'start', '--no-create-pr'],
    )

    assert result.exit_code == 0
    assert 'Detected changed projects:' in result.output
    assert 'Release summary: 2 succeeded, 0 failed.' in result.output

    local_branch_names = {branch.name for branch in repo.branches}
    assert any(name.startswith('release/core-') for name in local_branch_names)
    assert any(name.startswith('release/ui-') for name in local_branch_names)

    remote_heads = repo.git.ls_remote('--heads', 'origin')
    assert 'refs/heads/release/core-' in remote_heads
    assert 'refs/heads/release/ui-' in remote_heads


def test_cli_release_start_monorepo_autodetect_no_changes_exits_non_zero(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test monorepo `release start` exits non-zero when no projects changed."""
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()

    core_dir = tmp_path / 'packages' / 'core'
    ui_dir = tmp_path / 'packages' / 'ui'
    core_dir.mkdir(parents=True)
    ui_dir.mkdir(parents=True)

    (tmp_path / 'pyproject.toml').write_text(
        """
[tool.releez]
base-branch = "master"
git-remote = "origin"
create-pr = false

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
""".strip(),
        encoding='utf-8',
    )
    (core_dir / 'CHANGELOG.md').write_text(
        '# Core Changelog\n\n',
        encoding='utf-8',
    )
    (ui_dir / 'CHANGELOG.md').write_text('# UI Changelog\n\n', encoding='utf-8')
    (core_dir / 'main.py').write_text('print("core v1")\n', encoding='utf-8')
    (ui_dir / 'main.py').write_text('print("ui v1")\n', encoding='utf-8')

    repo = _init_repo(tmp_path)
    repo.index.add(
        [
            'packages/core/CHANGELOG.md',
            'packages/core/main.py',
            'packages/ui/CHANGELOG.md',
            'packages/ui/main.py',
            'pyproject.toml',
        ],
    )
    repo.index.commit('feat: initial monorepo state')
    repo.create_tag('core-1.0.0')
    repo.create_tag('ui-1.0.0')

    result = runner.invoke(
        cli.app,
        ['release', 'start', '--no-create-pr'],
    )

    assert result.exit_code == 1
    assert 'No projects with unreleased changes were detected.' in result.output
    assert {branch.name for branch in repo.branches} == {'master'}


def test_cli_release_commands_reject_unknown_project_name(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression guard: unknown --project values must hard fail across release commands."""
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    _init_two_project_monorepo_repo(tmp_path)

    for args in [
        ['release', 'start', '--project', 'does-not-exist', '--no-create-pr'],
        ['release', 'tag', '--project', 'does-not-exist'],
        ['release', 'preview', '--project', 'does-not-exist'],
        ['release', 'notes', '--project', 'does-not-exist'],
    ]:
        result = runner.invoke(cli.app, args)
        assert result.exit_code == 1
        assert 'Unknown project "does-not-exist"' in result.output
        assert 'Available projects: core, ui' in result.output


def test_cli_release_commands_reject_project_and_all_combination(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression guard: --project and --all together must fail to prevent ambiguous targeting."""
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    _init_two_project_monorepo_repo(tmp_path)

    for args in [
        ['release', 'start', '--project', 'core', '--all', '--no-create-pr'],
        ['release', 'tag', '--project', 'core', '--all'],
        ['release', 'preview', '--project', 'core', '--all'],
        ['release', 'notes', '--project', 'core', '--all'],
    ]:
        result = runner.invoke(cli.app, args)
        assert result.exit_code == 1
        assert 'Cannot use --project and --all together.' in result.output


def test_cli_release_commands_reject_monorepo_flags_in_single_repo_mode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression guard: monorepo-only selectors must fail clearly when projects are not configured."""
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()

    (tmp_path / 'pyproject.toml').write_text(
        """
[tool.releez]
base-branch = "master"
git-remote = "origin"
create-pr = false
""".strip(),
        encoding='utf-8',
    )
    (tmp_path / 'app.py').write_text('print("hello")\n', encoding='utf-8')
    repo = _init_repo(tmp_path)
    repo.index.add(['app.py', 'pyproject.toml'])
    repo.index.commit('feat: initial commit')

    for args in [
        ['release', 'start', '--project', 'core', '--no-create-pr'],
        ['release', 'start', '--all', '--no-create-pr'],
        ['release', 'tag', '--project', 'core'],
        ['release', 'tag', '--all'],
        ['release', 'preview', '--project', 'core'],
        ['release', 'preview', '--all'],
        ['release', 'notes', '--project', 'core'],
        ['release', 'notes', '--all'],
    ]:
        result = runner.invoke(cli.app, args)
        assert result.exit_code == 1
        assert 'No projects are configured. Remove --project/--all' in result.output


def test_cli_release_detect_from_branch_single_repo_current_branch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test single-repo branch detection using the real current git branch."""
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()

    (tmp_path / 'pyproject.toml').write_text(
        """
[tool.releez]
base-branch = "master"
create-pr = false
""".strip(),
        encoding='utf-8',
    )
    (tmp_path / 'app.py').write_text('print("hello")\n', encoding='utf-8')

    repo = _init_repo(tmp_path)
    repo.index.add(['app.py', 'pyproject.toml'])
    repo.index.commit('feat: initial commit')
    repo.git.checkout('-b', 'release/1.2.3')

    result = runner.invoke(cli.app, ['release', 'detect-from-branch'])

    assert result.exit_code == 0
    output = json.loads(result.stdout)
    assert output['version'] == '1.2.3'
    assert output['branch'] == 'release/1.2.3'
    assert 'project' not in output


def test_cli_projects_changed_single_repo_reports_not_configured(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test `projects changed` exits in single-repo mode with no project config."""
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()

    (tmp_path / 'pyproject.toml').write_text(
        """
[tool.releez]
base-branch = "master"
create-pr = false
""".strip(),
        encoding='utf-8',
    )
    (tmp_path / 'app.py').write_text('print("hello")\n', encoding='utf-8')

    repo = _init_repo(tmp_path)
    repo.index.add(['app.py', 'pyproject.toml'])
    repo.index.commit('feat: initial commit')

    result = runner.invoke(cli.app, ['projects', 'changed'])

    assert result.exit_code == 1
    assert 'No projects configured' in result.output


def test_cli_projects_changed_include_paths_integration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test `projects changed` detects changes from include-paths via CLI."""
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()

    core_dir = tmp_path / 'packages' / 'core'
    core_dir.mkdir(parents=True)

    (tmp_path / 'pyproject.toml').write_text(
        """
[tool.releez]
base-branch = "master"
create-pr = false

[[tool.releez.projects]]
name = "core"
path = "packages/core"
tag-prefix = "core-"
include-paths = ["uv.lock"]
""".strip(),
        encoding='utf-8',
    )
    (tmp_path / 'uv.lock').write_text('# lock v1\n', encoding='utf-8')
    (core_dir / 'main.py').write_text('print("core")\n', encoding='utf-8')

    repo = _init_repo(tmp_path)
    repo.index.add(['packages/core/main.py', 'pyproject.toml', 'uv.lock'])
    repo.index.commit('feat(core): initial commit')
    repo.create_tag('core-1.0.0')

    (tmp_path / 'uv.lock').write_text('# lock v2\n', encoding='utf-8')
    repo.index.add(['uv.lock'])
    repo.index.commit('chore: update lock')

    result = runner.invoke(
        cli.app,
        ['projects', 'changed', '--format', 'json', '--base', 'HEAD'],
    )

    assert result.exit_code == 0
    output = json.loads(result.stdout)
    assert output['projects'] == ['core']


def test_cli_release_tag_creates_and_pushes_alias_tags(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test `release tag` creates and pushes exact + alias tags."""
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()

    (tmp_path / 'pyproject.toml').write_text(
        """
[tool.releez]
base-branch = "master"
git-remote = "origin"
create-pr = false
""".strip(),
        encoding='utf-8',
    )
    (tmp_path / 'app.py').write_text('print("v1")\n', encoding='utf-8')

    repo = _init_repo(tmp_path)
    repo.index.add(['app.py', 'pyproject.toml'])
    repo.index.commit('feat: initial commit')
    _add_origin_remote(repo, tmp_path)

    result = runner.invoke(
        cli.app,
        [
            'release',
            'tag',
            '--version-override',
            '2.3.4',
            '--alias-versions',
            'minor',
        ],
    )

    assert result.exit_code == 0
    assert {'2.3.4', 'v2', 'v2.3'}.issubset({tag.name for tag in repo.tags})
    remote_tags = repo.git.ls_remote('--tags', 'origin')
    assert 'refs/tags/2.3.4' in remote_tags
    assert 'refs/tags/v2' in remote_tags
    assert 'refs/tags/v2.3' in remote_tags


def test_cli_release_tag_monorepo_project_creates_prefixed_tags(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test `release tag --project` with real monorepo tag prefixes."""
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()

    core_dir = tmp_path / 'packages' / 'core'
    core_dir.mkdir(parents=True)
    (core_dir / 'main.py').write_text('print("core")\n', encoding='utf-8')
    (core_dir / 'CHANGELOG.md').write_text(
        '# Core Changelog\n\n',
        encoding='utf-8',
    )

    (tmp_path / 'pyproject.toml').write_text(
        """
[tool.releez]
base-branch = "master"
git-remote = "origin"
create-pr = false

[[tool.releez.projects]]
name = "core"
path = "packages/core"
changelog-path = "CHANGELOG.md"
tag-prefix = "core-"
alias-versions = "major"
""".strip(),
        encoding='utf-8',
    )

    repo = _init_repo(tmp_path)
    repo.index.add(
        [
            'packages/core/main.py',
            'packages/core/CHANGELOG.md',
            'pyproject.toml',
        ],
    )
    repo.index.commit('feat(core): initial commit')
    _add_origin_remote(repo, tmp_path)

    result = runner.invoke(
        cli.app,
        [
            'release',
            'tag',
            '--project',
            'core',
            '--version-override',
            '1.2.3',
        ],
    )

    assert result.exit_code == 0
    assert {'core-1.2.3', 'core-v1'}.issubset({tag.name for tag in repo.tags})
    remote_tags = repo.git.ls_remote('--tags', 'origin')
    assert 'refs/tags/core-1.2.3' in remote_tags
    assert 'refs/tags/core-v1' in remote_tags


def test_cli_release_tag_monorepo_all_creates_tags_for_each_project(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test `release tag --all` creates tags for each configured project."""
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()

    core_dir = tmp_path / 'packages' / 'core'
    ui_dir = tmp_path / 'packages' / 'ui'
    core_dir.mkdir(parents=True)
    ui_dir.mkdir(parents=True)
    (core_dir / 'main.py').write_text('print("core")\n', encoding='utf-8')
    (ui_dir / 'main.py').write_text('print("ui")\n', encoding='utf-8')
    (core_dir / 'CHANGELOG.md').write_text(
        '# Core Changelog\n\n',
        encoding='utf-8',
    )
    (ui_dir / 'CHANGELOG.md').write_text('# UI Changelog\n\n', encoding='utf-8')

    (tmp_path / 'pyproject.toml').write_text(
        """
[tool.releez]
base-branch = "master"
git-remote = "origin"
create-pr = false

[[tool.releez.projects]]
name = "core"
path = "packages/core"
changelog-path = "CHANGELOG.md"
tag-prefix = "core-"
alias-versions = "major"

[[tool.releez.projects]]
name = "ui"
path = "packages/ui"
changelog-path = "CHANGELOG.md"
tag-prefix = "ui-"
alias-versions = "major"
""".strip(),
        encoding='utf-8',
    )

    repo = _init_repo(tmp_path)
    repo.index.add(
        [
            'packages/core/main.py',
            'packages/core/CHANGELOG.md',
            'packages/ui/main.py',
            'packages/ui/CHANGELOG.md',
            'pyproject.toml',
        ],
    )
    repo.index.commit('feat: initial commit')
    repo.create_tag('core-1.0.0')
    repo.create_tag('ui-2.0.0')

    (core_dir / 'main.py').write_text('print("core v2")\n', encoding='utf-8')
    repo.index.add(['packages/core/main.py'])
    repo.index.commit('feat(core): update')
    (ui_dir / 'main.py').write_text('print("ui v2")\n', encoding='utf-8')
    repo.index.add(['packages/ui/main.py'])
    repo.index.commit('feat(ui): update')
    _add_origin_remote(repo, tmp_path)

    existing_tags = {tag.name for tag in repo.tags}

    result = runner.invoke(
        cli.app,
        ['release', 'tag', '--all'],
    )

    assert result.exit_code == 0
    new_tags = {tag.name for tag in repo.tags} - existing_tags
    assert 'core-v1' in new_tags
    assert 'ui-v2' in new_tags
    assert any(re.fullmatch(r'core-\d+\.\d+\.\d+', tag) for tag in new_tags)
    assert any(re.fullmatch(r'ui-\d+\.\d+\.\d+', tag) for tag in new_tags)

    remote_tags = repo.git.ls_remote('--tags', 'origin')
    assert 'refs/tags/core-v1' in remote_tags
    assert 'refs/tags/ui-v2' in remote_tags


def test_cli_release_tag_monorepo_all_fails_fast_when_a_project_tag_exists(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression guard: --all tagging should fail deterministically and avoid partial retagging."""
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()

    repo, core_dir, ui_dir = _init_two_project_monorepo_repo(
        tmp_path,
        alias_versions='major',
    )
    (core_dir / 'main.py').write_text('print("core v2")\n', encoding='utf-8')
    (ui_dir / 'main.py').write_text('print("ui v2")\n', encoding='utf-8')
    repo.index.add(['packages/core/main.py', 'packages/ui/main.py'])
    repo.index.commit('feat: change both projects')
    _add_origin_remote(repo, tmp_path)

    first = runner.invoke(cli.app, ['release', 'tag', '--all'])
    assert first.exit_code == 0
    tags_after_first = {tag.name for tag in repo.tags}

    second = runner.invoke(cli.app, ['release', 'tag', '--all'])
    assert second.exit_code == 1
    assert 'already exists' in second.output.lower()
    assert {tag.name for tag in repo.tags} == tags_after_first


def test_cli_release_tag_monorepo_project_accepts_prefixed_version_override(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression guard: prefixed overrides like core-1.2.3 must be accepted for project tagging."""
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()

    repo, _, _ = _init_two_project_monorepo_repo(
        tmp_path,
        alias_versions='major',
    )
    _add_origin_remote(repo, tmp_path)

    result = runner.invoke(
        cli.app,
        [
            'release',
            'tag',
            '--project',
            'core',
            '--version-override',
            'core-1.2.3',
        ],
    )

    assert result.exit_code == 0
    assert {'core-1.2.3', 'core-v1'}.issubset({tag.name for tag in repo.tags})
    remote_tags = repo.git.ls_remote('--tags', 'origin')
    assert 'refs/tags/core-1.2.3' in remote_tags
    assert 'refs/tags/core-v1' in remote_tags


def test_cli_release_preview_and_notes_reject_invalid_monorepo_override(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression guard: invalid project overrides must fail for both preview and notes commands."""
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()

    repo, core_dir, _ = _init_two_project_monorepo_repo(tmp_path)
    (core_dir / 'main.py').write_text('print("core v2")\n', encoding='utf-8')
    repo.index.add(['packages/core/main.py'])
    repo.index.commit('feat(core): update')

    preview_result = runner.invoke(
        cli.app,
        [
            'release',
            'preview',
            '--project',
            'core',
            '--version-override',
            'core-not-a-version',
        ],
    )
    assert preview_result.exit_code == 1
    assert 'Expected a full release version like' in preview_result.output

    notes_result = runner.invoke(
        cli.app,
        [
            'release',
            'notes',
            '--project',
            'core',
            '--version-override',
            'core-not-a-version',
        ],
    )
    assert notes_result.exit_code == 1
    assert 'Expected a full release version like' in notes_result.output


def test_cli_release_preview_and_notes_write_output_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test `release preview` and `release notes` write output files."""
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()

    (tmp_path / 'pyproject.toml').write_text(
        """
[tool.releez]
base-branch = "master"
create-pr = false
""".strip(),
        encoding='utf-8',
    )
    (tmp_path / 'CHANGELOG.md').write_text('# Changelog\n\n', encoding='utf-8')
    (tmp_path / 'app.py').write_text('print("v1")\n', encoding='utf-8')

    repo = _init_repo(tmp_path)
    repo.index.add(['CHANGELOG.md', 'app.py', 'pyproject.toml'])
    repo.index.commit('feat: initial commit')
    repo.create_tag('1.0.0')
    (tmp_path / 'app.py').write_text('print("v2")\n', encoding='utf-8')
    repo.index.add(['app.py'])
    repo.index.commit('feat: add feature')

    preview_path = tmp_path / 'preview.md'
    notes_path = tmp_path / 'notes.md'

    preview_result = runner.invoke(
        cli.app,
        [
            'release',
            'preview',
            '--version-override',
            '2.0.0',
            '--alias-versions',
            'major',
            '--output',
            str(preview_path),
        ],
    )
    assert preview_result.exit_code == 0
    assert preview_path.exists()
    preview_text = preview_path.read_text(encoding='utf-8')
    assert '2.0.0' in preview_text
    assert 'v2' in preview_text

    notes_result = runner.invoke(
        cli.app,
        [
            'release',
            'notes',
            '--version-override',
            '1.1.0',
            '--output',
            str(notes_path),
        ],
    )
    assert notes_result.exit_code == 0
    assert notes_path.exists()
    assert notes_path.read_text(encoding='utf-8').strip() != ''


def test_cli_release_preview_and_notes_monorepo_project(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test monorepo `release preview/notes --project` end-to-end."""
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()

    core_dir = tmp_path / 'packages' / 'core'
    core_dir.mkdir(parents=True)
    (core_dir / 'CHANGELOG.md').write_text(
        '# Core Changelog\n\n',
        encoding='utf-8',
    )
    (core_dir / 'main.py').write_text('print("core v1")\n', encoding='utf-8')
    (tmp_path / 'pyproject.toml').write_text(
        """
[tool.releez]
base-branch = "master"
create-pr = false

[[tool.releez.projects]]
name = "core"
path = "packages/core"
changelog-path = "CHANGELOG.md"
tag-prefix = "core-"
alias-versions = "major"
""".strip(),
        encoding='utf-8',
    )

    repo = _init_repo(tmp_path)
    repo.index.add(
        [
            'packages/core/CHANGELOG.md',
            'packages/core/main.py',
            'pyproject.toml',
        ],
    )
    repo.index.commit('feat(core): initial commit')
    repo.create_tag('core-1.0.0')
    (core_dir / 'main.py').write_text('print("core v2")\n', encoding='utf-8')
    repo.index.add(['packages/core/main.py'])
    repo.index.commit('feat(core): update')

    preview_result = runner.invoke(
        cli.app,
        [
            'release',
            'preview',
            '--project',
            'core',
            '--version-override',
            '1.1.0',
        ],
    )
    assert preview_result.exit_code == 0
    assert '### `core`' in preview_result.output
    assert '`core-1.1.0`' in preview_result.output

    notes_result = runner.invoke(
        cli.app,
        ['release', 'notes', '--project', 'core'],
    )
    assert notes_result.exit_code == 0
    assert '## `core`' in notes_result.output
    assert notes_result.output.strip() != ''


def test_cli_changelog_regenerate_updates_changelog_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test `changelog regenerate` updates the changelog in a real repo."""
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()

    (tmp_path / 'pyproject.toml').write_text(
        """
[tool.releez]
base-branch = "master"
create-pr = false
""".strip(),
        encoding='utf-8',
    )
    changelog_path = tmp_path / 'CHANGELOG.md'
    changelog_path.write_text('# Changelog\n\n', encoding='utf-8')
    (tmp_path / 'app.py').write_text('print("v1")\n', encoding='utf-8')

    repo = _init_repo(tmp_path)
    repo.index.add(['CHANGELOG.md', 'app.py', 'pyproject.toml'])
    repo.index.commit('feat: initial commit')
    repo.create_tag('1.0.0')
    (tmp_path / 'app.py').write_text('print("v2")\n', encoding='utf-8')
    repo.index.add(['app.py'])
    repo.index.commit('feat: add feature')

    original_text = changelog_path.read_text(encoding='utf-8')
    result = runner.invoke(
        cli.app,
        ['changelog', 'regenerate', '--changelog-path', 'CHANGELOG.md'],
    )

    assert result.exit_code == 0
    regenerated_text = changelog_path.read_text(encoding='utf-8')
    assert regenerated_text != original_text
    assert regenerated_text.strip() != ''


def test_cli_release_start_fails_when_remote_base_branch_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test `release start` fails clearly if remote base branch is missing."""
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()

    (tmp_path / 'pyproject.toml').write_text(
        """
[tool.releez]
base-branch = "master"
git-remote = "origin"
create-pr = false
""".strip(),
        encoding='utf-8',
    )
    (tmp_path / 'CHANGELOG.md').write_text('# Changelog\n\n', encoding='utf-8')
    (tmp_path / 'app.py').write_text('print("v1")\n', encoding='utf-8')

    repo = _init_repo(tmp_path)
    repo.index.add(['CHANGELOG.md', 'app.py', 'pyproject.toml'])
    repo.index.commit('feat: initial release')
    _add_origin_remote(repo, tmp_path)

    result = runner.invoke(
        cli.app,
        [
            'release',
            'start',
            '--no-create-pr',
            '--version-override',
            '1.1.0',
            '--base',
            'main',
        ],
    )

    assert result.exit_code == 1
    assert 'Remote branch' in result.output


def test_start_release_monorepo_selective_staging_behavior(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test monorepo release stages project path only, not unrelated hook output."""
    monkeypatch.chdir(tmp_path)

    core_dir = tmp_path / 'packages' / 'core'
    ui_dir = tmp_path / 'packages' / 'ui'
    core_dir.mkdir(parents=True)
    ui_dir.mkdir(parents=True)
    (core_dir / 'CHANGELOG.md').write_text(
        '# Core Changelog\n\n',
        encoding='utf-8',
    )
    (core_dir / 'main.py').write_text('print("core")\n', encoding='utf-8')
    (ui_dir / 'main.py').write_text('print("ui")\n', encoding='utf-8')

    repo = _init_repo(tmp_path)
    repo.index.add(
        [
            'packages/core/CHANGELOG.md',
            'packages/core/main.py',
            'packages/ui/main.py',
        ],
    )
    repo.index.commit('feat: initial monorepo state')
    repo.create_tag('1.0.0')
    _add_origin_remote(repo, tmp_path)

    result = start_release(
        StartReleaseInput(
            bump='auto',
            version_override='1.1.0',
            base_branch='master',
            remote_name='origin',
            labels=['release'],
            title_prefix='chore(release): ',
            changelog_path='packages/core/CHANGELOG.md',
            post_changelog_hooks=[
                ['/bin/sh', '-c', 'echo hook > release-hook-marker.txt'],
            ],
            run_changelog_format=False,
            changelog_format_cmd=None,
            create_pr=False,
            github_token=None,
            dry_run=False,
            project_name='core',
            project_path=core_dir,
        ),
    )

    assert result.release_branch == 'release/1.1.0'
    changed_files = [
        line.strip()
        for line in repo.git.show(
            '--name-only',
            '--pretty=format:',
            'HEAD',
        ).splitlines()
        if line.strip()
    ]
    assert all(path.startswith('packages/core/') for path in changed_files)
    assert (tmp_path / 'release-hook-marker.txt').exists()
    assert 'release-hook-marker.txt' not in changed_files
