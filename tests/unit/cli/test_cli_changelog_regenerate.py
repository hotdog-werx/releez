from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Protocol

import pytest
from typer.testing import CliRunner

from releez import cli
from releez.errors import MissingCliError
from releez.settings import ReleezSettings

if TYPE_CHECKING:
    from unittest.mock import Mock

    from pytest_mock import MockerFixture


class MonorepoSetupResult(Protocol):
    """Protocol for monorepo changelog test setup result."""

    repo_root: Path
    core: Mock
    ui: Mock
    cliff: Mock


class ChangelogSetupCallable(Protocol):
    """Protocol for the changelog setup fixture callable."""

    def __call__(
        self,
        changelog_paths: list[str] | None = None,
    ) -> tuple[Path, Mock]: ...


@pytest.fixture
def mock_changelog_setup(
    mocker: MockerFixture,
    tmp_path: Path,
) -> ChangelogSetupCallable:
    """Set up common mocks for changelog tests.

    Returns:
        A callable that accepts optional changelog paths and returns (repo_root, mocked_cliff).
        If changelog_paths is None, creates the default CHANGELOG.md.
        If changelog_paths is an empty list, no changelog files are created.
    """

    def _setup(changelog_paths: list[str] | None = None) -> tuple[Path, Mock]:
        repo_root = tmp_path / 'repo'
        repo_root.mkdir()

        # Create changelog files if requested
        if changelog_paths is None:
            # Default behavior: create CHANGELOG.md
            changelog_file = repo_root / 'CHANGELOG.md'
            changelog_file.write_text('# Changelog\n')
        else:
            # Create specified changelog files (can be empty list for none)
            for path_str in changelog_paths:
                changelog_path = Path(path_str)
                if changelog_path.is_absolute():
                    # For absolute paths, create in the specified location
                    changelog_path.parent.mkdir(parents=True, exist_ok=True)
                    changelog_path.write_text('# Changelog\n')
                else:
                    # For relative paths, create under repo_root
                    changelog_file = repo_root / path_str
                    changelog_file.parent.mkdir(parents=True, exist_ok=True)
                    changelog_file.write_text('# Changelog\n')

        mocker.patch(
            'releez.subapps.changelog.open_repo',
            return_value=mocker.Mock(info=mocker.Mock(root=repo_root)),
        )

        cliff = mocker.Mock()
        mocker.patch('releez.subapps.changelog.GitCliff', return_value=cliff)

        return repo_root, cliff

    return _setup


def test_changelog_regenerate_basic(
    mock_changelog_setup: ChangelogSetupCallable,
) -> None:
    """Test basic changelog regeneration without formatting."""
    repo_root, cliff = mock_changelog_setup()  # Uses default CHANGELOG.md
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        ['changelog', 'regenerate'],
    )

    assert result.exit_code == 0
    cliff.regenerate_changelog.assert_called_once()
    call_args = cliff.regenerate_changelog.call_args
    assert call_args.kwargs['changelog_path'] == repo_root / 'CHANGELOG.md'


def test_changelog_regenerate_custom_path(
    mock_changelog_setup: ChangelogSetupCallable,
) -> None:
    """Test changelog regeneration with custom path."""
    repo_root, cliff = mock_changelog_setup(['HISTORY.md'])
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        ['changelog', 'regenerate', '--changelog-path', 'HISTORY.md'],
    )

    assert result.exit_code == 0
    cliff.regenerate_changelog.assert_called_once()
    call_args = cliff.regenerate_changelog.call_args
    assert call_args.kwargs['changelog_path'] == repo_root / 'HISTORY.md'


def test_changelog_regenerate_absolute_path(
    mock_changelog_setup: ChangelogSetupCallable,
    tmp_path: Path,
) -> None:
    """Test changelog regeneration with absolute path."""
    changelog_path = tmp_path / 'custom' / 'CHANGELOG.md'
    _, cliff = mock_changelog_setup([str(changelog_path)])
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        ['changelog', 'regenerate', '--changelog-path', str(changelog_path)],
    )

    assert result.exit_code == 0
    cliff.regenerate_changelog.assert_called_once()
    call_args = cliff.regenerate_changelog.call_args
    assert call_args.kwargs['changelog_path'] == changelog_path


