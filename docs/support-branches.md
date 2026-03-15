# Support Branches

Support branches are long-lived maintenance lines for shipping hotfixes or
backported features on older major versions — for example, releasing `1.5.0`
while `2.x` development continues on the default branch.

## Creating a support branch

Use `releez release support-branch` to create the branch from the correct
starting commit. Releez automatically finds the latest release tag for the
requested major and validates that you're not trying to fork the current latest
major (which doesn't need a support branch).

### Single-repo

```bash
# Creates support/1.x from the latest 1.x.x tag (e.g. 1.4.0)
releez release support-branch 1
```

### Monorepo

```bash
# Creates support/ui-1.x from the latest ui-1.x.x tag (e.g. ui-1.4.0)
releez release support-branch 1 --project ui
```

`--project` is required in monorepo mode and must match a configured project
name.

### Options

| Flag             | Description                                                                                           |
| ---------------- | ----------------------------------------------------------------------------------------------------- |
| `--commit <ref>` | Branch from a specific commit instead of the latest tag. Must be an ancestor of the latest N.x.x tag. |
| `--dry-run`      | Print what would be done without creating the branch.                                                 |

### Custom split point

If you want the support branch to start before the most recent patch release
(e.g. at the commit immediately before a large refactor was merged), use
`--commit`:

```bash
releez release support-branch 1 --commit abc1234
```

The provided commit must be reachable from (i.e., an ancestor of) the latest
1.x.x tag. Releez rejects commits that aren't in the 1.x history.

## Releasing from a support branch

Once on the support branch, use the standard `release start` command:

```bash
# Single-repo
git checkout support/1.x
releez release start

# Monorepo
git checkout support/ui-1.x
releez release start --project ui
```

Releez detects the support branch automatically and:

- Scopes git-cliff versioning to tags in the same major line (e.g. `1.x.x`).
- Uses the support branch as the PR base.
- Rejects versions that would bump to a different major.

## Naming conventions

| Mode                                         | Support branch name    |
| -------------------------------------------- | ---------------------- |
| Single-repo                                  | `support/{major}.x`    |
| Monorepo (project with `tag-prefix = "ui-"`) | `support/ui-{major}.x` |

## Custom branch naming (single-repo only)

If your team already uses a different naming scheme for support branches, set
`maintenance_branch_regex` in your config:

```toml
[tool.releez]
maintenance-branch-regex = '^hotfix/(?P<major>\d+)\.x$'
```

The regex must include a named `major` capture group. This setting applies to
single-repo mode only — monorepo branch detection is automatic from each
project's `tag-prefix`.

## Versioning scope

git-cliff is given a tag pattern scoped to the requested major line:

| Mode                              | Tag pattern used          |
| --------------------------------- | ------------------------- |
| Single-repo on `support/1.x`      | `^1\.[0-9]+\.[0-9]+$`     |
| Monorepo `ui` on `support/ui-1.x` | `^ui\-1\.[0-9]+\.[0-9]+$` |

This means only commits reachable from tags in the 1.x line are considered when
computing the next version and generating the changelog. Changes on the 2.x line
are invisible to the 1.x support release.
