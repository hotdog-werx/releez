"""Integration tests for commit message validation against real git-cliff.

Each test creates a self-contained git repository in tmp_path with a
standalone cliff.toml — no dependency on the releez project's own cliff.toml.

The fixture cliff.toml is deliberately written with the "wrong" settings
(filter_unconventional=true, fail_on_unmatched=false) so that the tests also
exercise _build_validation_config() applying the two overrides. No catch-all
parser is present so that unknown types are correctly rejected.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from git import Repo

from releez.cliff import GitCliff

if TYPE_CHECKING:
    from pathlib import Path

# Fixture cliff.toml intentionally has filter_unconventional=true and
# fail_on_unmatched=false so that the tests also exercise
# _build_validation_config() applying the two overrides.
# No catch-all parser (".*") is present — unknown types should be rejected.
_FIXTURE_CLIFF_TOML = """\
[changelog]
body = ""
render_always = false

[git]
conventional_commits = true
filter_unconventional = true
fail_on_unmatched_commit = false
commit_parsers = [
  { message = "^feat", group = "Features" },
  { message = "^fix", group = "Fixes" },
  { message = "^chore\\\\(release\\\\):", skip = true },
  { message = "^chore\\\\(deps", skip = true },
  { message = "^chore|^ci", group = "Misc" },
]
"""


def _setup_repo(tmp_path: Path) -> None:
    """Initialise a git repo with an initial commit and the fixture cliff.toml."""
    (tmp_path / 'cliff.toml').write_text(_FIXTURE_CLIFF_TOML, encoding='utf-8')
    repo = Repo.init(tmp_path)
    repo.config_writer().set_value('user', 'name', 'Test').release()
    repo.config_writer().set_value(
        'user',
        'email',
        'test@example.com',
    ).release()
    (tmp_path / 'README.md').write_text('# test\n', encoding='utf-8')
    repo.index.add(['cliff.toml', 'README.md'])
    repo.index.commit('feat: initial commit')


@pytest.mark.parametrize(
    ('message', 'expected_valid'),
    [
        # ── Valid: matches a named parser ──────────────────────────────────
        ('feat: add new feature', True),
        ('fix: correct a bug', True),
        ('feat(scope): scoped feature', True),
        ('fix(api): scoped fix', True),
        ('feat!: breaking change', True),
        ('fix(api)!: breaking scoped fix', True),
        ('chore: miscellaneous task', True),
        ('ci: update workflow', True),
        # ── Valid: skip=true parser matched — still a valid PR title ───────
        ('chore(release): 1.2.3', True),
        ('chore(deps): bump something', True),
        # ── Invalid: non-conventional format ──────────────────────────────
        ('half-done something', False),
        ('just a sentence without type', False),
        ('WIP', False),
        # ── Invalid: conventional format but type not in fixture parsers ───
        ('wip: something', False),
        ('docs: update readme', False),
        ('perf: speed improvement', False),
        ('refactor: clean up', False),
        ('test: add tests', False),
        # ── Invalid: wrong case (conventional commits are lowercase type) ──
        ('FEAT: something', False),
        ('Fix: something', False),
    ],
)
def test_validate_commit_message(
    message: str,
    expected_valid: bool,  # noqa: FBT001
    tmp_path: Path,
) -> None:
    _setup_repo(tmp_path)
    cliff = GitCliff(repo_root=tmp_path)
    result = cliff.validate_commit_message(message)
    assert result.valid is expected_valid, (
        f'Message {message!r}: expected valid={expected_valid}, got valid={result.valid} (reason: {result.reason})'
    )


# ---------------------------------------------------------------------------
# Regression: ".*" catch-all still requires conventional commit format
# ---------------------------------------------------------------------------

_CATCHALL_CLIFF_TOML = """\
[changelog]
body = ""
render_always = false

[git]
conventional_commits = true
filter_unconventional = true
fail_on_unmatched_commit = false
commit_parsers = [
  { message = "^feat", group = "Features" },
  { message = "^chore", group = "Misc" },
  { message = ".*", group = "Other" },
]
"""


@pytest.mark.parametrize(
    ('message', 'expected_valid'),
    [
        # "^feat" parser survives stripping — feat: is valid
        ('feat: known type', True),
        ('feat(scope): scoped', True),
        # ".*" is stripped by _build_validation_config, so unknown types are
        # rejected even though they were "caught" by ".*" in the source config.
        ('wip: unknown type', False),
        ('docs: not in explicit parsers', False),
        # Non-conventional format was matched by ".*" in the source config, but
        # ".*" is stripped so these are now correctly rejected.
        ('half-done something', False),
        ('just a sentence', False),
        ('WIP', False),
        ('FEAT: wrong case', False),
    ],
)
def test_catchall_parser_is_stripped_for_validation(
    message: str,
    expected_valid: bool,  # noqa: FBT001
    tmp_path: Path,
) -> None:
    """Regression: a ".*" catch-all in cliff.toml is stripped by build_validation_config before running git-cliff.

    Without stripping, our filter_unconventional=False override causes ".*" to
    match *any* raw commit message — including completely non-conventional text
    like "half-done something" — making validation a no-op.  Stripping ".*"
    preserves the intent of the project's explicit parser list.
    """
    (tmp_path / 'cliff.toml').write_text(_CATCHALL_CLIFF_TOML, encoding='utf-8')
    repo = Repo.init(tmp_path)
    repo.config_writer().set_value('user', 'name', 'Test').release()
    repo.config_writer().set_value(
        'user',
        'email',
        'test@example.com',
    ).release()
    (tmp_path / 'README.md').write_text('# test\n', encoding='utf-8')
    repo.index.add(['cliff.toml', 'README.md'])
    repo.index.commit('chore: initial commit')

    cliff = GitCliff(repo_root=tmp_path)
    result = cliff.validate_commit_message(message)
    assert result.valid is expected_valid, (
        f'Message {message!r}: expected valid={expected_valid}, got valid={result.valid} (reason: {result.reason})'
    )
