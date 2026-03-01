# GitHub Action Development

## Files

| File                                              | Purpose                                                                     |
| ------------------------------------------------- | --------------------------------------------------------------------------- |
| `action.yaml`                                     | Composite action (root of repo — enables `uses: hotdog-werx/releez@vX.Y.Z`) |
| `.github/tests/test-action-version-artifact.yaml` | Tests for `version-artifact` mode                                           |
| `.github/tests/test-action-finalize.yaml`         | Tests for `finalize` mode (dry-run, single-repo + monorepo)                 |
| `.github/tests/test-action-validate.yaml`         | Tests for `validate` mode (single-repo + monorepo)                          |
| `.github/tests/test-action-guard.yaml`            | Edge case tests (invalid mode, etc.)                                        |
| `.github/workflows/ci-checks.yaml`                | CI workflow — includes the 4 action test suite jobs alongside Python checks |
| `.actrc`                                          | Default `act` flags (platform image, `GITHUB_RUN_NUMBER`)                   |

## Running tests locally with act

```bash
# Run all action tests (all 4 suites sequentially)
poe test-action

# Run a single test suite
poe test-action-version-artifact
poe test-action-finalize
poe test-action-validate
poe test-action-guard

# Or use act directly with verbose output
act workflow_dispatch -W .github/tests/test-action-finalize.yaml --verbose
```

`act` reads `.actrc` automatically — no extra flags needed for the platform
image or `GITHUB_RUN_NUMBER`.

## Action modes

| Mode               | Trigger                             | What it does                                         |
| ------------------ | ----------------------------------- | ---------------------------------------------------- |
| `version-artifact` | Any build workflow                  | Computes version strings across semver/docker/pep440 |
| `validate`         | PR opened/updated on release branch | Previews the release, optionally comments on PR      |
| `finalize`         | PR merged from release branch       | Creates git tags, generates version outputs          |

## Version pinning (same-repo advantage)

The action installs the CLI directly from `github.action_path`:

```bash
uv tool install "${{ github.action_path }}"
```

Because `action.yaml` lives in the same repo as the Python package, the tagged
checkout at `github.action_path` IS the correct version — no separate PyPI
lookup needed. `uses: hotdog-werx/releez@v1.2.3` checks out that exact tag, so
version drift is impossible by construction.

## Output architecture

Step outputs are passed to the final `set-outputs` step via **`env:`** (not
inline `${{ }}` expressions in shell). This avoids shell quoting issues with
multiline values like release notes and version arrays.

```yaml
- name: Set outputs
  id: set-outputs
  env:
    FINALIZE_JSON: ${{ steps.finalize-versions.outputs.json }}
    VA_JSON: ${{ steps.va-compute.outputs.json }}
      ...
  run: |
    # Use $FINALIZE_JSON, $VA_JSON etc. safely as shell variables
```

Multiline outputs (version arrays, release notes) are written with
`printf 'key<<EOF\n%s\nEOF\n'` to avoid the `echo` EOF-on-empty-string footgun.

## Monorepo support

For monorepo release branches (e.g. `release/core-1.2.3`), `detect-from-branch`
returns both the full prefixed version (`version: "core-1.2.3"`) and the plain
semver (`semver_version:
"1.2.3"`).

The action uses these as follows:

| Output                                               | Source                                     | Example      |
| ---------------------------------------------------- | ------------------------------------------ | ------------ |
| `release-version`                                    | `version` (full, with prefix)              | `core-1.2.3` |
| `project`                                            | `project`                                  | `core`       |
| `semver-version`, `docker-version`, `pep440-version` | Computed from `semver_version` (no prefix) | `1.2.3`      |

The `--project <name>` flag is passed to `release tag`, `release notes`, and
`release preview` when a project name is detected, so those commands apply the
correct tag prefix and git-cliff path filtering.

## Branch input for testing

All three modes accept an optional `branch` input:

