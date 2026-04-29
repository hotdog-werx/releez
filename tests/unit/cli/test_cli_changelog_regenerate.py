from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

import pytest
from invoke_helper import invoke

from releez import cli
from releez.errors import MissingCliError
from releez.settings import ReleezSettings

if TYPE_CHECKING:
    from unittest.mock import Mock

    from pytest_mock import MockerFixture


@dataclass
class ChangelogSetup:
    repo_root: Path
    cliff: Mock


@dataclass
class MonorepoSetup:
    repo_root: Path
    core: Mock
    ui: Mock
    cliff: Mock


class ChangelogSetupCallable(Protocol):
    """Protocol for the changelog setup fixture callable."""

    def __call__(
        self,
        changelog_paths: list[str] | None = None,
    ) -> ChangelogSetup: ...


@pytest.fixture
def mock_changelog_setup(
    mocker: MockerFixture,
    tmp_path: Path,
) -> ChangelogSetupCallable:
    """Set up common mocks for changelog tests."""

    def _setup(changelog_paths: list[str] | None = None) -> ChangelogSetup:
        repo_root = tmp_path / 'repo'
        repo_root.mkdir()

        if changelog_paths is None:
            changelog_file = repo_root / 'CHANGELOG.md'
            changelog_file.write_text('# Changelog\n')
        else:
            for path_str in changelog_paths:
                changelog_path = Path(path_str)
                if changelog_path.is_absolute():
                    changelog_path.parent.mkdir(parents=True, exist_ok=True)
                    changelog_path.write_text('# Changelog\n')
                else:
                    changelog_file = repo_root / path_str
                    changelog_file.parent.mkdir(parents=True, exist_ok=True)
                    changelog_file.write_text('# Changelog\n')

        mocker.patch(
            'releez.subapps.changelog.open_repo',
            return_value=mocker.Mock(info=mocker.Mock(root=repo_root)),
        )

        cliff = mocker.Mock()
        mocker.patch('releez.subapps.changelog.GitCliff', return_value=cliff)

        return ChangelogSetup(repo_root=repo_root, cliff=cliff)

    return _setup


def test_changelog_regenerate_basic(
    mock_changelog_setup: ChangelogSetupCallable,
) -> None:
    """Test basic changelog regeneration without formatting."""
    setup = mock_changelog_setup()

    result = invoke(cli.app, ['changelog', 'regenerate'])

    assert result.exit_code == 0
    setup.cliff.regenerate_changelog.assert_called_once()
    call_args = setup.cliff.regenerate_changelog.call_args
    assert call_args.kwargs['changelog_path'] == setup.repo_root / 'CHANGELOG.md'


def test_changelog_regenerate_custom_path(
    mock_changelog_setup: ChangelogSetupCallable,
) -> None:
    """Test changelog regeneration with custom path."""
    setup = mock_changelog_setup(['HISTORY.md'])

    result = invoke(
        cli.app,
        ['changelog', 'regenerate', '--changelog-path', 'HISTORY.md'],
    )

    assert result.exit_code == 0
    setup.cliff.regenerate_changelog.assert_called_once()
    call_args = setup.cliff.regenerate_changelog.call_args
    assert call_args.kwargs['changelog_path'] == setup.repo_root / 'HISTORY.md'


def test_changelog_regenerate_absolute_path(
    mock_changelog_setup: ChangelogSetupCallable,
    tmp_path: Path,
) -> None:
    """Test changelog regeneration with absolute path."""
    changelog_path = tmp_path / 'custom' / 'CHANGELOG.md'
    setup = mock_changelog_setup([str(changelog_path)])

    result = invoke(
        cli.app,
        ['changelog', 'regenerate', '--changelog-path', str(changelog_path)],
    )

    assert result.exit_code == 0
    setup.cliff.regenerate_changelog.assert_called_once()
    call_args = setup.cliff.regenerate_changelog.call_args
    assert call_args.kwargs['changelog_path'] == changelog_path


def test_changelog_regenerate_handles_releez_error(
    mocker: MockerFixture,
    tmp_path: Path,
) -> None:
    """Test that ReleezError is properly handled and reported."""
    repo_root = tmp_path / 'repo'
    repo_root.mkdir()

    changelog_file = repo_root / 'CHANGELOG.md'
    changelog_file.write_text('# Changelog\n')

    mocker.patch(
        'releez.subapps.changelog.open_repo',
        return_value=mocker.Mock(info=mocker.Mock(root=repo_root)),
    )

    mocker.patch(
        'releez.subapps.changelog.GitCliff',
        side_effect=MissingCliError('git-cliff'),
    )

    result = invoke(cli.app, ['changelog', 'regenerate'])

    assert result.exit_code == 1
    assert 'git-cliff' in result.output


def test_changelog_regenerate_single_repo_rejects_project_flags(
    mock_changelog_setup: ChangelogSetupCallable,
) -> None:
    """Test that --all in single-repo mode (no projects configured) exits with error."""
    mock_changelog_setup()

    result = invoke(cli.app, ['changelog', 'regenerate', '--all'])

    assert result.exit_code == 1
    assert 'no projects are configured' in result.output.lower()


