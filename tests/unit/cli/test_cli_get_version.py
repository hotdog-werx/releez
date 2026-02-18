from __future__ import annotations

from typer.testing import CliRunner

from releez import __version__, cli


def test_cli_version_flag_prints_version() -> None:
    runner = CliRunner()

    result = runner.invoke(cli.app, ['--version'])

    assert result.exit_code == 0
    assert result.stdout == f'releez {__version__}\n'
