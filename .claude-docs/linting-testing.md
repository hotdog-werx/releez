# Linting & Testing Guide

This document covers how to run tests, type checking, and linters for the Releez
project.

## Critical Rules

### ✅ DO

- **Always** use `mise exec --` prefix for running development tools
- **Always** run `mise exec -- ty check` for type checking
- **Always** run `mise exec -- ruff check` for linting
- **Always** run `mise exec -- pytest` for tests
- Use auto-fix when available: `mise exec -- ruff check --fix`

### ❌ DON'T

- **Never** run `basedpyright` directly - use `mise exec -- ty check` instead
- **Never** skip quality checks before considering work complete
- **Never** commit code with failing tests or type errors

## Running Tests

### Full Test Suite

```bash
mise exec -- pytest
```

### Run Specific Test File

```bash
mise exec -- pytest tests/unit/core/test_git_repo.py
```

### Run Specific Test Function

```bash
mise exec -- pytest tests/unit/core/test_git_repo.py::test_detect_release_from_branch_single_repo
```

### Run with Coverage

```bash
mise exec -- pytest --cov=releez --cov-report=term-missing
```

### Run Integration Tests Only

```bash
mise exec -- pytest tests/integration/
```

### Run Unit Tests Only

```bash
mise exec -- pytest tests/unit/
```

## Type Checking

### Check All Files

```bash
mise exec -- ty check
```

**Why not basedpyright?** The `ty` command is a wrapper that ensures correct
configuration and environment. Using `basedpyright` directly may use wrong
settings or miss configuration.

### Common Type Errors

**Missing type hints**:

```python
# ❌ Bad
def compute_version(input):
    return input.version

# ✅ Good
def compute_version(input: ArtifactVersionInput) -> str:
    return input.version
```

**TYPE_CHECKING imports**:

```python
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path
    import pytest

def test_something(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ...
```

## Linting

### Check All Files

```bash
mise exec -- ruff check
```

### Auto-Fix Issues

```bash
mise exec -- ruff check --fix
```

### Check Specific File

```bash
mise exec -- ruff check src/releez/cli.py
```

### Common Linting Issues

**Cyclomatic complexity (PLR0912)**:

- Threshold: 10
- Solution: Extract helper functions

```python
# ❌ Bad (complexity too high)
def complex_function(x, y, z):
    if x:
        if y:
            if z:
                # ... many nested conditions
                pass

# ✅ Good (extracted helpers)
def complex_function(x, y, z):
    if _should_process(x, y):
        _process_data(z)

def _should_process(x, y):
    return x and y

def _process_data(z):
    # ... process logic
```

**Too many arguments (PLR0913)**:

- Threshold: 5
- Solution: Use dataclasses or add `# noqa: PLR0913` if necessary

```python
# ❌ Bad
def create_release(version, branch, remote, labels, title, body):
    pass

# ✅ Good - use dataclass
@dataclass
class ReleaseInput:
    version: str
    branch: str
    remote: str
    labels: list[str]
    title: str
    body: str

def create_release(input: ReleaseInput):
    pass

# ✅ Acceptable - if all params are truly needed
def emit_all_versions(  # noqa: PLR0913
    version: str,
    is_full_release: bool,
    prerelease_type: PrereleaseType,
    prerelease_number: int | None,
    build_number: int | None,
    alias_versions: AliasVersions,
) -> None:
    pass
```

**Import ordering (I001)**:

```python
# ❌ Bad
from releez.git_repo import open_repo
from pathlib import Path
import json

# ✅ Good - auto-fixed by ruff
from __future__ import annotations

import json
from pathlib import Path

from releez.git_repo import open_repo
```

**Local imports inside functions (PLC0415)**:

```python
# ❌ Bad - NEVER import inside functions
def test_something(tmp_path: Path) -> None:
    from releez.settings import ReleezSettings  # WRONG!
    settings = ReleezSettings()

# ✅ Good - import at module level
from releez.settings import ReleezSettings

def test_something(tmp_path: Path) -> None:
    settings = ReleezSettings()
```

**Unused imports**:

- Auto-fixed by `ruff check --fix`

## Formatting

### Check Formatting

```bash
mise exec -- ruff format --check
```

### Apply Formatting

```bash
mise exec -- ruff format
```

## Pre-Commit Checklist

Before considering work complete, always run:

```bash
# 1. Run tests
mise exec -- pytest

# 2. Type check
mise exec -- ty check

# 3. Lint and auto-fix
mise exec -- ruff check --fix

# 4. Format code
mise exec -- ruff format
```

Or run all at once:

```bash
mise exec -- pytest && \
mise exec -- ty check && \
mise exec -- ruff check --fix && \
mise exec -- ruff format
```

## Continuous Integration

The CI pipeline runs:

1. `mise exec -- pytest` - All tests must pass
2. `mise exec -- ty check` - No type errors allowed
3. `mise exec -- ruff check` - No linting errors allowed
4. `mise exec -- ruff format --check` - Code must be formatted

Match these locally before pushing.

## Test Count Tracking

The project currently has **104 tests** (as of monorepo implementation
completion).

When adding features:

- Add tests for new functionality
- Update test count in commit messages if significant
- Aim for high coverage (current: >90%)

## Debugging Failed Tests

### View Full Output

```bash
mise exec -- pytest -vv
```

### Stop on First Failure

```bash
mise exec -- pytest -x
```

### Re-run Failed Tests

```bash
mise exec -- pytest --lf
```

### Debug with Print Statements

```python
def test_something():
    result = compute_version(...)
    print(f"DEBUG: result = {result}")  # Will show in pytest output
    assert result == "1.2.3"
```

### Use pytest Capture Control

```bash
# Show all output (disable capture)
mise exec -- pytest -s

# Show output only for failed tests (default)
mise exec -- pytest
```

## Common Test Patterns

See [Testing Practices](.//testing-practices.md) for detailed testing
conventions.
