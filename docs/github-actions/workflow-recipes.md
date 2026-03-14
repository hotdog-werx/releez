# Workflow Recipes

Practical GitHub Actions workflow patterns using the Releez action. Copy, adjust
the image name / registry / environment, and ship.

---

## Recipe 0 — Validate commit messages against cliff.toml

Enforce that every PR title (and optionally every commit on a PR) follows the
project's `cliff.toml` commit parsers before it can be merged. Because
`releez validate commit-message` reads the same config used at release time,
adding a new type to `cliff.toml` immediately unblocks that type — no separate
validator list to maintain.

### Validate the PR title (squash-and-merge workflow)

In a squash-and-merge workflow the PR title becomes the commit message on
`main`, so validating the title is sufficient for a clean changelog.

```yaml
# .github/workflows/validate-pr-title.yaml
name: Validate PR Title

on:
  pull_request:
    types: [opened, edited, synchronize, reopened]

jobs:
  validate-title:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: hotdog-werx/releez@v0
        with:
          mode: validate-commit
          commit-message: ${{ github.event.pull_request.title }}
```

**What counts as valid**:

- Any type configured as a named parser in `cliff.toml`: `feat`, `fix`, `chore`,
  `ci`, etc.
- `skip = true` parsers (e.g. `chore(release): 1.2.3`) are also valid
- Breaking-change markers are accepted: `feat!:`, `fix(api)!:`
- Scoped variants: `feat(scope):`, `fix(api):`

**What is invalid**:

- Any unrecognised type not present in `cliff.toml` (e.g. `wip:`, `docs:` if not
  configured)
- Non-conventional format: `WIP`, `half-done something`
- Wrong case: `FEAT:`, `Fix:`

### Validate every commit on a PR (rebase/merge-commit workflow)

If your project uses rebase or merge-commit (not squash), every commit on the PR
branch lands on `main` individually, so you may want to validate all of them.

> **Note**: This is unnecessary in squash-and-merge workflows — validate the PR
> title instead (see above). Running both is harmless but redundant.

```yaml
# .github/workflows/validate-commits.yaml
name: Validate Commits

on:
  pull_request:
    types: [opened, synchronize, reopened]

jobs:
  validate-commits:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Validate each commit message
        env:
          BASE: ${{ github.event.pull_request.base.sha }}
          HEAD: ${{ github.event.pull_request.head.sha }}
        run: |
          fail=0
          while IFS= read -r msg; do
            if ! releez validate commit-message "$msg"; then
              fail=1
            fi
          done < <(git log --format=%s "${BASE}..${HEAD}")
          exit $fail
        shell: bash
```

`git log --format=%s` prints the subject line (first line) of each commit.
Adjust to `%B` if you want to validate the full commit body.

---

## Core concepts

| Mode               | When to use                             | Key outputs                                                       |
| ------------------ | --------------------------------------- | ----------------------------------------------------------------- |
| `validate-commit`  | Any PR (validate title or commits)      | none — pass/fail only                                             |
| `validate`         | PR opened / updated on a release branch | `release-preview`, `release-notes`, `validation-status`           |
| `finalize`         | Release PR merged to main               | `release-version`, `release-notes`, semver/docker/pep440 versions |
| `version-artifact` | Every build, on any branch              | semver/docker/pep440 version arrays                               |

The typical lifecycle for a release branch looks like this:

```
release/1.2.3 opened → validate runs → PR comment with preview
release/1.2.3 merged → finalize runs → tag created, GitHub Release published
                                      → build pipeline runs with full-release versions
any push / PR        → version-artifact → prerelease versions for CI builds
```

---

## Recipe 1 — Validate a release PR

Posts a preview comment when a `release/*` PR is opened or updated. Gives
reviewers a chance to see exactly what will be tagged and released before they
merge.

```yaml
# .github/workflows/validate-release.yaml
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
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
          fetch-tags: true

      - id: releez
        uses: hotdog-werx/releez@v0
        with:
          mode: validate
          post-comment: 'true' # updates the same comment on every push

      - name: Fail if validation did not succeed
        if: steps.releez.outputs.validation-status != 'success'
        run: |
          echo "::error::Release validation failed"
          exit 1
```

**What this does**:

- Detects the version from the branch name (`release/1.2.3` → `1.2.3`)
- Runs a dry-run of the release to generate a preview and notes
- Posts / updates a PR comment with both
- Fails the check if the branch name is unparseable or git-cliff errors

**Outputs available**:

