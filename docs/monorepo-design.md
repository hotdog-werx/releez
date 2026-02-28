# Monorepo Support for Releez - Implementation Plan

## Overview

Add monorepo support to releez, allowing independent versioning, changelogs, and
releases for multiple subprojects within a single repository.

## Design Decisions (User Confirmed)

1. **Configuration**: Root-only with `[[projects]]` array in
   pyproject.toml/releez.toml
2. **git-cliff config**: Single shared cliff.toml at root; tag patterns defined
   per-project in releez config
3. **Commit filtering**: Path-based (files changed) - more reliable than
   scope-based, works with GitHub squash-and-merge
4. **PR strategy**: One PR per subproject (separate branches)
5. **Workflow**: "Automagic" - detect changed projects automatically, no manual
   scoping required

## Architecture

### Configuration Schema

```toml
# Root pyproject.toml or releez.toml

[tool.releez]
# Global defaults (existing fields)
base-branch = "main"
git-remote = "origin"
create-pr = true
alias-versions = "none" # Global default

# Global hooks (apply to all projects)
[tool.releez.hooks]
post-changelog = [
  ["prettier", "--write", "{changelog}"],
]

# Monorepo configuration
[[tool.releez.projects]]
name = "core"
path = "packages/core" # Relative to repo root
changelog-path = "CHANGELOG.md" # Relative to project path (packages/core/CHANGELOG.md)
tag-prefix = "core-" # Creates tags: core-1.2.3, core-v1
alias-versions = "major" # Override global default
# Auto-generated tag pattern: ^core-([0-9]+\.[0-9]+\.[0-9]+)$

# Optional: additional paths to monitor (e.g., root dependencies)
include-paths = [
  "pyproject.toml", # Root pyproject.toml affects this project
  "uv.lock", # Lock file changes
]

# Per-project hooks (inline within project)
[[tool.releez.projects]]
name = "ui"
path = "packages/ui"
changelog-path = "CHANGELOG.md"
tag-prefix = "ui-"
alias-versions = "minor"
# UI doesn't include root files - only releases when UI code changes

# Hooks for ui project (inline table syntax)
[tool.releez.projects.ui.hooks]
post-changelog = [
  ["uv", "version", "{version}"], # Update version in pyproject.toml
]
```

**Note**: Per-project hooks use standard TOML table syntax, not array-of-tables.

### Core Concepts

**SubProject** - New data structure:

```python
@dataclass(frozen=True)
class SubProject:
    name: str
    path: Path  # Absolute path to project directory
    changelog_path: Path  # Absolute path to changelog
    tag_prefix: str  # e.g., "core-"
    tag_pattern: str  # Auto-generated regex: ^core-([0-9]+\.[0-9]+\.[0-9]+)$
    alias_versions: AliasVersions
    hooks: ReleezHooks  # Per-project hooks (merged with global)
    include_paths: list[str]  # Additional paths to monitor (e.g., ["pyproject.toml", "uv.lock"])

    @staticmethod
    def from_config(config: ProjectConfig, repo_root: Path, global_settings: ReleezSettings) -> SubProject:
        """Create SubProject from config with validation."""
        # Resolve paths relative to repo root
        # Generate tag pattern from prefix
        # Merge hooks with global hooks
        # Build include_paths: [project.path] + project.include_paths (optional)
        # Validate paths exist and are within repo
        pass
```

**Key behavior**:

- If NO `[[projects]]` defined → backwards compatible, treat entire repo as
  single project
- If `[[projects]]` defined → monorepo mode, each project is independent

### Commit-to-Project Mapping (Path-Based)

```python
def detect_changed_projects(
    *,
    repo: Repo,
    base_branch: str,
    projects: list[SubProject],
) -> list[SubProject]:
    """Detect which projects have unreleased changes.

    Returns:
        List of projects with unreleased changes
    """
    changed = []

    for project in projects:
        # Find latest tag for this project
        latest_tag = find_latest_tag_matching_pattern(repo, project.tag_pattern)

        # Get commits touching this project's paths (project.path + include_paths)
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
                break  # Found changes, no need to check other paths

    return changed
```

**Algorithm**:

1. For each project, find its latest tag matching `tag_pattern`
2. Get commits touching any of project's monitored paths:
   - Primary path: `project.path` (e.g., `packages/core`)
   - Additional paths: `project.include_paths` (e.g.,
     `["pyproject.toml", "uv.lock"]`)
