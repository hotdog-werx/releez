from __future__ import annotations

from typing import TYPE_CHECKING

from invoke_helper import invoke

from releez import cli
from releez.errors import MissingCliError

if TYPE_CHECKING:
    from pathlib import Path
    from unittest.mock import MagicMock

    from pytest_mock import MockerFixture


def _mock_settings(  # noqa: PLR0913
    mocker: MockerFixture,
    *,
    base_branch: str = 'master',
    git_remote: str = 'origin',
    changelog_path: str = 'CHANGELOG.md',
    create_pr: bool = False,
    is_monorepo: bool = False,
    projects: list | None = None,
) -> MagicMock:
    mock = mocker.MagicMock(
        base_branch=base_branch,
        git_remote=git_remote,
        changelog_path=changelog_path,
        create_pr=create_pr,
        is_monorepo=is_monorepo,
        projects=projects or [],
    )
    mocker.patch('releez.subapps.doctor.ReleezSettings', return_value=mock)
    return mock


def _mock_repo(
    mocker: MockerFixture,
    *,
    root: Path,
    is_dirty: bool = False,
    remotes: list[str] | None = None,
    rev_parse_raises: bool = False,
) -> MagicMock:
    repo = mocker.MagicMock()
    repo.is_dirty.return_value = is_dirty

    available_remotes = remotes if remotes is not None else ['origin']
    remote_names = {name: mocker.MagicMock() for name in available_remotes}

    def _getitem(_self: object, key: str | int) -> MagicMock:
        if isinstance(key, str):
            if key not in remote_names:
                raise IndexError(key)
            return remote_names[key]
        try:
            return list(remote_names.values())[key]
        except IndexError as exc:
            raise IndexError(key) from exc

    repo.remotes.__getitem__ = _getitem

    if rev_parse_raises:
        repo.git.rev_parse.side_effect = Exception('not found')
    else:
        repo.git.rev_parse.return_value = 'abc123'

    ctx = mocker.MagicMock()
    ctx.repo = repo
    ctx.info.root = root

    mocker.patch('releez.subapps.doctor.open_repo', return_value=ctx)
    return repo


def _write_cliff_toml(path: Path, content: str = '') -> None:
    cliff = path / 'cliff.toml'
    if content:
        cliff.write_text(content, encoding='utf-8')
    else:
        cliff.write_text(
            '[changelog]\nheader = ""\n\n[git]\ncommit_parsers = [\n  {message = "^feat", group = "Features"},\n]\n',
            encoding='utf-8',
        )


class TestDoctorAllPass:
    def test_all_checks_pass_exits_zero(
        self,
        mocker: MockerFixture,
        tmp_path: Path,
    ) -> None:
        """When all checks pass, the command exits 0 and prints check marks."""
        mocker.patch(
            'releez.subapps.doctor.shutil.which',
            return_value='/usr/bin/git',
        )
        mocker.patch(
            'releez.subapps.doctor._git_cliff_base_cmd',
            return_value=['git-cliff'],
        )
        _write_cliff_toml(tmp_path)
        (tmp_path / 'CHANGELOG.md').touch()
        _mock_repo(mocker, root=tmp_path)
        _mock_settings(mocker)

        result = invoke(cli.app, ['doctor'])

        assert result.exit_code == 0
        assert '✓' in result.stdout
        assert 'Doctor:' in result.stdout
        assert 'failed' in result.stdout

    def test_summary_shows_counts(
        self,
        mocker: MockerFixture,
        tmp_path: Path,
    ) -> None:
        """The final summary line reports passed/warning/failed counts."""
        mocker.patch(
            'releez.subapps.doctor.shutil.which',
            return_value='/usr/bin/git',
        )
        mocker.patch(
            'releez.subapps.doctor._git_cliff_base_cmd',
            return_value=['git-cliff'],
        )
        _write_cliff_toml(tmp_path)
        (tmp_path / 'CHANGELOG.md').touch()
        _mock_repo(mocker, root=tmp_path)
        _mock_settings(mocker)

        result = invoke(cli.app, ['doctor'])

        assert 'Doctor:' in result.output
        assert '0 failed' in result.output


