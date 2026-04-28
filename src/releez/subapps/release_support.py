from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Annotated

from cyclopts import Parameter

from releez.cli_utils import _exit
from releez.console import console, err_console
from releez.errors import (
    InvalidMaintenanceBranchRegexError,
    MajorVersionAlreadyLatestError,
    NoTagsForMajorError,
    ReleezError,
)
from releez.git_repo import (
    DetectedRelease,
    create_branch_from_ref,
    detect_release_from_branch,
    find_all_major_versions,
    find_latest_tag_matching_pattern,
    open_repo,
    validate_commit_for_major,
)
from releez.settings import ReleezSettings
from releez.subapps.release import _project_names_csv, release_app
from releez.subapps.release_maintenance import (
    _maintenance_major,
    _monorepo_maintenance_tag_pattern,
)
from releez.utils import handle_releez_errors

if TYPE_CHECKING:
    from git import Repo


# ---------------------------------------------------------------------------
# Support branch helpers
# ---------------------------------------------------------------------------


def _support_branch_name(*, tag_prefix: str, major: int, template: str) -> str:
    return template.format(prefix=tag_prefix, major=major)


def _validate_branch_name_prefix_regex(
    branch_name: str,
    tag_prefix: str,
    compiled: re.Pattern[str],
    mismatch_msg: str,
) -> None:
    m = compiled.match(branch_name)
    if m is None:
        raise ReleezError(mismatch_msg)
    if (m.group('prefix') or '') != tag_prefix:
        raise ReleezError(mismatch_msg)


def _validate_branch_name_per_project(
    branch_name: str,
    tag_prefix: str,
    major: int,
    mismatch_msg: str,
) -> None:
    per_project = rf'^support/{re.escape(tag_prefix)}(?P<major>\d+)\.x$'
    m = re.match(per_project, branch_name)
    if m is None or int(m.group('major')) != major:
        raise ReleezError(mismatch_msg)


def _validate_monorepo_branch_name(
    *,
    branch_name: str,
    tag_prefix: str,
    major: int,
    maintenance_regex: str,
    mismatch_msg: str,
) -> None:
    try:
        compiled = re.compile(maintenance_regex)
    except re.error as exc:
        raise InvalidMaintenanceBranchRegexError(
            maintenance_regex,
            reason=str(exc),
        ) from exc
    if 'prefix' in compiled.groupindex:
        _validate_branch_name_prefix_regex(
            branch_name,
            tag_prefix,
            compiled,
            mismatch_msg,
        )
    else:
        _validate_branch_name_per_project(
            branch_name,
            tag_prefix,
            major,
            mismatch_msg,
        )


def _validate_support_branch_name(
    *,
    branch_name: str,
    tag_prefix: str,
    major: int,
    maintenance_regex: str,
) -> None:
    _mismatch = (
        f'Branch name {branch_name!r} generated from maintenance-branch-template '
        f"won't be detected by maintenance-branch-regex {maintenance_regex!r}. "
        'Ensure maintenance-branch-template and maintenance-branch-regex are consistent.'
    )
    if tag_prefix:
        _validate_monorepo_branch_name(
            branch_name=branch_name,
            tag_prefix=tag_prefix,
            major=major,
            maintenance_regex=maintenance_regex,
            mismatch_msg=_mismatch,
        )
    else:
        detected = _maintenance_major(
            branch=branch_name,
            regex=maintenance_regex,
        )
        if detected != major:
            raise ReleezError(_mismatch)


def _run_support_branch_inner(  # noqa: PLR0913
    repo: Repo,
    *,
    tag_prefix: str,
    major: int,
    commit_ref: str | None,
    dry_run: bool,
    branch_template: str,
    maintenance_regex: str,
) -> None:
    all_majors = find_all_major_versions(repo, tag_prefix=tag_prefix)

    if major not in all_majors:
        raise NoTagsForMajorError(major=major, tag_prefix=tag_prefix)

    latest_major = max(all_majors)
    if major == latest_major:
        raise MajorVersionAlreadyLatestError(
            major=major,
            latest_major=latest_major,
        )

    latest_tag = find_latest_tag_matching_pattern(
        repo,
        pattern=_monorepo_maintenance_tag_pattern(tag_prefix, major),
    )
    assert latest_tag is not None  # noqa: S101

    if commit_ref is not None:
        next_major = min(m for m in all_majors if m > major)
        next_major_tag = find_latest_tag_matching_pattern(
            repo,
            pattern=_monorepo_maintenance_tag_pattern(tag_prefix, next_major),
        )
        assert next_major_tag is not None  # noqa: S101
        split_sha = validate_commit_for_major(
            repo,
            commit_ref=commit_ref,
            latest_tag=next_major_tag,
            major=major,
        )
        split_label = f'{commit_ref} ({split_sha[:8]})'
    else:
        tag_obj = next(t for t in repo.tags if t.name == latest_tag)
        split_sha = tag_obj.commit.hexsha
        split_label = f'{latest_tag} ({split_sha[:8]})'

    branch_name = _support_branch_name(
        tag_prefix=tag_prefix,
        major=major,
        template=branch_template,
    )
    _validate_support_branch_name(
        branch_name=branch_name,
        tag_prefix=tag_prefix,
        major=major,
        maintenance_regex=maintenance_regex,
    )

    if dry_run:
        console.print(
            f"Would create branch '{branch_name}' from {split_label}",
            markup=False,
        )
        return

    create_branch_from_ref(repo, name=branch_name, ref=split_sha)
    console.print(
        f"Created branch '{branch_name}' from {split_label}",
        style='green',
        markup=False,
    )


