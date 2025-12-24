import pytest

from releez.errors import InvalidReleaseVersionError
from releez.version_tags import compute_version_tags


def test_compute_version_tags_exact_never_v_prefixed() -> None:
    tags = compute_version_tags(version='v2.3.4', prefix='v')
    assert tags.exact == '2.3.4'
    assert tags.major == 'v2'
    assert tags.minor == 'v2.3'


def test_compute_version_tags_can_disable_alias_prefix() -> None:
    tags = compute_version_tags(version='2.3.4', prefix='')
    assert tags.exact == '2.3.4'
    assert tags.major == '2'
    assert tags.minor == '2.3'


@pytest.mark.parametrize('version', ['2.3', '2.3.4.5', 'v2.3', 'not-a-version'])
def test_compute_version_tags_rejects_invalid_versions(version: str) -> None:
    with pytest.raises(InvalidReleaseVersionError):
        compute_version_tags(version=version, prefix='v')
