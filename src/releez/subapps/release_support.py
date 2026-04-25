from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Annotated

import typer

from releez.cli_utils import _exit
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
from releez.subapps.release import _project_names_csv, release_app
from releez.subapps.release_maintenance import (
    _maintenance_major,
    _monorepo_maintenance_tag_pattern,
)
from releez.utils import handle_releez_errors

if TYPE_CHECKING:
    from git import Repo

    from releez.settings import ReleezSettings


# ---------------------------------------------------------------------------
# Support branch helpers
# ---------------------------------------------------------------------------


def _support_branch_name(*, tag_prefix: str, major: int, template: str) -> str:
    """Return the support branch name for a given tag prefix and major version."""
    return template.format(prefix=tag_prefix, major=major)


def _validate_branch_name_prefix_regex(
    branch_name: str,
    tag_prefix: str,
    compiled: re.Pattern[str],
    mismatch_msg: str,
) -> None:
    """Check branch_name via a regex that contains a (?P<prefix>...) group."""
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
    """Check branch_name via the hardcoded per-project pattern for the given prefix."""
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
    """Monorepo pre-flight: verify branch name is detectable for the given project prefix."""
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
    """Pre-flight: verify the generated branch name will be detected as a maintenance branch.

    Raises:
        ReleezError: If the branch name won't be detected by the current configuration.
        InvalidMaintenanceBranchRegexError: If the regex is invalid.
    """
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
    """Validate and create a support branch from the appropriate split point.

    Args:
        repo: Git repository.
        tag_prefix: Tag prefix for this project (empty string for single-repo).
        major: Major version line to support.
        commit_ref: Optional override commit ref to branch from.
        dry_run: If true, print what would be done without creating the branch.
        branch_template: Template string for constructing the branch name.
        maintenance_regex: Regex used to detect maintenance branches.

    Raises:
        NoTagsForMajorError: If no tags exist for the requested major.
        MajorVersionAlreadyLatestError: If major is the current latest.
        GitBranchExistsError: If the support branch already exists locally.
        InvalidSupportBranchCommitError: If --commit is not a valid split point.
        ReleezError: If the generated branch name won't be detected by maintenance_regex.
    """
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
    # Guaranteed non-None: we already confirmed major is in all_majors
    assert latest_tag is not None  # noqa: S101

    if commit_ref is not None:
        # Validate against the next major's latest tag: the commit must predate
        # the breaking change that caused the N+1 major bump, so it must be an
        # ancestor of at least one N+1.x.x release.
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
        # Resolve the tag to its commit SHA via the tag object we already found.
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
        typer.echo(f"Would create branch '{branch_name}' from {split_label}")
        return

    create_branch_from_ref(repo, name=branch_name, ref=split_sha)
    typer.secho(
        f"Created branch '{branch_name}' from {split_label}",
        fg=typer.colors.GREEN,
    )


# ---------------------------------------------------------------------------
# Detect-from-branch helpers
# ---------------------------------------------------------------------------


def _get_branch_name(branch: str | None) -> str:
    """Get branch name from parameter or detect current branch.

    Args:
        branch: Branch name from user, or None to auto-detect.

    Returns:
        Branch name to parse.

    Raises:
        typer.Exit: If in detached HEAD state without --branch.
    """
    if branch is not None:
        return branch

    info = open_repo().info
    if info.active_branch is None:
        typer.secho(
            'Error: Not on a branch (detached HEAD). Use --branch to specify branch name.',
            err=True,
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=1)
    return info.active_branch


def _format_detected_release_json(detected: DetectedRelease) -> str:
    """Format DetectedRelease as JSON string.

    Args:
        detected: Detected release information.

    Returns:
        JSON string with version, branch, and optional project.
    """
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


@release_app.command('detect-from-branch')
@handle_releez_errors
def release_detect_from_branch(
    ctx: typer.Context,
    *,
    branch: Annotated[
        str | None,
        typer.Option(
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
    settings: ReleezSettings = ctx.obj
    branch_name = _get_branch_name(branch)
    info = open_repo().info
    subprojects = settings.get_subprojects(repo_root=info.root)

    detected = detect_release_from_branch(
        branch_name=branch_name,
        projects=subprojects,
    )

    if detected is None:
        typer.secho(
            f'Error: Branch "{branch_name}" is not a release branch.',
            err=True,
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=1)

    typer.echo(_format_detected_release_json(detected))


@release_app.command('support-branch')
@handle_releez_errors
def release_support_branch(
    ctx: typer.Context,
    major: Annotated[
        int,
        typer.Argument(
            help='Major version line to create a support branch for (e.g. 1 creates support/1.x).',
        ),
    ],
    *,
    project_name: Annotated[
        str | None,
        typer.Option(
            '--project',
            help='Project name (required in monorepo mode).',
            show_default=False,
        ),
    ] = None,
    commit_ref: Annotated[
        str | None,
        typer.Option(
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
        typer.Option(
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
    settings: ReleezSettings = ctx.obj
    ctx_repo = open_repo()
    repo = ctx_repo.repo
    subprojects = settings.get_subprojects(repo_root=ctx_repo.info.root)

    branch_template = settings.effective_maintenance_branch_template
    maintenance_regex = settings.effective_maintenance_branch_regex

    if not subprojects:
        # Single-repo mode: --project must not be given
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
        # Monorepo mode: --project is required
        msg = f'--project is required in monorepo mode. Available projects: {_project_names_csv(subprojects)}'
        raise _exit(msg)
    else:
        # Monorepo mode with explicit project name (narrowed to str)
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
