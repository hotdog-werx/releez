from __future__ import annotations

import pytest

from releez.errors import InvalidGitHubRemoteError
from releez.github import _github_api_base_url_from_env, _parse_github_full_name


def test_parse_github_full_name_https_github_com() -> None:
    assert _parse_github_full_name('https://github.com/org/repo.git') == 'org/repo'


def test_parse_github_full_name_supports_github_server_url_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv('GITHUB_SERVER_URL', 'https://ghe.example.com')
    assert _parse_github_full_name('git@ghe.example.com:org/repo.git') == 'org/repo'


def test_parse_github_full_name_rejects_unknown_hosts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv('GITHUB_SERVER_URL', 'https://ghe.example.com')
    with pytest.raises(InvalidGitHubRemoteError):
        _parse_github_full_name('https://gitlab.com/org/repo.git')


def test_github_api_base_url_prefers_api_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv('GITHUB_API_URL', 'https://ghe.example.com/api/v3')
    monkeypatch.setenv('GITHUB_SERVER_URL', 'https://ghe.example.com')
    assert _github_api_base_url_from_env() == 'https://ghe.example.com/api/v3'


def test_github_api_base_url_derives_from_server_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv('GITHUB_API_URL', raising=False)
    monkeypatch.setenv('GITHUB_SERVER_URL', 'https://ghe.example.com/')
    assert _github_api_base_url_from_env() == 'https://ghe.example.com/api/v3'
