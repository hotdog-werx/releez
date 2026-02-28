from __future__ import annotations

from typing import TYPE_CHECKING

from typer.testing import CliRunner

from releez import __version__, cli

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


def test_cli_version_flag_prints_version() -> None:
    runner = CliRunner()

    result = runner.invoke(cli.app, ['--version'])

    assert result.exit_code == 0
    assert result.stdout == f'releez {__version__}\n'


def test_main_invokes_typer_app(mocker: MockerFixture) -> None:
    """Regression guard: script entrypoint must delegate directly to Typer app."""
    app = mocker.patch('releez.cli.app')

    cli.main()

    app.assert_called_once_with()