3. If commits exist for ANY monitored path, mark project as changed

**Edge cases**:

- File changes multiple projects → belongs to all (commit appears in both)
- Project with `include_paths = ["pyproject.toml"]` → releases when root changes
- Project without `include_paths` → only releases when its own code changes
- No tags yet for project → compare all commits on base_branch (bootstrap case)

**Root file handling**: Solved via `include_paths`! No special logic needed.

### git-cliff Integration

**Extend GitCliff class** to support per-project filtering:

```python
class GitCliff:
    def compute_next_version(
        self,
        *,
        bump: GitCliffBump,
        tag_pattern: str | None = None,  # NEW
        include_paths: list[str] | None = None,  # NEW
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
        # ... run command
```

**Changes needed**:

- Add optional `tag_pattern` parameter to all GitCliff methods
- Add optional `include_paths` parameter for path filtering
- Pass `--include-path <pattern>` to git-cliff (supports globs like
  `packages/core/**`)

**Tag pattern generation**:

```python
def generate_tag_pattern(tag_prefix: str) -> str:
    """Generate regex pattern for prefixed tags.

    Args:
        tag_prefix: Prefix like "core-" or "ui-"

    Returns:
        Regex pattern like "^core-([0-9]+\.[0-9]+\.[0-9]+)$"

    Raises:
        ValueError: If tag_prefix contains invalid characters
    """
    # Validate prefix: only alphanumeric, dash, underscore, slash
    if tag_prefix and not re.match(r'^[a-zA-Z0-9_/-]*$', tag_prefix):
        raise ValueError(
            f"Invalid tag prefix '{tag_prefix}'. "
            f"Only alphanumeric, dash, underscore, and slash allowed."
        )

    # Don't escape - git-cliff expects raw regex
    # Test with actual git-cliff to verify this works
    return f'^{tag_prefix}([0-9]+\\.[0-9]+\\.[0-9]+)$'
```

**TODO**: Test git-cliff tag pattern behavior:

```bash
git tag core-1.0.0
git-cliff --tag-pattern '^core-([0-9]+\.[0-9]+\.[0-9]+)$' --unreleased
```

### Release Workflow Changes

**Current**: `releez release start` → single release

**New**: `releez release start` → detect changed projects → release each

```
releez release start [--projects core,ui] [--all] [--auto]

Flags:
  --projects <names>  Comma-separated project names to release
  --all               Release ALL projects (ignore change detection)
  --auto              Auto-detect changed projects (DEFAULT)
```

**Algorithm**:

1. Load config → detect if monorepo (has [[projects]]) or single project
2. If single project → use existing workflow (backwards compatible)
3. If monorepo: a. Detect changed projects (or use --projects/--all) b. For each
   changed project:
   - Compute next version (with project tag pattern + path filter)
   - Generate release notes (with project tag pattern + path filter)
   - Create release branch: `release/<tag-prefix><version>` (e.g.,
     `release/core-1.2.3`)
   - Update project's changelog
   - Run project's post-changelog hooks
   - Stage changes: `repo.index.add([str(project.path)])` + root config if
     modified
   - Commit: `chore(release): <tag-prefix><version>`
   - Push branch
   - Create PR (one per project) c. Return results for all projects

**Key changes**:

- Support multiple release branches simultaneously
- Selective staging (only project files + root config changes)
- Multiple PRs created in parallel
- Project-specific hooks run with project context

### PR Creation Changes

**Current**: Single PR with title `chore(release): 1.2.3`

**New**: Multiple PRs, one per subproject

```python
# For core project:
title = "chore(release): core-1.2.3"
branch = "release/core-1.2.3"
body = """
# Release core-1.2.3

<release notes for core project only>
"""
labels = ["release", "release:core"]

# For ui project:
title = "chore(release): ui-4.5.6"
branch = "release/ui-4.5.6"
body = """
# Release ui-4.5.6

<release notes for ui project only>
"""
labels = ["release", "release:ui"]
```

**Changes**:

- Create multiple PRs in parallel
- Project-specific labels: `release:<project-name>`
- Each PR only contains changes for that project

### Version Tags Changes

**Current**: Tags like `1.2.3`, `v1`, `v1.2`

**New**: Prefixed tags per project

