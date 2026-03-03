# Monorepo Setup Guide

This guide explains how to configure and use Releez in a monorepo with multiple
independently-versioned projects.

## Overview

Releez supports monorepos through project-based configuration. Each project in
your monorepo can have:

- Independent versioning (e.g., `core-1.2.3`, `ui-4.5.6`)
- Separate changelogs
- Isolated release branches and PRs
- Custom hooks and settings
- Selective builds in CI/CD

## Quick Start

### 1. Basic Monorepo Configuration

Add a `[[tool.releez.projects]]` section for each independently-versioned
project:

```toml
# Root pyproject.toml or releez.toml

[tool.releez]
base-branch = "main"
git-remote = "origin"
create-pr = true

# Project 1: Core Library
[[tool.releez.projects]]
name = "core"
path = "packages/core"
changelog-path = "CHANGELOG.md" # Relative to packages/core/
tag-prefix = "core-"

# Project 2: UI Components
[[tool.releez.projects]]
name = "ui"
path = "packages/ui"
changelog-path = "CHANGELOG.md"
tag-prefix = "ui-"
```

### 2. Start a Release

Releez automatically detects which projects have unreleased changes:

```bash
# Auto-detect changed projects and release them
releez release start

# Release specific projects
releez release start --project core --project ui

# Release all projects regardless of changes
releez release start --all
```

### 3. What Happens

For each changed project, Releez will:

1. Compute the next version (e.g., `core-1.2.3`)
2. Generate release notes from commits affecting that project
3. Create a release branch: `release/core-1.2.3`
4. Update the project's changelog
5. Create a PR with label `release:core`

## Configuration Reference

### Project Configuration

Each `[[tool.releez.projects]]` entry supports:

| Field            | Required | Description                                          |
| ---------------- | -------- | ---------------------------------------------------- |
| `name`           | Yes      | Unique project identifier (used in CLI, labels)      |
| `path`           | Yes      | Directory path relative to repo root                 |
| `changelog-path` | Yes      | Changelog file path relative to project path         |
| `tag-prefix`     | Yes      | Prefix for git tags (e.g., `"core-"` → `core-1.2.3`) |
| `alias-versions` | No       | Override global alias-versions setting               |
| `include-paths`  | No       | Additional paths to monitor for changes              |

### Example: Full Configuration

```toml
[tool.releez]
base-branch = "main"
git-remote = "origin"
create-pr = true
alias-versions = "none" # Global default

# Global hooks (apply to all projects)
[tool.releez.hooks]
post-changelog = [
  ["prettier", "--write", "{changelog}"],
]

# Core library project
[[tool.releez.projects]]
name = "core"
path = "packages/core"
changelog-path = "CHANGELOG.md"
tag-prefix = "core-"
alias-versions = "major" # Override: create v1, v1.2 aliases

# Monitor root dependencies
include-paths = [
  "pyproject.toml",
  "uv.lock",
]

# Core-specific hooks (must follow the [[tool.releez.projects]] entry it belongs to)
[tool.releez.projects.hooks]
post-changelog = [
  ["uv", "version", "{version}"],
]

# UI components project
[[tool.releez.projects]]
name = "ui"
path = "packages/ui"
changelog-path = "CHANGELOG.md"
tag-prefix = "ui-"
# No include-paths: only releases when UI code changes
```

## Change Detection

### How It Works

Releez detects changed projects using **path-based filtering**:

1. For each project, find the latest git tag matching its `tag-prefix`
2. Get all commits since that tag that touched the project's paths
3. If commits exist, mark the project as changed

### Monitored Paths

Each project monitors:

- **Primary path**: The `path` directory (e.g., `packages/core`)
- **Additional paths**: Anything in `include-paths` (optional)

### Example: Root File Changes

Projects can explicitly opt-in to monitoring root-level files:

```toml
[[tool.releez.projects]]
name = "core"
path = "packages/core"
include-paths = [
  "pyproject.toml", # Root dependencies
  "uv.lock", # Lock file
  ".github/", # CI changes
]
```

**When to use `include-paths`**:

