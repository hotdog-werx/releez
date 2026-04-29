from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Annotated

from cyclopts import App, Parameter
from pydantic import BaseModel, model_validator

from releez.cli_utils import (
    _exit,
    _project_include_paths,
    _resolve_release_version,
)
from releez.cliff import GitCliffBump  # noqa: TC001
from releez.console import console
from releez.git_repo import open_repo
from releez.version_tags import AliasVersions  # noqa: TC001

if TYPE_CHECKING:
    from git import Repo
    from semver import VersionInfo

    from releez.settings import ReleezSettings
    from releez.subproject import SubProject

release_app = App(
    name='release',
    help='Release workflows (changelog + branch + PR).',
)


# ---------------------------------------------------------------------------
# Shared infrastructure
# ---------------------------------------------------------------------------


def _project_changelog_path(
    *,
    project: SubProject,
    repo_root: Path,
) -> str:
    return project.changelog_path.relative_to(repo_root).as_posix()


def _project_names_csv(projects: list[SubProject]) -> str:
    return ', '.join(project.name for project in projects)


def _resolve_target_projects(
    *,
    repo_root: Path,
    settings: ReleezSettings,
    project_names: list[str],
    all_projects: bool,
) -> list[SubProject] | None:
    """Resolve project targets for monorepo-aware commands.

    Returns None for single-repo mode, or a concrete project list in monorepo mode.
    """
    if not settings.is_monorepo:
        settings.validate_project_flags(
            project_names=project_names,
            all_projects=all_projects,
        )
        return None
    return settings.select_projects(
        repo_root=repo_root,
        project_names=project_names,
        all_projects=all_projects,
    )


class _ResolvedProjectTargets:
    __slots__ = (
        'active_branch',
        'repo',
        'repo_root',
        'settings',
        'target_projects',
    )

    def __init__(
        self,
        *,
        settings: ReleezSettings,
        repo: Repo,
        repo_root: Path,
        target_projects: list[SubProject] | None,
        active_branch: str | None = None,
    ) -> None:
        self.settings = settings
        self.repo = repo
        self.repo_root = repo_root
        self.target_projects = target_projects
        self.active_branch = active_branch


def _resolve_project_targets_for_command(
    *,
    settings: ReleezSettings,
    project_names: list[str],
    all_projects: bool,
) -> _ResolvedProjectTargets:
    ctx_repo = open_repo()
    repo, info = ctx_repo.repo, ctx_repo.info
    target_projects = _resolve_target_projects(
        repo_root=info.root,
        settings=settings,
        project_names=project_names,
        all_projects=all_projects,
    )
    return _ResolvedProjectTargets(
        settings=settings,
        repo=repo,
        repo_root=info.root,
        target_projects=target_projects,
        active_branch=info.active_branch,
    )


def _require_single_project_override_scope(
    *,
    version_override: str | None,
    target_projects: list[SubProject] | None,
    action_label: str,
) -> None:
    if version_override is None or target_projects is None:
        return
    if len(target_projects) <= 1:
        return
    raise _exit(
        message=f'--version-override can only be used when {action_label} a single project.',
    )


def _resolve_project_release_version(
    *,
    repo_root: Path,
    version_override: str | None,
    project: SubProject,
) -> VersionInfo:
    return _resolve_release_version(
        repo_root=repo_root,
        version_override=version_override,
        tag_pattern=project.tag_pattern,
        include_paths=_project_include_paths(
            project=project,
            repo_root=repo_root,
        ),
        tag_prefix=project.tag_prefix,
    )


def _project_semver_version(
    *,
    project: SubProject,  # noqa: ARG001
    version: VersionInfo,
) -> str:
    return str(version)


def _alias_versions_for_project(
    *,
    cli_alias_versions: AliasVersions | None,
    project: SubProject,
) -> AliasVersions:
    """Return the alias version strategy for a project.

    Explicit CLI value wins; None falls back to the project's own config.
    """
    if cli_alias_versions is not None:
        return cli_alias_versions
    return project.alias_versions


def _emit_or_write_output(
    *,
    output: Path | None,
    content: str,
) -> None:
    if output is None:
        console.print(content, markup=False)
        return
    output_path = Path(output)
    output_path.write_text(content, encoding='utf-8')


# ---------------------------------------------------------------------------
# Shared CLI option models (used by multiple commands)
# ---------------------------------------------------------------------------


class ProjectSelection(BaseModel):
    """Monorepo project selection options shared across release commands."""

    project_names: Annotated[
        list[str],
        Parameter(
            '--project',
            help='Project name (repeatable, monorepo only).',
            show_default=False,
        ),
    ] = []
    all_projects: Annotated[
        bool,
        Parameter(
            '--all',
            help='Target all configured projects (monorepo only).',
            show_default=True,
        ),
    ] = False

    @model_validator(mode='after')
    def _check_mutual_exclusion(self) -> ProjectSelection:
        if self.project_names and self.all_projects:
            msg = 'Cannot use --project and --all together.'
            raise _exit(msg)
        return self


# ---------------------------------------------------------------------------
# Per-command options models
# ---------------------------------------------------------------------------