```python
def compute_version_tags(
    *,
    version: str,
    tag_prefix: str = "",  # NEW
) -> VersionTags:
    normalized = version.strip().removeprefix('v')
    parsed = VersionInfo.parse(normalized)

    # With prefix "core-":
    exact = f"{tag_prefix}{normalized}"  # core-1.2.3
    major = f"{tag_prefix}v{parsed.major}"  # core-v1
    minor = f"{tag_prefix}v{parsed.major}.{parsed.minor}"  # core-v1.2

    return VersionTags(exact=exact, major=major, minor=minor)
```

**Tag collision prevention**:

- Each project has unique tag prefix → no collisions
- Multiple projects can have same version number (e.g., core-1.0.0 and ui-1.0.0)
- Existing repos without prefix continue to work (backwards compatible)

### Dependency Management Considerations

**Challenge**: packagea depends on packageb - when releasing packageb, should
packagea version be bumped?

**Solutions**:

1. **Manual** (Phase 1): User runs post-changelog hook to update dependencies
2. **Semi-automatic** (Future): Detect dependencies, suggest bumps
3. **Fully automatic** (Future): Auto-bump dependent projects

**Phase 1 approach** (recommended for initial implementation):

```toml
[[tool.releez.projects.packagea.hooks]]
post-changelog = [
  # Update packageb dependency version in packagea's pyproject.toml
  ["uv", "add", "--directory", "packages/packagea", "packageb@{version}"],
]
```

User manages inter-project dependencies via hooks. Releez doesn't need to
understand dependency graph.

## Implementation Plan

### Phase 1: Core Data Structures & Validation

**Files to create/modify**:

- `src/releez/subproject.py` (NEW) - SubProject dataclass and utilities
- `src/releez/settings.py` - Add projects configuration

**Tasks**:

1. Create `ProjectConfig` Pydantic model for TOML parsing
   - Add `include_paths: list[str] = Field(default_factory=list)` field
2. Create `SubProject` dataclass with validation
   - Add `include_paths: list[str]` field
3. Extend `ReleezSettings` to support `projects: list[ProjectConfig]`
4. Add `generate_tag_pattern()` utility with character validation
5. Add project validation:
   - No duplicate names or tag prefixes
   - Paths exist and are within repo
   - No overlapping paths (primary paths only, include_paths can overlap)
   - Changelog paths are writable
   - Include paths exist and are within repo
6. Add backwards compatibility check (if no projects → single-repo mode)

### Phase 2: Version Tags (moved up - needed by later phases)

**Files to modify**:

- `src/releez/version_tags.py` - Support tag prefixes

**Tasks**:

1. Update `compute_version_tags()` to accept `tag_prefix` parameter
2. Update tag creation/pushing to handle prefixed tags
3. Support tag aliasing per project (major/minor with prefix)
4. Add tests for prefixed tags

### Phase 3: Commit Detection

**Files to modify**:

- `src/releez/git_repo.py` - Add change detection functions

**Tasks**:

1. Implement `find_latest_tag_matching_pattern()` helper
2. Implement `detect_changed_projects()` - compares against latest tag per
   project
   - Returns: `list[SubProject]`
   - Checks all paths in `project.include_paths` (if any) in addition to
     `project.path`
3. Implement `get_changed_files_per_project()` - tracks which files changed per
   project
   - Returns: `dict[str, list[str]]` - mapping of project name to changed file
     paths
   - Used for debugging, CI optimization, and transparency
   - Example use cases:
     - Debug why a project was marked as changed
     - Skip certain CI steps if only docs changed
     - Advanced caching strategies
4. Add tests for change detection:
   - Project with only path changes
   - Project with include_paths (root files) changes
   - Multiple projects affected by root change
   - Changed files tracking accuracy

### Phase 4: git-cliff Integration

**Files to modify**:

- `src/releez/cliff.py` - Extend GitCliff class

**Tasks**:

1. **FIRST**: Test git-cliff CLI directly to verify:
   - `--tag-pattern '^core-([0-9]+\.[0-9]+\.[0-9]+)$'` syntax
   - `--include-path` syntax (can it be repeated for multiple paths?)
   - Example:
     `git-cliff --include-path packages/core/ --include-path pyproject.toml`
2. Add `tag_pattern` parameter to all GitCliff methods
3. Add `include_paths: list[str]` parameter for path filtering
4. Build git-cliff commands with `--tag-pattern` and multiple `--include-path`
   flags
