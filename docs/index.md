# releez — make releases ez

[![CI](https://img.shields.io/github/actions/workflow/status/hotdog-werx/releez/ci-checks.yaml)](https://github.com/hotdog-werx/releez/actions/workflows/ci-checks.yaml)
[![PyPI version](https://badge.fury.io/py/releez.svg)](https://pypi.org/project/releez/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

`releez` is a CLI tool that takes the friction out of semantic versioned
releases. It automates the repetitive parts — bumping versions, writing
changelogs, opening release PRs, creating git tags — so you can ship without the
ceremony.

Under the hood it uses [`git-cliff`](https://git-cliff.org/) for versioning
logic and changelog generation. You bring a `cliff.toml`; `releez` handles the
rest.

## What it does

| Task                             | Command                       |
| -------------------------------- | ----------------------------- |
| Start a release PR               | `releez release start`        |
| Preview what will be released    | `releez release preview`      |
| Generate release notes           | `releez release notes`        |
| Create git tags after merge      | `releez release tag`          |
| Compute artifact versions for CI | `releez version artifact`     |
| Regenerate the full changelog    | `releez changelog regenerate` |

## Key features

- **Auto version bumping** — `git-cliff` analyses your commit history and
  computes the next semver automatically, or you can pin it with
  `--bump patch|minor|major`.
- **Changelog management** — Prepends the new release section to your changelog
  file and optionally runs format hooks (e.g. Prettier, dprint).
- **GitHub PR workflow** — Creates a release branch, commits the changelog,
  opens a PR. Merge the PR; run `release tag` (or use the Action) to ship.
- **Artifact versions** — Computes semver / Docker / PEP 440 version strings for
  prerelease and full-release builds. Ideal for CI pipelines.
- **Monorepo support** — Multiple independently-versioned projects in one repo,
  each with its own changelog, tags, and release PRs.
- **GitHub Action** — Composite action that installs the matching CLI version
  and handles validate, finalize, and version-artifact modes.

## Install

```bash
uv tool install releez
```

Or pin it in your project:

```bash
uv add --dev releez
```

Requires Python 3.11+ and `git-cliff` on PATH (or installed via uv).

## Quick start

1. Add a `cliff.toml` at your repo root (see
   [git-cliff docs](https://git-cliff.org/docs/configuration)).
2. Run `releez release start` — it detects the next version, updates your
   changelog, and opens a release PR.
3. Review the PR, merge it, then run `releez release tag` (or let the GitHub
   Action do it automatically).

## Documentation

### Configuration

- [Settings](./configuration/settings.md) — Precedence, all settings, env vars,
  TOML examples
- [Hooks](./configuration/hooks.md) — Post-changelog hooks, template variables,
  migration guide

### GitHub Actions

- [Action Reference](./github-actions/action.md) — Inputs, outputs, and mode
  details
- [Workflow Recipes](./github-actions/workflow-recipes.md) — Copy-pasteable
  workflow examples

### Monorepo

- [Setup Guide](./monorepo/setup.md) — Configure multiple projects, change
  detection, uv workspaces
- [Design Reference](./monorepo/design.md) — Architecture and design decisions
