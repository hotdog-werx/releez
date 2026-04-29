from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from git import Repo
from invoke_helper import invoke
from semver import VersionInfo

from releez import cli
from releez.errors import (
    InvalidMaintenanceBranchRegexError,
    MaintenanceBranchMajorMismatchError,
    ReleezError,
)
from releez.git_repo import RepoInfo
from releez.subapps import release
from releez.subapps.release_maintenance import (
    MaintenanceContext,
    _maintenance_major,
    _monorepo_maintenance_context,
    _monorepo_maintenance_tag_pattern,
    _validate_maintenance_version,
)
from releez.subapps.release_start import _confirm_release_start
from releez.subapps.release_support import _validate_support_branch_name
from releez.subproject import SubProject

if TYPE_CHECKING:
    from pathlib import Path
    from unittest.mock import MagicMock

    from pytest_mock import MockerFixture


class TestMaintenanceMajor:
    """Tests for _maintenance_major function."""

    def test_invalid_regex_raises_error_with_reason(self) -> None:
        with pytest.raises(InvalidMaintenanceBranchRegexError) as exc_info:
            _maintenance_major(branch='support/1.x', regex='[invalid(regex')

        error = exc_info.value
        assert error.pattern == '[invalid(regex'
        assert 'unterminated character set' in str(error).lower()

    def test_missing_major_capture_group_raises_error(self) -> None:
        with pytest.raises(InvalidMaintenanceBranchRegexError) as exc_info:
            _maintenance_major(
                branch='support/1.x',
                regex=r'^support/(\d+)\.x$',
            )

        error = exc_info.value
        assert error.pattern == r'^support/(\d+)\.x$'
        assert 'missing named capture group "major"' in str(error)

    def test_non_integer_major_value_raises_error(self) -> None:
        with pytest.raises(InvalidMaintenanceBranchRegexError) as exc_info:
            _maintenance_major(
                branch='support/abc.x',
                regex=r'^support/(?P<major>\w+)\.x$',
            )

        error = exc_info.value
        assert error.pattern == r'^support/(?P<major>\w+)\.x$'
        assert "invalid major value 'abc'" in str(error)


class TestValidateMaintenanceVersion:
    """Tests for _validate_maintenance_version function."""

    def test_unparseable_version_raises_mismatch_error(self) -> None:
        ctx = MaintenanceContext(
            branch='support/1.x',
            major=1,
            tag_pattern='^1\\.[0-9]+\\.[0-9]+$',
        )
        with pytest.raises(MaintenanceBranchMajorMismatchError):
            _validate_maintenance_version(
                version='alpha-not-a-version',
                maintenance_ctx=ctx,
            )