5. Add tests for prefixed tag patterns and multiple include paths

### Phase 5: Release Workflow

**Files to modify**:

- `src/releez/release.py` - Support multi-project releases
- `src/releez/utils.py` - Project-aware hook execution

**Tasks**:

1. Extend `StartReleaseInput` to support optional project context
2. Create `start_release_monorepo()` function with error collection strategy
3. Implement per-project release loop:
   - Try to release each project
   - Collect results AND errors
   - Report all results at end
   - Exit with error if any failed
4. Update `run_post_changelog_hooks()` to accept project context
5. Selective git staging: stage project path + root config if modified
6. Handle multiple release branches (one per project)

### Phase 6: PR Creation

**Files to modify**:

- `src/releez/github.py` - Support multiple PRs
- `src/releez/release.py` - Call PR creation per project

**Tasks**:

1. Create PRs sequentially (or in parallel with rate limiting) for all released
   projects
2. Add project-specific labels: `["release", f"release:{project.name}"]`
3. Include only project's release notes in PR body
4. Handle PR creation failures gracefully (collect errors)

### Phase 7: CLI Updates

**Files to modify**:

- `src/releez/cli.py` - Add project selection flags and new subcommands

**Tasks**:

**A. Update existing `release` commands**:

1. Add `--project` (repeatable) flag to: `start`, `tag`, `notes`, `preview`
2. Add `--all` flag for operating on all projects
3. Validate mutual exclusivity: error if both `--project` and `--all` specified
4. Validate project names against configured projects in settings
5. Display per-project results:
   - `✓ core: 1.2.3` (success)
   - `❌ ui: Failed to compute version` (failure)
6. Exit with code 1 if any project failed

**B. Add new `projects` subcommand group**:

1. `releez projects list` - List all configured projects with metadata
2. `releez projects changed` - Detect changed projects (for CI)
   - `--format json|text|csv` - Output format (default: text)
   - `--base <ref>` - Base reference for comparison (default: base_branch)
   - `--include-files` - Include list of changed files per project (JSON format
     only)
   - **JSON output** (primary format for GitHub Actions):
     ```json
     {
       "projects": ["core", "ui"],
       "matrix": [
         { "project": "core", "path": "packages/core" },
         { "project": "ui", "path": "packages/ui" }
       ],
       "changes": {
         "core": [
           "packages/core/src/main.py",
           "packages/core/tests/test_main.py",
           "pyproject.toml"
         ],
         "ui": [
           "packages/ui/components/Button.tsx"
         ]
       }
     }
     ```
   - **Text output** (for humans):
     ```
     core
     ui
     ```
   - **CSV output** (for display):
     ```
     core,ui
     ```
3. `releez projects info <name>` - Show details about a project
   - Path, tag prefix, changelog path, hooks, etc.

### Phase 8: Comprehensive Testing

**Files to create**:

- `tests/integration/test_monorepo.py` - Integration tests
- `tests/fixtures/monorepo/` - Test fixture with multi-project structure

**Tasks**:

1. Create monorepo fixture with 2-3 projects
2. Unit tests for each new component
3. Integration test: full release workflow
4. Backwards compatibility test: ensure single-repo mode unchanged
5. Edge case tests:
   - Empty project paths
   - Overlapping paths
   - Concurrent releases
   - Root-level file changes
   - Hook failures

### Phase 9: Documentation & Examples

**Files to create**:

- `docs/monorepo-setup.md` - Complete guide
- `examples/monorepo-config.toml` - Example configuration
- Update `README.md` with monorepo support

**Content**:

1. How to configure monorepo projects
2. Commit filtering explanation (path-based)
3. Tag naming conventions
4. Dependency management strategies
5. Common workflows (release one vs all)
6. Migration guide from single-repo

## Critical Files Reference

| File                         | Purpose                      | Changes                                |
| ---------------------------- | ---------------------------- | -------------------------------------- |
| `src/releez/subproject.py`   | NEW - SubProject abstraction | Create dataclass + utilities           |
| `src/releez/settings.py`     | Configuration                | Add `[[projects]]` support             |
| `src/releez/cliff.py`        | git-cliff wrapper            | Add tag_pattern + include_paths params |
| `src/releez/git_repo.py`     | Git operations               | Add change detection                   |
| `src/releez/release.py`      | Release orchestration        | Support multi-project workflow         |
| `src/releez/version_tags.py` | Tag computation              | Support tag prefixes                   |
| `src/releez/utils.py`        | Utilities                    | Project-aware hooks                    |
| `src/releez/cli.py`          | CLI interface                | Add project selection flags            |

