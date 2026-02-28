# `releez`

[![CI](https://img.shields.io/github/actions/workflow/status/hotdog-werx/releez/ci-checks.yaml)](https://github.com/hotdog-werx/releez/actions/workflows/ci-checks.yaml)
[![PyPI version](https://badge.fury.io/py/releez.svg)](https://pypi.org/project/releez/)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Coverage](https://codecov.io/gh/hotdog-werx/releez/branch/master/graph/badge.svg)](https://codecov.io/gh/hotdog-werx/releez)

`releez` is a CLI tool for managing semantic versioned releases.

`releez` uses [`git-cliff`](https://git-cliff.org/) for versioning logic and
changelog generation under the hood. You should host a `cliff.toml` or other
compatible `git-cliff` configuration in your repo. Review the `git-cliff`
documentation for details.

## Usage

Start a release from your repo (requires `git` on `PATH`):

`releez release start`

Common options:

- `--bump auto|patch|minor|major`
- `--base main`
- `--changelog-path CHANGELOG.md` (or `--changelog`)
- `--no-create-pr` (skip GitHub PR creation)
- `--github-token ...` (or set `RELEEZ_GITHUB_TOKEN`, falling back to
  `GITHUB_TOKEN`)
- `--dry-run`

Compute an artifact version for CI:

`releez version artifact`

Common options:

- `--scheme docker|semver|pep440`
- `--version-override ...`
- `--is-full-release`
- `--prerelease-type alpha|beta|rc`
- `--prerelease-number ...`
- `--build-number ...`
- `--alias-versions none|major|minor` (full releases only)

Examples:

- Docker PR build:
  `releez version artifact --scheme docker --version-override 0.1.0 --prerelease-type alpha --prerelease-number 123 --build-number 456`
  (outputs `0.1.0-alpha123-456`)
- Python PR build:
  `releez version artifact --scheme pep440 --version-override 0.1.0 --prerelease-type alpha --prerelease-number 123 --build-number 456`
- Main branch RC build:
  `releez version artifact --scheme docker --version-override 0.1.0 --prerelease-type rc --prerelease-number 0 --build-number 456`
  (outputs `0.1.0-rc0-456`)

Create git tags for a release:

`releez release tag` (tags the git-cliff computed release version; pushes tags
to `origin` by default)

Override the tagged version if needed:

`releez release tag --version-override 2.3.4`

Optionally update major/minor tags:

- Major only:
  `releez release tag --version-override 2.3.4 --alias-versions major` (creates
  `2.3.4` and `v2`)
- Major + minor:
  `releez release tag --version-override 2.3.4 --alias-versions minor` (creates
  `2.3.4`, `v2`, `v2.3`)

Preview what will be published (version and tags):

`releez release preview` (prints markdown to stdout)

`releez release preview --output release-preview.md` (write markdown to a file)

Generate the unreleased changelog section for the release:

`releez release notes` (prints markdown to stdout)

`releez release notes --output release-notes.md` (write markdown to a file)

Regenerate the entire changelog from git history:

`releez changelog regenerate` (regenerates `CHANGELOG.md` using git-cliff)

Common options:

- `--changelog-path CHANGELOG.md` (specify a different changelog file)
- `--run-changelog-format` (run the configured format hook after regeneration)
- `--changelog-format-cmd ...` (override the configured format command)

This is useful for fixing changelog formatting issues or rebuilding the
changelog after repository changes.

## Monorepo Support

`releez` supports monorepos with multiple independently-versioned projects. Each
project can have its own:

- Version number (e.g., `core-1.2.3`, `ui-4.5.6`)
- Changelog file
- Git tags with unique prefixes
- Release branches and PRs
- Custom hooks and settings

### Quick Start

Configure projects in your root `pyproject.toml` or `releez.toml`:

```toml
[tool.releez]
base-branch = "main"

[[tool.releez.projects]]
name = "core"
path = "packages/core"
changelog-path = "CHANGELOG.md"
tag-prefix = "core-"

[[tool.releez.projects]]
name = "ui"
path = "packages/ui"
changelog-path = "CHANGELOG.md"
tag-prefix = "ui-"
```

Start releases for changed projects:

```bash
# Auto-detect which projects have unreleased changes
releez release start

# Release specific projects
releez release start --project core --project ui

# Release all projects
releez release start --all
```

### Monorepo Commands

List configured projects:

```bash
releez projects list
```

Detect which projects have unreleased changes:

```bash
releez projects changed
releez projects changed --format json  # For CI/CD
```

Get project information:

```bash
releez projects info core
```

Detect release from branch name (useful in GitHub Actions):

```bash
releez release detect-from-branch --branch release/core-1.2.3
# Output: {"version": "core-1.2.3", "project": "core", "branch": "release/core-1.2.3"}
```

### How It Works

`releez` uses path-based change detection:

1. For each project, find the latest git tag matching its `tag-prefix`
2. Check for commits since that tag touching the project's paths
3. If commits exist, mark the project as changed

Projects can monitor additional paths beyond their main directory:

```toml
[[tool.releez.projects]]
name = "core"
path = "packages/core"
tag-prefix = "core-"
include-paths = [
  "pyproject.toml", # Root dependencies affect core
  "uv.lock", # Lock file changes
]
```

### Tags and Versioning

Each project gets its own prefixed tags:

- Core: `core-1.2.3`, `core-v1`, `core-v1.2`
- UI: `ui-4.5.6`, `ui-v4`, `ui-v4.5`

This prevents tag collisions and allows independent versioning.

### Complete Documentation

For detailed monorepo configuration, including:

- Change detection strategies
- Dependency management between projects
- GitHub Actions integration
- Migration from single-repo setup

See the [Monorepo Setup Guide](./docs/monorepo-setup.md) and
[example configuration](./examples/monorepo-config.toml).

## Configuration

`releez` supports configuration via:

1. CLI flags for a command (highest)
2. `RELEEZ_*` environment variables
3. `releez.toml` in the repo root
4. `pyproject.toml` under `[tool.releez]` (lowest)

Config values are applied as defaults for relevant CLI options; passing the CLI
flag always wins.

### Config keys

TOML config supports both `snake_case` and `kebab-case` keys.

Env vars always use `RELEEZ_` + `SNAKE_CASE`, with `__` for nesting. Example:
`RELEEZ_HOOKS__CHANGELOG_FORMAT`.

### Supported settings

These are the settings currently loaded from config/env:

- `base_branch` (`--base` on `release start`)
- `git_remote` (`--remote` on `release start` / `release tag`)
- `pr_labels` (`--labels` on `release start`)
- `pr_title_prefix` (`--title-prefix` on `release start`)
- `changelog_path` (`--changelog-path` on `release start` /
  `changelog regenerate`)
- `create_pr` (`--create-pr/--no-create-pr` on `release start`)
- `run_changelog_format` (`--run-changelog-format` on `release start` /
  `changelog regenerate`)
- `hooks.changelog_format` (used by `release start` and `changelog regenerate`
  when formatting is enabled)
- `alias_versions` (`--alias-versions` on `release tag` / `release preview` /
  `version artifact`)

Other flags (e.g. `--version-override`, `--scheme`, `--build-number`) are
runtime inputs and are not read from config files.

### Examples

`pyproject.toml`:

```toml
[tool.releez]
base-branch = "master"
git-remote = "origin"
alias-versions = "minor"
run-changelog-format = true

[tool.releez.hooks]
changelog-format = ["poe", "format-dprint", "{changelog}"]
```

`releez.toml`:

```toml
base_branch = "main"
git_remote = "origin"
alias_versions = "minor"
run_changelog_format = true

[hooks]
changelog_format = ["poe", "format-dprint", "{changelog}"]
```

Environment variables:

```bash
export RELEEZ_GIT_REMOTE=origin
export RELEEZ_ALIAS_VERSIONS=major
export RELEEZ_HOOKS__CHANGELOG_FORMAT='["poe","format-dprint","{changelog}"]'
```

Notes:

- `releez` prefers `RELEEZ_GITHUB_TOKEN` over `GITHUB_TOKEN` for PR creation;
  the token is read separately and is not part of `RELEEZ_*` settings.
- `{changelog}` in `changelog_format` is replaced with the configured changelog
  path before execution.

## GitHub actions

We've built GitHub reusable actions which use `releez` to streamline integration
with CI pipelines.

### [`releez-action`](https://github.com/truss-security/releez-action) (Recommended)

A unified action supporting multiple modes:

- `version-artifact` - Generate artifact versions for CI builds
- `validate` - Validate release branches before merge
- `finalize` - Tag releases and create GitHub Releases

Supports both single-repo and monorepo workflows with automatic project
detection.

Example usage:

```yaml
- uses: truss-security/releez-action@v2
  with:
    mode: version-artifact
    project: core # Optional for monorepo
```

### Legacy Actions (v1)

These actions are still supported but will be superseded by the unified
`releez-action` v2:

#### [`releez-version-artifact-action`](https://github.com/hotdog-werx/releez-version-artifact-action)

This action can be used during CI to generate artifact versions with versions
corresponding to the versions suggested by `releez` (and implicitly,
`git-cliff`).

#### [`releez-finalize-action`](https://github.com/hotdog-werx/releez-finalize-action)

This action can be run to finalize a release. You can see
[this workflow](./.github/workflows/finalize-release.yaml) for an example a
usage.

It applies tags and outputs artifact versions as well as release notes that can
be used subsequently to create a GitHub Release.

A release should first be started with `releez release start`, usually locally,
unless you've given your actions permission to create PRs, such as via a GitHub
App.

## GitHub recommendations

If you use GitHub PRs, prefer squashing and using the PR title as the squash
commit message:

- Enable “Allow squash merging”
- Set “Default commit message” to “Pull request title”

This keeps your main branch history aligned with semantic PR titles (and works
well with `amannn/action-semantic-pull-request` and changelog generation via
`git-cliff`).