class TestConfirmReleaseStart:
    """Tests for _confirm_release_start function."""

    def test_confirm_release_start_shows_summary_and_prompts(
        self,
        mocker: MockerFixture,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Test that _confirm_release_start outputs summary and calls Confirm.ask."""
        confirm = mocker.patch(
            'releez.subapps.release_start.Confirm.ask',
            return_value=True,
        )

        options = release.ReleaseStartOptions(
            bump='auto',
            version_override=None,
            create_pr=False,
            dry_run=False,
            base='master',
            remote='origin',
            labels=None,
            title_prefix='chore(release): ',
            changelog_path='CHANGELOG.md',
            github_token=None,
        )
        _confirm_release_start(
            options=options,
            version=VersionInfo.parse('1.5.0'),
            active_branch='support/1.x',
        )

        captured = capsys.readouterr()
        assert 'Release summary' in captured.out
        confirm.assert_called_once_with('Proceed?')

    def test_confirm_release_start_raises_on_decline(
        self,
        mocker: MockerFixture,
    ) -> None:
        """Test that _confirm_release_start raises SystemExit when user declines."""
        mocker.patch(
            'releez.subapps.release_start.Confirm.ask',
            return_value=False,
        )

        options = release.ReleaseStartOptions(
            bump='auto',
            version_override=None,
            create_pr=False,
            dry_run=False,
            base='master',
            remote='origin',
            labels=None,
            title_prefix='chore(release): ',
            changelog_path='CHANGELOG.md',
            github_token=None,
        )

        with pytest.raises(SystemExit):
            _confirm_release_start(
                options=options,
                version=VersionInfo.parse('1.5.0'),
                active_branch='support/1.x',
            )


class TestReleaseStartConfirmInteractive:
    """Tests for interactive confirmation in _run_single_repo_release_start."""

    def test_release_start_on_maintenance_branch_prompts_when_not_dry_run(
        self,
        mocker: MockerFixture,
        tmp_path: Path,
    ) -> None:
        """Test that confirmation prompt is shown when non_interactive=False and not dry_run."""
        repo_info = RepoInfo(
            root=tmp_path,
            remote_url='',
            active_branch='support/1.x',
        )
        mocker.patch(
            'releez.subapps.release.open_repo',
            return_value=mocker.Mock(
                repo=mocker.Mock(spec=Repo),
                info=repo_info,
            ),
        )

        cliff = mocker.Mock()
        cliff.compute_next_version.return_value = '1.5.0'
        mocker.patch('releez.cli_utils.GitCliff', return_value=cliff)

        mocker.patch(
            'releez.subapps.release_start.start_release',
            return_value=mocker.Mock(
                version='1.5.0',
                release_notes_markdown='notes',
                release_branch=None,
                pr_url=None,
            ),
        )
        confirm = mocker.patch(
            'releez.subapps.release_start.Confirm.ask',
            return_value=True,
        )

        result = invoke(
            cli.app,
            [
                'release',
                'start',
                '--maintenance-branch-regex',
                r'^support/(?P<major>\d+)\.x$',
            ],
        )

        assert result.exit_code == 0
        confirm.assert_called_once_with('Proceed?')


class TestReleaseStartOnMaintenanceBranch:
    """Tests for release start command on maintenance branch."""

    def test_release_start_on_maintenance_branch_uses_tag_pattern(
        self,
        mocker: MockerFixture,
        tmp_path: Path,
    ) -> None:
        repo_info = RepoInfo(
            root=tmp_path,
            remote_url='',
            active_branch='support/1.x',
        )
        mocker.patch(
            'releez.subapps.release.open_repo',
            return_value=mocker.Mock(
                repo=mocker.Mock(spec=Repo),
                info=repo_info,
            ),
        )

        cliff = mocker.Mock()
        cliff.compute_next_version.return_value = '1.5.0'
        mocker.patch('releez.cli_utils.GitCliff', return_value=cliff)

        start_release = mocker.patch(
            'releez.subapps.release_start.start_release',
            return_value=mocker.Mock(
                version='1.5.0',
                release_notes_markdown='notes',
                release_branch=None,
                pr_url=None,
            ),
        )

        result = invoke(
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
        assert release_input.maintenance_tag_pattern == '^1\\.[0-9]+\\.[0-9]+$'

    def test_release_start_on_maintenance_branch_sets_base_to_current(
        self,
        mocker: MockerFixture,
        tmp_path: Path,
    ) -> None:
        repo_info = RepoInfo(
            root=tmp_path,
            remote_url='',
            active_branch='support/2.x',
        )
        mocker.patch(
            'releez.subapps.release.open_repo',
            return_value=mocker.Mock(
                repo=mocker.Mock(spec=Repo),
                info=repo_info,
            ),
        )

        cliff = mocker.Mock()
        cliff.compute_next_version.return_value = '2.1.0'
        mocker.patch('releez.cli_utils.GitCliff', return_value=cliff)

        start_release = mocker.patch(
            'releez.subapps.release_start.start_release',
            return_value=mocker.Mock(
                version='2.1.0',
                release_notes_markdown='notes',
                release_branch=None,
                pr_url=None,
            ),
        )

        result = invoke(
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
        assert release_input.base_branch == 'support/2.x'

    def test_release_start_on_non_maintenance_branch_uses_base(
        self,
        mocker: MockerFixture,
        tmp_path: Path,
    ) -> None:
        repo_info = RepoInfo(
            root=tmp_path,
            remote_url='',
            active_branch='feature/my-feature',
        )
        mocker.patch(
            'releez.subapps.release.open_repo',
            return_value=mocker.Mock(
                repo=mocker.Mock(spec=Repo),
                info=repo_info,
            ),
        )

        start_release = mocker.patch(
            'releez.subapps.release_start.start_release',
            return_value=mocker.Mock(
                version='3.0.0',
                release_notes_markdown='notes',
                release_branch=None,
                pr_url=None,
            ),
        )

        result = invoke(
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
        assert release_input.base_branch == 'master'
        assert release_input.maintenance_tag_pattern is None

    def test_release_start_on_maintenance_branch_version_mismatch_fails(
        self,
        mocker: MockerFixture,
        tmp_path: Path,
    ) -> None:
        repo_info = RepoInfo(
            root=tmp_path,
            remote_url='',
            active_branch='support/1.x',
        )
        mocker.patch(
            'releez.subapps.release.open_repo',
            return_value=mocker.Mock(
                repo=mocker.Mock(spec=Repo),
                info=repo_info,
            ),
        )

        cliff = mocker.Mock()
        cliff.compute_next_version.return_value = '2.0.0'
        mocker.patch('releez.cli_utils.GitCliff', return_value=cliff)

        result = invoke(
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
        repo = mocker.Mock(spec=Repo)
        repo_info = RepoInfo(
            root=tmp_path,
            remote_url='',
            active_branch='support/1.x',
        )
        mocker.patch(
            'releez.subapps.release.open_repo',
            return_value=mocker.Mock(repo=repo, info=repo_info),
        )
        mocker.patch('releez.subapps.release_tag.fetch')

        cliff = mocker.Mock()
        cliff.compute_next_version.return_value = '1.5.0'
        mocker.patch('releez.cli_utils.GitCliff', return_value=cliff)

        mocker.patch('releez.subapps.release_tag.compute_version_tags')
        mocker.patch(
            'releez.subapps.release_tag.select_tags',
            return_value=['1.5.0'],
        )
        mocker.patch('releez.subapps.release_tag.create_tags')
        mocker.patch('releez.subapps.release_tag.push_tags')

        result = invoke(cli.app, ['release', 'tag'])

        assert result.exit_code == 0
        cliff.compute_next_version.assert_called_once_with(
            bump='auto',
            tag_pattern='^1\\.[0-9]+\\.[0-9]+$',
            include_paths=None,
        )

    def test_release_tag_on_maintenance_branch_version_mismatch_fails(
        self,
        mocker: MockerFixture,
        tmp_path: Path,
    ) -> None:
        repo = mocker.Mock(spec=Repo)
        repo_info = RepoInfo(
            root=tmp_path,
            remote_url='',
            active_branch='support/1.x',
        )
        mocker.patch(
            'releez.subapps.release.open_repo',
            return_value=mocker.Mock(repo=repo, info=repo_info),
        )
        mocker.patch('releez.subapps.release_tag.fetch')

        cliff = mocker.Mock()
        cliff.compute_next_version.return_value = '2.0.0'
        mocker.patch('releez.cli_utils.GitCliff', return_value=cliff)

        mocker.patch('releez.subapps.release_tag.compute_version_tags')
        mocker.patch(
            'releez.subapps.release_tag.select_tags',
            return_value=['2.0.0'],
        )

        result = invoke(cli.app, ['release', 'tag'])

        assert result.exit_code == 1
        assert 'does not match maintenance branch' in result.output


class TestReleasePreviewOnMaintenanceBranch:
    """Tests for release preview command on maintenance branch."""

    def test_release_preview_on_maintenance_branch_uses_tag_pattern(
        self,
        mocker: MockerFixture,
        tmp_path: Path,
    ) -> None:
        repo_info = RepoInfo(
            root=tmp_path,
            remote_url='',
            active_branch='support/3.x',
        )
        mocker.patch(
            'releez.subapps.release.open_repo',
            return_value=mocker.Mock(
                repo=mocker.Mock(spec=Repo),
                info=repo_info,
            ),
        )

        cliff = mocker.Mock()
        cliff.compute_next_version.return_value = '3.2.0'
        mocker.patch('releez.cli_utils.GitCliff', return_value=cliff)

        result = invoke(cli.app, ['release', 'preview'])

        assert result.exit_code == 0
        cliff.compute_next_version.assert_called_with(
            bump='auto',
            tag_pattern='^3\\.[0-9]+\\.[0-9]+$',
            include_paths=None,
        )
        assert '`3.2.0`' in result.stdout

    def test_release_preview_on_maintenance_branch_version_mismatch_fails(
        self,
        mocker: MockerFixture,
        tmp_path: Path,
    ) -> None:
        repo_info = RepoInfo(
            root=tmp_path,
            remote_url='',
            active_branch='support/1.x',
        )
        mocker.patch(
            'releez.subapps.release.open_repo',
            return_value=mocker.Mock(
                repo=mocker.Mock(spec=Repo),
                info=repo_info,
            ),
        )

        cliff = mocker.Mock()
        cliff.compute_next_version.return_value = '2.0.0'
        mocker.patch('releez.cli_utils.GitCliff', return_value=cliff)

        result = invoke(cli.app, ['release', 'preview'])

        assert result.exit_code == 1
        assert 'does not match maintenance branch' in result.output


class TestReleaseNotesOnMaintenanceBranch:
    """Tests for release notes command on maintenance branch."""

    def test_release_notes_on_maintenance_branch_uses_tag_pattern(
        self,
        mocker: MockerFixture,
        tmp_path: Path,
    ) -> None:
        repo_info = RepoInfo(
            root=tmp_path,
            remote_url='',
            active_branch='support/2.x',
        )
        mocker.patch(
            'releez.subapps.release.open_repo',
            return_value=mocker.Mock(
                repo=mocker.Mock(spec=Repo),
                info=repo_info,
            ),
        )

        cliff = mocker.Mock()
        cliff.compute_next_version.return_value = '2.7.0'
        cliff.generate_unreleased_notes.return_value = '## 2.7.0\n\n- Fix\n'
        mocker.patch('releez.cli_utils.GitCliff', return_value=cliff)
        mocker.patch(
            'releez.subapps.release_notes.GitCliff',
            return_value=cliff,
        )

        result = invoke(cli.app, ['release', 'notes'])

        assert result.exit_code == 0
        cliff.compute_next_version.assert_called_with(
            bump='auto',
            tag_pattern='^2\\.[0-9]+\\.[0-9]+$',
            include_paths=None,
        )
        cliff.generate_unreleased_notes.assert_called_once_with(
            version='2.7.0',
            tag_pattern='^2\\.[0-9]+\\.[0-9]+$',
        )
        assert '## 2.7.0' in result.stdout

    def test_release_notes_on_maintenance_branch_version_mismatch_fails(
        self,
        mocker: MockerFixture,
        tmp_path: Path,
    ) -> None:
        repo_info = RepoInfo(
            root=tmp_path,
            remote_url='',
            active_branch='support/1.x',
        )
        mocker.patch(
            'releez.subapps.release.open_repo',
            return_value=mocker.Mock(
                repo=mocker.Mock(spec=Repo),
                info=repo_info,
            ),
        )

        cliff = mocker.Mock()
        cliff.compute_next_version.return_value = '2.0.0'
        mocker.patch('releez.cli_utils.GitCliff', return_value=cliff)

        result = invoke(cli.app, ['release', 'notes'])

        assert result.exit_code == 1
        assert 'does not match maintenance branch' in result.output


class TestMonorepoMaintenanceTagPattern:
    """Tests for _monorepo_maintenance_tag_pattern."""

    def test_generates_prefix_scoped_pattern(self) -> None:
        assert _monorepo_maintenance_tag_pattern('ui-', 2) == r'^ui\-2\.[0-9]+\.[0-9]+$'

    def test_escapes_special_chars_in_prefix(self) -> None:
        pattern = _monorepo_maintenance_tag_pattern('my.pkg-', 1)
        assert pattern == r'^my\.pkg\-1\.[0-9]+\.[0-9]+$'


class TestMonorepoMaintenanceContext:
    """Tests for _monorepo_maintenance_context."""

    def _make_project(
        self,
        mocker: MockerFixture,
        name: str,
        tag_prefix: str,
    ) -> SubProject:
        p = mocker.MagicMock(spec=SubProject)
        p.name = name
        p.tag_prefix = tag_prefix
        return p

    _DEFAULT_REGEX = r'^support/(?P<major>\d+)\.x$'

    def test_returns_none_when_branch_is_none(
        self,
        mocker: MockerFixture,
    ) -> None:
        proj = self._make_project(mocker, 'ui', 'ui-')
        assert (
            _monorepo_maintenance_context(
                None,
                [proj],
                regex=self._DEFAULT_REGEX,
            )
            is None
        )

    def test_returns_none_when_no_project_matches(
        self,
        mocker: MockerFixture,
    ) -> None:
        proj = self._make_project(mocker, 'ui', 'ui-')
        assert (
            _monorepo_maintenance_context(
                'support/core-1.x',
                [proj],
                regex=self._DEFAULT_REGEX,
            )
            is None
        )

    def test_returns_none_when_project_has_no_prefix(
        self,
        mocker: MockerFixture,
    ) -> None:
        proj = self._make_project(mocker, 'myapp', '')
        assert (
            _monorepo_maintenance_context(
                'support/1.x',
                [proj],
                regex=self._DEFAULT_REGEX,
            )
            is None
        )

    def test_matches_project_by_prefix(self, mocker: MockerFixture) -> None:
        ui = self._make_project(mocker, 'ui', 'ui-')
        core = self._make_project(mocker, 'core', 'core-')
        result = _monorepo_maintenance_context(
            'support/ui-3.x',
            [ui, core],
            regex=self._DEFAULT_REGEX,
        )
        assert result is not None
        project, ctx = result
        assert project is ui
        assert ctx.major == 3
        assert ctx.branch == 'support/ui-3.x'
        assert ctx.tag_pattern == r'^ui\-3\.[0-9]+\.[0-9]+$'

    def test_returns_correct_major(self, mocker: MockerFixture) -> None:
        core = self._make_project(mocker, 'core', 'core-')
        result = _monorepo_maintenance_context(
            'support/core-12.x',
            [core],
            regex=self._DEFAULT_REGEX,
        )
        assert result is not None
        _, ctx = result
        assert ctx.major == 12

    def test_prefix_group_regex_matches_project_by_prefix(
        self,
        mocker: MockerFixture,
    ) -> None:
        """When regex has (?P<prefix>...) group, uses it to detect the project."""
        ui = self._make_project(mocker, 'ui', 'ui-')
        core = self._make_project(mocker, 'core', 'core-')
        regex = r'^support/(?P<prefix>[a-z]+-)?(?P<major>\d+)\.x$'
        result = _monorepo_maintenance_context(
            'support/ui-3.x',
            [ui, core],
            regex=regex,
        )
        assert result is not None
        project, ctx = result
        assert project is ui
        assert ctx.major == 3
        assert ctx.branch == 'support/ui-3.x'

    def test_prefix_group_regex_returns_none_when_no_match(
        self,
        mocker: MockerFixture,
    ) -> None:
        ui = self._make_project(mocker, 'ui', 'ui-')
        regex = r'^support/(?P<prefix>[a-z]+-)?(?P<major>\d+)\.x$'
        assert _monorepo_maintenance_context('hotfix/ui-1.x', [ui], regex=regex) is None

    def test_prefix_group_regex_returns_none_when_prefix_matches_no_project(
        self,
        mocker: MockerFixture,
    ) -> None:
        ui = self._make_project(mocker, 'ui', 'ui-')
        regex = r'^support/(?P<prefix>[a-z]+-)?(?P<major>\d+)\.x$'
        assert _monorepo_maintenance_context('support/core-1.x', [ui], regex=regex) is None


class TestMonorepoMaintenanceContextEdgeCases:
    """Edge-case tests for _monorepo_maintenance_context."""

    def _make_project(
        self,
        mocker: MockerFixture,
        name: str,
        tag_prefix: str,
    ) -> SubProject:
        p = mocker.MagicMock(spec=SubProject)
        p.name = name
        p.tag_prefix = tag_prefix
        return p

    def test_returns_none_when_regex_is_invalid(
        self,
        mocker: MockerFixture,
    ) -> None:
        """An invalid regex silently returns None (errors surfaced elsewhere)."""
        ui = self._make_project(mocker, 'ui', 'ui-')
        assert (
            _monorepo_maintenance_context(
                'support/ui-1.x',
                [ui],
                regex='[invalid(regex',
            )
            is None
        )

    def test_returns_none_when_prefix_group_major_is_non_integer(
        self,
        mocker: MockerFixture,
    ) -> None:
        """Prefix-group regex whose major group captures a non-integer returns None."""
        ui = self._make_project(mocker, 'ui', 'ui-')
        regex = r'^support/(?P<prefix>[a-z]+-)?(?P<major>[a-z]+)\.x$'
        assert _monorepo_maintenance_context('support/ui-abc.x', [ui], regex=regex) is None


class TestValidateSupportBranchName:
    """Tests for _validate_support_branch_name pre-flight check."""

    def test_single_repo_valid_name_passes(self) -> None:
        _validate_support_branch_name(
            branch_name='support/1.x',
            tag_prefix='',
            major=1,
            maintenance_regex=r'^support/(?P<major>\d+)\.x$',
        )

    def test_single_repo_mismatch_raises(self) -> None:
        with pytest.raises(ReleezError, match='maintenance-branch-regex'):
            _validate_support_branch_name(
                branch_name='hotfix/1.x',
                tag_prefix='',
                major=1,
                maintenance_regex=r'^support/(?P<major>\d+)\.x$',
            )

    def test_monorepo_valid_name_passes(self) -> None:
        _validate_support_branch_name(
            branch_name='support/ui-1.x',
            tag_prefix='ui-',
            major=1,
            maintenance_regex=r'^support/(?P<major>\d+)\.x$',
        )

    def test_monorepo_with_prefix_group_regex_valid_passes(self) -> None:
        _validate_support_branch_name(
            branch_name='support/ui-1.x',
            tag_prefix='ui-',
            major=1,
            maintenance_regex=r'^support/(?P<prefix>[a-z]+-)?(?P<major>\d+)\.x$',
        )

    def test_monorepo_with_prefix_group_regex_no_match_raises(self) -> None:
        with pytest.raises(ReleezError, match='maintenance-branch-regex'):
            _validate_support_branch_name(
                branch_name='hotfix/ui-1.x',
                tag_prefix='ui-',
                major=1,
                maintenance_regex=r'^support/(?P<prefix>[a-z]+-)?(?P<major>\d+)\.x$',
            )

    def test_monorepo_with_prefix_group_regex_wrong_prefix_raises(self) -> None:
        with pytest.raises(ReleezError, match='maintenance-branch-regex'):
            _validate_support_branch_name(
                branch_name='support/core-1.x',
                tag_prefix='ui-',
                major=1,
                maintenance_regex=r'^support/(?P<prefix>[a-z]+-)?(?P<major>\d+)\.x$',
            )

    def test_monorepo_invalid_regex_raises(self) -> None:
        with pytest.raises(InvalidMaintenanceBranchRegexError):
            _validate_support_branch_name(
                branch_name='support/ui-1.x',
                tag_prefix='ui-',
                major=1,
                maintenance_regex='[invalid(regex',
            )

    def test_monorepo_per_project_fallback_mismatch_raises(self) -> None:
        with pytest.raises(ReleezError, match='maintenance-branch-regex'):
            _validate_support_branch_name(
                branch_name='hotfix/ui-1.x',
                tag_prefix='ui-',
                major=1,
                maintenance_regex=r'^support/(?P<major>\d+)\.x$',
            )


class TestMonorepoReleaseStartOnMaintenanceBranch:
    """Tests for monorepo release start on a maintenance branch."""

    def _mock_project(
        self,
        mocker: MockerFixture,
        name: str,
        tag_prefix: str,
        tmp_path: Path,
    ) -> MagicMock:
        p = mocker.MagicMock()
        p.name = name
        p.tag_prefix = tag_prefix
        p.tag_pattern = f'^{tag_prefix}([0-9]+\\.[0-9]+\\.[0-9]+)$'
        p.path = tmp_path
        p.alias_versions = mocker.MagicMock()
        p.hooks.post_changelog = []
        p.include_paths = []
        return p

    def test_monorepo_release_start_on_maintenance_branch_uses_maintenance_tag_pattern(
        self,
        mocker: MockerFixture,
        tmp_path: Path,
    ) -> None:
        """On support/ui-1.x, release start for project ui uses prefix-scoped tag pattern."""
        repo_info = RepoInfo(
            root=tmp_path,
            remote_url='',
            active_branch='support/ui-1.x',
        )
        mocker.patch(
            'releez.subapps.release.open_repo',
            return_value=mocker.Mock(
                repo=mocker.Mock(spec=Repo),
                info=repo_info,
            ),
        )
        ui = self._mock_project(mocker, 'ui', 'ui-', tmp_path)
        mocker.patch(
            'releez.subapps.release._resolve_target_projects',
            return_value=[ui],
        )
        mocker.patch(
            'releez.subapps.release._project_include_paths',
            return_value=[],
        )
        mocker.patch(
            'releez.subapps.release._project_changelog_path',
            return_value=str(tmp_path / 'CHANGELOG.md'),
        )
        cliff = mocker.Mock()
        cliff.compute_next_version.return_value = '1.5.0'
        mocker.patch('releez.cli_utils.GitCliff', return_value=cliff)
        start_release = mocker.patch(
            'releez.subapps.release_start.start_release',
            return_value=mocker.Mock(
                version='ui-1.5.0',
                release_notes_markdown='notes',
                release_branch=None,
                pr_url=None,
            ),
        )

        result = invoke(
            cli.app,
            ['release', 'start', '--dry-run', '--project', 'ui'],
        )

        assert result.exit_code == 0, result.output
        release_input = start_release.call_args.args[0]
        assert release_input.maintenance_tag_pattern == r'^ui\-1\.[0-9]+\.[0-9]+$'
        assert release_input.base_branch == 'support/ui-1.x'

    def test_monorepo_release_start_non_maintenance_branch_unaffected(
        self,
        mocker: MockerFixture,
        tmp_path: Path,
    ) -> None:
        """On master, monorepo release start for project ui has no maintenance tag pattern."""
        repo_info = RepoInfo(
            root=tmp_path,
            remote_url='',
            active_branch='master',
        )
        mocker.patch(
            'releez.subapps.release.open_repo',
            return_value=mocker.Mock(
                repo=mocker.Mock(spec=Repo),
                info=repo_info,
            ),
        )
        ui = self._mock_project(mocker, 'ui', 'ui-', tmp_path)
        mocker.patch(
            'releez.subapps.release._resolve_target_projects',
            return_value=[ui],
        )
        mocker.patch(
            'releez.subapps.release._project_include_paths',
            return_value=[],
        )
        mocker.patch(
            'releez.subapps.release._project_changelog_path',
            return_value=str(tmp_path / 'CHANGELOG.md'),
        )
        start_release = mocker.patch(
            'releez.subapps.release_start.start_release',
            return_value=mocker.Mock(
                version='ui-2.0.0',
                release_notes_markdown='notes',
                release_branch=None,
                pr_url=None,
            ),
        )

        result = invoke(
            cli.app,
            ['release', 'start', '--dry-run', '--project', 'ui'],
        )

        assert result.exit_code == 0, result.output
        release_input = start_release.call_args.args[0]
        assert release_input.maintenance_tag_pattern is None

    def test_monorepo_release_start_maintenance_branch_version_mismatch_fails(
        self,
        mocker: MockerFixture,
        tmp_path: Path,
    ) -> None:
        """On support/ui-1.x, if git-cliff returns 2.x version, it should fail."""
        repo_info = RepoInfo(
            root=tmp_path,
            remote_url='',
            active_branch='support/ui-1.x',
        )
        mocker.patch(
            'releez.subapps.release.open_repo',
            return_value=mocker.Mock(
                repo=mocker.Mock(spec=Repo),
                info=repo_info,
            ),
        )
        ui = self._mock_project(mocker, 'ui', 'ui-', tmp_path)
        mocker.patch(
            'releez.subapps.release._resolve_target_projects',
            return_value=[ui],
        )
        mocker.patch(
            'releez.subapps.release._project_include_paths',
            return_value=[],
        )
        cliff = mocker.Mock()
        cliff.compute_next_version.return_value = '2.0.0'
        mocker.patch('releez.cli_utils.GitCliff', return_value=cliff)

        result = invoke(
            cli.app,
            ['release', 'start', '--dry-run', '--project', 'ui'],
        )

        assert result.exit_code == 1
        assert 'does not match maintenance branch' in result.output