## Testing Strategy

1. **Unit tests**: Per-component tests (tag pattern generation, path mapping,
   etc.)
2. **Integration tests**: Monorepo fixture with 2-3 projects
3. **Backwards compatibility tests**: Ensure single-repo mode still works
4. **End-to-end tests**: Full release workflow for monorepo

## Backwards Compatibility

**Critical**: Must not break existing single-repo users!

**Approach**:

- If `[[projects]]` not configured → use existing workflow (no changes)
- All new parameters optional with sensible defaults
- Tag patterns default to existing pattern for single-repo
- CLI flags for project selection only apply in monorepo mode

## Design Decisions (Finalized)

### User-Confirmed Decisions

1. **Root-level file changes policy**: ✅ **Warn only**
   - When commits change root-level files (CI, docs, .github/), display warning
   - Don't automatically trigger releases
   - User can manually specify `--project` if they want to release despite root
     changes
   - Implementation: `detect_changed_projects()` returns
     `(changed_projects, root_files_changed)`

2. **Error handling strategy**: ✅ **Collect all errors**
   - Attempt to release each project independently
   - Collect successes AND failures
   - Report all results at end with clear success/failure indicators
   - Exit with error code if any project failed
   - Better UX: one failed project doesn't block others

3. **CLI flag style**: ✅ **--project (repeatable)**
   - `releez release start --project core --project ui`
   - Consistent with git add and other CLI tools
   - Also support `--all` flag to release all projects
   - Mutually exclusive validation: can't use both `--project` and `--all`

### Implementation-Time Testing Required

4. **git-cliff path filtering syntax**: ⚠️ **Needs testing**
   - Test during Phase 4 (git-cliff integration) which syntax works:
     - `--include-path 'packages/core/**'` (glob pattern)
     - `--include-path 'packages/core/'` (directory with trailing slash)
     - `--include-path 'packages/core'` (path prefix)
   - Document the correct syntax in code comments

## Success Criteria

1. ✅ Can configure multiple projects in root config with
   `[[tool.releez.projects]]`
2. ✅ Automatically detects which projects changed (path-based, since latest
   tag)
3. ✅ Generates independent changelogs per project using git-cliff path
   filtering
4. ✅ Creates prefixed tags per project (no collisions): `core-1.2.3`,
   `ui-4.5.6`
5. ✅ Creates separate PRs per project with project-specific labels
6. ✅ Backwards compatible with existing single-repo setup (no [[projects]] →
   single-repo mode)
7. ✅ Robust error handling: collect all errors, report at end
8. ✅ Warns about root-level file changes without triggering releases
9. ✅ Well documented with examples and migration guide

## Implementation Summary

**What's changing**:

- Add `[[tool.releez.projects]]` configuration support
- Each project: independent versioning, changelog, git tags (with prefix)
- Path-based commit filtering (not scope-based) - works with GitHub squash-merge
- One PR per subproject release
- Shared cliff.toml, tag patterns in releez config

**What's staying the same**:

- Single cliff.toml at root
- Existing single-repo workflow (backwards compatible)
- PR creation flow (just multiplied per project)
- Hook system (extended with project context)

**Key technical pieces**:

1. git-cliff `--include-path` and `--tag-pattern` flags for per-project
   filtering
2. Change detection: compare project paths against latest tag matching project's
   tag pattern
3. Multiple release branches: `release/core-1.2.3`, `release/ui-4.5.6`
4. Selective git staging: only stage files in project path (+ root config)
5. Error collection: try all projects, report all results

**Ready to implement**: All design decisions finalized, critical files
identified, test strategy defined.

---

## GitHub Actions Integration

### Consolidated releez-action (v2)

**Single action with mode parameter** (consolidates finalize +
version-artifact):

```yaml
# Mode 1: Detect changed projects (NEW)
- uses: releez-action@v2
  id: detect
  with:
    mode: detect-changed
  # Outputs: projects (JSON array), matrix (JSON array), changes (object)

# Mode 2: Get artifact version (EXISTING)
- uses: releez-action@v2
  with:
    mode: artifact-version
    project: core # Optional - auto-detect if not provided
# Outputs: version, changed

# Mode 3: Finalize release (EXISTING)
- uses: releez-action@v2
  with:
    mode: finalize
    project: core # Optional - auto-detect if not provided
```

