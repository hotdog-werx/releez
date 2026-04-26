from __future__ import annotations

import re
import warnings
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import (
    AliasChoices,
    AliasGenerator,
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    PyprojectTomlConfigSettingsSource,
    SettingsConfigDict,
    TomlConfigSettingsSource,
)

from releez.errors import InvalidMaintenanceBranchRegexError, ReleezError
from releez.version_tags import AliasVersions

if TYPE_CHECKING:
    from releez.subproject import SubProject


class _ReleezTomlConfigSettingsSource(TomlConfigSettingsSource):
    """Load settings from releez.toml, navigating into [tool.releez] if present.

    Preferred format (mirrors pyproject.toml):
        [tool.releez]
        base-branch = "main"

    Legacy flat format (deprecated):
        base-branch = "main"
    """

    _TABLE_HEADER: tuple[str, ...] = ('tool', 'releez')

    def __init__(self, settings_cls: type[BaseSettings]) -> None:
        self.toml_file_path = Path('releez.toml')
        raw_data: dict[str, object] = self._read_files(self.toml_file_path)

        data = raw_data
        found = True
        for key in self._TABLE_HEADER:
            if isinstance(data, dict) and key in data:
                data = data[key]
            else:
                found = False
                break

        if not found:
            if raw_data:
                warnings.warn(
                    'releez.toml: top-level configuration is deprecated. '
                    'Nest your settings under [tool.releez]:\n\n'
                    '  [tool.releez]\n'
                    '  base-branch = "main"\n\n'
                    'Top-level configuration will be removed in a future release.',
                    DeprecationWarning,
                    stacklevel=2,
                )
            data = raw_data

        self.toml_data = data
        super(TomlConfigSettingsSource, self).__init__(
            settings_cls,
            self.toml_data,
        )


def _to_kebab(name: str) -> str:
    """Convert snake_case to kebab-case."""
    return name.replace('_', '-')


def _validation_alias(name: str) -> AliasChoices:
    """Accept both snake_case and kebab-case for settings keys.

    `AliasChoices` order matters: we list the snake_case field name first so if both
    variants are present (e.g. env var + pyproject), the env var wins.
    """
    return AliasChoices(name, _to_kebab(name))


_ALIASES = AliasGenerator(
    validation_alias=_validation_alias,
    serialization_alias=_to_kebab,
)


class ReleezHooks(BaseModel):
    """Hook-related configuration.

    Attributes:
        post_changelog: List of commands to run after changelog generation. Each
            command is an argv list (e.g. [["uv", "version", "{version}"]]).
            Supports template variables:
              {version}         Bare semver (e.g. "1.2.3"), tag prefix stripped.
              {project_version} Full project version as tagged (e.g. "core-1.2.3").
              {changelog}       Absolute path to the changelog file.
    """

    model_config = ConfigDict(
        alias_generator=_ALIASES,
        populate_by_name=True,
    )

    post_changelog: list[list[str]] = Field(default_factory=list)


class ProjectConfig(BaseModel):
    """Configuration for a single project in a monorepo.

    Attributes:
        name: Unique project identifier.
        path: Project directory relative to repo root.
        changelog_path: Changelog file relative to project path.
        tag_prefix: Git tag prefix (e.g., "core-").
        alias_versions: Override global alias_versions setting.
        hooks: Per-project hooks, merged with global hooks.
        include_paths: Additional paths to monitor for changes.
    """

    model_config = ConfigDict(
        alias_generator=_ALIASES,
        populate_by_name=True,
    )

    name: str
    path: str  # Relative to repo root
    changelog_path: str = 'CHANGELOG.md'  # Relative to project path
    tag_prefix: str = ''
    alias_versions: AliasVersions | None = None
    hooks: ReleezHooks = Field(default_factory=ReleezHooks)
    include_paths: list[str] = Field(default_factory=list)


def _filter_projects_by_name(
    subprojects: list[SubProject],
    project_names: list[str],
) -> list[SubProject]:
    """Return a deduplicated ordered subset of *subprojects* matching *project_names*.

    Raises:
        ReleezError: If any name in *project_names* is not present in *subprojects*.
    """
    projects_by_name = {p.name: p for p in subprojects}
    unknown = [n for n in project_names if n not in projects_by_name]
    if unknown:
        available = ', '.join(sorted(projects_by_name))
        msg = f'Unknown project(s): {", ".join(sorted(unknown))}. Available: {available}'
        raise ReleezError(msg)
    seen: set[str] = set()
    selected: list[SubProject] = []
    for name in project_names:
        if name not in seen:
            seen.add(name)
            selected.append(projects_by_name[name])
    return selected


