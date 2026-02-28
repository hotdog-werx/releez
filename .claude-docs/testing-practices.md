# Testing Practices

This document outlines testing conventions and patterns used in the Releez
project.

## General Principles

1. **Use pytest_mock**, not unittest.mock directly
2. **Use fixtures** for common test setup
3. **Test file organization** mirrors source structure
4. **One test file per source file** (e.g., `test_git_repo.py` for
   `git_repo.py`)
5. **Descriptive test names** that explain what is being tested

## Mock Framework

### ✅ DO: Use pytest_mock

```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

def test_something(mocker: MockerFixture) -> None:
    mock_func = mocker.patch('releez.git_repo.open_repo')
    mock_func.return_value = (mock_repo, mock_info)
    # ... test code
```

### ❌ DON'T: Use unittest.mock directly

```python
# ❌ Bad - don't do this
from unittest.mock import patch

def test_something():
    with patch('releez.git_repo.open_repo') as mock_func:
        # ...
```

**Why?** pytest_mock integrates better with pytest, automatically cleans up
mocks, and provides better error messages.

## Test File Structure

### Imports

```python
from __future__ import annotations

import json
from typing import TYPE_CHECKING

from typer.testing import CliRunner

from releez import cli
from releez.git_repo import DetectedRelease

if TYPE_CHECKING:
    from pathlib import Path

    import pytest
    from pytest_mock import MockerFixture
```

**Pattern**:

1. `from __future__ import annotations` first
2. Standard library imports
3. Third-party imports (Typer, pytest, etc.)
4. Local imports (releez modules)
5. TYPE_CHECKING block for type-only imports

### Test Function Naming

```python
# Pattern: test_<function_name>_<scenario>

def test_detect_release_from_branch_single_repo() -> None:
    """Test detecting release from single-repo branch."""
    ...

def test_detect_release_from_branch_monorepo_with_prefix() -> None:
    """Test detecting release from monorepo branch with tag prefix."""
    ...

def test_cli_version_artifact_outputs_all_schemes_as_json() -> None:
    """Test JSON output when --scheme is not provided."""
    ...
```

**Convention**:

- Start with `test_`
- Include function/feature being tested
- Describe the specific scenario
- Add docstring for complex tests

## Common Test Patterns

### Testing CLI Commands

```python
from typer.testing import CliRunner

from releez import cli

def test_cli_command(mocker: MockerFixture) -> None:
    runner = CliRunner()

    # Mock dependencies
    mocker.patch('releez.cli.ReleezSettings', return_value=mock_settings)
    mocker.patch('releez.cli.detect_release_from_branch', return_value=mock_result)

    # Invoke CLI
    result = runner.invoke(
        cli.app,
        ['release', 'detect-from-branch', '--branch', 'release/1.2.3'],
    )

    # Assert results
    assert result.exit_code == 0
    output = json.loads(result.stdout)
    assert output['version'] == '1.2.3'
```

**Key points**:

- Use `CliRunner` from typer
- Mock external dependencies
- Check `result.exit_code`
- Parse JSON output if applicable
- Use `result.output` for combined stdout/stderr

### Testing Git Operations

```python
def test_git_operation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Change to temp directory for git operations
    monkeypatch.chdir(tmp_path)

    # Initialize git repo
    repo = Repo.init(tmp_path)

    # Create test data
    test_file = tmp_path / "test.txt"
    test_file.write_text("content")
    repo.index.add([str(test_file)])
    repo.index.commit("Initial commit")

    # Test your function
    result = your_function(repo)

    assert result == expected
```

**Key points**:

- Use `tmp_path` fixture for isolated file system
- Use `monkeypatch.chdir()` for git operations
- Use `base_branch='HEAD'` instead of 'master' to avoid branch issues

### Testing with SubProjects (Monorepo)

