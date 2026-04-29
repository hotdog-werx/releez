from __future__ import annotations

from typing import TYPE_CHECKING

from invoke_helper import invoke

from releez import __version__, cli

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


def test_cli_version_flag_prints_version() -> None:
    result = invoke(cli.app, ['--version'])

    assert result.exit_code == 0
    assert result.output == f'releez {__version__}\n'


def test_main_invokes_app(mocker: MockerFixture) -> None:
    """Regression guard: script entrypoint must delegate directly to the app."""
    app = mocker.patch('releez.cli.app')

    cli.main()

    app.assert_called_once_with()
