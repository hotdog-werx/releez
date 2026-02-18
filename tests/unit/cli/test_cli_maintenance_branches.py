from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from git import Repo
from typer.testing import CliRunner

from releez import cli
from releez.cli import _maintenance_major
from releez.errors import InvalidMaintenanceBranchRegexError
from releez.git_repo import RepoContext, RepoInfo

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture


class TestMaintenanceMajor:
    """Tests for _maintenance_major function."""

    def test_invalid_regex_raises_error_with_reason(self) -> None:
        """Test that an invalid regex raises InvalidMaintenanceBranchRegexError with reason."""
        with pytest.raises(InvalidMaintenanceBranchRegexError) as exc_info:
            _maintenance_major(branch='support/1.x', regex='[invalid(regex')

        error = exc_info.value
        assert error.pattern == '[invalid(regex'
        assert 'unterminated character set' in str(error).lower()

    def test_missing_major_capture_group_raises_error(self) -> None:
        """Test that missing 'major' capture group raises InvalidMaintenanceBranchRegexError."""
        # Regex without named 'major' capture group
        with pytest.raises(InvalidMaintenanceBranchRegexError) as exc_info:
            _maintenance_major(
                branch='support/1.x',
                regex=r'^support/(\d+)\.x$',
            )

        error = exc_info.value
        assert error.pattern == r'^support/(\d+)\.x$'
        assert 'missing named capture group "major"' in str(error)

    def test_non_integer_major_value_raises_error(self) -> None:
        """Test that non-integer major value raises InvalidMaintenanceBranchRegexError."""
        # Regex that captures non-integer value
        with pytest.raises(InvalidMaintenanceBranchRegexError) as exc_info:
            _maintenance_major(
                branch='support/abc.x',
                regex=r'^support/(?P<major>\w+)\.x$',
            )

        error = exc_info.value
        assert error.pattern == r'^support/(?P<major>\w+)\.x$'
        assert "invalid major value 'abc'" in str(error)


class TestReleaseStartOnMaintenanceBranch:
    """Tests for release start command on maintenance branch."""

    def test_release_start_on_maintenance_branch_uses_tag_pattern(
        self,
        mocker: MockerFixture,
        tmp_path: Path,
    ) -> None:
        """Test that release start on maintenance branch uses tag_pattern."""
        runner = CliRunner()

        repo_info = RepoInfo(
            root=tmp_path,
            remote_url='',
            active_branch='support/1.x',
        )
        mocker.patch(
            'releez.cli.open_repo',
            return_value=RepoContext(
                repo=mocker.Mock(spec=Repo),
                info=repo_info,
            ),
        )

        # Mock git-cliff to return a version with correct major
        cliff = mocker.Mock()
        cliff.compute_next_version.return_value = '1.5.0'
        mocker.patch('releez.cli.GitCliff', return_value=cliff)

        start_release = mocker.patch(
            'releez.cli.start_release',
            return_value=mocker.Mock(
                version='1.5.0',
                release_notes_markdown='notes',
                release_branch=None,
                pr_url=None,
            ),
        )

        result = runner.invoke(
            cli.app,
            [
                'release',
                'start',
                '--dry-run',
                '--maintenance-branch-regex',
                r'^support/(?P<major>\d+)\.x$',
            ],
        )

        assert result.exit_code == 0
        release_input = start_release.call_args.args[0]
        assert release_input.tag_pattern == r'^1\\.[0-9]+\\.[0-9]+$'

    def test_release_start_on_maintenance_branch_sets_base_to_current(
        self,
        mocker: MockerFixture,
        tmp_path: Path,
    ) -> None:
        """Test that release start on maintenance branch sets base to current branch."""
        runner = CliRunner()

        repo_info = RepoInfo(
            root=tmp_path,
            remote_url='',
            active_branch='support/2.x',
        )
        mocker.patch(
            'releez.cli.open_repo',
            return_value=RepoContext(
                repo=mocker.Mock(spec=Repo),
                info=repo_info,
            ),
        )

        # Mock git-cliff to return a version with correct major
        cliff = mocker.Mock()
        cliff.compute_next_version.return_value = '2.1.0'
        mocker.patch('releez.cli.GitCliff', return_value=cliff)

        start_release = mocker.patch(
            'releez.cli.start_release',
            return_value=mocker.Mock(
                version='2.1.0',
                release_notes_markdown='notes',
                release_branch=None,
                pr_url=None,
            ),
        )

        result = runner.invoke(
            cli.app,
            [
                'release',
                'start',
                '--dry-run',
                '--base',
                'master',
                '--maintenance-branch-regex',
                r'^support/(?P<major>\d+)\.x$',
            ],
        )

        assert result.exit_code == 0, f'Unexpected error: {result.output}'
        release_input = start_release.call_args.args[0]
        # Base should be set to maintenance branch, not 'master'
        assert release_input.base_branch == 'support/2.x'

    def test_release_start_on_non_maintenance_branch_uses_base(
        self,
        mocker: MockerFixture,
        tmp_path: Path,
    ) -> None:
        """Test that release start on non-maintenance branch uses provided base."""
        runner = CliRunner()

        repo_info = RepoInfo(
            root=tmp_path,
            remote_url='',
            active_branch='feature/my-feature',
        )
        mocker.patch(
            'releez.cli.open_repo',
            return_value=RepoContext(
                repo=mocker.Mock(spec=Repo),
                info=repo_info,
            ),
        )

        start_release = mocker.patch(
            'releez.cli.start_release',
            return_value=mocker.Mock(
                version='3.0.0',
                release_notes_markdown='notes',
                release_branch=None,
                pr_url=None,
            ),
        )

        result = runner.invoke(
            cli.app,
            [
                'release',
                'start',
                '--dry-run',
                '--base',
                'master',
                '--maintenance-branch-regex',
                r'^support/(?P<major>\d+)\.x$',
            ],
        )

        assert result.exit_code == 0
        release_input = start_release.call_args.args[0]
        # Base should remain 'master' since not on maintenance branch
        assert release_input.base_branch == 'master'
        assert release_input.tag_pattern is None

    def test_release_start_on_maintenance_branch_version_mismatch_fails(
        self,
        mocker: MockerFixture,
        tmp_path: Path,
    ) -> None:
        """Test that release start fails when version major doesn't match maintenance branch."""
        runner = CliRunner()

        repo_info = RepoInfo(
            root=tmp_path,
            remote_url='',
            active_branch='support/1.x',
        )
        mocker.patch(
            'releez.cli.open_repo',
            return_value=RepoContext(
                repo=mocker.Mock(spec=Repo),
                info=repo_info,
            ),
        )

        # Mock git-cliff to return version with wrong major
        cliff = mocker.Mock()
        cliff.compute_next_version.return_value = '2.0.0'
        mocker.patch('releez.cli.GitCliff', return_value=cliff)

        result = runner.invoke(
            cli.app,
            [
                'release',
                'start',
                '--dry-run',
                '--maintenance-branch-regex',
                r'^support/(?P<major>\d+)\.x$',
            ],
        )

        assert result.exit_code == 1
        assert 'does not match maintenance branch' in result.output