# ---------------------------------------------------------------------------
# Detect-from-branch helpers
# ---------------------------------------------------------------------------


def _get_branch_name(branch: str | None) -> str:
    if branch is not None:
        return branch

    info = open_repo().info
    if info.active_branch is None:
        err_console.print(
            'Error: Not on a branch (detached HEAD). Use --branch to specify branch name.',
            style='bold red',
        )
        raise SystemExit(1)
    return info.active_branch


def _format_detected_release_json(detected: DetectedRelease) -> str:
    output = {
        'version': detected.version,
        'semver_version': detected.semver_version,
        'branch': detected.branch_name,
    }
    if detected.project_name:
        output['project'] = detected.project_name
    return json.dumps(output, indent=2)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@release_app.command
@handle_releez_errors
def detect_from_branch(
    *,
    branch: Annotated[
        str | None,
        Parameter(
            '--branch',
            help='Branch name to parse. If not specified, uses current branch.',
            show_default=False,
        ),
    ] = None,
) -> None:
    """Detect release information from a branch name.

    Parses release branch names to extract version and project information.
    Useful for GitHub Actions workflows to detect which project is being released.

    Single repo format: release/1.2.3
    Monorepo format: release/core-1.2.3
    """
    settings = ReleezSettings()
    branch_name = _get_branch_name(branch)
    info = open_repo().info
    subprojects = settings.get_subprojects(repo_root=info.root)

    detected = detect_release_from_branch(
        branch_name=branch_name,
        projects=subprojects,
    )

    if detected is None:
        err_console.print(
            f'Error: Branch "{branch_name}" is not a release branch.',
            style='bold red',
            markup=False,
        )
        raise SystemExit(1)

    console.print(_format_detected_release_json(detected), markup=False)


@release_app.command
@handle_releez_errors
def support_branch(
    major: Annotated[
        int,
        Parameter(
            help='Major version line to create a support branch for (e.g. 1 creates support/1.x).',
        ),
    ],
    *,
    project_name: Annotated[
        str | None,
        Parameter(
            '--project',
            help='Project name (required in monorepo mode).',
            show_default=False,
        ),
    ] = None,
    commit_ref: Annotated[
        str | None,
        Parameter(
            '--commit',
            help=(
                'Commit ref to branch from. Defaults to the latest N.x.x tag. '
                'Must be an ancestor of the latest N.x.x tag.'
            ),
            show_default=False,
        ),
    ] = None,
    dry_run: Annotated[
        bool,
        Parameter(
            '--dry-run',
            help='Print what would be done without creating the branch.',
        ),
    ] = False,
) -> None:
    """Create a support branch for an older major version.

    Finds the latest N.x.x release tag and creates support/N.x from that
    commit. The major version must not be the current latest.

    Single-repo example (tags 1.4.0 and 2.0.0 exist):
        releez release support-branch 1
        → creates support/1.x from 1.4.0

    Monorepo example (project ui with tags ui-1.4.0 and ui-2.0.0):
        releez release support-branch 1 --project ui
        → creates support/ui-1.x from ui-1.4.0
    """
    settings = ReleezSettings()
    ctx_repo = open_repo()
    repo = ctx_repo.repo
    subprojects = settings.get_subprojects(repo_root=ctx_repo.info.root)

    branch_template = settings.effective_maintenance_branch_template
    maintenance_regex = settings.effective_maintenance_branch_regex

    if not subprojects:
        if project_name is not None:
            raise _exit(
                message='--project is only valid in monorepo mode (no projects configured).',
            )
        _run_support_branch_inner(
            repo,
            tag_prefix='',
            major=major,
            commit_ref=commit_ref,
            dry_run=dry_run,
            branch_template=branch_template,
            maintenance_regex=maintenance_regex,
        )
    elif project_name is None:
        msg = f'--project is required in monorepo mode. Available projects: {_project_names_csv(subprojects)}'
        raise _exit(msg)
    else:
        projects_by_name = {p.name: p for p in subprojects}
        if project_name not in projects_by_name:
            msg = f'Unknown project: {project_name}. Available: {", ".join(sorted(projects_by_name))}'
            raise _exit(msg)
        project = projects_by_name[project_name]
        _run_support_branch_inner(
            repo,
            tag_prefix=project.tag_prefix,
            major=major,
            commit_ref=commit_ref,
            dry_run=dry_run,
            branch_template=branch_template,
            maintenance_regex=maintenance_regex,
        )
