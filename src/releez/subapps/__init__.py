from __future__ import annotations

import releez.subapps.release_notes
import releez.subapps.release_preview
import releez.subapps.release_start
import releez.subapps.release_support
import releez.subapps.release_tag  # noqa: F401 — triggers command registration on release_app
from releez.subapps.changelog import changelog_app
from releez.subapps.doctor import doctor_app
from releez.subapps.projects import projects_app
from releez.subapps.release import release_app
from releez.subapps.validate import validate_app
from releez.subapps.version import version_app

__all__ = [
    'changelog_app',
    'doctor_app',
    'projects_app',
    'release_app',
    'validate_app',
    'version_app',
]
