# Code Style Guide

This document outlines Python code style conventions for the Releez project.

## Python Version

**Require Python 3.11+** for modern features:

```python
# ✅ Modern type hints (Python 3.11+)
def function(value: str | None) -> list[str]:
    ...

# ❌ Old style (Python 3.9)
from typing import Optional, List

def function(value: Optional[str]) -> List[str]:
    ...
```

## Imports

### Order

1. `from __future__ import annotations` (always first)
2. Standard library
3. Third-party packages
4. Local imports
5. TYPE_CHECKING block

```python
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from git import Repo
from pydantic import Field

from releez.errors import ReleezError
from releez.settings import ReleezSettings

if TYPE_CHECKING:
    import pytest
```

### TYPE_CHECKING

Use for type-only imports to avoid circular dependencies:

```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    import pytest
    from pytest_mock import MockerFixture

def test_something(tmp_path: Path, mocker: MockerFixture) -> None:
    ...
```

### ❌ No Local Imports

**Always import at module level, never inside functions.**

```python
# ❌ BAD - local import inside function
def test_something(tmp_path: Path) -> None:
    from releez.settings import ReleezSettings  # WRONG!
    settings = ReleezSettings()
    ...

# ✅ GOOD - import at module level
from releez.settings import ReleezSettings

def test_something(tmp_path: Path) -> None:
    settings = ReleezSettings()
    ...
```

**Why avoid local imports**:

- Harder to see dependencies at a glance
- Can hide import errors until runtime
- Slower (imports happen repeatedly instead of once)
- Against Python conventions (PEP 8)
- Makes code reviews harder

**Only exception**: Avoiding circular imports (use TYPE_CHECKING instead)

## Type Hints

### Required

All functions must have type hints:

```python
# ✅ Good
def compute_version(input: ArtifactVersionInput) -> str:
    return input.version

# ❌ Bad - missing type hints
def compute_version(input):
    return input.version
```

### Modern Syntax

Use Python 3.11+ style:

```python
# ✅ Good (3.11+)
def function(value: str | None) -> list[str]:
    ...

# ❌ Bad (old style)
from typing import Optional, List

def function(value: Optional[str]) -> List[str]:
    ...
```

### Annotate Variables

When type is not obvious:

```python
# ✅ Good
result: dict[str, list[str]] = {}
for scheme in ArtifactVersionScheme:
    result[scheme] = compute_versions(scheme)

# ❌ Acceptable but less clear
result = {}
for scheme in ArtifactVersionScheme:
    result[scheme] = compute_versions(scheme)
```

## Data Classes

### Use Frozen Dataclasses

For immutable data structures:

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class DetectedRelease:
    """Information parsed from a release branch name."""

    version: str
    project_name: str | None
    branch_name: str
```

**Why frozen=True**:

- Immutability prevents bugs
- Can be used as dict keys
- Thread-safe
- Clear intent (this is data, not mutable state)

### When to Use Dataclasses

```python
# ✅ Use dataclass for structured data
@dataclass(frozen=True)
class ReleaseInput:
    version: str
    branch: str
    remote: str

# ✅ Use dict for dynamic/flexible data
metadata: dict[str, str] = {
    'version': '1.2.3',
    'commit': 'abc123',
}
```

## Pydantic Models

### For Configuration

Use Pydantic for all configuration:

```python
from pydantic import BaseModel, Field

class ProjectConfig(BaseModel):
    """Configuration for a monorepo project."""

    name: str
    path: str
    changelog_path: str = Field(alias='changelog-path')
    tag_prefix: str = Field(default='', alias='tag-prefix')

    class Config:
        extra = 'forbid'  # Reject unknown fields
```

**Why Pydantic**:

- Automatic validation
- Type coercion
- Clear error messages
- Alias support (snake_case ↔ kebab-case)

## Enums

### Use StrEnum

For string constants:

```python
from enum import StrEnum

class PrereleaseType(StrEnum):
    """Supported prerelease types."""

    alpha = 'alpha'
    beta = 'beta'
    rc = 'rc'