```python
from releez.settings import ReleezSettings
from releez.subproject import SubProject

def test_monorepo_feature(tmp_path: Path) -> None:
    # Create project directory structure
    project_dir = tmp_path / 'packages' / 'core'
    project_dir.mkdir(parents=True)

    # Create SubProject
    subproject = SubProject(
        name='core',
        path=project_dir,
        changelog_path=project_dir / 'CHANGELOG.md',
        tag_prefix='core-',
        tag_pattern=r'^core-([0-9]+\.[0-9]+\.[0-9]+)$',
        alias_versions=ReleezSettings().alias_versions,
        hooks=ReleezSettings().hooks,
        include_paths=[],
    )

    # Test with subproject
    result = your_function(projects=[subproject])

    assert result is not None
```

**Key points**:

- Create realistic directory structures
- Use `SubProject` dataclass directly in tests
- Provide all required fields
- Use `ReleezSettings()` for default values

### Mocking Functions with Side Effects

```python
def test_with_side_effect(mocker: MockerFixture) -> None:
    def _fake_compute(artifact_input: ArtifactVersionInput) -> str:
        # Validate inputs
        assert artifact_input.scheme == ArtifactVersionScheme.semver
        assert artifact_input.version_override == '1.2.3'
        # Return test result
        return '1.2.3-alpha123+456'

    mocker.patch(
        'releez.cli.compute_artifact_version',
        side_effect=_fake_compute,
    )

    # Run test that calls compute_artifact_version
    result = run_your_function()

    assert result == expected
```

**Key points**:

- Use `side_effect` to validate inputs
- Return different values based on inputs
- Useful for functions called multiple times with different args

### Testing Error Cases

```python
def test_error_handling(mocker: MockerFixture) -> None:
    runner = CliRunner()

    # Mock to return None (error condition)
    mocker.patch('releez.cli.detect_release_from_branch', return_value=None)

    result = runner.invoke(cli.app, ['release', 'detect-from-branch', '--branch', 'main'])

    # Expect non-zero exit code
    assert result.exit_code == 1

    # Check error message
    assert 'not a release branch' in result.output
```

**Key points**:

- Test both success and failure paths
- Verify exit codes (0 = success, 1 = error)
- Check error messages are helpful

## Fixtures

### Common pytest Fixtures

- `tmp_path` - Temporary directory (pathlib.Path)
- `monkeypatch` - Modify environment, paths, attributes
- `mocker` - Create mocks (from pytest_mock)

### Using monkeypatch

```python
def test_with_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    # Set environment variable
    monkeypatch.setenv('RELEEZ_GITHUB_TOKEN', 'test-token')

    # Change working directory
    monkeypatch.chdir('/tmp')

    # Mock attribute
    monkeypatch.setattr('sys.stdout', io.StringIO())
```

## Test Organization

### Unit Tests (`tests/unit/`)

Test individual functions in isolation:

```
tests/unit/
├── cli/
│   ├── test_cli_release_detect_from_branch.py
│   └── test_cli_version_artifact.py
└── core/
    ├── test_detect_release_from_branch.py
    ├── test_git_repo.py
    └── test_subproject.py
```

**Characteristics**:

- Fast execution
- Mock external dependencies
- Test one function at a time
- No real git operations (use mocks)

### Integration Tests (`tests/integration/`)

Test multiple components working together:

```
tests/integration/
├── test_monorepo_workflow.py
└── test_release_workflow.py
```

**Characteristics**:

- Slower execution
- Minimal mocking
- Test real workflows
- May use real git operations in tmp_path

## Coverage

### Target Coverage

- Overall: >90%
- New code: 100%
- Critical paths (release, versioning): 100%
- Modified lines in a PR: 100%
- Modified branches in a PR: 100%

### Running Coverage

```bash
mise exec -- pytest --cov=releez --cov-report=term-missing
```

### Codecov Patch Standard (Required)

For every PR, tests must cover all changed lines and changed branches in touched
files. Do not consider work complete until patch coverage is clean.

Run this before pushing:

```bash
# Same coverage command CI runs
mise exec -- poe check-coverage

# Generate Codecov upload artifact
mise exec -- uv run coverage xml
```

Inspect `coverage.xml` when Codecov reports misses to see exact `hits="0"`
lines.

### Checking Uncovered Lines