class TestDoctorGitChecks:
    def test_git_not_available_exits_one(
        self,
        mocker: MockerFixture,
    ) -> None:
        """When git is not on PATH, the git check fails and the command exits 1."""
        mocker.patch('releez.subapps.doctor.shutil.which', return_value=None)
        mocker.patch(
            'releez.subapps.doctor._git_cliff_base_cmd',
            return_value=['git-cliff'],
        )
        mocker.patch(
            'releez.subapps.doctor.open_repo',
            side_effect=Exception('no git'),
        )
        mocker.patch(
            'releez.subapps.doctor.ReleezSettings',
            side_effect=Exception('no settings'),
        )

        result = invoke(cli.app, ['doctor'])

        assert result.exit_code == 1
        assert '✗' in result.stderr

    def test_git_cliff_not_available_exits_one(
        self,
        mocker: MockerFixture,
    ) -> None:
        """When git-cliff is missing, the git-cliff check fails and the command exits 1."""
        mocker.patch(
            'releez.subapps.doctor.shutil.which',
            return_value='/usr/bin/git',
        )
        mocker.patch(
            'releez.subapps.doctor._git_cliff_base_cmd',
            side_effect=MissingCliError('git-cliff'),
        )
        mocker.patch(
            'releez.subapps.doctor.open_repo',
            side_effect=Exception('no repo'),
        )
        mocker.patch(
            'releez.subapps.doctor.ReleezSettings',
            side_effect=Exception('no settings'),
        )

        result = invoke(cli.app, ['doctor'])

        assert result.exit_code == 1
        assert '✗' in result.stderr


class TestDoctorRepoCheck:
    def test_not_in_git_repo_exits_one(
        self,
        mocker: MockerFixture,
    ) -> None:
        """When the CWD is not inside a git repo, the repo check fails and exits 1."""
        mocker.patch(
            'releez.subapps.doctor.shutil.which',
            return_value='/usr/bin/git',
        )
        mocker.patch(
            'releez.subapps.doctor._git_cliff_base_cmd',
            return_value=['git-cliff'],
        )
        mocker.patch(
            'releez.subapps.doctor.open_repo',
            side_effect=Exception('not a repo'),
        )
        mocker.patch(
            'releez.subapps.doctor.ReleezSettings',
            side_effect=Exception('no settings'),
        )

        result = invoke(cli.app, ['doctor'])

        assert result.exit_code == 1
        assert 'not inside a git repository' in result.stderr


class TestDoctorCliffToml:
    def test_cliff_toml_missing_exits_one(
        self,
        mocker: MockerFixture,
        tmp_path: Path,
    ) -> None:
        """When cliff.toml does not exist in the repo root, the check fails and exits 1."""
        mocker.patch(
            'releez.subapps.doctor.shutil.which',
            return_value='/usr/bin/git',
        )
        mocker.patch(
            'releez.subapps.doctor._git_cliff_base_cmd',
            return_value=['git-cliff'],
        )
        _mock_repo(mocker, root=tmp_path)
        _mock_settings(mocker)

        result = invoke(cli.app, ['doctor'])

        assert result.exit_code == 1
        assert 'cliff.toml not found' in result.stderr

    def test_cliff_toml_invalid_toml_exits_one(
        self,
        mocker: MockerFixture,
        tmp_path: Path,
    ) -> None:
        """When cliff.toml contains invalid TOML, the check fails and exits 1."""
        mocker.patch(
            'releez.subapps.doctor.shutil.which',
            return_value='/usr/bin/git',
        )
        mocker.patch(
            'releez.subapps.doctor._git_cliff_base_cmd',
            return_value=['git-cliff'],
        )
        (tmp_path / 'cliff.toml').write_text(
            'not = valid [ toml !!!',
            encoding='utf-8',
        )
        _mock_repo(mocker, root=tmp_path)
        _mock_settings(mocker)

        result = invoke(cli.app, ['doctor'])

        assert result.exit_code == 1
        assert 'not valid TOML' in result.stderr

    def test_cliff_toml_catch_all_parser_is_warning(
        self,
        mocker: MockerFixture,
        tmp_path: Path,
    ) -> None:
        """A catch-all parser (message = ".*") is flagged as a warning, not a failure."""
        mocker.patch(
            'releez.subapps.doctor.shutil.which',
            return_value='/usr/bin/git',
        )
        mocker.patch(
            'releez.subapps.doctor._git_cliff_base_cmd',
            return_value=['git-cliff'],
        )
        (tmp_path / 'cliff.toml').write_text(
            '[git]\ncommit_parsers = [\n  {message = ".*", group = "Other"},\n]\n',
            encoding='utf-8',
        )
        (tmp_path / 'CHANGELOG.md').touch()
        _mock_repo(mocker, root=tmp_path)
        _mock_settings(mocker)

        result = invoke(cli.app, ['doctor'])

        assert result.exit_code == 0
        assert '⚠' in result.stdout
        assert 'catch-all' in result.stdout


