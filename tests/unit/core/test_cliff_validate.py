"""Unit tests for commit message validation in cliff.py.

Tests are split into two groups:
  1. _build_validation_config() — pure config transformation, no subprocess.
  2. GitCliff.validate_commit_message() — subprocess mocked via monkeypatch.

All tests use standalone cliff.toml fixtures written to tmp_path; they never
read the project's own cliff.toml.
"""

from __future__ import annotations

import tomllib
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path
import tomli_w

import releez.cliff
from releez.cliff import (
    CommitValidationResult,
    GitCliff,
    _build_validation_config,
)
from releez.errors import ExternalCommandError

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

_FIXTURE_TOML = """\
[git]
conventional_commits = true
filter_unconventional = true
fail_on_unmatched_commit = false
commit_parsers = [
  { message = "^feat", group = "Features" },
  { message = "^fix", group = "Fixes" },
  { message = "^chore\\\\(release\\\\):", skip = true },
  { message = ".*", group = "Other" },
]
"""

_NO_GIT_SECTION_TOML = """\
[changelog]
body = ""
render_always = false
"""


def _write_cliff_toml(tmp_path: Path, content: str = _FIXTURE_TOML) -> Path:
    p = tmp_path / 'cliff.toml'
    p.write_text(content, encoding='utf-8')
    return p


# ---------------------------------------------------------------------------
# _build_validation_config — config transformation tests
# ---------------------------------------------------------------------------


def test_forces_filter_unconventional_false(tmp_path: Path) -> None:
    """filter_unconventional is overridden to False.

    Non-conventional commits must reach parsers instead of being silently
    dropped before the match check.
    """
    cfg = _build_validation_config(_write_cliff_toml(tmp_path))
    assert cfg['git']['filter_unconventional'] is False


def test_forces_fail_on_unmatched_commit_true(tmp_path: Path) -> None:
    """fail_on_unmatched_commit is overridden to True.

    git-cliff must exit non-zero when no parser matches, so the CLI can
    report the message as invalid.
    """
    cfg = _build_validation_config(_write_cliff_toml(tmp_path))
    assert cfg['git']['fail_on_unmatched_commit'] is True


def test_removes_catchall_parser(tmp_path: Path) -> None:
    """Catch-all parsers (message = ".*") are stripped.

    Because filter_unconventional is overridden to False, a ".*" pattern would
    match any raw commit message — including completely non-conventional text
    like "half-done something" — making the validation check a no-op.
    """
    cfg = _build_validation_config(_write_cliff_toml(tmp_path))
    parsers: list[dict[str, object]] = cfg['git']['commit_parsers']
    assert not any(p.get('message') == '.*' for p in parsers)


def test_preserves_named_parsers(tmp_path: Path) -> None:
    """Explicit type parsers (e.g. ^feat, ^fix) survive transformation.

    They must be kept so that configured types continue to be accepted after
    the catch-all is removed.
    """
    cfg = _build_validation_config(_write_cliff_toml(tmp_path))
    parsers: list[dict[str, object]] = cfg['git']['commit_parsers']
    messages = [p['message'] for p in parsers]
    assert '^feat' in messages
    assert '^fix' in messages


def test_preserves_skip_true_parsers(tmp_path: Path) -> None:
    """Parsers with skip=true (e.g. chore(release):) are kept.

    skip=true means "omit from changelog", not "reject as invalid".  A PR
    title matching a skip parser is a valid conventional commit and should
    exit 0.
    """
    cfg = _build_validation_config(_write_cliff_toml(tmp_path))
    parsers: list[dict[str, object]] = cfg['git']['commit_parsers']
    assert any(p.get('skip') is True for p in parsers)


def test_no_git_section_creates_git_section(tmp_path: Path) -> None:
    """A cliff.toml without a [git] section still produces a valid config.

    The overrides are applied to a freshly created git table with an empty
    commit_parsers list — no KeyError is raised.
    """
    cfg = _build_validation_config(
        _write_cliff_toml(tmp_path, _NO_GIT_SECTION_TOML),
    )
    assert cfg['git']['filter_unconventional'] is False
    assert cfg['git']['fail_on_unmatched_commit'] is True
    assert cfg['git']['commit_parsers'] == []


def test_output_round_trips_as_valid_toml(tmp_path: Path) -> None:
    """The modified config dict serialises to valid TOML and back.

    Confirms that tomli_w round-trips the overrides correctly so the temp
    config file written to disk is parseable by git-cliff.
    """
    cfg = _build_validation_config(_write_cliff_toml(tmp_path))
    rendered = tomli_w.dumps(cfg)
    parsed = tomllib.loads(rendered)
    assert parsed['git']['fail_on_unmatched_commit'] is True
    assert parsed['git']['filter_unconventional'] is False
    assert not any(p.get('message') == '.*' for p in parsed['git']['commit_parsers'])


