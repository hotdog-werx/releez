# Regenerating the Changelog

`releez changelog regenerate` rebuilds your entire `CHANGELOG.md` from scratch
by replaying git history through `git-cliff`. This is useful when you:

- Change your `cliff.toml` commit parser rules and want existing history
  reformatted.
- Manually edit or delete changelog entries and want to restore the generated
  content.
- Add or rewrite commits (e.g. with `git rebase`) and need the changelog to
  reflect the new history.
- Bootstrap a changelog for an existing project that never had one.

Unlike `release start`, this command does not bump any version, create a branch,
or open a PR. It only overwrites the changelog file in place.

## Single-repo

```bash
releez changelog regenerate
```

Uses `CHANGELOG.md` by default. Pass `--changelog-path` to target a different
file:

```bash
releez changelog regenerate --changelog-path docs/CHANGELOG.md
```

## Monorepo

Specify one or more projects with `--project`, or regenerate all at once with
`--all`:

```bash
# One project
releez changelog regenerate --project core

# Multiple projects
releez changelog regenerate --project core --project ui

# All configured projects
releez changelog regenerate --all
```

Each project's changelog is written to the path configured under
`changelog-path` in `[[tool.releez.projects]]`.

## Options

| Flag                      | Description                                                         |
| ------------------------- | ------------------------------------------------------------------- |
| `--changelog-path <path>` | Changelog file to write (single-repo only). Default: `CHANGELOG.md` |
| `--project <name>`        | Project to regenerate (repeatable, monorepo only).                  |
| `--all`                   | Regenerate all configured projects (monorepo only).                 |

## Running format hooks

If you have `post-changelog` hooks configured they do **not** run automatically
during `changelog regenerate` — hooks are reserved for the release workflow
(`release start`). To format the changelog after regeneration, run your
formatter manually or chain the commands:

```bash
releez changelog regenerate && prettier --write CHANGELOG.md
```

See [Hooks](./configuration/hooks.md) for how to configure `post-changelog`
hooks in the release workflow.