```

**Benefits**:

- Type-safe
- Auto-complete in IDE
- Prevents typos
- Can iterate over all values

## Errors

### Custom Exceptions

Create specific exception types:

```python
class ReleezError(Exception):
    """Base exception for releez errors."""

class BuildNumberRequiredError(ReleezError):
    """Build number is required for prerelease builds."""

# Usage
if build_number is None:
    raise BuildNumberRequiredError
```

**Why**:

- Users can catch specific errors
- Self-documenting
- Consistent error handling

### Error Messages

Make them helpful:

```python
# ✅ Good - specific and actionable
raise ValueError(
    f"Invalid tag prefix '{tag_prefix}'. "
    f"Only alphanumeric, dash, underscore, and slash allowed."
)

# ❌ Bad - vague
raise ValueError("Invalid prefix")
```

## Functions

### Keep Functions Small

Target: ≤10 lines of logic (excluding docstrings)

```python
# ✅ Good - small, focused
def detect_release_from_branch(
    *,
    branch_name: str,
    projects: list[SubProject],
) -> DetectedRelease | None:
    """Detect release information from a branch name."""
    if not branch_name.startswith('release/'):
        return None

    version_with_prefix = branch_name.removeprefix('release/')
    project_name = _find_matching_project(version_with_prefix, projects)

    return DetectedRelease(
        version=version_with_prefix,
        project_name=project_name,
        branch_name=branch_name,
    )

# Helper extracted
def _find_matching_project(
    version_with_prefix: str,
    projects: list[SubProject],
) -> str | None:
    """Find project matching version prefix."""
    for project in projects:
        if version_with_prefix.startswith(project.tag_prefix):
            return project.name
    return None
```

### Cyclomatic Complexity

**Maximum: 10** (enforced by ruff)

If complexity too high, extract helper functions:

```python
# ❌ Bad - complexity too high
def complex_function(x, y, z):
    if x:
        if y:
            if z:
                # ... many nested conditions
                pass

# ✅ Good - extracted helpers
def complex_function(x, y, z):
    if _should_process(x, y):
        _process_data(z)

def _should_process(x, y):
    return x and y

def _process_data(z):
    # ... process logic
```

### Function Parameters

**Maximum: 5 arguments** (enforced by ruff)

If more needed, use dataclass or add `# noqa: PLR0913`:

```python
# ❌ Bad - too many parameters
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

# ✅ Acceptable - with noqa if truly needed
def emit_all_versions(  # noqa: PLR0913
    version: str,
    is_full_release: bool,
    prerelease_type: PrereleaseType,
    prerelease_number: int | None,
    build_number: int | None,
    alias_versions: AliasVersions,
) -> None:
    """Emit versions for all schemes."""
    pass
```

### Keyword-Only Arguments

Use for clarity:

```python
# ✅ Good - keyword-only (note the *)
def detect_changed_projects(
    *,
    repo: Repo,
    base_branch: str,
    projects: list[SubProject],
) -> list[SubProject]:
    """Detect projects with unreleased changes."""
    ...

# Must call with keywords
detect_changed_projects(repo=repo, base_branch='main', projects=[...])

# ❌ Positional arguments hard to read
detect_changed_projects(repo, 'main', [...])
```

## Naming Conventions

### Functions and Variables

```python
# snake_case
def compute_next_version() -> str:
    ...

latest_tag = find_latest_tag(...)
```

### Classes

```python
# PascalCase
class SubProject:
    ...

class ReleezSettings:
    ...
```

### Constants

```python
# SCREAMING_SNAKE_CASE
DEFAULT_BRANCH = 'main'
MAX_COMPLEXITY = 10
```

### Private Functions

```python
# Leading underscore
def _internal_helper() -> str:
    """Private helper function."""
    ...
```

Use for:

- Helper functions not part of public API
- Functions that reduce complexity
- Implementation details

## Docstrings

### Module Docstrings

```python
"""Git repository operations and change detection."""
```

### Function Docstrings

Use for public API:

