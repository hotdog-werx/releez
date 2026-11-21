"""Tests for releez.console output helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from releez.console import emit

if TYPE_CHECKING:
    import pytest


def test_emit_writes_text_verbatim_even_when_color_forced(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """emit() bypasses Rich: no styling, highlighting, or wrapping of long lines."""
    monkeypatch.setenv('FORCE_COLOR', '1')
    text = '{"version": "1.2.3"} ' + 'x' * 300

    emit(text)

    assert capsys.readouterr().out == f'{text}\n'
