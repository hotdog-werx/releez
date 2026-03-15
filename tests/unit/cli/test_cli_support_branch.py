from __future__ import annotations

from typing import TYPE_CHECKING

from typer.testing import CliRunner

from releez import cli
from releez.errors import (
    GitBranchExistsError,
    InvalidSupportBranchCommitError,
    MajorVersionAlreadyLatestError,
)
from releez.git_repo import RepoInfo

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture


def _make_repo_mock(mocker: MockerFixture, tmp_path: Path) -> object:
    repo_info = RepoInfo(root=tmp_path, remote_url='', active_branch='master')
    return mocker.Mock(repo=mocker.Mock(), info=repo_info)


def _make_project_mock(
    mocker: MockerFixture,
    name: str,
    tag_prefix: str,
) -> object:
    p = mocker.MagicMock()
    p.name = name
    p.tag_prefix = tag_prefix
    return p


class TestSupportBranchSingleRepo:
    def test_happy_path_creates_branch(
        self,
        mocker: MockerFixture,
        tmp_path: Path,
    ) -> None:
        """Single-repo: creates support/1.x from the latest 1.x.x tag."""
        runner = CliRunner()
        tag_obj = mocker.Mock()
        tag_obj.name = '1.4.0'
        tag_obj.commit.hexsha = 'abc1234def5678901234abcd'
        repo_mock = mocker.Mock()
        repo_mock.tags = [tag_obj]
        mocker.patch(
            'releez.cli.open_repo',
            return_value=mocker.Mock(
                repo=repo_mock,
                info=RepoInfo(
                    root=tmp_path,
                    remote_url='',
                    active_branch='master',
                ),
            ),
        )
        mocker.patch('releez.cli._build_subprojects_list', return_value=[])
        mocker.patch('releez.cli.find_all_major_versions', return_value=[1, 2])
        mocker.patch(
            'releez.cli.find_latest_tag_matching_pattern',
            return_value='1.4.0',
        )
        create_branch = mocker.patch('releez.cli.create_branch_from_ref')

        result = runner.invoke(cli.app, ['release', 'support-branch', '1'])

        assert result.exit_code == 0, result.output
        create_branch.assert_called_once()
        assert create_branch.call_args.kwargs['name'] == 'support/1.x'

    def test_dry_run_does_not_create_branch(
        self,
        mocker: MockerFixture,
        tmp_path: Path,
    ) -> None:
        """--dry-run prints intent but does not call create_branch_from_ref."""
        runner = CliRunner()
        tag_obj = mocker.Mock()
        tag_obj.name = '1.4.0'
        tag_obj.commit.hexsha = 'abc1234def5678901234abcd'
        repo_mock = mocker.Mock()
        repo_mock.tags = [tag_obj]
        ctx_mock = mocker.Mock(
            repo=repo_mock,
            info=RepoInfo(root=tmp_path, remote_url='', active_branch='master'),
        )
        mocker.patch('releez.cli.open_repo', return_value=ctx_mock)
        mocker.patch('releez.cli._build_subprojects_list', return_value=[])
        mocker.patch('releez.cli.find_all_major_versions', return_value=[1, 2])
        mocker.patch(
            'releez.cli.find_latest_tag_matching_pattern',
            return_value='1.4.0',
        )
        create_branch = mocker.patch('releez.cli.create_branch_from_ref')

        result = runner.invoke(
            cli.app,
            ['release', 'support-branch', '1', '--dry-run'],
        )

        assert result.exit_code == 0, result.output
        assert "Would create branch 'support/1.x'" in result.output
        create_branch.assert_not_called()

    def test_project_flag_in_single_repo_mode_errors(
        self,
        mocker: MockerFixture,
        tmp_path: Path,
    ) -> None:
        """--project is not valid in single-repo mode."""
        runner = CliRunner()
        mocker.patch(
            'releez.cli.open_repo',
            return_value=mocker.Mock(
                repo=mocker.Mock(),
                info=RepoInfo(
                    root=tmp_path,
                    remote_url='',
                    active_branch='master',
                ),
            ),
        )
        mocker.patch('releez.cli._build_subprojects_list', return_value=[])

        result = runner.invoke(
            cli.app,
            ['release', 'support-branch', '1', '--project', 'core'],
        )

        assert result.exit_code == 1
        assert 'only valid in monorepo mode' in result.output

    def test_major_is_latest_errors(
        self,
        mocker: MockerFixture,
        tmp_path: Path,
    ) -> None:
        """Requesting a support branch for the latest major is an error."""
        runner = CliRunner()
        mocker.patch(
            'releez.cli.open_repo',
            return_value=mocker.Mock(
                repo=mocker.Mock(),
                info=RepoInfo(
                    root=tmp_path,
                    remote_url='',
                    active_branch='master',
                ),
            ),
        )
        mocker.patch('releez.cli._build_subprojects_list', return_value=[])
        mocker.patch('releez.cli.find_all_major_versions', return_value=[1, 2])

        result = runner.invoke(cli.app, ['release', 'support-branch', '2'])

        assert result.exit_code == 1
        assert 'latest major' in result.output

    def test_no_tags_for_major_errors(
        self,
        mocker: MockerFixture,
        tmp_path: Path,
    ) -> None:
        """No tags for the requested major is an error."""
        runner = CliRunner()
        mocker.patch(
            'releez.cli.open_repo',
            return_value=mocker.Mock(
                repo=mocker.Mock(),
                info=RepoInfo(
                    root=tmp_path,
                    remote_url='',
                    active_branch='master',
                ),
            ),
        )
        mocker.patch('releez.cli._build_subprojects_list', return_value=[])
        mocker.patch('releez.cli.find_all_major_versions', return_value=[2])

        result = runner.invoke(cli.app, ['release', 'support-branch', '1'])

        assert result.exit_code == 1
        assert '1' in result.output

    def test_branch_already_exists_errors(
        self,
        mocker: MockerFixture,
        tmp_path: Path,
    ) -> None:
        """GitBranchExistsError propagates as an exit code 1."""
        runner = CliRunner()
        tag_obj = mocker.Mock()
        tag_obj.name = '1.4.0'
        tag_obj.commit.hexsha = 'abc1234def5678901234abcd'
        repo_mock = mocker.Mock()
        repo_mock.tags = [tag_obj]
        mocker.patch(
            'releez.cli.open_repo',
            return_value=mocker.Mock(
                repo=repo_mock,
                info=RepoInfo(
                    root=tmp_path,
                    remote_url='',
                    active_branch='master',
                ),
            ),
        )
        mocker.patch('releez.cli._build_subprojects_list', return_value=[])
        mocker.patch('releez.cli.find_all_major_versions', return_value=[1, 2])
        mocker.patch(
            'releez.cli.find_latest_tag_matching_pattern',
            return_value='1.4.0',
        )
        mocker.patch(
            'releez.cli.create_branch_from_ref',
            side_effect=GitBranchExistsError('support/1.x'),
        )

        result = runner.invoke(cli.app, ['release', 'support-branch', '1'])

        assert result.exit_code == 1
        assert 'support/1.x' in result.output

    def test_commit_override_valid(
        self,
        mocker: MockerFixture,
        tmp_path: Path,
    ) -> None:
        """A valid --commit uses the provided SHA as the split point."""
        runner = CliRunner()
        tag_obj = mocker.Mock()
        tag_obj.name = '1.4.0'
        tag_obj.commit.hexsha = 'tag1234' * 4 + 'tag12345'
        repo_mock = mocker.Mock()
        repo_mock.tags = [tag_obj]
        mocker.patch(
            'releez.cli.open_repo',
            return_value=mocker.Mock(
                repo=repo_mock,
                info=RepoInfo(
                    root=tmp_path,
                    remote_url='',
                    active_branch='master',
                ),
            ),
        )
        mocker.patch('releez.cli._build_subprojects_list', return_value=[])
        mocker.patch('releez.cli.find_all_major_versions', return_value=[1, 2])
        mocker.patch(
            'releez.cli.find_latest_tag_matching_pattern',
            return_value='1.4.0',
        )
        custom_sha = 'deadbeef' * 4 + 'deadbeef'
        mocker.patch(
            'releez.cli.validate_commit_for_major',
            return_value=custom_sha,
        )
        create_branch = mocker.patch('releez.cli.create_branch_from_ref')

        result = runner.invoke(
            cli.app,
            ['release', 'support-branch', '1', '--commit', 'deadbeef'],
        )

        assert result.exit_code == 0, result.output
        create_branch.assert_called_once()
        assert create_branch.call_args.kwargs['ref'] == custom_sha

    def test_commit_override_invalid_errors(
        self,
        mocker: MockerFixture,
        tmp_path: Path,
    ) -> None:
        """An invalid --commit produces exit code 1."""
        runner = CliRunner()
        tag_obj = mocker.Mock()
        tag_obj.name = '1.4.0'
        tag_obj.commit.hexsha = 'abc1234def5678901234abcd'
        repo_mock = mocker.Mock()
        repo_mock.tags = [tag_obj]
        mocker.patch(
            'releez.cli.open_repo',
            return_value=mocker.Mock(
                repo=repo_mock,
                info=RepoInfo(
                    root=tmp_path,
                    remote_url='',
                    active_branch='master',
                ),
            ),
        )
        mocker.patch('releez.cli._build_subprojects_list', return_value=[])
        mocker.patch('releez.cli.find_all_major_versions', return_value=[1, 2])
        mocker.patch(
            'releez.cli.find_latest_tag_matching_pattern',
            return_value='1.4.0',
        )
        mocker.patch(
            'releez.cli.validate_commit_for_major',
            side_effect=InvalidSupportBranchCommitError(
                commit='badsha',
                major=1,
                reason='not an ancestor',
            ),
        )

        result = runner.invoke(
            cli.app,
            ['release', 'support-branch', '1', '--commit', 'badsha'],
        )

        assert result.exit_code == 1
        assert 'badsha' in result.output


