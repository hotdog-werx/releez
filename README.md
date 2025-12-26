# releez

releez is a CLI tool for managing semantic versioned releases.

## Usage

Start a release from your repo (requires `git` and `git-cliff` on `PATH`):

`releez release start`

Common options:

- `--bump auto|patch|minor|major`
- `--base main`
- `--changelog CHANGELOG.md`
- `--no-create-pr` (skip GitHub PR creation)
- `--github-token ...` (or set `GITHUB_TOKEN`)
- `--dry-run`

Compute an artifact version for CI:

`releez version artifact`

Common options / env vars:

- `--scheme docker|semver|pep440`
- `--next-version-override ...` (or set `NEXT_VERSION` /
  `__GIT_CLIFF_NEXT_VERSION`)
- `--is-full-release` (or set `RELEEZ_IS_FULL_RELEASE`)
- `--prerelease-type alpha|beta|rc` (or set `RELEEZ_PRERELEASE_TYPE`)
- `--prerelease-number ...` (or set `RELEEZ_PRERELEASE_NUMBER`)
- `--build-number ...` (or set `RELEEZ_BUILD_NUMBER`)
- `--alias-tags none|major|minor` (full releases only)
- `--v-prefix/--no-v-prefix` (when using `--alias-tags`, whether tags are
  `v`-prefixed; default: `--v-prefix`)

Examples:

- Docker PR build:
  `releez version artifact --scheme docker --next-version-override 0.1.0 --prerelease-type alpha --prerelease-number 123 --build-number 456`
  (outputs `0.1.0-alpha123-456`)
- Python PR build:
  `releez version artifact --scheme pep440 --next-version-override 0.1.0 --prerelease-type alpha --prerelease-number 123 --build-number 456`
- Main branch RC build:
  `releez version artifact --scheme docker --next-version-override 0.1.0 --prerelease-type rc --prerelease-number 0 --build-number 456`
  (outputs `0.1.0-rc0-456`)

Create git tags for a release:

`releez release tag` (tags the git-cliff computed release version; pushes tags
to `origin` by default)

Override the tagged version if needed:

`releez release tag --version-override 2.3.4`

Optionally update major/minor tags:

- Major only: `releez release tag --version-override 2.3.4 --alias-tags major`
  (creates `2.3.4` and `v2`)
- Major + minor:
  `releez release tag --version-override 2.3.4 --alias-tags minor` (creates
  `2.3.4`, `v2`, `v2.3`)

Preview what will be published (version and tags):

`releez release preview` (prints markdown to stdout)

`releez release preview --output release-preview.md` (write markdown to a file)

## GitHub recommendations

If you use GitHub PRs, prefer squashing and using the PR title as the squash
commit message:

- Enable “Allow squash merging”
- Set “Default commit message” to “Pull request title”

This keeps your main branch history aligned with semantic PR titles (and works
well with `amannn/action-semantic-pull-request` and changelog generation via
`git-cliff`).
