from __future__ import annotations

from pydantic import AliasChoices, AliasGenerator, BaseModel, ConfigDict, Field
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    PyprojectTomlConfigSettingsSource,
    SettingsConfigDict,
    TomlConfigSettingsSource,
)

from releez.version_tags import AliasTags


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
        changelog_format: Optional argv list used to format the changelog (e.g.
            ["dprint", "fmt", "{changelog}"]).
    """

    model_config = ConfigDict(
        alias_generator=_ALIASES,
        populate_by_name=True,
    )

    changelog_format: list[str] | None = None


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
    alias_tags: AliasTags = AliasTags.none
    hooks: ReleezHooks = Field(default_factory=ReleezHooks)

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