def test_changelog_regenerate_with_format(
    mock_changelog_setup: ChangelogSetupCallable,
    mocker: MockerFixture,
) -> None:
    """Test changelog regeneration with formatting enabled."""
    repo_root, cliff = mock_changelog_setup()  # Uses default CHANGELOG.md
    runner = CliRunner()

    run_checked = mocker.patch('releez.utils.run_checked')

    result = runner.invoke(
        cli.app,
        [
            'changelog',
            'regenerate',
            '--run-changelog-format',
            '--changelog-format-cmd',
            'prettier',
            '--changelog-format-cmd',
            '--write',
            '--changelog-format-cmd',
            '{changelog}',
        ],
    )

    assert result.exit_code == 0
    cliff.regenerate_changelog.assert_called_once()
    run_checked.assert_called_once()
    call_args = run_checked.call_args
    expected_changelog = repo_root / 'CHANGELOG.md'
    assert call_args.args[0] == ['prettier', '--write', str(expected_changelog)]
    assert call_args.kwargs['cwd'] == repo_root
    assert call_args.kwargs['capture_stdout'] is False


def test_changelog_regenerate_format_without_cmd_raises_error(
    mock_changelog_setup: ChangelogSetupCallable,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that enabling format without providing cmd raises error."""
    _, cliff = mock_changelog_setup()  # Uses default CHANGELOG.md
    runner = CliRunner()
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(
        cli.app,
        ['changelog', 'regenerate', '--run-changelog-format'],
    )

    assert result.exit_code == 1
    assert 'no format command is configured' in result.output.lower()
    # Verify GitCliff was not called since error happens before
    cliff.regenerate_changelog.assert_not_called()


def test_changelog_regenerate_handles_releez_error(
    mocker: MockerFixture,
    tmp_path: Path,
) -> None:
    """Test that ReleezError is properly handled and reported."""
    runner = CliRunner()
    repo_root = tmp_path / 'repo'
    repo_root.mkdir()

    # Create the changelog file
    changelog_file = repo_root / 'CHANGELOG.md'
    changelog_file.write_text('# Changelog\n')

    mocker.patch(
        'releez.subapps.changelog.open_repo',
        return_value=mocker.Mock(info=mocker.Mock(root=repo_root)),
    )

    # This test needs to raise an error during GitCliff creation,
    # so we can't use the fixture which mocks it successfully
    mocker.patch(
        'releez.subapps.changelog.GitCliff',
        side_effect=MissingCliError('git-cliff'),
    )

    result = runner.invoke(
        cli.app,
        ['changelog', 'regenerate'],
    )

    assert result.exit_code == 1
    assert 'git-cliff' in result.output


def test_changelog_regenerate_single_repo_rejects_project_flags(
    mock_changelog_setup: ChangelogSetupCallable,
) -> None:
    """Test that --all in single-repo mode (no projects configured) exits with error."""
    mock_changelog_setup()
    runner = CliRunner()

    result = runner.invoke(cli.app, ['changelog', 'regenerate', '--all'])

    assert result.exit_code == 1
    assert 'no projects are configured' in result.output.lower()


class TestChangelogRegenerateMonorepo:
    """Tests for changelog regenerate in monorepo mode."""

    @pytest.fixture
    def monorepo_setup(
        self,
        mocker: MockerFixture,
        tmp_path: Path,
    ) -> tuple[Path, Mock, Mock, Mock]:
        """Set up mocks for monorepo changelog tests.

        Returns (repo_root, core_project, ui_project, cliff_mock).
        """
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

        # Patch at class level so the real select_projects logic runs
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

        return repo_root, core, ui, cliff

    def test_all_projects_regenerates_both(
        self,
        monorepo_setup: tuple[Path, Mock, Mock, Mock],
    ) -> None:
        """--all regenerates changelog for every configured project."""
        _, core, ui, cliff = monorepo_setup
        runner = CliRunner()

        result = runner.invoke(cli.app, ['changelog', 'regenerate', '--all'])

        assert result.exit_code == 0
        assert cliff.regenerate_changelog.call_count == 2
        calls = cliff.regenerate_changelog.call_args_list
        assert calls[0].kwargs['changelog_path'] == core.changelog_path
        assert calls[0].kwargs['tag_pattern'] == core.tag_pattern
        assert calls[0].kwargs['include_paths'] == core.include_paths
        assert calls[1].kwargs['changelog_path'] == ui.changelog_path

    def test_specific_project(
        self,
        monorepo_setup: tuple[Path, Mock, Mock, Mock],
    ) -> None:
        """--project <name> regenerates only the named project."""
        _, core, _ui, cliff = monorepo_setup
        runner = CliRunner()

        result = runner.invoke(
            cli.app,
            ['changelog', 'regenerate', '--project', 'core'],
        )

        assert result.exit_code == 0
        cliff.regenerate_changelog.assert_called_once()
        assert cliff.regenerate_changelog.call_args.kwargs['changelog_path'] == core.changelog_path

    def test_multiple_projects(
        self,
        monorepo_setup: tuple[Path, Mock, Mock, Mock],
    ) -> None:
        """--project can be repeated to select multiple projects."""
        _, _, _, cliff = monorepo_setup
        runner = CliRunner()

        result = runner.invoke(
            cli.app,
            ['changelog', 'regenerate', '--project', 'core', '--project', 'ui'],
        )

        assert result.exit_code == 0
        assert cliff.regenerate_changelog.call_count == 2

    @pytest.mark.usefixtures('monorepo_setup')
    def test_no_selection_exits_with_error(self) -> None:
        """Monorepo mode without --project or --all exits with an informative error."""
        runner = CliRunner()

        result = runner.invoke(cli.app, ['changelog', 'regenerate'])

        assert result.exit_code == 1
        assert 'project selection is required' in result.output.lower()

    @pytest.mark.usefixtures('monorepo_setup')
    def test_unknown_project_exits_with_error(self) -> None:
        """--project with an unknown name exits with an error."""
        runner = CliRunner()

        result = runner.invoke(
            cli.app,
            ['changelog', 'regenerate', '--project', 'nonexistent'],
        )

        assert result.exit_code == 1
        assert 'unknown project' in result.output.lower()

    @pytest.mark.usefixtures('monorepo_setup')
    def test_project_and_all_together_exits_with_error(self) -> None:
        """Using --project and --all together exits with an error."""
        runner = CliRunner()

        result = runner.invoke(
            cli.app,
            ['changelog', 'regenerate', '--project', 'core', '--all'],
        )

        assert result.exit_code == 1
        assert '--project' in result.output
        assert '--all' in result.output

    def test_regenerate_with_format_runs_formatter(
        self,
        monorepo_setup: tuple[Path, Mock, Mock, Mock],
        mocker: MockerFixture,
    ) -> None:
        """--run-changelog-format runs the formatter for each regenerated project."""
        _, core, _ui, _cliff = monorepo_setup
        run_checked = mocker.patch('releez.utils.run_checked')
        runner = CliRunner()

        result = runner.invoke(
            cli.app,
            [
                'changelog',
                'regenerate',
                '--project',
                'core',
                '--run-changelog-format',
                '--changelog-format-cmd',
                'prettier',
                '--changelog-format-cmd',
                '--write',
                '--changelog-format-cmd',
                '{changelog}',
            ],
        )

        assert result.exit_code == 0
        run_checked.assert_called_once()
        assert str(core.changelog_path) in run_checked.call_args.args[0]