class TestDoctorRemoteChecks:
    def test_remote_not_found_exits_one(
        self,
        mocker: MockerFixture,
        tmp_path: Path,
    ) -> None:
        """When the configured git remote does not exist locally, the check fails and exits 1."""
        mocker.patch(
            'releez.subapps.doctor.shutil.which',
            return_value='/usr/bin/git',
        )
        mocker.patch(
            'releez.subapps.doctor._git_cliff_base_cmd',
            return_value=['git-cliff'],
        )
        _write_cliff_toml(tmp_path)
        _mock_repo(mocker, root=tmp_path, remotes=[])
        _mock_settings(mocker)

        result = invoke(cli.app, ['doctor'])

        assert result.exit_code == 1
        assert 'does not exist' in result.stderr

    def test_base_branch_not_cached_is_warning(
        self,
        mocker: MockerFixture,
        tmp_path: Path,
    ) -> None:
        """When the base branch ref is absent from the local ref cache, a warning is shown but exits 0."""
        mocker.patch(
            'releez.subapps.doctor.shutil.which',
            return_value='/usr/bin/git',
        )
        mocker.patch(
            'releez.subapps.doctor._git_cliff_base_cmd',
            return_value=['git-cliff'],
        )
        _write_cliff_toml(tmp_path)
        (tmp_path / 'CHANGELOG.md').touch()
        _mock_repo(mocker, root=tmp_path, rev_parse_raises=True)
        _mock_settings(mocker)

        result = invoke(cli.app, ['doctor'])

        assert result.exit_code == 0
        assert '⚠' in result.stdout
        assert 'not found in local ref cache' in result.stdout


class TestDoctorWorkingTree:
    def test_dirty_working_tree_is_warning(
        self,
        mocker: MockerFixture,
        tmp_path: Path,
    ) -> None:
        """A dirty working tree is flagged as a warning so doctor is safe to run mid-work."""
        mocker.patch(
            'releez.subapps.doctor.shutil.which',
            return_value='/usr/bin/git',
        )
        mocker.patch(
            'releez.subapps.doctor._git_cliff_base_cmd',
            return_value=['git-cliff'],
        )
        _write_cliff_toml(tmp_path)
        (tmp_path / 'CHANGELOG.md').touch()
        _mock_repo(mocker, root=tmp_path, is_dirty=True)
        _mock_settings(mocker)

        result = invoke(cli.app, ['doctor'])

        assert result.exit_code == 0
        assert '⚠' in result.stdout
        assert 'dirty' in result.stdout


class TestDoctorChangelog:
    def test_changelog_missing_is_warning(
        self,
        mocker: MockerFixture,
        tmp_path: Path,
    ) -> None:
        """A missing changelog file is a warning rather than a hard failure."""
        mocker.patch(
            'releez.subapps.doctor.shutil.which',
            return_value='/usr/bin/git',
        )
        mocker.patch(
            'releez.subapps.doctor._git_cliff_base_cmd',
            return_value=['git-cliff'],
        )
        _write_cliff_toml(tmp_path)
        # Do NOT create CHANGELOG.md
        _mock_repo(mocker, root=tmp_path)
        _mock_settings(mocker)

        result = invoke(cli.app, ['doctor'])

        assert result.exit_code == 0
        assert '⚠' in result.stdout
        assert 'CHANGELOG.md' in result.stdout


