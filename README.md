# `releez`

[![CI](https://img.shields.io/github/actions/workflow/status/hotdog-werx/releez/ci-checks.yaml)](https://github.com/hotdog-werx/releez/actions/workflows/ci-checks.yaml)
[![PyPI version](https://badge.fury.io/py/releez.svg)](https://pypi.org/project/releez/)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Coverage](https://codecov.io/gh/hotdog-werx/releez/branch/master/graph/badge.svg)](https://codecov.io/gh/hotdog-werx/releez)

`releez` is a CLI tool for managing semantic versioned releases. It automates
version bumping, changelog generation, release PRs, and git tags — powered by
[`git-cliff`](https://git-cliff.org/) under the hood.

```bash
uv tool install releez
```

## Commands

```bash
releez release start           # bump version, update changelog, open PR
releez release preview         # print what would be released
releez release notes           # print unreleased changelog section
releez release tag             # create git tags after merging the release PR
releez version artifact        # compute semver/docker/pep440 versions for CI
releez changelog regenerate    # rebuild the full CHANGELOG from git history
```

Common flags: `--bump auto|patch|minor|major`, `--base <branch>`, `--dry-run`,
`--alias-versions none|major|minor`.

For monorepo projects, add `--project <name>` (repeatable) or `--all`.

## Monorepo support

Configure multiple independently-versioned projects in your root
`pyproject.toml`:

```toml
[tool.releez]
base-branch = "main"

[[tool.releez.projects]]
name = "core"
path = "packages/core"
tag-prefix = "core-"
changelog-path = "CHANGELOG.md"

[[tool.releez.projects]]
name = "ui"
path = "packages/ui"
tag-prefix = "ui-"
changelog-path = "CHANGELOG.md"
```

Each project gets its own changelog, release branch, PR, and tags (e.g.
`core-1.2.3`, `core-v1`). `releez` auto-detects which projects have unreleased
changes.

See [docs/monorepo/setup.md](./docs/monorepo/setup.md) for full configuration,
change detection, uv workspace integration, and CI patterns.

## Configuration

Precedence (highest first): CLI flags → `RELEEZ_*` env vars → `releez.toml` →
`pyproject.toml` (`[tool.releez]`).

```toml
[tool.releez]
base-branch = "master"
git-remote = "origin"
alias-versions = "minor"

[tool.releez.hooks]
post-changelog = [
  ["uv", "version", "{version}"], # {version} = bare semver
  ["prettier", "--write", "{changelog}"],
]
```

Hooks run automatically after the changelog is updated. Template variables:
`{version}` (bare semver), `{project_version}` (full tagged version, e.g.
`core-1.2.3`), `{changelog}` (absolute path).

See [docs/configuration/hooks.md](./docs/configuration/hooks.md) for the full
hook reference and migration guide.

## GitHub Action

`releez` ships a composite GitHub Action. Pin it by tag — the matching CLI
version is installed automatically.

### Modes

| Mode               | When                               | What it does                                      |
| ------------------ | ---------------------------------- | ------------------------------------------------- |
| `validate`         | PR opened / updated on `release/*` | Dry-runs the release, posts a preview comment     |
| `finalize`         | Release PR merged                  | Creates git tags, emits version outputs           |
| `version-artifact` | Any build                          | Computes semver / docker / pep440 version strings |

### Validate a release PR

```yaml
- uses: hotdog-werx/releez@v0
  with:
    mode: validate
    post-comment: 'true'
```

### Finalize and create a GitHub Release

```yaml
- id: releez
  uses: hotdog-werx/releez@v0
  with:
    mode: finalize
    alias-versions: major

- uses: softprops/action-gh-release@v2
  with:
    tag_name: ${{ steps.releez.outputs.release-version }}
    body: ${{ steps.releez.outputs.release-notes }}
```

### Artifact versions for a Docker build

```yaml
- id: version
  uses: hotdog-werx/releez@v0
  with:
    mode: version-artifact
    is-full-release: ${{ github.event_name != 'pull_request' }}
    prerelease-number: ${{ github.event.pull_request.number }}
```

Key outputs: `release-version`, `semver-versions`, `docker-versions`,
`pep440-versions`, `release-notes`, `project` (monorepo).

For full input/output reference and workflow recipes see
[docs/github-actions/action.md](./docs/github-actions/action.md) and
[docs/github-actions/workflow-recipes.md](./docs/github-actions/workflow-recipes.md).

## GitHub recommendations

Prefer squash merging with "Pull request title" as the default commit message.
This keeps your history aligned with semantic PR titles and works well with
`amannn/action-semantic-pull-request` and `git-cliff` changelog generation.
