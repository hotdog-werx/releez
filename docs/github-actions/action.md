# GitHub Action Reference

`releez` ships a composite GitHub Action at the root of this repository. Because
the action and the CLI live in the same repo, the pinned tag and the installed
CLI version are always identical — version drift is impossible by construction.

```yaml
- uses: hotdog-werx/releez@v0 # pins the action tag
  with:
    mode: finalize # installs releez==<same version> at runtime
```

## Contents

- [Modes](#modes)
- [Inputs](#inputs)
- [Outputs](#outputs)
- [Mode details](#mode-details)
  - [finalize](#finalize)
  - [validate](#validate)
  - [version-artifact](#version-artifact)
  - [validate-commit](#validate-commit)
- [Monorepo support](#monorepo-support)
- [Workflow recipes](#workflow-recipes)

---

## Modes

| Mode                                    | Typical trigger                    | Purpose                                                         |
| --------------------------------------- | ---------------------------------- | --------------------------------------------------------------- |
| [`finalize`](#finalize)                 | Release PR merged to main          | Create git tags, generate release notes, emit version outputs   |
| [`validate`](#validate)                 | PR opened / updated on `release/*` | Dry-run the release, post a preview comment on the PR           |
| [`version-artifact`](#version-artifact) | Any push or PR                     | Compute artifact version strings (semver / docker / pep440)     |
| [`validate-commit`](#validate-commit)   | PR opened / updated (any PR)       | Check that a commit message is a valid conventional commit type |

---

## Inputs

### Common inputs

| Input              | Required | Default | Description                                                                                                                                                                                                                                                        |
| ------------------ | -------- | ------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `mode`             | Yes      | —       | `finalize`, `validate`, `version-artifact`, or `validate-commit`                                                                                                                                                                                                   |
| `releez-version`   | No       | `''`    | Override the releez CLI version to install. Bare version (`1.2.3`) installs from PyPI; full specifiers (`git+https://github.com/hotdog-werx/releez@branch`) are passed through to `uv tool install` unchanged. Defaults to the version co-located with the action. |
| `is-full-release`  | No       | `true`  | `false` produces prerelease version strings                                                                                                                                                                                                                        |
| `alias-versions`   | No       | `''`    | Optional override for alias tags on full releases: `none`, `major` (adds `v1`), or `minor` (adds `v1` and `v1.2`). When unset, releez config/defaults are used.                                                                                                    |
| `version-override` | No       | `''`    | Explicit version string — skips git-cliff auto-detection                                                                                                                                                                                                           |
| `branch`           | No       | `''`    | Branch name for release detection. Defaults to `github.head_ref` (finalize) or current branch (validate/version-artifact). Useful for testing with `act`.                                                                                                          |

### `finalize` inputs

| Input     | Default | Description                                                        |
| --------- | ------- | ------------------------------------------------------------------ |
| `dry-run` | `false` | Skip tag creation and push; all version outputs are still computed |

### `validate` inputs

| Input          | Default                   | Description                                                                                                    |
| -------------- | ------------------------- | -------------------------------------------------------------------------------------------------------------- |
| `post-comment` | `true`                    | Post / update a PR comment with the release preview and notes                                                  |
| `comment-tag`  | `releez-validate-release` | Identifier for the PR comment — enables updating the same comment on every push instead of creating duplicates |

### `validate-commit` inputs

| Input            | Required | Default | Description                                         |
| ---------------- | -------- | ------- | --------------------------------------------------- |
| `commit-message` | Yes      | `''`    | The commit message to validate against `cliff.toml` |

### `version-artifact` inputs

| Input                | Default             | Description                                                                                                                                                  |
| -------------------- | ------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `detect-from-branch` | `false`             | Auto-detect the version from the current `release/*` branch name. `continue-on-error: true` is set internally, so non-release branches fall back gracefully. |
| `prerelease-type`    | `alpha`             | Prerelease label: `alpha`, `beta`, or `rc`                                                                                                                   |
| `prerelease-number`  | `''`                | Prerelease number, e.g. the PR number. Makes each PR build's version unique.                                                                                 |
| `build-number`       | `github.run_number` | Build number appended as metadata. Defaults to the GitHub run number.                                                                                        |

---

## Outputs

### Release metadata

| Output              | Modes              | Description                                                                                               |
| ------------------- | ------------------ | --------------------------------------------------------------------------------------------------------- |
| `release-version`   | finalize, validate | Full version string as detected from the branch name, e.g. `1.2.3` or `core-1.2.3` for a monorepo project |
| `project`           | finalize, validate | Project name for monorepo releases. Empty for single-repo.                                                |
| `release-notes`     | finalize, validate | Markdown changelog section for the release                                                                |
| `release-preview`   | validate           | Markdown dry-run preview of what will be released                                                         |
| `validation-status` | validate           | `success` when the branch parses and the dry-run completes without error                                  |

### Artifact version arrays

All version outputs are newline-separated strings. With `alias-versions: major`
on a full release they contain multiple entries, e.g.:

```
1.2.3
v1
```

With aliases disabled (for example `alias-versions: none`, or unset with config
defaulting to none) they contain a single entry. The **first line is always the
exact version** (e.g. `1.2.3`); alias tags (e.g. `v1`, `v1.2`) follow on
subsequent lines when aliases are enabled.

| Output            | Description                                                                                 |
| ----------------- | ------------------------------------------------------------------------------------------- |
| `semver-versions` | Newline-separated semver version strings. First line is the exact version; aliases follow.  |
| `docker-versions` | Newline-separated Docker-safe version strings (no `+` in build metadata — uses `-` instead) |
| `pep440-versions` | Newline-separated PEP 440 version strings (aliases not supported for PEP 440)               |
| `semver-version`  | Exact semver version only — first entry of `semver-versions`, no aliases                    |
| `docker-version`  | Exact Docker-safe version only — first entry of `docker-versions`, no aliases               |
| `pep440-version`  | Exact PEP 440 version only — always identical to the first entry of `pep440-versions`       |

Use `semver-version` / `docker-version` / `pep440-version` when downstream steps
should never receive alias tags (e.g. PyPI uploads, GitHub releases). Use the
`*-versions` plural outputs when you need the full alias list (e.g. Docker
multi-tag pushes).

---

## Mode details

### `finalize`

Runs after a release PR is merged. Reads the merged branch name from
`github.head_ref` (or the `branch` input) to determine the version, then:

1. Creates the exact release tag (e.g. `1.2.3`)
2. Creates alias tags if `alias-versions` is set (e.g. `v1`, `v1.2`)
3. Generates release notes from git-cliff
4. Computes artifact version arrays (semver / docker / pep440)

```yaml
name: Finalize Release
on:
  pull_request:
    types: [closed]
    branches: [main]

jobs:
  finalize:
    if: |
      github.event.pull_request.merged == true &&
      startsWith(github.head_ref, 'release/')
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - uses: actions/checkout@v6
        with:
          fetch-depth: 0
          fetch-tags: true

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

**Outputs populated**: `release-version`, `project`, `release-notes`,
`semver-versions`, `docker-versions`, `pep440-versions`.

**Note on `dry-run`**: set `dry-run: 'true'` to skip tag creation while still
computing all outputs. Useful for testing workflow logic on a branch without
accidentally tagging.

---

### `validate`

Runs when a release PR is opened or updated. Reads the current branch name (or
the `branch` input), runs a dry-run of the release, and optionally posts a
comment on the PR with the preview and notes.

```yaml
name: Validate Release
on:
  pull_request:
    branches: [main]

jobs:
  validate:
    if: startsWith(github.head_ref, 'release/')
    runs-on: ubuntu-latest
    permissions:
      contents: read
      pull-requests: write # required for post-comment
    steps:
      - uses: actions/checkout@v6
        with:
          fetch-depth: 0
          fetch-tags: true

      - id: releez
        uses: hotdog-werx/releez@v0
        with:
          mode: validate
          post-comment: 'true'

      - name: Fail if validation did not succeed
        if: steps.releez.outputs.validation-status != 'success'
        run: |
          echo "::error::Release validation failed"
          exit 1
```

**Outputs populated**: `release-version`, `project`, `release-notes`,
`release-preview`, `validation-status`.

**PR comment**: When `post-comment: 'true'` and a real PR exists, the action
uses `thollander/actions-comment-pull-request` to post or update a comment
identified by `comment-tag`. On each push to the release branch the comment is
replaced in-place, keeping the PR timeline clean.

**`post-comment: 'false'` in `act`**: There is no real PR when running locally
with `act`, so always set `post-comment: 'false'` in test workflows.

---

### `version-artifact`

Computes artifact version strings for use in build pipelines. Works on any
branch — not just release branches.

**Version resolution order**:

1. `version-override` input (explicit)
2. Branch detection from `release/*` branch name (if
   `detect-from-branch: 'true'`)
3. git-cliff `--bumped-version` auto-detection

For prereleases the version format is:

| Scheme | Format                           | Example             |
| ------ | -------------------------------- | ------------------- |
| semver | `X.Y.Z-<type><number>+<build>`   | `1.2.3-alpha42+789` |
| docker | `X.Y.Z-<type><number>-<build>`   | `1.2.3-alpha42-789` |
| pep440 | `X.Y.Z<type><number>.dev<build>` | `1.2.3a42.dev789`   |

For full releases (no prerelease) with `alias-versions: major`:

| Scheme | Tags                                       |
| ------ | ------------------------------------------ |
| semver | `1.2.3`, `v1`                              |
| docker | `1.2.3`, `v1`                              |
| pep440 | `1.2.3` (PEP 440 does not support aliases) |

```yaml
- id: version
  uses: hotdog-werx/releez@v0
  with:
    mode: version-artifact
    is-full-release: ${{ github.event_name != 'pull_request' }}
    prerelease-number: ${{ github.event.pull_request.number }}
    detect-from-branch: 'true'
    alias-versions: major
```

**Outputs populated**: `semver-versions`, `docker-versions`, `pep440-versions`.
Release metadata outputs (`release-version`, `project`, `release-notes`) are
populated only when `detect-from-branch: 'true'` and the current branch is a
`release/*` branch.

---

### `validate-commit`

Validates a commit message against the project's `cliff.toml` commit parsers —
the same rules used at release time. This ensures that squash-and-merge commits
produce a clean changelog without maintaining a separate validator config.

A message is **valid** if it matches any named parser in `cliff.toml`, including
`skip = true` parsers (e.g. `chore(release): 1.2.3`). Any unrecognised type or
non-conventional format exits 1.

```yaml
- uses: hotdog-werx/releez@v0
  with:
    mode: validate-commit
    commit-message: ${{ github.event.pull_request.title }}
```

**What this does**:

- Derives a validation config from the project's `cliff.toml` with three
  overrides: `filter_unconventional = false`, `fail_on_unmatched_commit = true`,
  and catch-all parsers (`message = ".*"`) removed
- Runs `releez validate commit-message "<message>"` and exits 0 or 1 accordingly
- Fails the step (and the workflow job) if the message does not match any parser

**Outputs populated**: none — this mode is purely a pass/fail check.

**Tip**: combine with `pull_request_target` if you need to validate PRs from
forks (the workflow must have access to the repo's `cliff.toml`).

---

## Monorepo support

When the repo has `[[tool.releez.projects]]` configured, release branches use
the format `release/<tag-prefix><version>`, e.g. `release/core-1.2.3`.

The action detects the project automatically:

| Output            | Example      | Description                                                 |
| ----------------- | ------------ | ----------------------------------------------------------- |
| `release-version` | `core-1.2.3` | Full version with prefix — use as the git tag name          |
| `project`         | `core`       | Project name — use to scope downstream steps                |
| `semver-versions` | `1.2.3`      | Plain semver, prefix stripped — first line for artifact use |

```yaml
- id: releez
  uses: hotdog-werx/releez@v0
  with:
    mode: finalize

# Extract plain semver (first line of semver-versions, prefix stripped)
- id: ver
  env:
    SEMVER_VERSIONS: ${{ steps.releez.outputs.semver-versions }}
  run: echo "semver=$(echo "$SEMVER_VERSIONS" | head -1)" >> "$GITHUB_OUTPUT"
  shell: bash

- name: Create GitHub Release
  uses: softprops/action-gh-release@v2
  with:
    tag_name: ${{ steps.releez.outputs.release-version }} # "core-1.2.3"
    name: '${{ steps.releez.outputs.project }} ${{ steps.ver.outputs.semver }}'
    body: ${{ steps.releez.outputs.release-notes }}
```

See [Monorepo Setup Guide](../monorepo/setup.md) for configuring projects,
`include-paths`, and per-project hooks.

---

## Workflow recipes

Complete copy-pasteable workflow examples:

- [Validate commit messages / PR titles](./workflow-recipes.md#recipe-0--validate-commit-messages-against-clifftomll)
- [Validate release PRs](./workflow-recipes.md#recipe-1--validate-a-release-pr)
- [Finalize and create a GitHub Release](./workflow-recipes.md#recipe-2--finalize-a-release-and-publish-a-github-release)
- [Publish to PyPI](./workflow-recipes.md#recipe-3--publish-a-python-package-to-pypi)
- [Build and push Docker images](./workflow-recipes.md#recipe-4--build-and-push-a-docker-image)
- [Full combined pipeline](./workflow-recipes.md#recipe-5--combined-pipeline-validate--finalize--build)
- [Monorepo: detect changed projects](./workflow-recipes.md#monorepo-recipes)