```python
def detect_release_from_branch(
    *,
    branch_name: str,
    projects: list[SubProject],
) -> DetectedRelease | None:
    """Detect release information from a branch name.

    Parses branch names like:
    - Single repo: "release/1.2.3"
    - Monorepo: "release/core-1.2.3"

    Args:
        branch_name: Git branch name to parse
        projects: List of configured projects (empty for single-repo)

    Returns:
        DetectedRelease if branch is a release branch, None otherwise
    """
    ...
```

### Class Docstrings

```python
@dataclass(frozen=True)
class DetectedRelease:
    """Information parsed from a release branch name.

    Attributes:
        version: Version string (e.g., "1.2.3" or "core-1.2.3")
        project_name: Project name for monorepo, None for single-repo
        branch_name: Full branch name (e.g., "release/core-1.2.3")
    """

    version: str
    project_name: str | None
    branch_name: str
```

## Comments

### When to Add Inline Comments

Add a comment **wherever the logic is not immediately obvious**. The rule of
thumb: if you had to think for more than a second about _why_ the code does what
it does, add a comment explaining the reason.

Common triggers:

- A non-obvious algorithmic choice (e.g., topology walk vs. date sort)
- A constraint imposed by an external system (e.g., Docker tag format)
- A fallback or defensive branch that handles edge cases
- A suppressed warning or linting directive

```python
# ✅ Good - explains WHY topology over date
# More reliable than date-based sorting when tags are created in rapid succession
for commit in repo.iter_commits():
    ...

# ✅ Good - explains external format constraint
# semver uses + as build separator; docker uses - (+ is not valid in image tags)
if scheme == ArtifactVersionScheme.semver:
    return f'{version}-{pre}+{build}'

# ✅ Good - explains non-obvious fallback
# Fall back to PATH lookup if not found in scripts dir
if shutil.which(GIT_CLIFF_BIN):
    return [GIT_CLIFF_BIN]

# ✅ Good - explains suppressed lint
# noqa: PLR0913 - All parameters required for git-cliff command
def emit_all_versions(...):
    ...

# ✅ Good - explains data structure key convention
# include key matches GitHub Actions matrix strategy format
output = {'projects': [...], 'include': [...]}

# ❌ Bad - restates what the code already says
# Loop through projects
for project in projects:
    ...

# ❌ Bad - redundant
x = x + 1  # Increment x
```

### Inline vs. Above-line Comments

```python
# ✅ Good - above-line for multi-word explanation
# On Windows, try platform-specific extensions before the bare name
candidates = ['git-cliff.exe', 'git-cliff.cmd', 'git-cliff']

# ✅ Good - end-of-line for very short clarifications
hosts.add(raw.strip().rstrip('/'))  # allow plain host values (not URLs)
```

## String Formatting

### Use f-strings

```python
# ✅ Good
message = f"Releasing {project.name} version {version}"

# ❌ Bad
message = "Releasing %s version %s" % (project.name, version)
message = "Releasing {} version {}".format(project.name, version)
```

### Multi-line Strings

```python
# ✅ Good - triple quotes for multi-line
error_message = """
Invalid configuration detected:
  - Project paths cannot overlap
  - Each tag prefix must be unique
"""

# ✅ Good - parentheses for concatenation
message = (
    f"Detected {len(projects)} changed projects: "
    f"{', '.join(p.name for p in projects)}"
)
```

## Boolean Expressions

### Explicit is Better

```python
# ✅ Good
if value is None:
    ...

if len(items) == 0:
    ...

if result is not None:
    ...

# ❌ Less clear
if not value:  # Could be None, empty string, 0, False...
    ...

if not items:  # Empty list or None?
    ...
```

### Guard Clauses

Prefer early returns:

```python
# ✅ Good
def function(value: str | None) -> str:
    if value is None:
        return ""

    if not value.startswith("prefix"):
        return value

    # Main logic here
    return process(value)

# ❌ Bad - nested
def function(value: str | None) -> str:
    if value is not None:
        if value.startswith("prefix"):
            return process(value)
        else:
            return value
    else:
        return ""
```