class TestReleaseTagOnMaintenanceBranch:
    """Tests for release tag command on maintenance branch."""

    def test_release_tag_on_maintenance_branch_uses_tag_pattern(
        self,
        mocker: MockerFixture,
        tmp_path: Path,
    ) -> None:
        """Test that release tag on maintenance branch uses tag_pattern."""
        runner = CliRunner()

        repo = mocker.Mock(spec=Repo)
        repo_info = RepoInfo(
            root=tmp_path,
            remote_url='',
            active_branch='support/1.x',
        )
        mocker.patch(
            'releez.cli.open_repo',
            return_value=RepoContext(repo=repo, info=repo_info),
        )
        mocker.patch('releez.cli.fetch')

        cliff = mocker.Mock()
        cliff.compute_next_version.return_value = '1.5.0'
        mocker.patch('releez.cli.GitCliff', return_value=cliff)

        mocker.patch('releez.cli.compute_version_tags')
        mocker.patch('releez.cli.select_tags', return_value=['1.5.0'])
        mocker.patch('releez.cli.create_tags')
        mocker.patch('releez.cli.push_tags')

        result = runner.invoke(cli.app, ['release', 'tag'])

        assert result.exit_code == 0
        cliff.compute_next_version.assert_called_once_with(
            bump='auto',
            tag_pattern=r'^1\\.[0-9]+\\.[0-9]+$',
        )

    def test_release_tag_on_maintenance_branch_version_mismatch_fails(
        self,
        mocker: MockerFixture,
        tmp_path: Path,
    ) -> None:
        """Test that release tag fails when version major doesn't match maintenance branch."""
        runner = CliRunner()

        repo = mocker.Mock(spec=Repo)
        repo_info = RepoInfo(
            root=tmp_path,
            remote_url='',
            active_branch='support/1.x',
        )
        mocker.patch(
            'releez.cli.open_repo',
            return_value=RepoContext(repo=repo, info=repo_info),
        )
        mocker.patch('releez.cli.fetch')

        # Mock git-cliff to return version with wrong major
        cliff = mocker.Mock()
        cliff.compute_next_version.return_value = '2.0.0'
        mocker.patch('releez.cli.GitCliff', return_value=cliff)

        result = runner.invoke(cli.app, ['release', 'tag'])

        assert result.exit_code == 1
        assert 'does not match maintenance branch' in result.output


