# CLAUDE.md — spectrik

## Overview

spectrik is a public Python library on PyPI. It provides a generic
specification/blueprint pattern for declarative configuration-as-code tools.
Other projects depend on this library — changes here have downstream impact.

## Guardrails

- **NEVER commit or push to `main` directly.** Always work in a feature
  branch or worktree. Use `just preflight` before pushing.
- **Do not skip pre-commit hooks** (`--no-verify`) unless explicitly asked.
- **No breaking changes without consideration.** This is a published library
  with downstream consumers. Changing the public API surface, renaming
  modules, or altering behavior requires careful thought.
- **No private repo references** — this is a public project.
- **No secrets in code** — tokens, keys, and credentials stay in GitHub
  Secrets or local env files (which are gitignored).
- **Do not create tags manually.** Always use `just release`.

## Architecture

### Core Abstractions

The library provides a layered composition model:

- **Specification** — generic ABC (`Specification[P]`) defining desired-state
  resources with `equals()`, `apply()`, `remove()`, and optional `exists()`.
- **SpecOp** — strategy wrappers (Present, Ensure, Absent) that control
  _when_ a spec executes. Dry-run is handled here, not in specs.
- **Blueprint** — named, ordered collection of SpecOps.
- **Project** — top-level build target that composes blueprints. Consumer
  apps subclass this with domain-specific fields (e.g. `CustomProject`).
- **Context** — runtime state (`target`, `dry_run`) passed to specs during
  execution.
- **Workspace** — lazy-resolving, typed `Mapping[str, P]` of projects built
  from parsed refs. Each access resolves a fresh instance.

### HCL Loading Pipeline

The `spectrik.hcl` module (accessed via `import spectrik.hcl`, not
re-exported) provides:

- `scan()` — finds `.hcl` files, parses them, returns a ready Workspace
- `parse()` — single file to list of WorkspaceRef
- `load()` — raw HCL dict with optional variable interpolation

HCL blocks map to strategies: `present`, `ensure`, `absent` contain spec
type and attributes. Blueprints use `include` for composition; projects
use `use` to reference blueprints.

### Spec Registry

`@spectrik.spec("name")` registers spec classes in a global
`_spec_registry` dict for HCL block decoding. This is global state —
tests must save/clear/restore it in setup/teardown.

### Variable Resolution

The `Resolver` class in `resolve.py` handles `${...}` interpolation in
HCL-parsed dicts. Key behaviors: type preservation for full-string refs,
dotted path traversal, callable invocation, and `$${...}` escaping.

## Development

### Workflow

Use `just` recipes — do not run tools directly:

- `just preflight` — full validation gate (pre-commit + tests)
- `just tidy` — auto-format, lint-fix, and type-check
- `just test` — unit tests only

If the venv gets stale after dependency changes: `just clobber && just setup`

### Testing

Follow TDD: write failing tests first, then implement.

- Tests mirror `src/spectrik/` structure in `tests/`
- Use `pytest` fixtures (`tmp_path` for HCL file tests)
- The `_spec_registry` is global state — use a fixture that saves, clears,
  and restores it between tests
- Integration tests in `test_integration.py` cover the full HCL-to-build
  pipeline

### Code Style

- Python 3.12+ — use modern syntax (PEP 695 generics, `X | Y` unions)
- Pydantic v2 for models
- `src/` layout with `hatchling` build
- Public API surface is defined by `__init__.py` re-exports

### Release Process

1. `just release (major|minor|patch)` — runs preflight, bumps version,
   tags, and pushes
2. GitHub Actions creates a draft release
3. Human publishes the release, which triggers PyPI publish

### Dependencies

When adding or removing dependencies, also update
`.pre-commit-config.yaml` under the pyright hook's
`additional_dependencies` list so type checking works in pre-commit.
