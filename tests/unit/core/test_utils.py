from __future__ import annotations

from typing import TYPE_CHECKING

from releez.utils import resolve_changelog_path

if TYPE_CHECKING:
    from pathlib import Path


def test_resolve_changelog_path_returns_existing_file(tmp_path: Path) -> None:
    """An existing changelog file is returned as-is without being overwritten."""
    changelog = tmp_path / 'CHANGELOG.md'
    changelog.write_text('# existing')

    result = resolve_changelog_path('CHANGELOG.md', tmp_path)

    assert result == changelog
    assert changelog.read_text() == '# existing'


def test_resolve_changelog_path_creates_file_when_missing(
    tmp_path: Path,
) -> None:
    """A missing changelog file is created empty at the resolved path."""
    result = resolve_changelog_path('CHANGELOG.md', tmp_path)

    assert result == tmp_path / 'CHANGELOG.md'
    assert result.exists()
    assert result.read_text() == ''


def test_resolve_changelog_path_absolute_path(tmp_path: Path) -> None:
    """An absolute changelog path is honored as given rather than joined to the repo root."""
    changelog = tmp_path / 'CHANGELOG.md'
    changelog.touch()

    result = resolve_changelog_path(str(changelog), tmp_path)

    assert result == changelog
