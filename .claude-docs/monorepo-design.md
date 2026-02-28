# Monorepo Design & Architecture

This document describes the design and architecture of monorepo support in
Releez.

## Overview

Releez supports monorepos with multiple independently-versioned projects. Each
project has:

- Independent version number (e.g., `core-1.2.3`, `ui-4.5.6`)
- Separate changelog file
- Unique git tag prefix
- Independent release branches and PRs
- Custom hooks and settings

## Core Concepts

### SubProject

The fundamental abstraction for a monorepo project:

```python
@dataclass(frozen=True)
class SubProject:
    name: str                    # Unique identifier (e.g., "core")
    path: Path                   # Absolute path to project directory
    changelog_path: Path         # Absolute path to changelog file
    tag_prefix: str             # Tag prefix (e.g., "core-")
    tag_pattern: str            # Auto-generated regex pattern
    alias_versions: AliasVersions
    hooks: ReleezHooks
    include_paths: list[str]    # Additional paths to monitor
```

### Configuration

Projects are configured in the root `pyproject.toml` or `releez.toml`:

```toml
[tool.releez]
base-branch = "main"

[[tool.releez.projects]]
name = "core"
path = "packages/core"
changelog-path = "CHANGELOG.md"
tag-prefix = "core-"
include-paths = ["pyproject.toml", "uv.lock"]
```

## Architecture Decisions

### 1. Path-Based Change Detection

**Decision**: Use file paths, not commit scopes, to detect project changes.

**Why**:

- Works reliably with GitHub's squash-and-merge
- No dependency on commit message conventions
- More intuitive (changed files = changed project)

**Implementation**:

```python
def detect_changed_projects(
    *,
    repo: Repo,
    base_branch: str,
    projects: list[SubProject],
) -> list[SubProject]:
    """Detect projects with unreleased changes."""
    changed = []

    for project in projects:
        # Find latest tag for this project
        latest_tag = find_latest_tag_matching_pattern(repo, project.tag_pattern)

        # Get commits touching project's monitored paths
        if latest_tag:
            range_spec = f"{latest_tag}..{base_branch}"
        else:
            range_spec = base_branch

        # Check all paths this project monitors
        all_paths = [str(project.path)] + project.include_paths
        for path in all_paths:
            commits = repo.git.log(range_spec, '--format=%H', '--', path)
            if commits:
                changed.append(project)
                break

    return changed
```

**Monitored Paths**:

- Primary: `project.path` (e.g., `packages/core`)
- Additional: `project.include_paths` (e.g., `["pyproject.toml", "uv.lock"]`)

### 2. Tag Patterns

**Decision**: Use prefixed tags with regex patterns.

**Format**: `{tag_prefix}{version}`

**Examples**:

- Core: `core-1.2.3`, `core-v1`, `core-v1.2`
- UI: `ui-4.5.6`, `ui-v4`, `ui-v4.5`

**Pattern Generation**:

```python
def generate_tag_pattern(tag_prefix: str) -> str:
    """Generate regex pattern for prefixed tags.

    Examples:
        "core-" → "^core-([0-9]+\\.[0-9]+\\.[0-9]+)$"
        "ui-"   → "^ui-([0-9]+\\.[0-9]+\\.[0-9]+)$"
    """
    return f'^{tag_prefix}([0-9]+\\.[0-9]+\\.[0-9]+)$'
```

**Benefits**:

- No tag collisions between projects
- Each project can have same version independently
- Works with git-cliff's `--tag-pattern` flag

### 3. Topology-Aware Tag Finding

**Problem**: Tags created rapidly can have same timestamp, breaking date-based
sorting.

**Solution**: Walk commit graph from HEAD backwards.

```python
def find_latest_tag_matching_pattern(
    repo: Repo,
    pattern: str,
) -> str | None:
    """Find the most recent tag matching a pattern.

    Uses commit topology instead of timestamps for reliability.
    """
    pattern_re = re.compile(pattern)

    # Build map: commit SHA → tags
    commit_to_tags: dict[str, list[str]] = {}
    for tag in repo.tags:
        if pattern_re.match(tag.name):
            commit_sha = tag.commit.hexsha
            commit_to_tags.setdefault(commit_sha, []).append(tag.name)

    # Walk commits from HEAD backwards
    for commit in repo.iter_commits():
        if commit.hexsha in commit_to_tags:
            return commit_to_tags[commit.hexsha][0]

    return None
```

