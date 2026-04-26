from __future__ import annotations

import warnings
from typing import TYPE_CHECKING

import pytest

from releez.errors import InvalidMaintenanceBranchRegexError, ReleezError
from releez.settings import ReleezSettings
from releez.version_tags import AliasVersions

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture


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


class TestEffectiveMaintenanceBranchSettings:
    """Tests for effective_maintenance_branch_regex and effective_maintenance_branch_template."""

    def test_single_repo_defaults_when_not_set(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """With no config and no projects, effective values are single-repo defaults."""
        monkeypatch.chdir(tmp_path)
        settings = ReleezSettings()
        assert settings.maintenance_branch_regex is None
        assert settings.maintenance_branch_template is None
        assert settings.effective_maintenance_branch_regex == r'^support/(?P<major>\d+)\.x$'
        assert settings.effective_maintenance_branch_template == 'support/{major}.x'

    def test_monorepo_defaults_when_projects_configured(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """With projects configured and no explicit regex/template, effective values are monorepo defaults."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / 'src').mkdir()
        (tmp_path / 'pyproject.toml').write_text(
            '[tool.releez]\n[[tool.releez.projects]]\nname = "core"\npath = "src"\ntag-prefix = "core-"\n',
            encoding='utf-8',
        )
        settings = ReleezSettings()
        assert settings.effective_maintenance_branch_regex == r'^support/(?P<prefix>[^\d]+-)?(?P<major>\d+)\.x$'
        assert settings.effective_maintenance_branch_template == 'support/{prefix}{major}.x'

    def test_explicit_regex_passes_through(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Explicitly set regex is returned as-is by the effective property."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / 'pyproject.toml').write_text(
            '[tool.releez]\nmaintenance-branch-regex = "^hotfix/(?P<major>\\\\d+)\\\\.x$"\n',
            encoding='utf-8',
        )
        settings = ReleezSettings()
        assert settings.effective_maintenance_branch_regex == r'^hotfix/(?P<major>\d+)\.x$'

    def test_explicit_template_passes_through(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Explicitly set template is returned as-is by the effective property."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / 'pyproject.toml').write_text(
            '[tool.releez]\nmaintenance-branch-template = "hotfix/{major}.x"\n',
            encoding='utf-8',
        )
        settings = ReleezSettings()
        assert settings.effective_maintenance_branch_template == 'hotfix/{major}.x'

    def test_invalid_regex_raises_on_load(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """An invalid maintenance-branch-regex raises InvalidMaintenanceBranchRegexError at load time."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / 'pyproject.toml').write_text(
            '[tool.releez]\nmaintenance-branch-regex = "[invalid(regex"\n',
            encoding='utf-8',
        )
        with pytest.raises(InvalidMaintenanceBranchRegexError):
            ReleezSettings()

    def test_regex_missing_major_group_raises_on_load(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A regex without (?P<major>...) raises InvalidMaintenanceBranchRegexError at load time."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / 'pyproject.toml').write_text(
            '[tool.releez]\nmaintenance-branch-regex = "^support/(\\\\d+)\\\\.x$"\n',
            encoding='utf-8',
        )
        with pytest.raises(InvalidMaintenanceBranchRegexError, match='major'):
            ReleezSettings()

    def test_template_missing_major_raises_on_load(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A template without {major} raises ReleezError at load time."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / 'pyproject.toml').write_text(
            '[tool.releez]\nmaintenance-branch-template = "support/{prefix}.x"\n',
            encoding='utf-8',
        )
        with pytest.raises(ReleezError, match='major'):
            ReleezSettings()

    def test_monorepo_template_missing_prefix_raises_on_load(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """In monorepo mode, a template without {prefix} raises ReleezError at load time."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / 'src').mkdir()
        (tmp_path / 'pyproject.toml').write_text(
            '[tool.releez]\n'
            'maintenance-branch-template = "support/{major}.x"\n'
            '[[tool.releez.projects]]\n'
            'name = "core"\npath = "src"\ntag-prefix = "core-"\n',
            encoding='utf-8',
        )
        with pytest.raises(ReleezError, match='prefix'):
            ReleezSettings()

    def test_monorepo_regex_missing_prefix_group_raises_on_load(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """In monorepo mode, a regex without (?P<prefix>...) raises at load time."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / 'src').mkdir()
        (tmp_path / 'pyproject.toml').write_text(
            '[tool.releez]\n'
            'maintenance-branch-regex = "^support/(?P<major>\\\\d+)\\\\.x$"\n'
            '[[tool.releez.projects]]\n'
            'name = "core"\npath = "src"\ntag-prefix = "core-"\n',
            encoding='utf-8',
        )
        with pytest.raises(InvalidMaintenanceBranchRegexError, match='prefix'):
            ReleezSettings()


class TestSelectProjects:
    """Tests for ReleezSettings.select_projects."""

    def _make_settings(
        self,
        mocker: MockerFixture,
        *,
        subprojects: list[object],
    ) -> ReleezSettings:
        """Return a ReleezSettings instance with get_subprojects mocked."""
        settings = mocker.MagicMock(spec=ReleezSettings)
        settings.is_monorepo = bool(subprojects)
        settings.get_subprojects.return_value = subprojects
        settings.select_projects = ReleezSettings.select_projects.__get__(
            settings,
        )
        return settings

    def test_single_repo_raises(
        self,
        mocker: MockerFixture,
        tmp_path: Path,
    ) -> None:
        """Calling select_projects() in single-repo mode (no projects) raises ReleezError."""
        settings = self._make_settings(mocker, subprojects=[])
        with pytest.raises(ReleezError, match='requires monorepo mode'):
            settings.select_projects(
                repo_root=tmp_path,
                project_names=[],
                all_projects=False,
            )

    def test_all_flag_returns_all_projects(
        self,
        mocker: MockerFixture,
        tmp_path: Path,
    ) -> None:
        """--all returns all configured projects."""
        core = mocker.Mock(name='core')
        core.name = 'core'
        ui = mocker.Mock(name='ui')
        ui.name = 'ui'
        settings = self._make_settings(mocker, subprojects=[core, ui])
        result = settings.select_projects(
            repo_root=tmp_path,
            project_names=[],
            all_projects=True,
        )
        assert result == [core, ui]

    def test_project_name_returns_matching(
        self,
        mocker: MockerFixture,
        tmp_path: Path,
    ) -> None:
        """--project <name> returns only the named project."""
        core = mocker.Mock()
        core.name = 'core'
        ui = mocker.Mock()
        ui.name = 'ui'
        settings = self._make_settings(mocker, subprojects=[core, ui])
        result = settings.select_projects(
            repo_root=tmp_path,
            project_names=['core'],
            all_projects=False,
        )
        assert result == [core]

    def test_unknown_project_raises_with_available(
        self,
        mocker: MockerFixture,
        tmp_path: Path,
    ) -> None:
        """Unknown project name raises ReleezError listing available names."""
        core = mocker.Mock()
        core.name = 'core'
        settings = self._make_settings(mocker, subprojects=[core])
        with pytest.raises(ReleezError, match='Available'):
            settings.select_projects(
                repo_root=tmp_path,
                project_names=['missing'],
                all_projects=False,
            )

    def test_project_and_all_together_raise(
        self,
        mocker: MockerFixture,
        tmp_path: Path,
    ) -> None:
        """--project and --all together raises ReleezError."""
        core = mocker.Mock()
        core.name = 'core'
        settings = self._make_settings(mocker, subprojects=[core])
        with pytest.raises(ReleezError, match='--project and --all'):
            settings.select_projects(
                repo_root=tmp_path,
                project_names=['core'],
                all_projects=True,
            )

    def test_no_selection_raises(
        self,
        mocker: MockerFixture,
        tmp_path: Path,
    ) -> None:
        """No selection in monorepo mode raises ReleezError."""
        core = mocker.Mock()
        core.name = 'core'
        settings = self._make_settings(mocker, subprojects=[core])
        with pytest.raises(ReleezError, match='Project selection is required'):
            settings.select_projects(
                repo_root=tmp_path,
                project_names=[],
                all_projects=False,
            )

    def test_deduplicates_repeated_project_names(
        self,
        mocker: MockerFixture,
        tmp_path: Path,
    ) -> None:
        """Repeated project names in --project resolve to a single entry."""
        core = mocker.Mock()
        core.name = 'core'
        settings = self._make_settings(mocker, subprojects=[core])
        result = settings.select_projects(
            repo_root=tmp_path,
            project_names=['core', 'core'],
            all_projects=False,
        )
        assert result == [core]
