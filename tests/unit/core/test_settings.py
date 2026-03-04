from __future__ import annotations

import warnings
from typing import TYPE_CHECKING

from releez.settings import ReleezSettings
from releez.version_tags import AliasVersions

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def test_settings_reads_pyproject_tool_releez_kebab_case(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / 'pyproject.toml').write_text(
        '[tool.releez]\nalias-versions = "major"\ngit-remote = "upstream"\n',
        encoding='utf-8',
    )

    settings = ReleezSettings()
    assert settings.alias_versions == AliasVersions.major
    assert settings.git_remote == 'upstream'


def test_settings_reads_releez_toml_tool_releez_table(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / 'releez.toml').write_text(
        '[tool.releez]\nalias-versions = "minor"\ngit-remote = "upstream"\n',
        encoding='utf-8',
    )

    settings = ReleezSettings()
    assert settings.alias_versions == AliasVersions.minor
    assert settings.git_remote == 'upstream'


def test_settings_reads_releez_toml_flat_legacy_warns(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / 'releez.toml').write_text(
        'alias_versions = "minor"\n',
        encoding='utf-8',
    )

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter('always')
        settings = ReleezSettings()

    assert settings.alias_versions == AliasVersions.minor
    assert any(
        issubclass(warning.category, DeprecationWarning) and 'tool.releez' in str(warning.message) for warning in w
    )


def test_settings_reads_env_vars(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('RELEEZ_ALIAS_VERSIONS', 'major')

    settings = ReleezSettings()
    assert settings.alias_versions == AliasVersions.major


def test_settings_env_vars_override_pyproject_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / 'pyproject.toml').write_text(
        '[tool.releez.hooks]\nchangelog-format = ["mise", "exec", "--", "poe", "format-dprint", "{changelog}"]\n',
        encoding='utf-8',
    )
    monkeypatch.setenv(
        'RELEEZ_HOOKS__CHANGELOG_FORMAT',
        '["dprint", "fmt", "{changelog}"]',
    )

    settings = ReleezSettings()
    assert settings.hooks.changelog_format == ['dprint', 'fmt', '{changelog}']


def test_settings_warns_deprecated_run_changelog_format(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / 'pyproject.toml').write_text(
        '[tool.releez]\nrun-changelog-format = true\n',
        encoding='utf-8',
    )

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter('always')
        settings = ReleezSettings()
        assert settings.run_changelog_format is True

        # Check deprecation warning was raised
        assert len(w) == 1
        assert issubclass(w[0].category, DeprecationWarning)
        assert 'run_changelog_format' in str(w[0].message)
        assert 'post_changelog' in str(w[0].message)


def test_settings_warns_deprecated_changelog_format_hook(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / 'pyproject.toml').write_text(
        '[tool.releez.hooks]\nchangelog-format = ["prettier", "--write", "{changelog}"]\n',
        encoding='utf-8',
    )

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter('always')
        settings = ReleezSettings()

        # Check deprecation warning was raised
        assert len(w) == 1
        assert issubclass(w[0].category, DeprecationWarning)
        assert 'changelog_format' in str(w[0].message)
        assert 'post-changelog' in str(w[0].message)

        # Check auto-migration happened
        assert settings.hooks.post_changelog == [
            ['prettier', '--write', '{changelog}'],
        ]