class ReleaseStartOptions(BaseModel):
    """CLI options for the `release start` command."""

    bump: Annotated[
        GitCliffBump,
        Parameter(help='Bump mode passed to git-cliff.', show_default=True),
    ] = 'auto'
    version_override: Annotated[
        str | None,
        Parameter(
            '--version-override',
            help='Override version instead of computing via git-cliff.',
            show_default=False,
        ),
    ] = None
    create_pr: Annotated[
        bool | None,
        Parameter(
            help='Create a GitHub PR (requires token). [default: from config create-pr; fallback: false]',
            show_default=False,
        ),
    ] = None
    dry_run: Annotated[
        bool,
        Parameter(help='Compute version and notes without changing the repo.'),
    ] = False
    base: Annotated[
        str | None,
        Parameter(
            help='Base branch for the release PR. [default: from config base-branch; fallback: master]',
            show_default=False,
        ),
    ] = None
    remote: Annotated[
        str | None,
        Parameter(
            help='Remote name to use. [default: from config git-remote; fallback: origin]',
            show_default=False,
        ),
    ] = None
    labels: Annotated[
        str | None,
        Parameter(
            help='Comma-separated label(s) to add to the PR. [default: from config pr-labels; fallback: release]',
            show_default=False,
        ),
    ] = None
    title_prefix: Annotated[
        str | None,
        Parameter(
            help='Prefix for PR title. [default: from config pr-title-prefix; fallback: "chore(release): "]',
            show_default=False,
        ),
    ] = None
    changelog_path: Annotated[
        str | None,
        Parameter(
            ('--changelog-path', '--changelog'),
            help='Changelog file to prepend to. [default: from config changelog-path; fallback: CHANGELOG.md]',
            show_default=False,
        ),
    ] = None
    github_token: Annotated[
        str | None,
        Parameter(
            env_var=['RELEEZ_GITHUB_TOKEN', 'GITHUB_TOKEN'],
            help='GitHub token for PR creation (prefer RELEEZ_GITHUB_TOKEN; falls back to GITHUB_TOKEN).',
            show_default=False,
        ),
    ] = None

    def resolve(self, settings: ReleezSettings) -> ReleaseStartOptions:
        """Return a copy with all None fields filled from settings."""
        return self.model_copy(
            update={
                'base': self.base if self.base is not None else settings.base_branch,
                'remote': self.remote if self.remote is not None else settings.git_remote,
                'labels': self.labels if self.labels is not None else settings.pr_labels,
                'title_prefix': self.title_prefix if self.title_prefix is not None else settings.pr_title_prefix,
                'changelog_path': self.changelog_path if self.changelog_path is not None else settings.changelog_path,
                'create_pr': self.create_pr if self.create_pr is not None else settings.create_pr,
            },
        )

    @property
    def labels_list(self) -> list[str]:
        """Split comma-separated labels string into a list."""
        labels = self.labels or ''
        return labels.split(',') if labels else []


class ReleaseTagOptions(BaseModel):
    """CLI options for the `release tag` command."""

    version_override: Annotated[
        str | None,
        Parameter(
            '--version-override',
            help='Override release version to tag (x.y.z).',
            show_default=False,
        ),
    ] = None
    alias_versions: Annotated[
        AliasVersions | None,
        Parameter(
            '--alias-versions',
            help='Also create major/minor tags (v2, v2.3). [default: from config alias-versions; fallback: none]',
            show_default=False,
        ),
    ] = None
    remote: Annotated[
        str | None,
        Parameter(
            '--remote',
            help='Remote to push tags to. [default: from config git-remote; fallback: origin]',
            show_default=False,
        ),
    ] = None

    def resolve(self, settings: ReleezSettings) -> ReleaseTagOptions:
        """Return a copy with all None fields filled from settings."""
        return self.model_copy(
            update={
                'alias_versions': self.alias_versions if self.alias_versions is not None else settings.alias_versions,
                'remote': self.remote if self.remote is not None else settings.git_remote,
            },
        )


class ReleasePreviewOptions(BaseModel):
    """CLI options for the `release preview` command."""

    version_override: Annotated[
        str | None,
        Parameter(
            '--version-override',
            help='Override release version to preview (x.y.z).',
            show_default=False,
        ),
    ] = None
    alias_versions: Annotated[
        AliasVersions | None,
        Parameter(
            '--alias-versions',
            help='Include major/minor tags in the preview. [default: from config alias-versions; fallback: none]',
            show_default=False,
        ),
    ] = None
    output: Annotated[
        Path | None,
        Parameter(
            '--output',
            help='Write markdown preview to a file instead of stdout.',
            show_default=False,
        ),
    ] = None

    def resolve(self, settings: ReleezSettings) -> ReleasePreviewOptions:
        """Return a copy with all None fields filled from settings."""
        return self.model_copy(
            update={
                'alias_versions': self.alias_versions if self.alias_versions is not None else settings.alias_versions,
            },
        )


class ReleaseNotesOptions(BaseModel):
    """CLI options for the `release notes` command."""

    version_override: Annotated[
        str | None,
        Parameter(
            '--version-override',
            help='Override release version for the notes section (x.y.z).',
            show_default=False,
        ),
    ] = None
    output: Annotated[
        Path | None,
        Parameter(
            '--output',
            help='Write release notes to a file instead of stdout.',
            show_default=False,
        ),
    ] = None
