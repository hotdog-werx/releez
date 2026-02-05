from __future__ import annotations

from typing import TYPE_CHECKING

from git import Repo

import releez.release
from releez.git_repo import RepoContext, RepoInfo

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture


def test_start_release_runs_changelog_format_command(
    mocker: MockerFixture,
    tmp_path: Path,
) -> None:
    changelog = tmp_path / 'CHANGELOG.md'
    changelog.write_text('# Changelog\n', encoding='utf-8')

    repo = mocker.Mock(spec=Repo)
    info = RepoInfo(root=tmp_path, remote_url='', active_branch='feature/test')
    mocker.patch(
        'releez.release.open_repo',
        return_value=RepoContext(repo=repo, info=info),
    )
    mocker.patch('releez.release.ensure_clean')
    mocker.patch('releez.release.fetch')
    mocker.patch('releez.release.checkout_remote_branch')
    mocker.patch('releez.release.create_and_checkout_branch')
    mocker.patch('releez.release.commit_file')
    mocker.patch('releez.release.push_set_upstream')
    mocker.patch('releez.release._maybe_create_pull_request', return_value=None)

    cliff = mocker.Mock()
    cliff.compute_next_version.return_value = '1.2.3'
    cliff.generate_unreleased_notes.return_value = 'notes'
    mocker.patch('releez.release.GitCliff', return_value=cliff)

    run_checked = mocker.patch('releez.utils.run_checked', return_value='')

    result = releez.release.start_release(
        releez.release.StartReleaseInput(
            bump='auto',
            version_override=None,
            base_branch='master',
            remote_name='origin',
            labels=[],
            title_prefix='chore(release): ',
            changelog_path='CHANGELOG.md',
            run_changelog_format=True,
            changelog_format_cmd=['dprint', 'fmt', '{changelog}'],
            create_pr=False,
            github_token=None,
            dry_run=False,
            tag_pattern=None,
        ),
    )

    cliff.prepend_to_changelog.assert_called_once_with(
        version='1.2.3',
        changelog_path=changelog,
        tag_pattern=None,
    )
    run_checked.assert_called_once_with(
        ['dprint', 'fmt', str(changelog)],
        cwd=tmp_path,
        capture_stdout=False,
    )
    assert result.version == '1.2.3'