**Backwards Compatibility Strategy**:

The action auto-detects monorepo vs single-repo based on branch naming:

```typescript
// Branch pattern detection
if (match = branch.match(/^release\/([a-z-]+)-(\d+\.\d+\.\d+)$/)) {
  // Monorepo mode: release/core-1.2.3
  project = match[1]  // "core"
  version = match[2]  // "1.2.3"
} else if (match = branch.match(/^release\/(\d+\.\d+\.\d+)$/)) {
  // Single-repo mode: release/1.2.3 (BACKWARDS COMPATIBLE)
  version = match[1]
}
```

**No breaking changes**: Existing single-repo users upgrade to v2 without any
config changes.

### Output Formats for mode=detect-changed

**CRITICAL**: Use **JSON arrays** for exact element matching in GitHub Actions.

**Why**: `contains()` does substring matching on strings, leading to bugs:

```yaml
# ❌ BROKEN: Substring matching
projects: 'core,core-ui'
if: contains(needs.detect.outputs.projects, 'ui') # TRUE (wrong!)

# ✅ CORRECT: Exact element matching
projects: '["core", "core-ui"]'
if: contains(fromJSON(needs.detect.outputs.projects), 'ui') # FALSE ✅
```

**Output format**:

```typescript
{
  // JSON array for exact matching (PRIMARY - use this!)
  projects: JSON.stringify(['core', 'core-ui']),
  // Example: '["core","core-ui"]'

  // JSON array for matrix strategy
  matrix: JSON.stringify([
    { project: 'core', path: 'packages/core' },
    { project: 'core-ui', path: 'packages/core-ui' }
  ]),

  // Per-project changed files (for debugging/advanced workflows)
  changes: JSON.stringify({
    'core': [
      'packages/core/src/main.py',
      'packages/core/tests/test_main.py',
      'pyproject.toml'  // from include-paths
    ],
    'core-ui': [
      'packages/core-ui/components/Button.tsx'
    ]
  })
}
```

### CI Workflow Patterns

**Philosophy**: Allow multi-project changes in development, detect and test
affected projects in CI.

**Standard monorepo practice** (Nx, Turborepo, Google monorepo, Lerna):

- ✅ **DO**: Allow multi-project changes in feature PRs
- ✅ **DO**: Detect and test all affected projects in CI
- ✅ **DO**: Release projects independently (separate release PRs)
- ❌ **DON'T**: Restrict PRs to single project changes

**Reason**: Real-world changes often span multiple projects (refactoring, shared
types, API changes, root dependencies).

#### Pattern 1: Separate Jobs (Polyglot Monorepo)

**Best for**: Different tech stacks per project (Python + Node + Rust)

```yaml
name: CI

on: pull_request

jobs:
  # Step 1: Detect which projects changed
  detect-changes:
    runs-on: ubuntu-latest
    outputs:
      projects: ${{ steps.detect.outputs.projects }}
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - uses: releez-action@v2
        id: detect
        with:
          mode: detect-changed

  # Step 2: Separate job for EACH project with custom workflows

  # Python backend
  check-core:
    needs: detect-changes
    if: contains(fromJSON(needs.detect-changes.outputs.projects), 'core')
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
      - run: uv sync
      - run: uv run pytest packages/core

  # React frontend
  check-ui:
    needs: detect-changes
    if: contains(fromJSON(needs.detect-changes.outputs.projects), 'ui')
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
      - run: npm ci --prefix packages/ui
      - run: npm test --prefix packages/ui

  # Final check (require all relevant jobs)
  all-checks:
    needs: [detect-changes, check-core, check-ui]
    if: always()
    runs-on: ubuntu-latest
    steps:
      - run: |
          # Verify all jobs succeeded or were skipped
          if [[ "${{ needs.check-core.result }}" != "success" && "${{ needs.check-core.result }}" != "skipped" ]]; then
            exit 1
          fi
          if [[ "${{ needs.check-ui.result }}" != "success" && "${{ needs.check-ui.result }}" != "skipped" ]]; then
            exit 1
          fi
```

**Benefits**:

- ✅ Different languages/tools per project
- ✅ Different check commands per project
- ✅ Conditional execution (only run for changed projects)
- ✅ Clear in UI (separate job per project)