def test_no_parsers_in_source_stays_empty(tmp_path: Path) -> None:
    """A [git] section with no commit_parsers key yields an empty list.

    No KeyError or unexpected default insertion should occur.
    """
    toml = '[git]\nconventional_commits = true\n'
    cfg = _build_validation_config(_write_cliff_toml(tmp_path, toml))
    assert cfg['git']['commit_parsers'] == []


def test_multiple_catchalls_all_removed(tmp_path: Path) -> None:
    """All ".*" entries are removed, not just the first one.

    Guards against a cliff.toml that happens to contain more than one
    catch-all parser.
    """
    toml = (
        '[git]\n'
        'commit_parsers = [\n'
        '  { message = "^feat", group = "Features" },\n'
        '  { message = ".*", group = "Other1" },\n'
        '  { message = ".*", group = "Other2" },\n'
        ']\n'
    )
    cfg = _build_validation_config(_write_cliff_toml(tmp_path, toml))
    parsers: list[dict[str, object]] = cfg['git']['commit_parsers']
    assert len(parsers) == 1
    assert parsers[0]['message'] == '^feat'


def test_raises_type_error_if_git_is_not_a_dict(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A malformed cliff.toml where [git] is not a table raises TypeError.

    The error must carry a descriptive message rather than producing a silent
    AttributeError downstream.
    """
    monkeypatch.setattr(tomllib, 'load', lambda _f: {'git': 'not-a-dict'})
    with pytest.raises(TypeError, match='Expected \\[git\\] to be a table'):
        _build_validation_config(_write_cliff_toml(tmp_path))


def test_raises_type_error_if_commit_parsers_is_not_a_list(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A malformed cliff.toml where commit_parsers is not an array raises TypeError.

    The error must carry a descriptive message rather than failing silently.
    """
    monkeypatch.setattr(
        tomllib,
        'load',
        lambda _f: {'git': {'commit_parsers': 'not-a-list'}},
    )
    with pytest.raises(
        TypeError,
        match='Expected commit_parsers to be an array',
    ):
        _build_validation_config(_write_cliff_toml(tmp_path))


# ---------------------------------------------------------------------------
# GitCliff.validate_commit_message — subprocess mocked
# ---------------------------------------------------------------------------


def _make_cliff(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> GitCliff:
    """Return a GitCliff instance with _git_cliff_base_cmd patched."""
    monkeypatch.setattr(
        releez.cliff,
        '_git_cliff_base_cmd',
        lambda: ['git-cliff'],
    )
    _write_cliff_toml(tmp_path)
    return GitCliff(repo_root=tmp_path)


def test_validate_returns_valid_on_exit_0(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A git-cliff exit 0 produces a CommitValidationResult with valid=True.

    The result must also carry a non-empty reason string.
    """
    monkeypatch.setattr(releez.cliff, 'run_checked', lambda *_a, **_kw: '')
    cliff = _make_cliff(tmp_path, monkeypatch)
    result = cliff.validate_commit_message('feat: something')
    assert isinstance(result, CommitValidationResult)
    assert result.valid is True
    assert result.reason


def test_validate_returns_invalid_on_nonzero_exit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A git-cliff non-zero exit produces a CommitValidationResult with valid=False.

    The ExternalCommandError must be caught and converted to a result rather
    than propagated to the caller.
    """

    def _fail(cmd: list[str], **_kw: object) -> str:
        if 'git-cliff' in cmd[0]:
            raise ExternalCommandError(cmd_args=cmd, returncode=101, stderr='')
        return ''

    monkeypatch.setattr(releez.cliff, 'run_checked', _fail)
    cliff = _make_cliff(tmp_path, monkeypatch)
    result = cliff.validate_commit_message('bad message')
    assert isinstance(result, CommitValidationResult)
    assert result.valid is False
    assert result.reason


def test_validate_passes_with_commit_and_config_flags(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """git-cliff is invoked with --with-commit, --config, and --unreleased.

    --with-commit injects the message as a synthetic commit; --config points
    to the temp validation config; --unreleased ensures only that synthetic
    commit is evaluated, not the project's real git history.
    """
    captured: list[list[str]] = []

    def _capture(cmd: list[str], **_kw: object) -> str:
        captured.append(cmd)
        return ''

    monkeypatch.setattr(releez.cliff, 'run_checked', _capture)
    cliff = _make_cliff(tmp_path, monkeypatch)
    cliff.validate_commit_message('feat: test')

    # Find the git-cliff call (others are git setup commands for the temp repo)
    cliff_calls = [cmd for cmd in captured if 'git-cliff' in cmd[0]]
    assert len(cliff_calls) == 1
    cmd = cliff_calls[0]
    assert '--with-commit' in cmd
    assert 'feat: test' in cmd
    assert '--config' in cmd
    assert '--unreleased' in cmd
