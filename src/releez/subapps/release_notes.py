from __future__ import annotations

from pathlib import Path  # noqa: TC003
from typing import TYPE_CHECKING, Annotated

from cyclopts import Parameter

from releez.cli_utils import _project_include_paths, _resolve_release_version
from releez.cliff import GitCliff
from releez.settings import ReleezSettings
from releez.subapps.release import (
    ProjectSelection,
    ReleaseNotesOptions,
    _emit_or_write_output,
    _project_semver_version,
    _require_single_project_override_scope,
    _resolve_project_release_version,
    _resolve_project_targets_for_command,
    release_app,
)
from releez.subapps.release_maintenance import _maintenance_context
from releez.utils import handle_releez_errors
from releez.version_tags import compute_version_tags

if TYPE_CHECKING:
    from releez.subproject import SubProject


def _generate_release_notes_single_repo(
    *,
    cliff: GitCliff,
    repo_root: Path,
    version_override: str | None,
    tag_pattern: str | None = None,
) -> str:
    version = _resolve_release_version(
        repo_root=repo_root,
        version_override=version_override,
        tag_pattern=tag_pattern,
    )
    compute_version_tags(version=str(version))
    return cliff.generate_unreleased_notes(
        version=str(version),
        tag_pattern=tag_pattern,
    )


def _generate_release_notes_monorepo(
    *,
    cliff: GitCliff,
    repo_root: Path,
    version_override: str | None,
    projects: list[SubProject],
) -> str:
    sections: list[str] = []
    for project in projects:
        version = _resolve_project_release_version(
            repo_root=repo_root,
            version_override=version_override,
            project=project,
        )
        semver_version = _project_semver_version(
            project=project,
            version=version,
        )
        compute_version_tags(
            version=semver_version,
            tag_prefix=project.tag_prefix,
        )
        project_notes = cliff.generate_unreleased_notes(
            version=str(version),
            tag_pattern=project.tag_pattern,
            include_paths=_project_include_paths(
                project=project,
                repo_root=repo_root,
            ),
        )
        sections.extend([f'## `{project.name}`', '', project_notes.strip(), ''])
    return '\n'.join(sections).rstrip() + '\n'


def _run_release_notes_command(
    *,
    settings: ReleezSettings,
    options: ReleaseNotesOptions,
    project_names: list[str],
    all_projects: bool,
) -> None:
    resolved = _resolve_project_targets_for_command(
        settings=settings,
        project_names=project_names,
        all_projects=all_projects,
    )
    _require_single_project_override_scope(
        version_override=options.version_override,
        target_projects=resolved.target_projects,
        action_label='generating notes for',
    )

    maintenance_ctx = _maintenance_context(
        branch=resolved.active_branch,
        regex=settings.effective_maintenance_branch_regex,
    )
    cliff = GitCliff(repo_root=resolved.repo_root)
    if resolved.target_projects is None:
        tag_pattern = maintenance_ctx.tag_pattern if maintenance_ctx else None
        if maintenance_ctx:
            version = _resolve_release_version(
                repo_root=resolved.repo_root,
                version_override=options.version_override,
                tag_pattern=tag_pattern,
            )
            maintenance_ctx.ensure_version_matches(version)
        notes = _generate_release_notes_single_repo(
            cliff=cliff,
            repo_root=resolved.repo_root,
            version_override=options.version_override,
            tag_pattern=tag_pattern,
        )
    else:
        notes = _generate_release_notes_monorepo(
            cliff=cliff,
            repo_root=resolved.repo_root,
            version_override=options.version_override,
            projects=resolved.target_projects,
        )

    _emit_or_write_output(output=options.output, content=notes)


@release_app.command
@handle_releez_errors
def notes(
    options: Annotated[ReleaseNotesOptions, Parameter(name='*')] | None = None,
    selection: Annotated[ProjectSelection, Parameter(name='*')] | None = None,
) -> None:
    """Generate the new changelog section for the release."""
    if options is None:
        options = ReleaseNotesOptions()
    if selection is None:
        selection = ProjectSelection()
    settings = ReleezSettings()
    _run_release_notes_command(
        settings=settings,
        options=options,
        project_names=selection.project_names,
        all_projects=selection.all_projects,
    )