class ReleezSettings(BaseSettings):
    """Settings loaded from CLI args, env vars, and config files.

    Precedence (highest first):
      1. Explicit init kwargs (CLI layer)
      2. RELEEZ_* env vars
      3. releez.toml
      4. pyproject.toml ([tool.releez])
    """

    model_config = SettingsConfigDict(
        env_prefix='RELEEZ_',
        env_nested_delimiter='__',
        extra='ignore',
        pyproject_toml_table_header=('tool', 'releez'),
        alias_generator=_ALIASES,
        populate_by_name=True,
    )

    base_branch: str = 'master'
    git_remote: str = 'origin'
    pr_labels: str = 'release'
    pr_title_prefix: str = 'chore(release): '
    changelog_path: str = 'CHANGELOG.md'
    create_pr: bool = False
    maintenance_branch_regex: str | None = None
    maintenance_branch_template: str | None = None
    alias_versions: AliasVersions = AliasVersions.none
    hooks: ReleezHooks = Field(default_factory=ReleezHooks)
    projects: list[ProjectConfig] = Field(default_factory=list)

    @property
    def is_monorepo(self) -> bool:
        """Return True if any projects are configured (monorepo mode)."""
        return bool(self.projects)

    @property
    def effective_maintenance_branch_regex(self) -> str:
        r"""Return the active maintenance branch regex, applying a smart default if unset.

        Single-repo default: ``^support/(?P<major>\d+)\.x$``
        Monorepo default:    ``^support/(?P<prefix>[^\d]+-)?(?P<major>\d+)\.x$``
        """
        if self.maintenance_branch_regex is not None:
            return self.maintenance_branch_regex
        if self.is_monorepo:
            return r'^support/(?P<prefix>[^\d]+-)?(?P<major>\d+)\.x$'
        return r'^support/(?P<major>\d+)\.x$'

    @property
    def effective_maintenance_branch_template(self) -> str:
        """Return the active branch name template, applying a smart default if unset.

        Single-repo default: ``support/{major}.x``
        Monorepo default:    ``support/{prefix}{major}.x``
        """
        if self.maintenance_branch_template is not None:
            return self.maintenance_branch_template
        if self.is_monorepo:
            return 'support/{prefix}{major}.x'
        return 'support/{major}.x'

    @model_validator(mode='after')
    def _validate_maintenance_branch_regex(self) -> ReleezSettings:
        """Validate effective maintenance branch regex.

        Checks the regex is compilable and has a ``(?P<major>...)`` group.
        In monorepo mode also requires a ``(?P<prefix>...)`` group so branches
        for different projects can be distinguished.
        """
        regex = self.effective_maintenance_branch_regex
        try:
            compiled = re.compile(regex)
        except re.error as exc:
            raise InvalidMaintenanceBranchRegexError(
                regex,
                reason=str(exc),
            ) from exc
        if 'major' not in compiled.groupindex:
            raise InvalidMaintenanceBranchRegexError(
                regex,
                reason='missing named capture group "major"',
            )
        if self.is_monorepo and 'prefix' not in compiled.groupindex:
            raise InvalidMaintenanceBranchRegexError(
                regex,
                reason='missing named capture group "prefix" (required in monorepo mode)',
            )
        return self

    @model_validator(mode='after')
    def _validate_maintenance_branch_template(self) -> ReleezSettings:
        """Validate effective maintenance branch template.

        Checks the template contains ``{major}``. In monorepo mode also
        requires ``{prefix}`` so each project gets a unique branch name.
        """
        template = self.effective_maintenance_branch_template
        if '{major}' not in template:
            msg = f'maintenance-branch-template {template!r} must contain {{major}}'
            raise ReleezError(msg)
        if self.is_monorepo and '{prefix}' not in template:
            msg = (
                f'maintenance-branch-template {template!r} must contain {{prefix}} '
                'in monorepo mode so each project gets a unique branch name'
            )
            raise ReleezError(msg)
        return self

    def get_subprojects(self, *, repo_root: Path) -> list[SubProject]:
        """Build SubProject instances from all configured projects.

        Args:
            repo_root: Absolute path to the repository root.

        Returns:
            List of SubProject instances; empty list in single-repo mode.
        """
        from releez.subproject import SubProject  # noqa: PLC0415 (local import to avoid circular dependency)

        return [
            SubProject.from_config(
                config,
                repo_root=repo_root,
                global_settings=self,
            )
            for config in self.projects
        ]

    def validate_project_flags(
        self,
        *,
        project_names: list[str],
        all_projects: bool,
    ) -> None:
        """Raise ReleezError if project flags are used in single-repo mode.

        No-op in monorepo mode.

        Raises:
            ReleezError: If called with project flags when not in monorepo mode.
        """
        if not self.is_monorepo and (project_names or all_projects):
            msg = 'No projects are configured. Remove --project/--all or configure [tool.releez.projects].'
            raise ReleezError(msg)

    def select_projects(
        self,
        *,
        repo_root: Path,
        project_names: list[str],
        all_projects: bool,
    ) -> list[SubProject]:
        """Resolve project selection for a monorepo-aware command.

        Only valid in monorepo mode. Callers must check ``is_monorepo`` before
        calling this method.

        Raises:
            ReleezError: If called in single-repo mode, or for conflicting flags,
                unknown project names, or missing selection in monorepo mode.
        """
        if not self.is_monorepo:
            msg = 'select_projects() requires monorepo mode; check is_monorepo first'
            raise ReleezError(msg)

        subprojects = self.get_subprojects(repo_root=repo_root)

        if project_names and all_projects:
            msg = 'Cannot use --project and --all together.'
            raise ReleezError(msg)

        if all_projects:
            return subprojects

        if project_names:
            return _filter_projects_by_name(subprojects, project_names)

        msg = 'Project selection is required in monorepo mode. Use --project <name> (repeatable) or --all.'
        raise ReleezError(msg)

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Customize settings sources for Releez."""
        _ = (dotenv_settings, file_secret_settings)
        releez_toml = _ReleezTomlConfigSettingsSource(settings_cls)
        pyproject_toml = PyprojectTomlConfigSettingsSource(settings_cls)
        return (
            init_settings,
            env_settings,
            releez_toml,
            pyproject_toml,
        )
