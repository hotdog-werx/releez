from __future__ import annotations

from importlib import metadata as importlib_metadata

from releez.git_repo import DetectedRelease, detect_release_from_branch

__version__ = importlib_metadata.version('releez')

__all__ = [
    'DetectedRelease',
    '__version__',
    'detect_release_from_branch',
]