class TestChangelogRegenerateMonorepo:
    """Tests for changelog regenerate in monorepo mode."""

    @pytest.fixture
    def monorepo_setup(
        self,
        mocker: MockerFixture,
        tmp_path: Path,
    ) -> MonorepoSetup:
        """Set up mocks for monorepo changelog tests."""
        repo_root = tmp_path / 'repo'
        repo_root.mkdir()

        core_changelog = repo_root / 'packages' / 'core' / 'CHANGELOG.md'
        ui_changelog = repo_root / 'packages' / 'ui' / 'CHANGELOG.md'
        core_changelog.parent.mkdir(parents=True)
        ui_changelog.parent.mkdir(parents=True)
        core_changelog.write_text('# Core\n')
        ui_changelog.write_text('# UI\n')

        mocker.patch(
            'releez.subapps.changelog.open_repo',
            return_value=mocker.Mock(info=mocker.Mock(root=repo_root)),
        )

        core = mocker.Mock()
        core.name = 'core'
        core.tag_pattern = '^core-([0-9]+\\.[0-9]+\\.[0-9]+)$'
        core.include_paths = ['packages/core/**']
        core.changelog_path = core_changelog

        ui = mocker.Mock()
        ui.name = 'ui'
        ui.tag_pattern = '^ui-([0-9]+\\.[0-9]+\\.[0-9]+)$'
        ui.include_paths = ['packages/ui/**']
        ui.changelog_path = ui_changelog

        mocker.patch.object(
            ReleezSettings,
            'get_subprojects',
            return_value=[core, ui],
        )
        mocker.patch.object(
            ReleezSettings,
            'is_monorepo',
            new_callable=mocker.PropertyMock,
            return_value=True,
        )

        cliff = mocker.Mock()
        mocker.patch('releez.subapps.changelog.GitCliff', return_value=cliff)

        return MonorepoSetup(repo_root=repo_root, core=core, ui=ui, cliff=cliff)

    def test_all_projects_regenerates_both(
        self,
        monorepo_setup: MonorepoSetup,
    ) -> None:
        """--all regenerates changelog for every configured project."""
        result = invoke(cli.app, ['changelog', 'regenerate', '--all'])

        assert result.exit_code == 0
        assert monorepo_setup.cliff.regenerate_changelog.call_count == 2
        calls = monorepo_setup.cliff.regenerate_changelog.call_args_list
        assert calls[0].kwargs['changelog_path'] == monorepo_setup.core.changelog_path
        assert calls[0].kwargs['tag_pattern'] == monorepo_setup.core.tag_pattern
        assert calls[0].kwargs['include_paths'] == monorepo_setup.core.include_paths
        assert calls[1].kwargs['changelog_path'] == monorepo_setup.ui.changelog_path

    def test_specific_project(
        self,
        monorepo_setup: MonorepoSetup,
    ) -> None:
        """--project <name> regenerates only the named project."""
        result = invoke(
            cli.app,
            ['changelog', 'regenerate', '--project', 'core'],
        )

        assert result.exit_code == 0
        monorepo_setup.cliff.regenerate_changelog.assert_called_once()
        assert (
            monorepo_setup.cliff.regenerate_changelog.call_args.kwargs['changelog_path']
            == monorepo_setup.core.changelog_path
        )

    def test_multiple_projects(
        self,
        monorepo_setup: MonorepoSetup,
    ) -> None:
        """--project can be repeated to select multiple projects."""
        result = invoke(
            cli.app,
            ['changelog', 'regenerate', '--project', 'core', '--project', 'ui'],
        )

        assert result.exit_code == 0
        assert monorepo_setup.cliff.regenerate_changelog.call_count == 2

    @pytest.mark.usefixtures('monorepo_setup')
    def test_no_selection_exits_with_error(
        self,
    ) -> None:
        """Monorepo mode without --project or --all exits with an informative error."""
        result = invoke(cli.app, ['changelog', 'regenerate'])

        assert result.exit_code == 1
        assert 'project selection is required' in result.output.lower()

    @pytest.mark.usefixtures('monorepo_setup')
    def test_unknown_project_exits_with_error(
        self,
    ) -> None:
        """--project with an unknown name exits with an error."""
        result = invoke(
            cli.app,
            ['changelog', 'regenerate', '--project', 'nonexistent'],
        )

        assert result.exit_code == 1
        assert 'unknown project' in result.output.lower()

    @pytest.mark.usefixtures('monorepo_setup')
    def test_project_and_all_together_exits_with_error(
        self,
    ) -> None:
        """Using --project and --all together exits with an error."""
        result = invoke(
            cli.app,
            ['changelog', 'regenerate', '--project', 'core', '--all'],
        )

        assert result.exit_code == 1
        assert '--project' in result.output
        assert '--all' in result.output