class TestReleasePreviewOnMaintenanceBranch:
    """Tests for release preview command on maintenance branch."""

    def test_release_preview_on_maintenance_branch_uses_tag_pattern(
        self,
        mocker: MockerFixture,
        tmp_path: Path,
    ) -> None:
        """Test that release preview on maintenance branch uses tag_pattern."""
        runner = CliRunner()

        repo_info = RepoInfo(
            root=tmp_path,
            remote_url='',
            active_branch='support/3.x',
        )
        mocker.patch(
            'releez.cli.open_repo',
            return_value=RepoContext(
                repo=mocker.Mock(spec=Repo),
                info=repo_info,
            ),
        )

        cliff = mocker.Mock()
        cliff.compute_next_version.return_value = '3.2.0'
        mocker.patch('releez.cli.GitCliff', return_value=cliff)

        result = runner.invoke(cli.app, ['release', 'preview'])

        assert result.exit_code == 0
        cliff.compute_next_version.assert_called_once_with(
            bump='auto',
            tag_pattern=r'^3\\.[0-9]+\\.[0-9]+$',
        )
        assert '`3.2.0`' in result.stdout

    def test_release_preview_on_maintenance_branch_version_mismatch_fails(
        self,
        mocker: MockerFixture,
        tmp_path: Path,
    ) -> None:
        """Test that release preview fails when version major doesn't match maintenance branch."""
        runner = CliRunner()

        repo_info = RepoInfo(
            root=tmp_path,
            remote_url='',
            active_branch='support/1.x',
        )
        mocker.patch(
            'releez.cli.open_repo',
            return_value=RepoContext(
                repo=mocker.Mock(spec=Repo),
                info=repo_info,
            ),
        )

        # Mock git-cliff to return version with wrong major
        cliff = mocker.Mock()
        cliff.compute_next_version.return_value = '2.0.0'
        mocker.patch('releez.cli.GitCliff', return_value=cliff)

        result = runner.invoke(cli.app, ['release', 'preview'])

        assert result.exit_code == 1
        assert 'does not match maintenance branch' in result.output


class TestReleaseNotesOnMaintenanceBranch:
    """Tests for release notes command on maintenance branch."""

    def test_release_notes_on_maintenance_branch_uses_tag_pattern(
        self,
        mocker: MockerFixture,
        tmp_path: Path,
    ) -> None:
        """Test that release notes on maintenance branch uses tag_pattern."""
        runner = CliRunner()

        repo_info = RepoInfo(
            root=tmp_path,
            remote_url='',
            active_branch='support/2.x',
        )
        mocker.patch(
            'releez.cli.open_repo',
            return_value=RepoContext(
                repo=mocker.Mock(spec=Repo),
                info=repo_info,
            ),
        )

        cliff = mocker.Mock()
        cliff.compute_next_version.return_value = '2.7.0'
        cliff.generate_unreleased_notes.return_value = '## 2.7.0\n\n- Fix\n'
        mocker.patch('releez.cli.GitCliff', return_value=cliff)

        result = runner.invoke(cli.app, ['release', 'notes'])

        assert result.exit_code == 0
        cliff.compute_next_version.assert_called_once_with(
            bump='auto',
            tag_pattern=r'^2\\.[0-9]+\\.[0-9]+$',
        )
        cliff.generate_unreleased_notes.assert_called_once_with(
            version='2.7.0',
            tag_pattern=r'^2\\.[0-9]+\\.[0-9]+$',
        )
        assert '## 2.7.0' in result.stdout

    def test_release_notes_on_maintenance_branch_version_mismatch_fails(
        self,
        mocker: MockerFixture,
        tmp_path: Path,
    ) -> None:
        """Test that release notes fails when version major doesn't match maintenance branch."""
        runner = CliRunner()

        repo_info = RepoInfo(
            root=tmp_path,
            remote_url='',
            active_branch='support/1.x',
        )
        mocker.patch(
            'releez.cli.open_repo',
            return_value=RepoContext(
                repo=mocker.Mock(spec=Repo),
                info=repo_info,
            ),
        )

        # Mock git-cliff to return version with wrong major
        cliff = mocker.Mock()
        cliff.compute_next_version.return_value = '3.0.0'
        mocker.patch('releez.cli.GitCliff', return_value=cliff)

        result = runner.invoke(cli.app, ['release', 'notes'])

        assert result.exit_code == 1
        assert 'does not match maintenance branch' in result.output