```yaml
${{ steps.releez.outputs.release-version }}   # "1.2.3"
${{ steps.releez.outputs.release-preview }}   # markdown changelog preview
${{ steps.releez.outputs.release-notes }}     # markdown notes for GitHub Release
${{ steps.releez.outputs.validation-status }} # "success"
```

---

## Recipe 2 — Finalize a release and publish a GitHub Release

Runs when a release PR is merged. Creates the git tag(s) and opens a GitHub
Release.

```yaml
# .github/workflows/finalize-release.yaml
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
      contents: write # required for tag creation and GitHub Release
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
          fetch-tags: true

      - id: releez
        uses: hotdog-werx/releez@v0
        with:
          mode: finalize
          alias-versions: major # also creates v1, updated on every minor/patch

      - name: Create GitHub Release
        uses: softprops/action-gh-release@v2
        with:
          tag_name: ${{ steps.releez.outputs.release-version }}
          body: ${{ steps.releez.outputs.release-notes }}
          make_latest: true
```

**What this does**:

- Reads the merged PR's head branch (`github.head_ref`) to detect the version
- Creates the exact tag (`1.2.3`) and the alias tag (`v1`)
- Emits semver / docker / pep440 version arrays for downstream jobs
- Opens a GitHub Release with the generated changelog as its body

**Outputs available**:

```yaml
${{ steps.releez.outputs.release-version }}  # "1.2.3"
${{ steps.releez.outputs.semver-versions }}  # "1.2.3\nv1"  (first line = exact version)
${{ steps.releez.outputs.docker-versions }}  # "1.2.3\nv1"
${{ steps.releez.outputs.pep440-versions }}  # "1.2.3"
${{ steps.releez.outputs.release-notes }}    # markdown body for GitHub Release
```

---

## Recipe 3 — Publish a Python package to PyPI

Combines finalize with a PyPI trusted publisher upload.

```yaml
# .github/workflows/publish-pypi.yaml
name: Publish to PyPI

on:
  pull_request:
    types: [closed]
    branches: [main]

jobs:
  publish:
    if: |
      github.event.pull_request.merged == true &&
      startsWith(github.head_ref, 'release/')
    runs-on: ubuntu-latest
    environment: pypi
    permissions:
      contents: write
      id-token: write # required for trusted publishing

    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
          fetch-tags: true

      - id: releez
        uses: hotdog-werx/releez@v0
        with:
          mode: finalize

      - name: Build
        run: |
          pip install uv
          uv build

      - name: Publish to PyPI
        uses: pypa/gh-action-pypi-publish@release/v1

      - name: Create GitHub Release
        uses: softprops/action-gh-release@v2
        with:
          tag_name: ${{ steps.releez.outputs.release-version }}
          body: ${{ steps.releez.outputs.release-notes }}
```

---

## Recipe 4 — Build and push a Docker image

### Simple: single tag per build

```yaml
# .github/workflows/docker.yaml
name: Docker Build

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  build:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write

    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
          fetch-tags: true

      # Full release on merge, prerelease on PRs
      - id: version
        uses: hotdog-werx/releez@v0
        with:
          mode: version-artifact
          is-full-release: ${{ github.event_name == 'push' && github.ref == 'refs/heads/main' }}
          prerelease-number: ${{ github.event.pull_request.number }}
          detect-from-branch: 'true' # reads version from release/* branch name if on one

      - uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - uses: docker/build-push-action@v6
        with:
          push: true
          tags: ${{ steps.version.outputs.docker-versions }}
```

### Advanced: alias tags (v1, v1.2, 1.2.3)

When using `alias-versions: minor`, the `docker-versions` output contains
multiple newline-separated tags. Build a tag list by prefixing each line with
your image name:

```yaml
- id: version
  uses: hotdog-werx/releez@v0
  with:
    mode: version-artifact
    is-full-release: 'true'
    alias-versions: minor
    detect-from-branch: 'true'

- name: Build Docker tag list
  id: tags
  env:
    DOCKER_VERSIONS: ${{ steps.version.outputs.docker-versions }}
  run: |
    IMAGE="ghcr.io/${{ github.repository }}"
    {
      echo 'tags<<EOF'
      while IFS= read -r ver; do
        echo "$IMAGE:$ver"
      done <<< "$DOCKER_VERSIONS"
      echo 'EOF'
    } >> "$GITHUB_OUTPUT"

- uses: docker/build-push-action@v6
  with:
    push: true
    tags: ${{ steps.tags.outputs.tags }}
```

