# Post-Changelog Hooks

Post-changelog hooks allow you to run custom commands after the changelog is
generated but before committing the release. This is useful for tasks like:

- Updating version numbers in project files
- Running code formatters
- Generating additional release artifacts
- Any other release preparation tasks

## Configuration

Configure hooks in your `pyproject.toml`:

```toml
[tool.releez.hooks]
post-changelog = [
  ["uv", "version", "{version}"],
  ["prettier", "--write", "{changelog}"],
]
```

Or in `releez.toml` (same table structure as `pyproject.toml`):

```toml
[tool.releez.hooks]
post-changelog = [
  ["uv", "version", "{version}"],
  ["prettier", "--write", "{changelog}"],
]
```

## Template Variables

The following template variables are available in hook commands:

- `{version}` - Bare semver version (e.g., `1.2.3`). In monorepo projects the
  tag prefix is stripped, so this is always a plain semver suitable for tools
  like `uv version`.
- `{project_version}` - Full project version as it appears in the git tag (e.g.,
  `core-1.2.3`). Identical to `{version}` for single-repo projects.
- `{changelog}` - Absolute path to the changelog file

Example:

```toml
post-changelog = [
  ["echo", "Releasing version {version}"],
  ["sed", "-i", "s/VERSION = .*/VERSION = {version}/", "config.py"],
]
```

## Hook Execution

Hooks are executed in order:

1. Changelog is generated and prepended
2. Each hook runs sequentially
3. If any hook fails (non-zero exit), the release stops
4. All modified files are staged (not just the changelog)
5. Changes are committed

## Automatic Execution

Hooks run automatically when configured - no CLI flag needed:

```bash
# Hooks from config will run automatically
releez release start
```

## Migration from `changelog-format`

The old `changelog-format` hook and `run-changelog-format` setting are
deprecated. They will continue to work with deprecation warnings.

**Old format:**

```toml
[tool.releez]
run-changelog-format = true # DEPRECATED - remove this

[tool.releez.hooks]
changelog-format = ["prettier", "--write", "{changelog}"] # DEPRECATED
```

**New format:**

```toml
[tool.releez.hooks]
post-changelog = [
  ["prettier", "--write", "{changelog}"],
]
# Runs automatically - no run-post-changelog-hooks flag needed!
```

Key changes:

- Each hook is now an array (note the extra wrapper)
- Hooks run automatically when configured
- Remove `run-changelog-format` setting from config

## Common Use Cases

### Update version in pyproject.toml

```toml
post-changelog = [
  ["uv", "version", "{version}"],
]
```

In single-repo mode releez uses `git add -A`, so any files modified by hooks
(including `uv.lock`) are staged automatically — no explicit `git add` needed.

### uv workspace (monorepo): bump version and update lock file

In a uv workspace, `uv version` (without `--frozen`) bumps the package version
in `pyproject.toml` _and_ re-resolves `uv.lock` in one step. In monorepo mode
releez uses selective staging (only the project directory), so `uv.lock` at the
repo root must be staged explicitly:

```toml
post-changelog = [
  ["uv", "version", "--directory", "packages/my-pkg", "{version}"],
  ["git", "add", "uv.lock"], # only needed in monorepo mode
]
```

See
[Monorepo Setup — uv Workspace Integration](../monorepo/setup.md#uv-workspace-integration)
for a complete example.

### Format multiple files

```toml
post-changelog = [
  ["prettier", "--write", "{changelog}"],
  ["ruff", "format", "."],
]
```

### Update version in multiple places

```toml
post-changelog = [
  ["uv", "version", "{version}"],
  [
    "sed",
    "-i",
    "s/__version__ = .*/__version__ = '{version}'/",
    "src/__init__.py",
  ],
]
```

## Error Handling

If a hook fails:

- The release process stops immediately
- No commit is created
- Working tree remains in modified state
- You can fix the issue and run `releez release start` again

## Notes

- Hooks run from the repository root directory
- Hook commands must be available on PATH
- Each hook is a separate process invocation
- Exit code 0 = success, non-zero = failure