#### Pattern 2: Matrix Strategy (Homogeneous Monorepo)

**Best for**: All projects use same tech stack (all Python, all Node, etc.)

```yaml
jobs:
  detect-changes:
    outputs:
      matrix: ${{ steps.detect.outputs.matrix }}
    steps:
      - uses: releez-action@v2
        id: detect
        with:
          mode: detect-changed

  check:
    needs: detect-changes
    if: needs.detect-changes.outputs.matrix != '[]'
    strategy:
      fail-fast: false
      matrix:
        include: ${{ fromJSON(needs.detect-changes.outputs.matrix) }}
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pytest packages/${{ matrix.project }} # Same command, different path
```

**Benefits**:

- ✅ Simple for homogeneous projects
- ✅ Automatic parallelization
- ⚠️ All projects must use same check workflow

#### Pattern 3: Reusable Workflows (Best of Both)

**Best for**: Multiple projects per stack (e.g., 3 Python projects, 2 Node
projects)

```yaml
# .github/workflows/ci.yaml
jobs:
  detect-changes:
  # ... same as above

  check-core:
    needs: detect-changes
    if: contains(fromJSON(needs.detect-changes.outputs.projects), 'core')
    uses: ./.github/workflows/check-python.yaml
    with:
      project-path: packages/core

  check-ui:
    needs: detect-changes
    if: contains(fromJSON(needs.detect-changes.outputs.projects), 'ui')
    uses: ./.github/workflows/check-node.yaml
    with:
      project-path: packages/ui
```

```yaml
# .github/workflows/check-python.yaml (reusable)
on:
  workflow_call:
    inputs:
      project-path:
        required: true
        type: string

jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
      - run: uv sync --directory ${{ inputs.project-path }}
      - run: uv run pytest ${{ inputs.project-path }}
```

**Benefits**:

- ✅ DRY (reuse workflows across projects with same stack)
- ✅ Custom workflows per stack
- ✅ Easy to maintain

### Release Finalization Workflow

```yaml
# .github/workflows/finalize-release.yaml
on:
  pull_request:
    types: [closed]
    branches: [master]

jobs:
  finalize:
    if: github.event.pull_request.merged == true && startsWith(github.head_ref, 'release/')
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: releez-action@v2
        with:
          mode: finalize
          # Auto-detects project from branch name:
          # - release/core-1.2.3 → project: core
          # - release/1.2.3 → single-repo mode (backwards compatible)
```

**Backwards compatibility**:

- Branch `release/1.2.3` → single-repo mode, no project specified
- Branch `release/core-1.2.3` → monorepo mode, project: core

### Key Takeaways for Actions

1. **Output Format**: Use **JSON arrays** (`'["core","ui"]'`), NOT
   comma-separated strings
   - Reason: `contains(fromJSON(...), 'value')` does exact element matching
   - Avoids bugs with overlapping names (`core` vs `core-ui`)

2. **Conditional Execution**: Use
   `contains(fromJSON(needs.detect.outputs.projects), 'core')`
   - Works correctly with all project names
   - Exact element matching, no false positives

3. **Workflow Philosophy**:
   - Allow multi-project changes in development
   - Detect and test all affected projects in CI
   - Release projects independently (separate PRs)

4. **Backwards Compatibility**:
   - Auto-detect monorepo vs single-repo from branch naming
   - No breaking changes for existing users
   - v2 works seamlessly with both modes

5. **Changed Files**:
   - Include per-project changed files in output
   - Useful for debugging and advanced CI workflows
   - Optional in JSON output via `changes` field

### Root pyproject.toml Changes

**Solution**: Use `include-paths` per project!

Projects that care about root file changes can explicitly include them:

```toml
[[tool.releez.projects]]
name = "core"
path = "packages/core"
include-paths = [
  "pyproject.toml", # Root dependencies affect core
  "uv.lock", # Lock file changes
]
```

**Benefits**:

- Explicit control - each project declares what it cares about
- Flexible - some projects can ignore root changes, others can't
- No special logic needed - uses same path filtering as project code
- If ALL projects include `pyproject.toml`, root changes release everything
- If NO projects include it, root changes release nothing

**Example scenarios**:

- Shared library project → include root pyproject.toml
- Independent microservice → don't include root files
- Workspace with shared dev deps → projects choose individually
