from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from invoke_helper import InvokeResult
from invoke_helper import invoke as _invoke

if TYPE_CHECKING:
    from collections.abc import Callable


@pytest.fixture
def invoke() -> Callable[[object, list[str]], InvokeResult]:
    """Fixture providing a callable to invoke cyclopts Apps in tests."""
    return _invoke