- **`finalize`**: defaults to `github.head_ref` (the merged PR's head branch)
- **`validate`**: defaults to the current git branch
  (`releez release detect-from-branch` with no flag)
- **`version-artifact` + `detect-from-branch: true`**: defaults to current git
  branch

Pass `branch: release/1.2.3` in tests to avoid needing to physically create and
checkout a release branch in act:

```yaml
- uses: ./
  with:
    mode: finalize
    branch: 'release/1.2.3'
    dry-run: 'true'
```

## CI integration

The action test jobs live in `ci-checks.yaml` alongside the Python checks,
triggering on `pull_request` and `push` to `master`. They call all 4 test suites
**in parallel** using the `workflow_call` trigger.

Locally, `poe test-action` runs all suites **sequentially** (to avoid Docker
contention with `act`). Each suite can also be run independently with its own
`poe` task.

## Adding a new test

1. Choose the appropriate test file based on the mode being tested
2. Add a new job (jobs within a file can run in parallel — no shared state
   between jobs)
3. Set up git state in a dedicated step (`git tag`, `git commit`)
4. **Write a test-specific `cliff.toml`** (see below) — tests must not depend on
   the repo's `cliff.toml`, which could change and may use GitHub API
   integration
5. Run the action with `uses: ./`
6. Assert with `assert_eq` helper — print `OK`/`FAIL` and aggregate into
   `exit $fail`
7. For monorepo tests: write `[[tool.releez.projects]]` config to
   `pyproject.toml` before invoking the action

### Test cliff.toml

All `finalize` and `validate` tests must write a minimal `cliff.toml` before
running the action. This ensures tests:

- Are isolated from changes to the repo's `cliff.toml`
- Do not make GitHub API calls (which require a token and hit rate limits)

```yaml
- name: Write test cliff.toml (no GitHub remote)
  run: |
    cat > cliff.toml << 'TOML'
    [changelog]
    body = """
    {% if version %}## [{{ version | trim_start_matches(pat="v") }}] - {{ timestamp | date(format="%Y-%m-%d") }}
    {% else %}## [unreleased]
    {% endif %}
    {% for group, commits in commits | group_by(attribute="group") %}
    ### {{ group | striptags | trim | upper_first }}
    {% for commit in commits %}
    - {% if commit.scope %}*({{ commit.scope }})* {% endif %}{{ commit.message | upper_first }}
    {% endfor %}
    {% endfor %}
    """
    trim = true
    render_always = true

    [git]
    conventional_commits = true
    filter_unconventional = true
    commit_parsers = [
      { message = "^feat", group = "Features" },
      { message = "^fix", group = "Bug Fixes" },
      { message = "^chore\\(release\\):", skip = true },
      { message = ".*", group = "Other" },
    ]
    filter_commits = false
    topo_order_commits = true
    sort_commits = "oldest"
    TOML
  shell: bash
```

The `version-artifact` tests do not need this because `releez version artifact`
computes versions via git-cliff's `--bumped-version` flag (no changelog
generation, no GitHub API calls).

## Common pitfalls

**`github.head_ref` is empty in `workflow_dispatch`** — use the `branch` input
in tests.

**Monorepo finalize/validate tests need `[[tool.releez.projects]]`** — the test
must write a valid projects config to `pyproject.toml` before invoking the
action, otherwise `detect-from-branch` cannot resolve the project name from the
branch.

**`post-comment: 'false'` in act tests** —
`thollander/actions-comment-pull-request` will fail in act because there's no
real PR. Always set `post-comment: 'false'` for validate mode act tests.

**`continue-on-error: true` on `va-detect`** — `detect-from-branch` is allowed
to fail in `version-artifact` mode (e.g. when not on a release branch). The step
uses `continue-on-error: true` so a non-release branch gracefully falls back to
the explicit `version-override` or git-cliff auto-detection.

**`release-version` vs `semver-version` in monorepo** — `release-version`
contains the full prefixed version (e.g. `core-1.2.3`) to uniquely identify the
project and version. `semver-version`/`docker-version`/`pep440-version` contain
the plain artifact version (`1.2.3`) suitable for docker tags, PyPI, etc.