class TestDoctorGitHubToken:
    def test_create_pr_true_no_token_exits_one(
        self,
        mocker: MockerFixture,
        tmp_path: Path,
    ) -> None:
        """When create-pr is true and no GitHub token is set, the token check fails and exits 1."""
        mocker.patch(
            'releez.subapps.doctor.shutil.which',
            return_value='/usr/bin/git',
        )
        mocker.patch(
            'releez.subapps.doctor._git_cliff_base_cmd',
            return_value=['git-cliff'],
        )
        mocker.patch.dict('os.environ', {}, clear=True)
        _write_cliff_toml(tmp_path)
        (tmp_path / 'CHANGELOG.md').touch()
        _mock_repo(mocker, root=tmp_path)
        _mock_settings(mocker, create_pr=True)

        result = invoke(cli.app, ['doctor'])

        assert result.exit_code == 1
        assert 'GitHub token' in result.stderr

    def test_create_pr_false_token_check_skipped(
        self,
        mocker: MockerFixture,
        tmp_path: Path,
    ) -> None:
        """When create-pr is false, the GitHub token check is skipped entirely."""
        mocker.patch(
            'releez.subapps.doctor.shutil.which',
            return_value='/usr/bin/git',
        )
        mocker.patch(
            'releez.subapps.doctor._git_cliff_base_cmd',
            return_value=['git-cliff'],
        )
        mocker.patch.dict('os.environ', {}, clear=True)
        _write_cliff_toml(tmp_path)
        (tmp_path / 'CHANGELOG.md').touch()
        _mock_repo(mocker, root=tmp_path)
        _mock_settings(mocker, create_pr=False)

        result = invoke(cli.app, ['doctor'])

        assert result.exit_code == 0
        assert 'GitHub token' not in result.output

    def test_create_pr_true_token_set_passes(
        self,
        mocker: MockerFixture,
        tmp_path: Path,
    ) -> None:
        """When create-pr is true and RELEEZ_GITHUB_TOKEN is set, the token check passes."""
        mocker.patch(
            'releez.subapps.doctor.shutil.which',
            return_value='/usr/bin/git',
        )
        mocker.patch(
            'releez.subapps.doctor._git_cliff_base_cmd',
            return_value=['git-cliff'],
        )
        mocker.patch.dict('os.environ', {'RELEEZ_GITHUB_TOKEN': 'tok_abc'})
        _write_cliff_toml(tmp_path)
        (tmp_path / 'CHANGELOG.md').touch()
        _mock_repo(mocker, root=tmp_path)
        _mock_settings(mocker, create_pr=True)

        result = invoke(cli.app, ['doctor'])

        assert result.exit_code == 0
        assert 'GitHub token is set' in result.stdout


class TestDoctorMonorepo:
    def test_monorepo_project_path_missing_exits_one(
        self,
        mocker: MockerFixture,
        tmp_path: Path,
    ) -> None:
        """In monorepo mode, a project whose configured path does not exist fails and exits 1."""
        mocker.patch(
            'releez.subapps.doctor.shutil.which',
            return_value='/usr/bin/git',
        )
        mocker.patch(
            'releez.subapps.doctor._git_cliff_base_cmd',
            return_value=['git-cliff'],
        )
        _write_cliff_toml(tmp_path)
        (tmp_path / 'CHANGELOG.md').touch()
        _mock_repo(mocker, root=tmp_path)

        project = mocker.MagicMock(name='core', path='packages/core')
        project.name = 'core'
        project.path = 'packages/core'
        _mock_settings(mocker, is_monorepo=True, projects=[project])

        result = invoke(cli.app, ['doctor'])

        assert result.exit_code == 1
        assert 'core' in result.stderr
        assert 'does not exist' in result.stderr

    def test_monorepo_project_path_exists_passes(
        self,
        mocker: MockerFixture,
        tmp_path: Path,
    ) -> None:
        """In monorepo mode, all project path checks pass when the directories exist."""
        mocker.patch(
            'releez.subapps.doctor.shutil.which',
            return_value='/usr/bin/git',
        )
        mocker.patch(
            'releez.subapps.doctor._git_cliff_base_cmd',
            return_value=['git-cliff'],
        )
        _write_cliff_toml(tmp_path)
        (tmp_path / 'CHANGELOG.md').touch()
        (tmp_path / 'packages' / 'core').mkdir(parents=True)
        _mock_repo(mocker, root=tmp_path)

        project = mocker.MagicMock()
        project.name = 'core'
        project.path = 'packages/core'
        _mock_settings(mocker, is_monorepo=True, projects=[project])

        result = invoke(cli.app, ['doctor'])

        assert result.exit_code == 0
        assert 'core' in result.stdout
