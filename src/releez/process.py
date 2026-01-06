from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

from releez.errors import ExternalCommandError, MissingCliError

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path


def run_checked(
    args: Sequence[str],
    *,
    cwd: Path | None = None,
    capture_stdout: bool = True,
) -> str:
    """Run a command and raise a ReleezError on failure.

    Args:
        args: The command and arguments to execute.
        cwd: Optional working directory for the command.
        capture_stdout: If false, stdout is not captured.

    Returns:
        The stripped stdout of the command.

    Raises:
        MissingCliError: If the executable is not found.
        ExternalCommandError: If the command exits non-zero.
    """
    try:
        res = subprocess.run(  # noqa: S603
            list(args),
            cwd=cwd,
            check=True,
            text=True,
            stdout=subprocess.PIPE if capture_stdout else None,
            stderr=subprocess.PIPE,
        )
    except FileNotFoundError as exc:
        raise MissingCliError(args[0]) from exc
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or '').strip()
        raise ExternalCommandError(
            cmd_args=args,
            returncode=exc.returncode,
            stderr=stderr,
        ) from exc

    return (res.stdout or '').strip()
