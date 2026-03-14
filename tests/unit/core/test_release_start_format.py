from __future__ import annotations

from typing import TYPE_CHECKING

import releez.release

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture


def test_start_release_runs_changelog_format_command(
    mocker: MockerFixture,
    tmp_path: Path,
) -> None:
    changelog = tmp_path / 'CHANGELOG.md'
    changelog.write_text('# Changelog\n', encoding='utf-8')

    repo = mocker.Mock()
    info = mocker.Mock(root=tmp_path)
    mocker.patch(
        'releez.release.open_repo',
        return_value=mocker.Mock(repo=repo, info=info),
    )
    mocker.patch('releez.release.ensure_clean')
    mocker.patch('releez.release.fetch')
    mocker.patch('releez.release.checkout_remote_branch')
    mocker.patch('releez.release.create_and_checkout_branch')
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
            post_changelog_hooks=None,
            run_changelog_format=True,
            changelog_format_cmd=['dprint', 'fmt', '{changelog}'],
            create_pr=False,
            github_token=None,
            dry_run=False,
        ),
    )

    cliff.prepend_to_changelog.assert_called_once_with(
        version='1.2.3',
        changelog_path=changelog,
        tag_pattern=None,
        include_paths=None,
    )
    run_checked.assert_called_once_with(
        ['dprint', 'fmt', str(changelog)],
        cwd=tmp_path,
        capture_stdout=False,
    )
    assert result.version == '1.2.3'


def test_start_release_runs_post_changelog_hooks(
    mocker: MockerFixture,
    tmp_path: Path,
) -> None:
    changelog = tmp_path / 'CHANGELOG.md'
    changelog.write_text('# Changelog\n', encoding='utf-8')

    repo = mocker.Mock()
    info = mocker.Mock(root=tmp_path)
    mocker.patch(
        'releez.release.open_repo',
        return_value=mocker.Mock(repo=repo, info=info),
    )
    mocker.patch('releez.release.ensure_clean')
    mocker.patch('releez.release.fetch')
    mocker.patch('releez.release.checkout_remote_branch')
    mocker.patch('releez.release.create_and_checkout_branch')
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
            post_changelog_hooks=[
                ['uv', 'version', '{version}'],
                ['prettier', '--write', '{changelog}'],
            ],
            run_changelog_format=False,
            changelog_format_cmd=None,
            create_pr=False,
            github_token=None,
            dry_run=False,
        ),
    )

    cliff.prepend_to_changelog.assert_called_once_with(
        version='1.2.3',
        changelog_path=changelog,
        tag_pattern=None,
        include_paths=None,
    )
    # Should run both hooks in order
    assert run_checked.call_count == 2
    run_checked.assert_any_call(
        ['uv', 'version', '1.2.3'],
        cwd=tmp_path,
        capture_stdout=False,
    )
    run_checked.assert_any_call(
        ['prettier', '--write', str(changelog)],
        cwd=tmp_path,
        capture_stdout=False,
    )
    assert result.version == '1.2.3'


def test_start_release_stages_project_path_and_adds_project_label(
    mocker: MockerFixture,
    tmp_path: Path,
) -> None:
    repo = mocker.Mock()
    info = mocker.Mock(root=tmp_path)
    project_path = tmp_path / 'packages' / 'core'
    (tmp_path / 'CHANGELOG.md').write_text('# Changelog\n', encoding='utf-8')

    mocker.patch(
        'releez.release.open_repo',
        return_value=mocker.Mock(repo=repo, info=info),
    )
    mocker.patch('releez.release.ensure_clean')
    mocker.patch('releez.release.fetch')
    mocker.patch('releez.release.checkout_remote_branch')
    mocker.patch('releez.release.create_and_checkout_branch')
    mocker.patch('releez.release.push_set_upstream')
    maybe_create_pr = mocker.patch(
        'releez.release._maybe_create_pull_request',
        return_value=None,
    )

    cliff = mocker.Mock()
    cliff.compute_next_version.return_value = 'core-1.2.3'
    cliff.generate_unreleased_notes.return_value = 'notes'
    mocker.patch('releez.release.GitCliff', return_value=cliff)

    result = releez.release.start_release(
        releez.release.StartReleaseInput(
            bump='auto',
            version_override=None,
            base_branch='master',
            remote_name='origin',
            labels=['release'],
            title_prefix='chore(release): ',
            changelog_path='CHANGELOG.md',
            post_changelog_hooks=None,
            run_changelog_format=False,
            changelog_format_cmd=None,
            create_pr=False,
            github_token=None,
            dry_run=False,
            project_name='core',
            project_path=project_path,
        ),
    )

    repo.git.add.assert_called_once_with('packages/core')
    assert result.release_branch == 'release/core-1.2.3'

    pr_input = maybe_create_pr.call_args.kwargs['pr_input']
    assert pr_input.labels == ['release', 'release:core']