**Full release output** (with `alias-versions: minor`):

```
1.2.3
v1
v1.2
```

**Prerelease output** (no aliases apply):

```
1.2.3-alpha42+789
```

---

## Recipe 5 — Combined pipeline (validate + finalize + build)

A complete setup for a Python + Docker project: validate on PR, finalize on
merge, build on both.

```yaml
# .github/workflows/release.yaml
name: Release

on:
  pull_request:
    branches: [main]
  push:
    branches: [main]

jobs:

  # ── Validate release PR ────────────────────────────────────────────────────
  validate:
    if: |
      github.event_name == 'pull_request' &&
      startsWith(github.head_ref, 'release/')
    runs-on: ubuntu-latest
    permissions:
      contents: read
      pull-requests: write
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
          fetch-tags: true
      - uses: hotdog-werx/releez@v0
        with:
          mode: validate
          post-comment: 'true'

  # ── Finalize release on merge ──────────────────────────────────────────────

  finalize:
    if: |
      github.event_name == 'push' &&
      startsWith(github.event.head_commit.message, 'chore(release):')
    runs-on: ubuntu-latest
    outputs:
      release-version: ${{ steps.releez.outputs.release-version }}
      pep440-versions: ${{ steps.releez.outputs.pep440-versions }}
      docker-versions: ${{ steps.releez.outputs.docker-versions }}
      release-notes: ${{ steps.releez.outputs.release-notes }}
    permissions:
      contents: write
    steps:
      - uses: actions/checkout@v4
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

  # ── Build artifact versions ────────────────────────────────────────────────

  version:
    runs-on: ubuntu-latest
    outputs:
      docker-versions: ${{ steps.releez.outputs.docker-versions }}
      pep440-versions: ${{ steps.releez.outputs.pep440-versions }}
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
          fetch-tags: true
      - id: releez
        uses: hotdog-werx/releez@v0
        with:
          mode: version-artifact
          is-full-release: ${{ github.event_name == 'push' }}
          prerelease-number: ${{ github.event.pull_request.number }}
          detect-from-branch: 'true'
          alias-versions: major

  # ── Build and push Docker ──────────────────────────────────────────────────

  docker:
    needs: version
    runs-on: ubuntu-latest
    permissions:
      packages: write
    steps:
      - uses: actions/checkout@v4
      - name: Build Docker tag list
        id: tags
        env:
          DOCKER_VERSIONS: ${{ needs.version.outputs.docker-versions }}
        run: |
          IMAGE="ghcr.io/${{ github.repository }}"
          {
            echo 'tags<<EOF'
            while IFS= read -r ver; do echo "$IMAGE:$ver"; done <<< "$DOCKER_VERSIONS"
            echo 'EOF'
          } >> "$GITHUB_OUTPUT"
      - uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - uses: docker/build-push-action@v6
        with:
          push: true
          tags: ${{ steps.tags.outputs.tags }}

  # ── Publish to PyPI (release builds only) ─────────────────────────────────

  pypi:
    needs: [finalize, version]
    if: needs.finalize.result == 'success'
    runs-on: ubuntu-latest
    environment: pypi
    permissions:
      id-token: write
    steps:
      - uses: actions/checkout@v4
      - run: uv build
      - uses: pypa/gh-action-pypi-publish@release/v1
```

> **Tip**: The `finalize` job uses the commit message (`chore(release): ...`) as
> a trigger because `github.head_ref` is empty on `push` events. Alternatively,
> trigger on `pull_request: types: [closed]` and check
> `github.event.pull_request.merged`.

---

## Monorepo recipes

### Detect and build changed projects

Run builds only for projects with unreleased changes. Uses
`releez projects changed` to produce a matrix, then fans out to per-project
build jobs.

```yaml
# .github/workflows/build-changed.yaml
name: Build Changed Projects

on:
  pull_request:
    branches: [main]

jobs:
  detect:
    runs-on: ubuntu-latest
    outputs:
      matrix: ${{ steps.detect.outputs.matrix }}
      has-changes: ${{ steps.detect.outputs.has-changes }}
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
          fetch-tags: true
      - run: uv tool install releez

      - id: detect
        run: |
          CHANGED=$(releez projects changed --format json)
          echo "matrix=$(echo "$CHANGED" | jq -c '.include')" >> "$GITHUB_OUTPUT"
          echo "has-changes=$(echo "$CHANGED" | jq 'if .projects | length > 0 then "true" else "false" end' -r)" >> "$GITHUB_OUTPUT"

  build:
    needs: detect
    if: needs.detect.outputs.has-changes == 'true'
    strategy:
      fail-fast: false
      matrix: ${{ fromJson(needs.detect.outputs.matrix) }}
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
          fetch-tags: true

      - id: version
        uses: hotdog-werx/releez@v0
        with:
          mode: version-artifact
          is-full-release: 'false'
          prerelease-number: ${{ github.event.pull_request.number }}
          detect-from-branch: 'true'

      - name: Build ${{ matrix.project }}
        run: |
          echo "Building ${{ matrix.project }} @ $(echo '${{ steps.version.outputs.pep440-versions }}' | head -1)"
          # your project-specific build command here
```

