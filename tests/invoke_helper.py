from __future__ import annotations

import contextlib
import io
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cyclopts import App


@dataclass
class InvokeResult:
    """Result of invoking a cyclopts App in tests."""

    exit_code: int
    stdout: str
    stderr: str = field(default='')

    @property
    def output(self) -> str:
        """Combined stdout + stderr (mirrors typer CliRunner default mix_stderr=True)."""
        return self.stdout + self.stderr


def invoke(app: App, args: list[str]) -> InvokeResult:
    """Invoke a cyclopts App with args, capturing stdout/stderr and exit code."""
    stdout = io.StringIO()
    stderr = io.StringIO()
    exit_code = 0
    try:
        with (
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            app(args)  # type: ignore[operator]
    except SystemExit as exc:
        exit_code = int(exc.code) if exc.code is not None else 0
    return InvokeResult(
        exit_code=exit_code,
        stdout=stdout.getvalue(),
        stderr=stderr.getvalue(),
    )
