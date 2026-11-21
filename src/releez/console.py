from __future__ import annotations

import sys
from typing import Any

from rich.console import Console


class _DynamicConsole:
    """Wraps Rich Console, reading sys.stdout/sys.stderr at print time.

    This allows contextlib.redirect_stdout/redirect_stderr to work correctly
    in tests — a new Console is constructed on each call so it picks up
    whatever sys.stdout/sys.stderr currently points at.
    """

    def __init__(self, *, stderr: bool = False) -> None:
        self._stderr = stderr

    def print(self, *args: Any, **kwargs: Any) -> None:
        file = sys.stderr if self._stderr else sys.stdout
        Console(file=file).print(*args, **kwargs)


def emit(text: str) -> None:
    """Write machine-readable output to stdout verbatim.

    Bypasses Rich so output consumed by scripts (JSON, versions, release
    notes) never gains ANSI styling or line wrapping, even when color is
    forced (e.g. ``FORCE_COLOR=1`` in CI).
    """
    sys.stdout.write(f'{text}\n')


console = _DynamicConsole()
err_console = _DynamicConsole(stderr=True)
