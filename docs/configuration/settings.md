# Configuration Settings

## Precedence

Settings are resolved in this order (highest wins):

1. **CLI flags** — e.g. `--base main`, `--alias-versions major`
2. **`RELEEZ_*` environment variables**
3. **`releez.toml`** in the repo root
4. **`pyproject.toml`** under `[tool.releez]`

CLI flags always win. Config files supply defaults.

## Key format

TOML config accepts both `snake_case` and `kebab-case` for all keys:

```toml
base-branch = "main" # kebab-case ✓
base_branch = "main" # snake_case ✓  (same setting)
```

Environment variables always use `RELEEZ_` + `UPPER_SNAKE_CASE`. Use `__` for
nested keys:

```bash
RELEEZ_BASE_BRANCH=main
RELEEZ_ALIAS_VERSIONS=major
RELEEZ_HOOKS__CHANGELOG_FORMAT='["prettier","--write","{changelog}"]'
```

## Settings reference

| Setting           | CLI flag                                                                     | Default           | Description                     |
| ----------------- | ---------------------------------------------------------------------------- | ----------------- | ------------------------------- |
| `base_branch`     | `--base` on `release start`                                                  | `master`          | Branch to base releases on      |
| `git_remote`      | `--remote` on `release start` / `release tag`                                | `origin`          | Git remote name                 |
| `pr_labels`       | `--labels` on `release start`                                                | `release`         | Comma-separated PR labels       |
| `pr_title_prefix` | `--title-prefix` on `release start`                                          | `chore(release):` | Prefix for release PR titles    |
| `changelog_path`  | `--changelog-path` on `release start` / `changelog regenerate`               | `CHANGELOG.md`    | Path to changelog file          |
| `create_pr`       | `--create-pr` / `--no-create-pr` on `release start`                          | `false`           | Whether to open a GitHub PR     |
| `alias_versions`  | `--alias-versions` on `release tag` / `release preview` / `version artifact` | `none`            | Create `v1` / `v1.2` alias tags |

Runtime-only flags (`--version-override`, `--scheme`, `--build-number`, etc.)
are not read from config files.

## Examples

### `pyproject.toml`

```toml
[tool.releez]
base-branch = "master"
git-remote = "origin"
alias-versions = "minor"
create-pr = true

[tool.releez.hooks]
post-changelog = [
  ["uv", "version", "{version}"],
  ["prettier", "--write", "{changelog}"],
]
```

### `releez.toml`

```toml
[tool.releez]
base-branch = "main"
git-remote = "origin"
alias-versions = "minor"
create-pr = true

[tool.releez.hooks]
post-changelog = [
  ["uv", "version", "{version}"],
  ["prettier", "--write", "{changelog}"],
]
```

The table structure mirrors `pyproject.toml` exactly — you can copy a
`[tool.releez]` block between files unchanged.

!!! note "Legacy flat format" Older `releez.toml` files with top-level keys (no
`[tool.releez]` header) still work but emit a deprecation warning. Move your
settings under `[tool.releez]` to silence it.

### Environment variables

```bash
export RELEEZ_BASE_BRANCH=main
export RELEEZ_GIT_REMOTE=origin
export RELEEZ_ALIAS_VERSIONS=major
export RELEEZ_CREATE_PR=true
```

## GitHub token

`releez` reads the GitHub token separately from the `RELEEZ_*` settings chain:

1. `RELEEZ_GITHUB_TOKEN`
2. `GITHUB_TOKEN`

Use `RELEEZ_GITHUB_TOKEN` to override the token without affecting other
workflows that depend on `GITHUB_TOKEN`.

The token is only needed when `create_pr = true` or when passing
`--github-token` explicitly.

## Hooks

Post-changelog hooks are configured under `hooks.post-changelog`. See the
[Hooks documentation](./hooks.md) for template variables, execution order, and
common patterns.