**`releez projects changed --format json` output**:

```json
{
  "projects": ["core", "ui"],
  "include": [
    { "project": "core" },
    { "project": "ui" }
  ]
}
```

### Finalize monorepo releases

Release PRs from a monorepo use branch names like `release/core-1.2.3`. The
action automatically detects the project and strips the prefix for artifact
version computation.

```yaml
# .github/workflows/finalize-release.yaml
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
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
          fetch-tags: true

      - id: releez
        uses: hotdog-werx/releez@v0
        with:
          mode: finalize
          alias-versions: major

      # release-version: "core-1.2.3"  (full, with prefix — use as git tag)
      # project: "core"
      # semver-versions: "1.2.3\nv1"  (first line = plain semver, prefix stripped)
      # docker-versions: "1.2.3\nv1"

      # Extract plain semver (first line, prefix stripped) for release title
      - id: ver
        env:
          SEMVER_VERSIONS: ${{ steps.releez.outputs.semver-versions }}
          PEP440_VERSIONS: ${{ steps.releez.outputs.pep440-versions }}
        run: |
          echo "semver=$(echo "$SEMVER_VERSIONS" | head -1)" >> "$GITHUB_OUTPUT"
          echo "pep440=$(echo "$PEP440_VERSIONS" | head -1)" >> "$GITHUB_OUTPUT"
        shell: bash

      - name: Create GitHub Release
        uses: softprops/action-gh-release@v2
        with:
          tag_name: ${{ steps.releez.outputs.release-version }}
          name: '${{ steps.releez.outputs.project }} ${{ steps.ver.outputs.semver }}'
          body: ${{ steps.releez.outputs.release-notes }}

      - name: Build and publish ${{ steps.releez.outputs.project }}
        run: |
          PROJECT="${{ steps.releez.outputs.project }}"
          VERSION="${{ steps.ver.outputs.pep440 }}"
          echo "Publishing $PROJECT @ $VERSION"
          # e.g. uv build --directory "packages/$PROJECT"
```

---

## Tips

### Filter to release branches only

Add a `paths` or `branches` filter if your repo has many non-release PRs to
avoid wasting CI minutes on the `validate` job:

```yaml
on:
  pull_request:
    branches: [main]
    types: [opened, synchronize, reopened]

jobs:
  validate:
    if: startsWith(github.head_ref, 'release/')
```

### Reuse finalize outputs in downstream jobs

Emit finalize outputs and consume them with `needs`:

```yaml
jobs:
  finalize:
    outputs:
      docker-versions: ${{ steps.releez.outputs.docker-versions }}
    steps:
      - id: releez
        uses: hotdog-werx/releez@v0
        with:
          mode: finalize

  docker:
    needs: finalize
    steps:
      - run: echo "${{ needs.finalize.outputs.docker-versions }}"
```

### Dry-run finalize in tests

Set `dry-run: 'true'` to compute and emit all version outputs without creating
tags. Useful for debugging or testing your workflow logic in a branch:

```yaml
- uses: hotdog-werx/releez@v0
  with:
    mode: finalize
    dry-run: 'true'
```

### Prerelease type by event

Pick a semantically meaningful prerelease type based on the GitHub event:

```yaml
- id: version
  uses: hotdog-werx/releez@v0
  with:
    mode: version-artifact
    is-full-release: 'false'
    prerelease-type: ${{ github.event_name == 'pull_request' && 'alpha' || 'rc' }}
    prerelease-number: ${{ github.event.pull_request.number }}
    build-number: ${{ github.run_number }}
```

Output examples:

- PR build: `1.2.3-alpha42+789` (semver), `1.2.3-alpha42-789` (docker),
  `1.2.3a42.dev789` (pep440)
- Post-merge: `1.2.3-rc.0+789`