## File Organization

### Module Structure

```python
# 1. Module docstring
"""Git repository operations and change detection."""

# 2. from __future__ imports
from __future__ import annotations

# 3. Standard library imports
import re
from pathlib import Path

# 4. Third-party imports
from git import Repo

# 5. Local imports
from releez.errors import ReleezError

# 6. TYPE_CHECKING block
if TYPE_CHECKING:
    import pytest

# 7. Constants
DEFAULT_BRANCH = 'main'

# 8. Functions and classes
def function():
    ...

class MyClass:
    ...
```

## Line Length

**Maximum: 100 characters** (ruff default)

Break long lines:

```python
# ✅ Good
result = some_function(
    arg1=value1,
    arg2=value2,
    arg3=value3,
)

# ✅ Good
message = (
    f"This is a very long message that needs to be split "
    f"across multiple lines for readability"
)

# ❌ Bad - too long
result = some_function(arg1=value1, arg2=value2, arg3=value3, arg4=value4, arg5=value5)
```

## Best Practices

### Immutability

Prefer immutable data:

```python
# ✅ Good - frozen dataclass
@dataclass(frozen=True)
class Config:
    name: str
    value: int

# ✅ Good - tuple for fixed sequences
VALID_TYPES = ('alpha', 'beta', 'rc')

# ❌ Avoid - mutable default
def function(items: list[str] = []):  # Dangerous!
    items.append('new')
    return items

# ✅ Good - None default
def function(items: list[str] | None = None) -> list[str]:
    if items is None:
        items = []
    items.append('new')
    return items
```

### Context Managers

Use for resource management:

```python
# ✅ Good
with open(file_path) as f:
    content = f.read()

# ✅ Good - pathlib
content = Path(file_path).read_text()
```

### Path Handling

Use pathlib:

```python
from pathlib import Path

# ✅ Good
project_dir = Path('packages') / 'core'
changelog = project_dir / 'CHANGELOG.md'

if changelog.exists():
    content = changelog.read_text()

# ❌ Bad - string concatenation
import os

project_dir = os.path.join('packages', 'core')
changelog = os.path.join(project_dir, 'CHANGELOG.md')

if os.path.exists(changelog):
    with open(changelog) as f:
        content = f.read()
```

### List Comprehensions

Use when clear:

```python
# ✅ Good - simple transformation
names = [project.name for project in projects]

# ✅ Good - simple filter
changed = [p for p in projects if p.has_changes()]

# ❌ Bad - too complex
result = [
    process_project(p, config, settings)
    for p in projects
    if p.has_changes() and p.is_valid()
    and config.should_process(p.name)
]

# ✅ Better - use regular loop for complex logic
result = []
for project in projects:
    if project.has_changes() and project.is_valid():
        if config.should_process(project.name):
            result.append(process_project(project, config, settings))
```

## Anti-Patterns to Avoid

### Don't Use Wildcard Imports

```python
# ❌ Bad
from releez.git_repo import *

# ✅ Good
from releez.git_repo import open_repo, detect_release_from_branch
```

### Don't Mutate Function Arguments

```python
# ❌ Bad
def add_item(items: list[str], item: str) -> None:
    items.append(item)  # Mutates input!

# ✅ Good - return new list
def add_item(items: list[str], item: str) -> list[str]:
    return [*items, item]
```

### Don't Catch Broad Exceptions

```python
# ❌ Bad
try:
    result = risky_operation()
except Exception:  # Too broad!
    pass

# ✅ Good - catch specific exceptions
try:
    result = risky_operation()
except (ValueError, KeyError) as e:
    logger.error(f"Operation failed: {e}")
    raise
```

## Formatting

All formatting handled by ruff:

```bash
# Check formatting
mise exec -- ruff format --check

# Apply formatting
mise exec -- ruff format
```

Don't worry about manual formatting - ruff handles:

- Indentation
- Line breaks
- Quote style
- Trailing commas
- Import ordering