**Why topology over timestamps**:

- More reliable when tags created in quick succession
- Respects git history order
- Avoids clock skew issues

### 4. Selective Git Staging

**Decision**: Only stage files in the project being released.

**Single repo**:

```python
repo.git.add('-A')  # Stage everything
```

**Monorepo**:

```python
if release_input.project_path:
    # Only stage project directory
    repo.git.add(str(rel_project_path))
else:
    # Single repo: stage all
    repo.git.add('-A')
```

**Benefits**:

- Multiple release branches can coexist
- Each release only modifies its project's files
- Clean commit history per project

### 5. git-cliff Integration

**Decision**: Extend git-cliff with project-specific filtering.

**Parameters added**:

- `tag_pattern: str | None` - Filter to project's tags
- `include_paths: list[str] | None` - Filter to project's files

**Example git-cliff command**:

```bash
git-cliff \
  --unreleased \
  --bumped-version \
  --tag-pattern '^core-([0-9]+\.[0-9]+\.[0-9]+)$' \
  --include-path 'packages/core/**' \
  --include-path 'pyproject.toml' \
  --bump
```

**Implementation**:

```python
class GitCliff:
    def compute_next_version(
        self,
        *,
        bump: GitCliffBump,
        tag_pattern: str | None = None,
        include_paths: list[str] | None = None,
    ) -> str:
        cmd = [
            *self._cmd,
            '--unreleased',
            '--bumped-version',
            '--tag-pattern', tag_pattern or GIT_CLIFF_TAG_PATTERN,
            *_bump_args(bump),
        ]
        if include_paths:
            for path in include_paths:
                cmd.extend(['--include-path', path])

        return subprocess.check_output(cmd).decode().strip()
```

## Data Flow

### Release Start Workflow

```
1. User runs: releez release start

2. Load configuration
   ├─ Read pyproject.toml/releez.toml
   ├─ Parse [[tool.releez.projects]]
   └─ Create SubProject instances

3. Detect changed projects
   ├─ For each project:
   │  ├─ Find latest tag matching tag_pattern
   │  ├─ Get commits since tag touching project paths
   │  └─ Mark as changed if commits exist
   └─ Return list of changed projects

4. For each changed project:
   ├─ Compute next version
   │  └─ git-cliff --tag-pattern <pattern> --include-path <path>
   ├─ Generate release notes
   │  └─ git-cliff --unreleased --tag-pattern <pattern> --include-path <path>
   ├─ Create release branch
   │  └─ release/<tag-prefix><version>
   ├─ Update changelog
   ├─ Run post-changelog hooks
   ├─ Stage changes
   │  └─ git add <project-path>
   ├─ Commit
   │  └─ "chore(release): <tag-prefix><version>"
   ├─ Push branch
   └─ Create PR
      └─ Labels: ["release", "release:<project-name>"]

5. Report results
   └─ Show success/failure for each project
```

### Change Detection Flow

```
releez projects changed

1. Load configuration
   └─ Get list of SubProject instances

2. For each project:
   ├─ Find latest tag (topology-aware)
   ├─ Build commit range
   │  ├─ If tag exists: <tag>..HEAD
   │  └─ If no tag: HEAD (all commits)
   ├─ Check primary path
   │  └─ git log <range> -- <project.path>
   └─ Check include_paths
      └─ git log <range> -- <include_path>

3. Collect changed projects

4. Output results
   ├─ Text: "Changed projects: core, ui"
   └─ JSON: {"projects": ["core", "ui"], "include": [...]}
```

## File Structure

### New Files

- `src/releez/subproject.py` - SubProject dataclass and validation
- `tests/unit/core/test_subproject.py` - SubProject tests (18 tests)
- `tests/unit/core/test_git_repo_monorepo.py` - Change detection tests (10
  tests)
- `tests/unit/core/test_cliff_monorepo.py` - git-cliff integration tests (5
  tests)
- `tests/integration/test_monorepo_workflow.py` - End-to-end tests (3 tests)

### Modified Files

- `src/releez/settings.py` - Added `ProjectConfig` and `projects` field
- `src/releez/version_tags.py` - Added `tag_prefix` parameter
- `src/releez/git_repo.py` - Added change detection functions
- `src/releez/cliff.py` - Extended all methods with monorepo parameters
- `src/releez/release.py` - Added project context to `StartReleaseInput`
- `src/releez/cli.py` - Added `projects` subcommand group

