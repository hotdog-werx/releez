"""Tests for the `validate commit-message` CLI subcommand."""

from __future__ import annotations

from typing import TYPE_CHECKING

from typer.testing import CliRunner

from releez import cli
from releez.cliff import CommitValidationResult

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


runner = CliRunner()


def _mock_validate(mocker: MockerFixture, *, valid: bool) -> None:
    reason = (
        'Valid: matches a commit parser'
        if valid
        else ('Invalid: does not match any commit parser (expected: type(scope?): subject)')
    )
    mocker.patch(
        'releez.cli.GitCliff.validate_commit_message',
        return_value=CommitValidationResult(valid=valid, reason=reason),
    )
    mocker.patch(
        'releez.cli.open_repo',
        return_value=(mocker.MagicMock(), mocker.MagicMock(root='/fake/repo')),
    )


def test_valid_message_exits_0(mocker: MockerFixture) -> None:
    _mock_validate(mocker, valid=True)
    result = runner.invoke(
        cli.app,
        ['validate', 'commit-message', 'feat: add feature'],
    )
    assert result.exit_code == 0
    assert '✓' in result.output


def test_valid_message_prints_reason(mocker: MockerFixture) -> None:
    _mock_validate(mocker, valid=True)
    result = runner.invoke(
        cli.app,
        ['validate', 'commit-message', 'feat: add feature'],
    )
    assert 'Valid: matches a commit parser' in result.output


def test_invalid_message_exits_1(mocker: MockerFixture) -> None:
    _mock_validate(mocker, valid=False)
    result = runner.invoke(
        cli.app,
        ['validate', 'commit-message', 'bad message'],
    )
    assert result.exit_code == 1


def test_invalid_message_prints_reason_to_stderr(mocker: MockerFixture) -> None:
    _mock_validate(mocker, valid=False)
    result = runner.invoke(
        cli.app,
        ['validate', 'commit-message', 'bad message'],
        catch_exceptions=False,
    )
    assert '✗' in result.output
    assert 'Invalid' in result.output


def test_message_is_passed_to_validate(mocker: MockerFixture) -> None:
    captured: list[str] = []
    reason = 'Valid: matches a commit parser'

    def _capture(self: object, message: str) -> CommitValidationResult:
        captured.append(message)
        return CommitValidationResult(valid=True, reason=reason)

    mocker.patch('releez.cli.GitCliff.validate_commit_message', _capture)
    mocker.patch(
        'releez.cli.open_repo',
        return_value=(mocker.MagicMock(), mocker.MagicMock(root='/fake/repo')),
    )

    runner.invoke(
        cli.app,
        ['validate', 'commit-message', 'feat(api): my message'],
    )
    assert captured == ['feat(api): my message']