- ✅ Shared dependencies affect this project
- ✅ Root config changes require releasing
- ❌ Independent microservices (don't need root files)

## Tag Naming

### Tag Patterns

Each project's tags follow a consistent pattern:

```
{tag-prefix}{version}
```

Examples:

- Core library: `core-1.2.3`, `core-v1`, `core-v1.2`
- UI components: `ui-4.5.6`, `ui-v4`, `ui-v4.5`
- API service: `api-2.0.0`, `api-v2`, `api-v2.0`

### Alias Versions

For full releases (not prereleases), Releez can create alias tags:

```toml
[[tool.releez.projects]]
name = "core"
tag-prefix = "core-"
alias-versions = "major" # Creates core-v1
```

Options:

- `"none"` - No aliases (only exact version)
- `"major"` - Create major alias (e.g., `core-v1`)
- `"minor"` - Create major and minor aliases (e.g., `core-v1`, `core-v1.2`)

**Note**: Aliases are only created for full releases, not prereleases.

## Release Workflows

### Auto-Detect and Release Changed Projects

```bash
# Detects which projects have unreleased commits
releez release start
```

Output:

```
Detected 2 changed projects: core, ui

✓ core: Starting release for version core-1.2.3
  Created branch: release/core-1.2.3
  Created PR: https://github.com/org/repo/pull/123

✓ ui: Starting release for version ui-4.5.6
  Created branch: release/ui-4.5.6
  Created PR: https://github.com/org/repo/pull/124
```

### Release Specific Projects

```bash
# Release only the core project
releez release start --project core

# Release multiple specific projects
releez release start --project core --project ui
```

### Release All Projects

```bash
# Bypass change detection, release everything
releez release start --all
```

### Check Which Projects Changed

```bash
# See which projects have unreleased changes
releez projects changed

# Output format for CI
releez projects changed --format json
```

JSON output:

```json
{
  "projects": ["core", "ui"],
  "include": [
    { "project": "core" },
    { "project": "ui" }
  ]
}
```

## uv Workspace Integration

If your monorepo is a
[uv workspace](https://docs.astral.sh/uv/concepts/workspaces/), each package has
its own `pyproject.toml` with a `[project]` version field, and a shared
`uv.lock` at the repo root tracks the resolved dependency graph including
workspace member versions.

### Recommended Hook Pattern

Use `uv version` (without `--frozen`) to bump the package version and regenerate
the lock file in a single step. Then explicitly stage `uv.lock` so it is
included in the release commit:

```toml
[tool.uv.workspace]
members = ["packages/core", "packages/ui"]

[tool.releez]
base-branch = "main"

[[tool.releez.projects]]
name = "core"
path = "packages/core"
tag-prefix = "core-"
changelog-path = "CHANGELOG.md"
include-paths = ["pyproject.toml", "uv.lock"]

[tool.releez.projects.hooks]
post-changelog = [
  ["uv", "version", "--directory", "packages/core", "{version}"],
  ["git", "add", "uv.lock"],
]

[[tool.releez.projects]]
name = "ui"
path = "packages/ui"
tag-prefix = "ui-"
changelog-path = "CHANGELOG.md"
include-paths = ["pyproject.toml", "uv.lock"]

[tool.releez.projects.hooks]
post-changelog = [
  ["uv", "version", "--directory", "packages/ui", "{version}"],
  ["git", "add", "uv.lock"],
]
```

**Why this works:**

- `uv version --directory packages/ui 0.2.3` updates
  `packages/ui/pyproject.toml` _and_ re-resolves `uv.lock` in one step,
  preserving all existing pins (it is equivalent to `uv lock` without
  `--upgrade`).
- `git add uv.lock` explicitly stages the updated lock file. Because `uv.lock`
  lives outside the project directory, releez's selective staging would
  otherwise leave it out of the release commit.
- The `{version}` template variable is always the bare semver (e.g. `0.2.3`),
  with the tag prefix stripped — exactly what `uv version` expects.

**Why `include-paths = ["pyproject.toml", "uv.lock"]`:**

Both files are declared as `include-paths` so that a root-level dependency
update (bump in `pyproject.toml` or `uv.lock`) registers as an unreleased change
and triggers a new release for all affected projects.

### Changelog Staging

The project changelog (`packages/ui/CHANGELOG.md`) is inside the project
directory and is staged automatically by releez — no explicit `git add` needed
for it. Only files **outside** the project directory (like the root `uv.lock`)
require an explicit `git add` hook.

## Dependency Management

### Inter-Project Dependencies

When one project depends on another, you can use hooks to update versions:

```toml
[[tool.releez.projects]]
name = "app"
path = "packages/app"
tag-prefix = "app-"

# Update core dependency version after release
[tool.releez.projects.hooks]
post-changelog = [
  ["uv", "add", "--directory", "packages/app", "core@{version}"],
]
```

### Strategies

**Manual** (recommended for Phase 1):

- Use `post-changelog` hooks to update dependencies
- Commit dependency updates in the same release PR

**Semi-automatic** (future):

- Detect projects with dependencies on released projects
- Suggest bumping dependent projects

**Fully automatic** (future):

- Auto-bump all dependent projects
- Create cascading releases

## GitHub Actions Integration

### Detect Changed Projects

#### Matrix Strategy (Homogeneous Stacks)

When all projects use the same tech stack, use the `include` matrix output to
fan out jobs automatically:

```yaml
name: Build Changed Projects

on: pull_request

jobs:
  detect:
    runs-on: ubuntu-latest
    outputs:
      matrix: ${{ steps.detect.outputs.matrix }}
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uv tool install releez

      - id: detect
        run: |
          releez projects changed --format json > changed.json
          echo "matrix=$(jq -c '.include' changed.json)" >> $GITHUB_OUTPUT

  build:
    needs: detect
    if: needs.detect.outputs.matrix != '[]'
    strategy:
      matrix: ${{ fromJson(needs.detect.outputs.matrix) }}
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Build ${{ matrix.project }}
        run: echo "Building ${{ matrix.project }}"
```

#### Conditional Jobs per Project (Polyglot Stacks)

When projects use different tech stacks, emit the `projects` JSON array and use
`contains(fromJSON(...))` to gate each job:

```yaml
jobs:
  detect:
    runs-on: ubuntu-latest
    outputs:
      projects: ${{ steps.detect.outputs.projects }}
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uv tool install releez

      - id: detect
        run: |
          CHANGED=$(releez projects changed --format json)
          echo "projects=$(echo "$CHANGED" | jq -c '.projects')" >> $GITHUB_OUTPUT

  check-core:
    needs: detect
    if: contains(fromJSON(needs.detect.outputs.projects), 'core')
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pytest packages/core

  check-ui:
    needs: detect
    if: contains(fromJSON(needs.detect.outputs.projects), 'ui')
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: npm test --prefix packages/ui
```

> **Pitfall**: Use `contains(fromJSON(outputs.projects), 'core')`, **not**
> `contains(outputs.projects, 'core')`. The latter does substring matching on
> the raw JSON string — `'core'` would incorrectly match `"core-ui"` too.

### Version Artifacts for Changed Projects

```yaml
- uses: hotdog-werx/releez@v0
  id: version
  with:
    mode: version-artifact
    project: ${{ matrix.project }}

- name: Build with version
  run: |
    echo "Version: ${{ steps.version.outputs.version }}"
    echo "Changed: ${{ steps.version.outputs.changed }}"
```

### Finalize Releases

```yaml
name: Finalize Release

on:
  pull_request:
    types: [closed]
    branches: [main]

jobs:
  finalize:
    if: github.event.pull_request.merged == true
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uv tool install releez

      - uses: hotdog-werx/releez@v0
        with:
          mode: finalize
          github-token: ${{ secrets.GITHUB_TOKEN }}
```

## Migration from Single Repo

### Step 1: Backup Current State

```bash
git tag -l > tags-backup.txt
git log --oneline > commits-backup.txt
```

### Step 2: Add Projects Configuration

```toml
# Before (single repo)
[tool.releez]
base-branch = "main"

# After (monorepo)
[tool.releez]
base-branch = "main"

[[tool.releez.projects]]
name = "main"
path = "."
changelog-path = "CHANGELOG.md"
tag-prefix = "" # Keep existing tag format
```

### Step 3: Test Configuration

```bash
# Validate configuration
releez projects list

# Check change detection
releez projects changed
```

### Step 4: Gradual Migration

If you want to transition to prefixed tags:

```toml
[[tool.releez.projects]]
name = "main"
path = "."
changelog-path = "CHANGELOG.md"
tag-prefix = "main-" # New prefix
```

Then:

1. Release once with new prefix: `main-2.0.0`
2. Future releases use new format
3. Old tags remain valid for history

## CLI Reference

### Projects Commands

```bash
# List all configured projects
releez projects list

# Show project details
releez projects info core

# Detect changed projects
releez projects changed
releez projects changed --format json
```

### Release Commands with Project Support

```bash
# Start release for changed projects
releez release start
releez release start --project core
releez release start --all

# Preview version/tags for a project
releez release preview --project core

# Generate release notes for a project
releez release notes --project core

# Tag releases
releez release tag --project core
```

For `release tag`, `release preview`, and `release notes`, monorepo mode
requires explicit project selection: use `--project <name>` (repeatable) or
`--all`.

### Detect Release from Branch

```bash
# Detect which project and version from branch name
releez release detect-from-branch --branch release/core-1.2.3

# Use current branch
releez release detect-from-branch
```

Output:

```json
{
  "version": "core-1.2.3",
  "project": "core",
  "branch": "release/core-1.2.3"
}
```

## Troubleshooting

### Project Not Detected as Changed

**Issue**: Made changes but `releez projects changed` doesn't show the project.

**Solutions**:

1. Check if changes are committed: `git status`
2. Verify paths in config match actual directory structure
3. Check if latest tag exists: `git tag -l 'core-*'`
4. Manually specify project: `releez release start --project core`

### Tag Already Exists

**Issue**: Error when creating tag: "tag already exists"

**Solutions**:

1. Check existing tags: `git tag -l 'core-*'`
2. Ensure `tag-prefix` is unique per project
3. Delete local tag if incorrect: `git tag -d core-1.2.3`

### Root File Changes Not Triggering Release

**Issue**: Updated root `pyproject.toml` but project didn't release.

**Solution**: Add root files to `include-paths`:

```toml
[[tool.releez.projects]]
name = "core"
path = "packages/core"
include-paths = ["pyproject.toml", "uv.lock"]
```

### Multiple Projects in One PR

**Issue**: Want to release multiple projects in a single PR.

**Current limitation**: Releez creates one PR per project for cleaner reviews.

**Workaround**: Manually release each project, then combine branches:

```bash
git checkout -b release/combined
git merge release/core-1.2.3
git merge release/ui-4.5.6
```

## Best Practices

### 1. Use Descriptive Tag Prefixes

```toml
# Good: Clear, short prefixes
tag-prefix = "api-"
tag-prefix = "core-"
tag-prefix = "ui-"

# Avoid: Too verbose
tag-prefix = "my-awesome-project-"
```

### 2. Strategic Use of `include-paths`

Only add root files that truly affect the project:

```toml
# Library that uses root dependencies
[[tool.releez.projects]]
name = "core"
include-paths = ["pyproject.toml", "uv.lock"]

# Independent service
[[tool.releez.projects]]
name = "worker"
# No include-paths: only releases when worker code changes
```

### 3. Consistent Alias Versions

Set a global default, override only when needed:

```toml
[tool.releez]
alias-versions = "none" # Default: no aliases

[[tool.releez.projects]]
name = "sdk"
alias-versions = "major" # Exception: SDK needs v1 for convenience
```

### 4. Hooks for Automation

Use hooks to maintain consistency:

```toml
# Global hook: format changelogs for every project
[tool.releez.hooks]
post-changelog = [
  ["prettier", "--write", "{changelog}"],
]

# Per-project hook (must follow the [[tool.releez.projects]] entry it belongs to)
[[tool.releez.projects]]
name = "python-pkg"
path = "packages/python-pkg"
tag-prefix = "python-pkg-"
changelog-path = "CHANGELOG.md"

[tool.releez.projects.hooks]
post-changelog = [
  ["uv", "version", "--directory", "packages/python-pkg", "{version}"],
  ["git", "add", "uv.lock"],
]
```

### 5. CI/CD Optimization

Only build what changed:

```yaml
jobs:
  detect:
    outputs:
      matrix: ${{ steps.detect.outputs.matrix }}
      has-changes: ${{ steps.detect.outputs.has-changes }}
    steps:
      - id: detect
        run: |
          CHANGED=$(releez projects changed --format json)
          echo "matrix=$(echo "$CHANGED" | jq -c '.include')" >> $GITHUB_OUTPUT
          echo "has-changes=$(echo "$CHANGED" | jq -e '.projects | length > 0')" >> $GITHUB_OUTPUT

  build:
    needs: detect
    if: needs.detect.outputs.has-changes == 'true'
    strategy:
      matrix: ${{ fromJson(needs.detect.outputs.matrix) }}
```

## Examples

See [examples/monorepo-config.toml](../examples/monorepo-config.toml) for a
complete example configuration with:

- Multiple projects (core, ui, api)
- Different alias-versions strategies
- Custom hooks per project
- Strategic use of include-paths

## Further Reading

- [Hooks Documentation](../configuration/hooks.md)
- [GitHub Actions Integration](../github-actions/action.md)
- [Conventional Commits](https://www.conventionalcommits.org/)
