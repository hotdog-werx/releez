from __future__ import annotations

from typing import TYPE_CHECKING

from releez.utils import resolve_changelog_path

if TYPE_CHECKING:
    from pathlib import Path


def test_resolve_changelog_path_returns_existing_file(tmp_path: Path) -> None:
    changelog = tmp_path / 'CHANGELOG.md'
    changelog.write_text('# existing')

    result = resolve_changelog_path('CHANGELOG.md', tmp_path)

    assert result == changelog
    assert changelog.read_text() == '# existing'


def test_resolve_changelog_path_creates_file_when_missing(
    tmp_path: Path,
) -> None:
    result = resolve_changelog_path('CHANGELOG.md', tmp_path)

    assert result == tmp_path / 'CHANGELOG.md'
    assert result.exists()
    assert result.read_text() == ''


def test_resolve_changelog_path_absolute_path(tmp_path: Path) -> None:
    changelog = tmp_path / 'CHANGELOG.md'
    changelog.touch()

    result = resolve_changelog_path(str(changelog), tmp_path)

    assert result == changelog
