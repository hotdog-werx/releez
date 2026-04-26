# `releez`

[![CI](https://img.shields.io/github/actions/workflow/status/hotdog-werx/releez/ci-checks.yaml)](https://github.com/hotdog-werx/releez/actions/workflows/ci-checks.yaml)
[![PyPI version](https://badge.fury.io/py/releez.svg)](https://pypi.org/project/releez/)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Coverage](https://codecov.io/gh/hotdog-werx/releez/branch/master/graph/badge.svg)](https://codecov.io/gh/hotdog-werx/releez)

`releez` is a CLI tool for managing semantic versioned releases. It automates
version bumping, changelog generation, release PRs, and git tags — powered by
[`git-cliff`](https://git-cliff.org/) under the hood.

**[Full documentation at hotdog-werx.github.io/releez](https://hotdog-werx.github.io/releez/)**

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

See the
[Monorepo Setup Guide](https://hotdog-werx.github.io/releez/monorepo/setup/) for
full configuration, change detection, uv workspace integration, and CI patterns.

## Support branches

Support branches are long-lived maintenance lines for shipping hotfixes or
backported features on older majors (e.g. `support/1.x` while `2.x` development
continues on the default branch).

**Create** a support branch with:

```bash
releez release support-branch 1            # single-repo → support/1.x
releez release support-branch 1 --project ui  # monorepo  → support/ui-1.x
```

**Release** from a support branch with the normal `releez release start` command
— Releez detects the branch automatically and scopes versioning to the correct
major line.

See the
[Support Branches guide](https://hotdog-werx.github.io/releez/support-branches/)
for full details including `--commit` overrides, custom naming, and monorepo
configuration.

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

See the
[Settings reference](https://hotdog-werx.github.io/releez/configuration/settings/)
and
[Hooks documentation](https://hotdog-werx.github.io/releez/configuration/hooks/)
for details.

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
`pep440-versions`, `semver-version`, `docker-version`, `pep440-version`
(singular = exact version only, no aliases), `release-notes`, `project`
(monorepo).

For the full input/output reference and workflow recipes see the
[Action Reference](https://hotdog-werx.github.io/releez/github-actions/action/)
and
[Workflow Recipes](https://hotdog-werx.github.io/releez/github-actions/workflow-recipes/).

## GitHub recommendations

Prefer squash merging with "Pull request title" as the default commit message.
This keeps your history aligned with semantic PR titles and works well with
`amannn/action-semantic-pull-request` and `git-cliff` changelog generation.
