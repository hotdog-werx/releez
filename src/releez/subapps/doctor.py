from __future__ import annotations

import os
import shutil
import tomllib
from dataclasses import dataclass
from typing import TYPE_CHECKING

from cyclopts import App

from releez.cliff import MissingCliError, _git_cliff_base_cmd
from releez.console import console, err_console
from releez.errors import ReleezError
from releez.git_repo import open_repo
from releez.settings import ReleezSettings

if TYPE_CHECKING:
    from pathlib import Path

    from git import Repo

    from releez.git_repo import RepoContext
    from releez.settings import ProjectConfig

doctor_app = App(
    name='doctor',
    help='Check releez configuration and environment.',
)


@dataclass
class _Check:
    message: str
    passed: bool
    warning: bool = False  # warning=True → yellow ⚠, not counted as failure


def _emit(check: _Check) -> None:
    if not check.passed:
        err_console.print(f'✗ {check.message}', style='bold red', markup=False)
    elif check.warning:
        console.print(f'⚠ {check.message}', style='yellow', markup=False)
    else:
        console.print(f'✓ {check.message}', style='green', markup=False)


def _check_git() -> _Check:
    if shutil.which('git') is not None:
        return _Check(message='git is available', passed=True)
    return _Check(message='git is not available', passed=False)


def _check_git_cliff() -> _Check:
    try:
        _git_cliff_base_cmd()
    except MissingCliError:
        return _Check(message='git-cliff is not available', passed=False)
    return _Check(message='git-cliff is available', passed=True)


def _check_in_repo() -> tuple[_Check, RepoContext | None]:
    try:
        ctx = open_repo()
    except (ReleezError, Exception):  # noqa: BLE001
        return _Check(message='not inside a git repository', passed=False), None
    return _Check(
        message=f'inside a git repository ({ctx.info.root})',
        passed=True,
    ), ctx


def _check_cliff_toml(repo_root: Path) -> list[_Check]:
    cliff_toml = repo_root / 'cliff.toml'
    if not cliff_toml.exists():
        return [
            _Check(message='cliff.toml not found in repo root', passed=False),
        ]

    checks: list[_Check] = [
        _Check(message='cliff.toml found and valid', passed=True),
    ]
    try:
        with cliff_toml.open('rb') as f:
            config = tomllib.load(f)
    except Exception:  # noqa: BLE001
        checks[0] = _Check(
            message='cliff.toml found but is not valid TOML',
            passed=False,
        )
        return checks

    git_section = config.get('git', {})
    parsers = git_section.get('commit_parsers', []) if isinstance(git_section, dict) else []
    catch_alls = [p for p in parsers if isinstance(p, dict) and p.get('message') == '.*']
    if catch_alls:
        checks.append(
            _Check(
                message='cliff.toml has a catch-all parser (.*) — non-conventional commits will pass validation',
                passed=True,
                warning=True,
            ),
        )
    return checks


def _check_remote(repo: Repo, remote_name: str) -> _Check:
    try:
        _ = repo.remotes[remote_name]
    except IndexError:
        return _Check(
            message=f'remote {remote_name!r} does not exist',
            passed=False,
        )
    return _Check(message=f'remote {remote_name!r} exists', passed=True)


def _check_base_branch(
    repo: Repo,
    remote_name: str,
    base_branch: str,
) -> _Check:
    ref = f'{remote_name}/{base_branch}'
    try:
        repo.git.rev_parse('--verify', ref)
    except Exception:  # noqa: BLE001
        return _Check(
            message=f'{ref} not found in local ref cache (run git fetch to refresh)',
            passed=True,
            warning=True,
        )
    return _Check(message=f'{ref} exists in local ref cache', passed=True)


def _check_working_tree(repo: Repo) -> _Check:
    if repo.is_dirty(untracked_files=True):
        return _Check(
            message='working tree is dirty (uncommitted or untracked changes)',
            passed=True,
            warning=True,
        )
    return _Check(message='working tree is clean', passed=True)


def _check_changelog(repo_root: Path, changelog_path: str) -> _Check:
    path = repo_root / changelog_path
    if not path.exists():
        return _Check(
            message=f'changelog file not found: {changelog_path}',
            passed=True,
            warning=True,
        )
    return _Check(
        message=f'changelog file exists: {changelog_path}',
        passed=True,
    )


def _check_github_token() -> _Check:
    token = os.environ.get('RELEEZ_GITHUB_TOKEN') or os.environ.get(
        'GITHUB_TOKEN',
    )
    if not token:
        return _Check(
            message='GitHub token not set (RELEEZ_GITHUB_TOKEN / GITHUB_TOKEN) — required for PR creation',
            passed=False,
        )
    return _Check(message='GitHub token is set', passed=True)


def _check_monorepo_projects(
    repo_root: Path,
    projects: list[ProjectConfig],
) -> list[_Check]:
    checks: list[_Check] = []
    for project in projects:
        project_path = repo_root / project.path
        if not project_path.exists():
            checks.append(
                _Check(
                    message=f'project {project.name!r}: path does not exist ({project.path})',
                    passed=False,
                ),
            )
        else:
            checks.append(
                _Check(
                    message=f'project {project.name!r}: path exists ({project.path})',
                    passed=True,
                ),
            )
    return checks


def _collect_checks_with_repo(
    ctx: RepoContext,
    settings: ReleezSettings | None,
) -> list[_Check]:
    """Collect all checks that require a valid repo context."""
    checks = list(_check_cliff_toml(ctx.info.root))
    if settings is None:
        checks.append(_check_working_tree(ctx.repo))
        return checks
    remote_check = _check_remote(ctx.repo, settings.git_remote)
    checks.append(remote_check)
    if remote_check.passed:
        checks.append(
            _check_base_branch(
                ctx.repo,
                settings.git_remote,
                settings.base_branch,
            ),
        )
    checks.append(_check_working_tree(ctx.repo))
    checks.append(_check_changelog(ctx.info.root, settings.changelog_path))
    if settings.create_pr:
        checks.append(_check_github_token())
    if settings.is_monorepo:
        checks.extend(
            _check_monorepo_projects(ctx.info.root, settings.projects),
        )
    return checks


@doctor_app.default
def run_checks() -> None:
    """Run pre-flight health checks on the releez configuration and environment."""
    checks: list[_Check] = []

    checks.append(_check_git())
    checks.append(_check_git_cliff())

    repo_check, ctx = _check_in_repo()
    checks.append(repo_check)

    settings: ReleezSettings | None = None
    if ctx is not None:
        try:
            settings = ReleezSettings()
        except Exception as exc:  # noqa: BLE001
            checks.append(
                _Check(message=f'failed to load settings: {exc}', passed=False),
            )
        checks.extend(_collect_checks_with_repo(ctx, settings))

    for check in checks:
        _emit(check)

    passed = sum(1 for c in checks if c.passed and not c.warning)
    warnings = sum(1 for c in checks if c.warning)
    failed = sum(1 for c in checks if not c.passed)

    summary_style = 'green' if failed == 0 else 'bold red'
    console.print(
        f'\nDoctor: {passed} passed, {warnings} warnings, {failed} failed.',
        style=summary_style,
    )

    if failed:
        raise SystemExit(1)