def test_start_release_monorepo_first_release_prefixes_version(
    mocker: MockerFixture,
    tmp_path: Path,
) -> None:
    """First monorepo release: bare semver from git-cliff gets tag prefix prepended.

    When no prior tags match the project's tag pattern, git-cliff falls back to
    "0.1.0" (no prefix). _resolve_release_version must prepend the tag_prefix so
    the branch is "release/core-0.1.0", not "release/0.1.0".
    """
    (tmp_path / 'CHANGELOG.md').write_text('# Changelog\n', encoding='utf-8')

    repo = mocker.Mock()
    info = mocker.Mock(root=tmp_path)
    mocker.patch(
        'releez.release.open_repo',
        return_value=mocker.Mock(repo=repo, info=info),
    )
    mocker.patch('releez.release.ensure_clean')
    mocker.patch('releez.release.fetch')
    mocker.patch('releez.release.checkout_remote_branch')
    mocker.patch('releez.release.create_and_checkout_branch')
    mocker.patch('releez.release.push_set_upstream')
    mocker.patch('releez.release._maybe_create_pull_request', return_value=None)

    cliff = mocker.Mock()
    # Simulate git-cliff returning bare semver (no prefix) for first release
    cliff.compute_next_version.return_value = '0.1.0'
    cliff.generate_unreleased_notes.return_value = 'notes'
    mocker.patch('releez.release.GitCliff', return_value=cliff)

    result = releez.release.start_release(
        releez.release.StartReleaseInput(
            bump='auto',
            version_override=None,
            base_branch='master',
            remote_name='origin',
            labels=[],
            title_prefix='chore(release): ',
            changelog_path='CHANGELOG.md',
            post_changelog_hooks=None,
            run_changelog_format=False,
            changelog_format_cmd=None,
            create_pr=False,
            github_token=None,
            dry_run=False,
            project_name='core',
            tag_prefix='core-',
        ),
    )

    assert result.version == 'core-0.1.0'
    assert result.release_branch == 'release/core-0.1.0'


def test_start_release_monorepo_hooks_receive_bare_semver(
    mocker: MockerFixture,
    tmp_path: Path,
) -> None:
    """Monorepo: {version} in hooks is stripped of tag prefix; {release_version} keeps it."""
    changelog = tmp_path / 'CHANGELOG.md'
    changelog.write_text('# Changelog\n', encoding='utf-8')

    repo = mocker.Mock()
    info = mocker.Mock(root=tmp_path)
    mocker.patch(
        'releez.release.open_repo',
        return_value=mocker.Mock(repo=repo, info=info),
    )
    mocker.patch('releez.release.ensure_clean')
    mocker.patch('releez.release.fetch')
    mocker.patch('releez.release.checkout_remote_branch')
    mocker.patch('releez.release.create_and_checkout_branch')
    mocker.patch('releez.release.push_set_upstream')
    mocker.patch('releez.release._maybe_create_pull_request', return_value=None)

    cliff = mocker.Mock()
    cliff.compute_next_version.return_value = 'core-1.2.3'
    cliff.generate_unreleased_notes.return_value = 'notes'
    mocker.patch('releez.release.GitCliff', return_value=cliff)

    run_checked = mocker.patch('releez.utils.run_checked', return_value='')

    releez.release.start_release(
        releez.release.StartReleaseInput(
            bump='auto',
            version_override=None,
            base_branch='master',
            remote_name='origin',
            labels=[],
            title_prefix='chore(release): ',
            changelog_path='CHANGELOG.md',
            post_changelog_hooks=[
                ['uv', 'version', '{version}'],
                ['echo', '{project_version}'],
            ],
            run_changelog_format=False,
            changelog_format_cmd=None,
            create_pr=False,
            github_token=None,
            dry_run=False,
            project_name='core',
            tag_prefix='core-',
        ),
    )

    # {version} should be bare semver (prefix stripped)
    run_checked.assert_any_call(
        ['uv', 'version', '1.2.3'],
        cwd=tmp_path,
        capture_stdout=False,
    )
    # {project_version} should retain the full prefixed version
    run_checked.assert_any_call(
        ['echo', 'core-1.2.3'],
        cwd=tmp_path,
        capture_stdout=False,
    )