```bash
mise exec -- pytest --cov=releez --cov-report=html
open htmlcov/index.html
```

## Assertions

### Use Specific Assertions

```python
# ✅ Good - specific assertions
assert result.version == '1.2.3'
assert result.project_name == 'core'
assert len(projects) == 2

# ❌ Bad - too broad
assert result is not None
assert projects
```

### Test Data Structures

```python
# For dataclasses/objects
assert result == DetectedRelease(
    version='core-1.2.3',
    project_name='core',
    branch_name='release/core-1.2.3',
)

# For dicts
assert output == {
    'version': '1.2.3',
    'project': 'core',
    'branch': 'release/core-1.2.3',
}

# For lists
assert result == ['1.2.3', 'v1']
```

## Common Pitfalls

### ❌ CRITICAL: Local Imports Inside Functions

**This is a very common mistake - NEVER import inside functions.**

```python
# ❌ WRONG - import inside test function
def test_something(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from releez.settings import ReleezSettings  # NO! NO! NO!
    from releez.git_repo import open_repo  # WRONG!
    settings = ReleezSettings()
    ...

# ❌ WRONG - import inside any function
def process_data() -> None:
    from releez.cliff import GitCliff  # NEVER DO THIS!
    ...
```

### ✅ Correct: Always Import at Module Level

**ALL imports must be at the top of the file.**

```python
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from releez.git_repo import open_repo
from releez.settings import ReleezSettings

if TYPE_CHECKING:
    import pytest

def test_something(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = ReleezSettings()  # ✅ Good - imported at module level
    repo, _ = open_repo()  # ✅ Good - imported at module level
    ...
```

**Why this matters**:

- Harder to see dependencies
- Hides import errors until function is called
- Violates PEP 8 and Python conventions
- Makes linting (PLC0415) fail
- Slower performance

### ❌ Incorrect: Mixing stdout and stderr

```python
# ❌ Don't use mix_stderr (doesn't exist in typer)
runner = CliRunner(mix_stderr=False)
```

### ✅ Correct: Use result.output

```python
# ✅ Use result.output which combines stdout and stderr
runner = CliRunner()
result = runner.invoke(cli.app, [...])
assert 'error message' in result.output
```

### ❌ Incorrect: Unused function parameters

```python
def test_something(tmp_path: Path) -> None:  # ❌ tmp_path unused
    result = compute_version(...)
    assert result == '1.2.3'
```

### ✅ Correct: Remove unused parameters or use them

```python
# Option 1: Remove if not needed
def test_something() -> None:
    result = compute_version(...)
    assert result == '1.2.3'

# Option 2: Use underscore if required by test framework
def test_something(_tmp_path: Path) -> None:
    # Parameter exists for compatibility but not used
    result = compute_version(...)
    assert result == '1.2.3'
```

## Test Data

### Use Realistic Test Data

```python
# ✅ Good - realistic version
version = '1.2.3'

# ✅ Good - realistic tag prefix
tag_prefix = 'core-'

# ✅ Good - realistic branch name
branch_name = 'release/core-1.2.3'

# ❌ Bad - unrealistic
version = '999.999.999'
tag_prefix = 'x-y-z-'
```

### Use Constants for Common Values

```python
# At module level
TEST_VERSION = '1.2.3'
TEST_BRANCH = 'release/1.2.3'

def test_function() -> None:
    result = detect_release(TEST_BRANCH)
    assert result.version == TEST_VERSION
```

## Best Practices

1. **Test behavior, not implementation** - Focus on inputs/outputs, not internal
   details
2. **One assertion per test** (when possible) - Makes failures clear
3. **Setup, execute, assert** - Clear test structure
4. **Descriptive names** - Test name should explain what's being tested
5. **Keep tests simple** - Complex test code is hard to maintain
6. **Independent tests** - Tests shouldn't depend on each other
7. **Fast tests** - Mock slow operations (network, disk)

## Test Maintenance

- Update tests when refactoring
- Remove tests for removed features
- Keep test count in sync with features
- Review test coverage regularly
- Fix flaky tests immediately
