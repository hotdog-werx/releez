from __future__ import annotations

import pytest

from releez.errors import InvalidReleaseVersionError
from releez.version_tags import compute_version_tags


def test_compute_version_tags_exact_never_v_prefixed() -> None:
    tags = compute_version_tags(version='v2.3.4')
    assert tags.exact == '2.3.4'
    assert tags.major == 'v2'
    assert tags.minor == 'v2.3'


@pytest.mark.parametrize(
    'version',
    [
        '2.3',
        '2.3.4.5',
        '2.3.4-rc.1',
        '2.3.4+99',
        'v2.3',
        'not-a-version',
    ],
)
def test_compute_version_tags_rejects_invalid_versions(version: str) -> None:
    with pytest.raises(InvalidReleaseVersionError):
        compute_version_tags(version=version)


def test_compute_version_tags_with_prefix() -> None:
    """Test that tag prefix is applied to all tags."""
    tags = compute_version_tags(version='1.2.3', tag_prefix='core-')
    assert tags.exact == 'core-1.2.3'
    assert tags.major == 'core-v1'
    assert tags.minor == 'core-v1.2'


def test_compute_version_tags_without_prefix_backwards_compatible() -> None:
    """Test that omitting tag_prefix maintains backwards compatibility."""
    tags = compute_version_tags(version='1.2.3')
    assert tags.exact == '1.2.3'
    assert tags.major == 'v1'
    assert tags.minor == 'v1.2'


def test_compute_version_tags_with_empty_prefix() -> None:
    """Test that empty string prefix works (same as no prefix)."""
    tags = compute_version_tags(version='1.2.3', tag_prefix='')
    assert tags.exact == '1.2.3'
    assert tags.major == 'v1'
    assert tags.minor == 'v1.2'


def test_compute_version_tags_with_different_prefixes() -> None:
    """Test various valid tag prefixes."""
    # Simple dash prefix
    tags = compute_version_tags(version='2.0.0', tag_prefix='ui-')
    assert tags.exact == 'ui-2.0.0'
    assert tags.major == 'ui-v2'

    # Namespace-style prefix
    tags = compute_version_tags(version='3.1.4', tag_prefix='api/v2-')
    assert tags.exact == 'api/v2-3.1.4'
    assert tags.major == 'api/v2-v3'

    # Underscore prefix
    tags = compute_version_tags(version='1.0.0', tag_prefix='lib_')
    assert tags.exact == 'lib_1.0.0'
    assert tags.minor == 'lib_v1.0'