class TestSupportBranchMonorepo:
    def _mock_project(
        self,
        mocker: MockerFixture,
        name: str,
        tag_prefix: str,
    ) -> object:
        return _make_project_mock(mocker, name, tag_prefix)

    def test_monorepo_happy_path(
        self,
        mocker: MockerFixture,
        tmp_path: Path,
    ) -> None:
        """Monorepo: --project ui creates support/ui-1.x from ui-1.4.0."""
        runner = CliRunner()
        tag_obj = mocker.Mock()
        tag_obj.name = 'ui-1.4.0'
        tag_obj.commit.hexsha = 'abc1234def5678901234abcd'
        repo_mock = mocker.Mock()
        repo_mock.tags = [tag_obj]
        ui = self._mock_project(mocker, 'ui', 'ui-')
        mocker.patch(
            'releez.cli.open_repo',
            return_value=mocker.Mock(
                repo=repo_mock,
                info=RepoInfo(
                    root=tmp_path,
                    remote_url='',
                    active_branch='master',
                ),
            ),
        )
        mocker.patch('releez.cli._build_subprojects_list', return_value=[ui])
        mocker.patch(
            'releez.cli._selected_projects_from_names',
            return_value=[ui],
        )
        mocker.patch('releez.cli.find_all_major_versions', return_value=[1, 2])
        mocker.patch(
            'releez.cli.find_latest_tag_matching_pattern',
            return_value='ui-1.4.0',
        )
        create_branch = mocker.patch('releez.cli.create_branch_from_ref')

        result = runner.invoke(
            cli.app,
            ['release', 'support-branch', '1', '--project', 'ui'],
        )

        assert result.exit_code == 0, result.output
        create_branch.assert_called_once()
        assert create_branch.call_args.kwargs['name'] == 'support/ui-1.x'

    def test_monorepo_missing_project_errors(
        self,
        mocker: MockerFixture,
        tmp_path: Path,
    ) -> None:
        """Monorepo mode without --project produces a helpful error."""
        runner = CliRunner()
        ui = self._mock_project(mocker, 'ui', 'ui-')
        mocker.patch(
            'releez.cli.open_repo',
            return_value=mocker.Mock(
                repo=mocker.Mock(),
                info=RepoInfo(
                    root=tmp_path,
                    remote_url='',
                    active_branch='master',
                ),
            ),
        )
        mocker.patch('releez.cli._build_subprojects_list', return_value=[ui])

        result = runner.invoke(cli.app, ['release', 'support-branch', '1'])

        assert result.exit_code == 1
        assert '--project is required' in result.output

    def test_monorepo_major_is_latest_errors(
        self,
        mocker: MockerFixture,
        tmp_path: Path,
    ) -> None:
        """MajorVersionAlreadyLatestError propagates from monorepo path."""
        runner = CliRunner()
        ui = self._mock_project(mocker, 'ui', 'ui-')
        mocker.patch(
            'releez.cli.open_repo',
            return_value=mocker.Mock(
                repo=mocker.Mock(),
                info=RepoInfo(
                    root=tmp_path,
                    remote_url='',
                    active_branch='master',
                ),
            ),
        )
        mocker.patch('releez.cli._build_subprojects_list', return_value=[ui])
        mocker.patch(
            'releez.cli._selected_projects_from_names',
            return_value=[ui],
        )
        mocker.patch(
            'releez.cli.find_all_major_versions',
            side_effect=MajorVersionAlreadyLatestError(major=2, latest_major=2),
        )

        result = runner.invoke(
            cli.app,
            ['release', 'support-branch', '2', '--project', 'ui'],
        )

        assert result.exit_code == 1
        assert 'latest major' in result.output

    def test_monorepo_dry_run(
        self,
        mocker: MockerFixture,
        tmp_path: Path,
    ) -> None:
        """--dry-run in monorepo mode does not create the branch."""
        runner = CliRunner()
        tag_obj = mocker.Mock()
        tag_obj.name = 'ui-1.4.0'
        tag_obj.commit.hexsha = 'abc1234def5678901234abcd'
        repo_mock = mocker.Mock()
        repo_mock.tags = [tag_obj]
        ui = self._mock_project(mocker, 'ui', 'ui-')
        mocker.patch(
            'releez.cli.open_repo',
            return_value=mocker.Mock(
                repo=repo_mock,
                info=RepoInfo(
                    root=tmp_path,
                    remote_url='',
                    active_branch='master',
                ),
            ),
        )
        mocker.patch('releez.cli._build_subprojects_list', return_value=[ui])
        mocker.patch(
            'releez.cli._selected_projects_from_names',
            return_value=[ui],
        )
        mocker.patch('releez.cli.find_all_major_versions', return_value=[1, 2])
        mocker.patch(
            'releez.cli.find_latest_tag_matching_pattern',
            return_value='ui-1.4.0',
        )
        create_branch = mocker.patch('releez.cli.create_branch_from_ref')

        result = runner.invoke(
            cli.app,
            ['release', 'support-branch', '1', '--project', 'ui', '--dry-run'],
        )

        assert result.exit_code == 0, result.output
        assert "Would create branch 'support/ui-1.x'" in result.output
        create_branch.assert_not_called()
