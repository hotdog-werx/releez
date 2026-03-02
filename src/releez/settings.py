from __future__ import annotations

import warnings

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

from releez.version_tags import AliasVersions


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
        changelog_format: (DEPRECATED) Use post_changelog instead. Optional argv
            list used to format the changelog.
    """

    model_config = ConfigDict(
        alias_generator=_ALIASES,
        populate_by_name=True,
    )

    post_changelog: list[list[str]] = Field(default_factory=list)
    changelog_format: list[str] | None = None

    @model_validator(mode='after')
    def _migrate_changelog_format(self) -> ReleezHooks:
        """Migrate deprecated changelog_format to post_changelog."""
        if self.changelog_format is not None:
            warnings.warn(
                'The `changelog_format` hook is deprecated. '
                'Use `post_changelog` instead:\n'
                '  [tool.releez.hooks]\n'
                '  post-changelog = [\n'
                '    ["prettier", "--write", "{changelog}"],\n'
                '  ]',
                DeprecationWarning,
                stacklevel=2,
            )
            if not self.post_changelog:
                # Auto-migrate: wrap single command in list
                self.post_changelog = [self.changelog_format]
        return self


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
    run_changelog_format: bool = False
    alias_versions: AliasVersions = AliasVersions.none
    hooks: ReleezHooks = Field(default_factory=ReleezHooks)
    projects: list[ProjectConfig] = Field(default_factory=list)

    @model_validator(mode='after')
    def _warn_deprecated_settings(self) -> ReleezSettings:
        """Warn about deprecated settings."""
        if self.run_changelog_format:
            warnings.warn(
                'The `run_changelog_format` setting is deprecated. '
                'Remove it from your config and use `post_changelog` hooks instead:\n'
                '  [tool.releez.hooks]\n'
                '  post-changelog = [\n'
                '    ["prettier", "--write", "{changelog}"],\n'
                '  ]\n'
                'Hooks will run automatically when configured.',
                DeprecationWarning,
                stacklevel=2,
            )
        return self

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
        releez_toml = TomlConfigSettingsSource(
            settings_cls,
            toml_file='releez.toml',
        )
        pyproject_toml = PyprojectTomlConfigSettingsSource(settings_cls)
        return (
            init_settings,
            env_settings,
            releez_toml,
            pyproject_toml,
        )
