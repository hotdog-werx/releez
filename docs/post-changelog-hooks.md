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

Or in `releez.toml`:

```toml
[hooks]
post-changelog = [
  ["uv", "version", "{version}"],
  ["prettier", "--write", "{changelog}"],
]
```

## Template Variables

The following template variables are available in hook commands:

- `{version}` - The release version (e.g., `1.2.3`)
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
