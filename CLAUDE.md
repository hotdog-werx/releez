# Claude Development Guide

This document provides guidance for AI assistants (Claude) working on the Releez
codebase.

## Quick Reference

- [Linting & Testing](./.claude-docs/linting-testing.md) - How to run tests,
  type checking, and linters
- [Design Principles](./.claude-docs/design-principles.md) - Core design
  philosophy and patterns
- [Testing Practices](./.claude-docs/testing-practices.md) - Testing conventions
  and patterns
- [Monorepo Implementation](./.claude-docs/monorepo-design.md) - Monorepo
  feature design and architecture
- [Code Style](./.claude-docs/code-style.md) - Python code style and conventions

## Overview

Releez is a CLI tool for managing semantic versioned releases. It uses
`git-cliff` for versioning logic and changelog generation, and supports both
single-repo and monorepo workflows.

## Development Workflow

1. **Before making changes**: Read the relevant subsections above
2. **Run tests**: `mise exec -- pytest` (see
   [Linting & Testing](./.claude-docs/linting-testing.md))
3. **Match Codecov patch coverage**:
   `mise exec -- poe check-coverage && mise exec -- uv run coverage xml` (all
   modified lines + modified branches must be covered)
4. **Check types**: `mise exec -- ty check` (see
   [Linting & Testing](./.claude-docs/linting-testing.md))
5. **Check linting**: `mise exec -- ruff check` (see
   [Linting & Testing](./.claude-docs/linting-testing.md))
6. **Fix issues**: `mise exec -- ruff check --fix`

## Key Technologies

- **Python 3.11+**: Modern Python with type hints
- **Typer**: CLI framework
- **Pydantic**: Configuration and validation
- **GitPython**: Git operations
- **git-cliff**: Changelog generation and versioning
- **pytest**: Testing framework
- **mise**: Development environment management

## Project Structure

```
src/releez/
├── cli.py              # CLI commands (Typer app)
├── settings.py         # Configuration (Pydantic models)
├── git_repo.py         # Git operations
├── cliff.py            # git-cliff wrapper
├── release.py          # Release workflow
├── subproject.py       # Monorepo project abstraction
├── version_tags.py     # Tag computation
├── artifact_version.py # Artifact version computation
└── utils.py            # Utilities

tests/
├── unit/               # Unit tests
│   ├── cli/            # CLI command tests
│   └── core/           # Core functionality tests
└── integration/        # Integration tests
```

## Important Notes

- Always use `mise exec --` for running development tools (pytest, ruff, ty)
- Never run `basedpyright` directly - use `mise exec -- ty check` instead
- Use `pytest_mock` (the mocker fixture) instead of `unittest.mock` directly
- Test behavior/outcomes, not internal implementation details
- Keep cyclomatic complexity ≤10 (enforced by ruff)
- All functions should have type hints
- Use `Read` tool before editing files
- Prefer `Edit` over `Write` for existing files

## Getting Help

- Check subsections above for specific topics
- Review test files for examples of patterns and usage
- Check
  [Memory](./.claude/projects/-Users-jamestrousdale-work-personal-releez/memory/MEMORY.md)
  for project-specific learnings
