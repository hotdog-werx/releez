# Design Principles

This document outlines the core design philosophy and principles for the Releez
project. Edit this file to reflect evolving design decisions.

## Core Philosophy

**Releez is a thin, opinionated wrapper around git-cliff that adds release
workflow automation.**

- Delegate versioning and changelog generation to git-cliff
- Add value through automation (branch creation, PRs, tagging)
- Support both single-repo and monorepo workflows
- Prioritize CLI/CI use cases over programmatic API

## Design Principles

### 1. Simplicity Over Features

**Don't add features that aren't clearly needed.**

- Only implement what users actually request
- Resist the urge to add "what if" features
- Keep configuration minimal and obvious
- Prefer convention over configuration

Examples:

- ✅ Auto-detect changed projects (user doesn't need to think about it)
- ❌ Complex project dependency graphs (add only when needed)

### 2. git-cliff is the Source of Truth

**Releez computes versions and changelogs through git-cliff.**

- Never implement custom version bumping logic
- Never parse git history directly (use git-cliff)
- Configuration lives in `cliff.toml` where possible
- Only add releez config for workflow concerns (not versioning)

Examples:

- ✅ Use `git-cliff --bumped-version` for next version
- ✅ Use `git-cliff --unreleased` for release notes
- ❌ Parse commits manually to compute version

### 3. Path-Based Over Scope-Based

**Use file paths to detect changes, not commit scopes.**

Why:

- Works reliably with GitHub's squash-and-merge
- No dependency on commit message conventions
- More intuitive for users (changed files = changed project)

Examples:

- ✅ `git log release/1.0.0..HEAD -- packages/core`
- ❌ `git log --grep="^feat(core):"`

### 4. Explicit Configuration

**Make configuration discoverable and type-safe.**

- Use Pydantic for all configuration models
- Validate at load time, not runtime
- Provide clear error messages
- Support both TOML and environment variables

Examples:

- ✅ `[[tool.releez.projects]]` - discoverable in TOML
- ✅ Pydantic validation with helpful error messages
- ❌ Hidden "magic" configuration

### 5. Monorepo as First-Class

**Monorepo support shouldn't be an afterthought.**

- Single-repo mode is just "monorepo with one project"
- All features should work in both modes
- Project prefixes prevent collisions
- Independent versioning by default

Examples:

- ✅ All CLI commands accept `--project` flag
- ✅ Tags use prefixes: `core-1.2.3`, `ui-4.5.6`
- ❌ Special-case code for single-repo mode

### 6. Composable CLI

**CLI commands should compose well with scripts and CI.**

- JSON output for machine consumption
- Exit codes: 0 = success, 1 = error
- Minimal required arguments
- Sensible defaults

Examples:

- ✅ `releez projects changed --format json`
- ✅ `releez release detect-from-branch` (uses current branch)
- ❌ Interactive prompts (breaks CI)

### 7. Safe by Default

**Make the safe choice the default.**

- Don't create PRs without explicit permission
- Don't force-push unless explicitly requested
- Validate before destructive operations
- Fail fast on configuration errors

Examples:

- ✅ `create_pr = false` by default (opt-in)
- ✅ Validate tag doesn't exist before creating
- ❌ Automatically force-push to remote

### 8. Testable Code

**Write code that's easy to test.**

- Extract pure functions where possible
- Use dependency injection (pass repos, not create them)
- Mock external dependencies (git, GitHub API)
- Keep functions focused (low cyclomatic complexity)

Examples:

- ✅ `detect_release_from_branch(branch_name, projects)` - pure function
- ✅ `open_repo()` returns repo object for injection
- ❌ Functions that create repos internally

### 9. Progressive Disclosure

**Start simple, reveal complexity as needed.**

- Basic workflow requires minimal configuration
- Advanced features are opt-in
- Documentation starts with quick-start
- Error messages guide users to solutions

Examples:

- ✅ Monorepo: `[[tool.releez.projects]]` is all you need to start
- ✅ `include-paths` is optional (only for advanced cases)
- ❌ Require full configuration upfront

### 10. Backwards Compatibility

**Don't break existing users.**

- New features are additive
- Configuration migrations are gradual
- Deprecate before removing
- Test existing workflows

Examples:

- ✅ Empty `projects = []` maintains single-repo behavior
- ✅ Empty `tag-prefix = ""` for backward-compatible tags
- ❌ Changing existing CLI flag behavior

## Technical Decisions

### Python Version

**Require Python 3.11+**

Why:

- Modern type hints (`str | None`, no `from typing import Union`)
- Better error messages
- Performance improvements
- `tomllib` in standard library

### Type Hints

**All functions must have type hints.**

Why:

- Catches bugs at type-check time
- Self-documenting code
- Better IDE support
- Enforced by CI

### Dataclasses Over Dictionaries

**Use frozen dataclasses for data structures.**

```python
# ✅ Good
@dataclass(frozen=True)
class DetectedRelease:
    version: str
    project_name: str | None
    branch_name: str

# ❌ Bad
detected = {
    'version': '1.2.3',
    'project_name': 'core',
    'branch_name': 'release/core-1.2.3',
}
```

Why:

- Type-safe
- Immutable by default (frozen=True)
- Clear structure
- Better IDE autocomplete

### Pydantic for Configuration

**Use Pydantic models for all configuration.**

Why:

- Automatic validation
- Type coercion
- Clear error messages
- Support for aliases (snake_case ↔ kebab-case)

### Error Handling

**Use custom exceptions with clear messages.**

```python
# ✅ Good
class BuildNumberRequiredError(ReleezError):
    """Build number is required for prerelease builds."""

# Usage
if build_number is None:
    raise BuildNumberRequiredError

# ❌ Bad
if build_number is None:
    raise ValueError("Build number required")
```

Why:

- Users can catch specific errors
- Clear, consistent error messages
- Easier to document

## Anti-Patterns

### ❌ Don't: Magic Strings

```python
# ❌ Bad
if mode == "alpha":
    ...

# ✅ Good
class PrereleaseType(StrEnum):
    alpha = "alpha"
    beta = "beta"
    rc = "rc"

if prerelease_type == PrereleaseType.alpha:
    ...
```

### ❌ Don't: Mutable Defaults

```python
# ❌ Bad
def function(items: list[str] = []):
    ...

# ✅ Good
def function(items: list[str] | None = None):
    if items is None:
        items = []
```

### ❌ Don't: Over-Engineering

```python
# ❌ Bad - unnecessary abstraction
class ReleaseStrategy(ABC):
    @abstractmethod
    def execute(self) -> None: ...

class SingleRepoStrategy(ReleaseStrategy):
    def execute(self) -> None: ...

class MonorepoStrategy(ReleaseStrategy):
    def execute(self) -> None: ...

# ✅ Good - simple conditional
def start_release(projects: list[SubProject]) -> None:
    if not projects:
        _start_single_repo_release()
    else:
        _start_monorepo_release(projects)
```

### ❌ Don't: Hidden Coupling

```python
# ❌ Bad - function reaches into global state
def create_release():
    repo, info = open_repo()  # Hidden dependency
    settings = load_settings()  # Hidden dependency
    ...

# ✅ Good - explicit dependencies
def create_release(
    repo: Repo,
    info: RepoInfo,
    settings: ReleezSettings,
) -> None:
    ...
```

## Evolution Strategy

### Adding New Features

1. **Validate need**: Is this solving a real user problem?
2. **Design**: How does it fit with existing features?
3. **Configuration**: What new config is needed?
4. **Backwards compatibility**: Will it break existing users?
5. **Tests**: Add comprehensive tests
6. **Documentation**: Update user-facing docs

### Refactoring

1. **Keep tests passing**: Refactor with green tests
2. **One change at a time**: Don't refactor + add features
3. **Extract before abstracting**: Wait for 3+ examples before abstracting
4. **Measure complexity**: Keep cyclomatic complexity ≤10

### Deprecation Process

1. **Mark as deprecated**: Add warning in next minor version
2. **Document migration**: Provide clear upgrade path
3. **Remove in major version**: Follow semantic versioning

## Code Review Checklist

Before considering code complete:

- [ ] All functions have type hints
- [ ] Tests added for new functionality
- [ ] Documentation updated (if user-facing)
- [ ] No regressions (all existing tests pass)
- [ ] Cyclomatic complexity ≤10
- [ ] Code formatted with ruff
- [ ] Type checking passes
- [ ] No linting errors

## Questions for Design Decisions

When making design choices, ask:

1. **Is this the simplest solution?**
2. **Does this delegate to git-cliff where possible?**
3. **Is this backwards compatible?**
4. **Can this be tested easily?**
5. **Is the configuration obvious?**
6. **Does this work in both single-repo and monorepo?**
7. **Will this be clear to users in 6 months?**

## Future Considerations

Areas for potential evolution (not commitments):

- **Dependency management**: Auto-bump dependent projects in monorepo
- **Release orchestration**: Coordinate releases across projects
- **Changelog customization**: Per-project changelog templates
- **GitHub Apps integration**: Better automation without token management
- **Validation rules**: Pre-release checks and policies

Remember: Add these only when users request them, not preemptively.
