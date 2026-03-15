from __future__ import annotations

from typing import TYPE_CHECKING

from typer.testing import CliRunner

from releez import cli
from releez.version_tags import AliasVersions

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture


def _mock_settings(
    mocker: MockerFixture,
    *,
    projects: list[object],
) -> None:
    hooks = mocker.MagicMock(post_changelog=[], changelog_format=None)
    mocker.patch(
        'releez.cli.ReleezSettings',
        return_value=mocker.MagicMock(
            base_branch='master',
            git_remote='origin',
            pr_labels='release',
            pr_title_prefix='chore(release): ',
            changelog_path='CHANGELOG.md',
            create_pr=False,
            run_changelog_format=False,
            alias_versions=AliasVersions.none,
            hooks=hooks,
            projects=projects,
        ),
    )


def test_cli_release_preview_writes_markdown(
    mocker: MockerFixture,
    tmp_path: Path,
) -> None:
    runner = CliRunner()

    repo_root = tmp_path / 'repo'
    repo_root.mkdir()

    mocker.patch(
        'releez.cli.open_repo',
        return_value=mocker.Mock(
            repo=object(),
            info=mocker.Mock(root=repo_root, active_branch=None),
        ),
    )

    cliff = mocker.Mock()
    cliff.compute_next_version.return_value = '2.3.4'
    mocker.patch('releez.cli.GitCliff', return_value=cliff)

    output = tmp_path / 'preview.md'
    result = runner.invoke(
        cli.app,
        [
            'release',
            'preview',
            '--alias-versions',
            'major',
            '--output',
            str(output),
        ],
    )

    assert result.exit_code == 0
    content = output.read_text(encoding='utf-8')
    assert '## `releez` release preview' in content
    assert '`2.3.4`' in content


def test_cli_release_preview_delegates_to_command_helper(
    mocker: MockerFixture,
) -> None:
    runner = CliRunner()
    run_command = mocker.patch('releez.cli._run_release_preview_command')

    result = runner.invoke(
        cli.app,
        [
            'release',
            'preview',
            '--project',
            'core',
            '--all',
            '--version-override',
            '1.2.3',
            '--alias-versions',
            'major',
        ],
    )

    assert result.exit_code == 0
    run_command.assert_called_once()
    call_kwargs = run_command.call_args.kwargs
    options = call_kwargs['options']
    assert options.version_override == '1.2.3'
    assert options.alias_versions == AliasVersions.major
    assert call_kwargs['project_names'] == ['core']
    assert call_kwargs['all_projects'] is True


def test_cli_release_preview_stdout(
    mocker: MockerFixture,
    tmp_path: Path,
) -> None:
    runner = CliRunner()

    repo_root = tmp_path / 'repo'
    repo_root.mkdir()

    mocker.patch(
        'releez.cli.open_repo',
        return_value=mocker.Mock(
            repo=object(),
            info=mocker.Mock(root=repo_root, active_branch=None),
        ),
    )

    cliff = mocker.Mock()
    cliff.compute_next_version.return_value = '1.2.3'
    mocker.patch('releez.cli.GitCliff', return_value=cliff)

    result = runner.invoke(
        cli.app,
        [
            'release',
            'preview',
            '--alias-versions',
            'none',
        ],
    )

    assert result.exit_code == 0
    assert '## `releez` release preview' in result.stdout
    assert '`1.2.3`' in result.stdout


def test_cli_release_preview_monorepo_requires_project_selection(
    mocker: MockerFixture,
    tmp_path: Path,
) -> None:
    runner = CliRunner()
    _mock_settings(mocker, projects=[mocker.MagicMock(name='core-config')])

    mocker.patch(
        'releez.cli.open_repo',
        return_value=mocker.Mock(
            repo=mocker.MagicMock(),
            info=mocker.Mock(root=tmp_path, active_branch=None),
        ),
    )
    core = mocker.MagicMock(
        name='core',
        path=tmp_path / 'packages' / 'core',
        changelog_path=tmp_path / 'packages' / 'core' / 'CHANGELOG.md',
        tag_pattern=r'^core-([0-9]+\.[0-9]+\.[0-9]+)$',
        include_paths=[],
        tag_prefix='core-',
        alias_versions=AliasVersions.major,
    )
    core.name = 'core'
    core.hooks.post_changelog = []
    mocker.patch('releez.cli.SubProject.from_config', return_value=core)

    result = runner.invoke(cli.app, ['release', 'preview'])

    assert result.exit_code == 1
    assert 'Project selection is required in monorepo mode' in result.output


def test_cli_release_preview_monorepo_project_outputs_prefixed_tags(
    mocker: MockerFixture,
    tmp_path: Path,
) -> None:
    runner = CliRunner()
    _mock_settings(mocker, projects=[mocker.MagicMock(name='core-config')])

    project_path = tmp_path / 'packages' / 'core'
    mocker.patch(
        'releez.cli.open_repo',
        return_value=mocker.Mock(
            repo=mocker.MagicMock(),
            info=mocker.Mock(root=tmp_path, active_branch=None),
        ),
    )
    core = mocker.MagicMock(
        name='core',
        path=project_path,
        changelog_path=project_path / 'CHANGELOG.md',
        tag_pattern=r'^core-([0-9]+\.[0-9]+\.[0-9]+)$',
        include_paths=['pyproject.toml'],
        tag_prefix='core-',
        alias_versions=AliasVersions.major,
    )
    core.name = 'core'
    core.hooks.post_changelog = []
    mocker.patch('releez.cli.SubProject.from_config', return_value=core)
    mocker.patch('releez.cli._resolve_release_version', return_value='1.2.3')

    result = runner.invoke(cli.app, ['release', 'preview', '--project', 'core'])

    assert result.exit_code == 0
    assert '### `core`' in result.stdout
    assert '`core-1.2.3`' in result.stdout
    assert '`core-v1`' in result.stdout