## Validation Rules

### Project Validation

When loading `[[tool.releez.projects]]`:

1. **No duplicate names**: Each project must have unique name
2. **No duplicate prefixes**: Each tag_prefix must be unique
3. **Paths exist**: All paths must exist in repository
4. **Paths within repo**: All paths must be under repo root
5. **No overlapping paths**: Primary paths cannot overlap (include_paths can)
6. **Changelog writable**: Changelog parent directory must exist

### Tag Pattern Validation

Tag prefixes can only contain:

- Alphanumeric characters
- Dash (`-`)
- Underscore (`_`)
- Forward slash (`/`)

Invalid characters raise `ValueError` at configuration load time.

## Backwards Compatibility

### Single-Repo Mode

If no `[[tool.releez.projects]]` configured:

- Uses existing single-repo workflow
- All behavior unchanged
- No migration required

### Empty Tag Prefix

For gradual migration:

```toml
[[tool.releez.projects]]
name = "main"
path = "."
tag-prefix = "" # No prefix - backwards compatible
```

This maintains existing tag format while gaining monorepo infrastructure.

### Default Values

All new parameters have safe defaults:

- `tag_prefix = ""`
- `include_paths = []`
- `projects = []`

## Edge Cases

### Root File Changes

**Scenario**: Root `pyproject.toml` changes.

**Behavior**:

- Projects without `include-paths = ["pyproject.toml"]` are NOT triggered
- Projects with `include-paths = ["pyproject.toml"]` ARE triggered

**Why**: Explicit opt-in gives users control over when root changes trigger
releases.

### Multiple Projects Changed

**Scenario**: Commit touches both `packages/core` and `packages/ui`.

**Behavior**:

- Both projects detected as changed
- Two release branches created: `release/core-1.2.3` and `release/ui-4.5.6`
- Two PRs created

### No Tags Yet (Bootstrap)

**Scenario**: First release of a project (no tags exist).

**Behavior**:

- `find_latest_tag_matching_pattern()` returns `None`
- Change detection compares against entire `base_branch` history
- First release includes all commits touching project

### Same Version Across Projects

**Scenario**: Both `core` and `ui` are at version `1.0.0`.

**Behavior**:

- Tags: `core-1.0.0` and `ui-1.0.0` (no collision)
- Each project tracks its own tags independently
- No conflicts

## Testing Strategy

### Unit Tests (65 tests)

Test individual components in isolation:

- SubProject validation
- Tag pattern generation
- Change detection logic
- git-cliff parameter passing

### Integration Tests (3 tests)

Test end-to-end workflows:

- Multi-project change detection
- Full release workflow
- Include paths handling

### Test Patterns

```python
# Use HEAD instead of branch names
detect_changed_projects(repo=repo, base_branch='HEAD', projects=[...])

# Valid TOML in tests
(tmp_path / 'pyproject.toml').write_text(
    '[tool.releez]\nbase-branch = "main"'
)

# Change directory for git operations
monkeypatch.chdir(tmp_path)
```

## Performance Considerations

### Change Detection

**Optimization**: Early exit when first changed path found.

```python
for path in all_paths:
    commits = repo.git.log(range_spec, '--format=%H', '--', path)
    if commits:
        changed.append(project)
        break  # Don't check remaining paths
```

### Tag Finding

**Optimization**: Build commit→tags map once, then walk commits.

```python
# O(tags) to build map
commit_to_tags = {}
for tag in repo.tags:
    if pattern_re.match(tag.name):
        commit_to_tags.setdefault(tag.commit.hexsha, []).append(tag.name)

# O(commits) until first match
for commit in repo.iter_commits():
    if commit.hexsha in commit_to_tags:
        return commit_to_tags[commit.hexsha][0]
```

## Future Enhancements

Not implemented, but considered in design:

1. **Dependency tracking**: Auto-detect when Project A depends on Project B
2. **Cascading releases**: Automatically bump dependent projects
3. **Parallel releases**: Release multiple projects concurrently
4. **Custom tag patterns**: Allow users to override default pattern
5. **Shared changelogs**: Option for single changelog with project sections

These remain unimplemented until user demand justifies complexity.
