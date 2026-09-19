# CLAUDE.md — spectrik

## Overview

spectrik is a public Go library. It provides a generic
specification/blueprint pattern for declarative configuration-as-code
tools. Other projects depend on this library — changes here have
downstream impact.

This tree is the Go port of the Python `spectrik` package. The Python
implementation lives in `main`'s history and remains published on PyPI.
The port's rationale, prior art, and open design decisions are in
`docs/adr/2026-09-17-go-port.md`. Read it before changing the core model.

## Guardrails

- **NEVER commit or push to `main` directly.** Always work in a feature
  branch or worktree. Use `just preflight` before pushing.
- **Do not skip pre-commit hooks** (`--no-verify`) unless explicitly asked.
- **No breaking changes without consideration.** This is a published
  library with downstream consumers. Changing the public API surface
  requires careful thought.
- **No private repo references** — this is a public project.
- **No secrets in code** — tokens, keys, and credentials stay in GitHub
  Secrets or local env files (which are gitignored).
- **Do not create tags manually.** Always use `just release`.

## Architecture

The library is a single flat package, `spectrik`. One concern per file,
with a matching `_test.go` beside it.

- **Spec** — interface for a desired-state resource. `Apply` is required;
  comparison, existence, and removal are optional interfaces detected by
  type assertion.
- **Strategies** — `Present`, `Ensure`, `Absent` implement `Op` and decide
  _when_ a spec runs. Dry-run is handled here, not in specs.
- **Blueprint** — named, ordered collection of ops, composed by `include`.
- **Project** — top-level build target that composes blueprints by `use`.
  Consumers embed it in their own struct to add fields.
- **Context** — runtime state (target, dry-run, hooks) passed to specs.
- **Registry** — maps HCL block names to spec and project types. Explicit
  type with a package-level default; no `init()`-only global state.
- **HCL loading** — built on `hashicorp/hcl/v2` and `gohcl`. Blocks decode
  straight into typed structs; `${...}` is real HCL expression evaluation.

Anything not yet decided is listed under "Design decisions to settle" in
the ADR. Settle it there first, then implement.

## Commit Conventions

Use [Conventional Commits](https://www.conventionalcommits.org/) format:

```
<type>(<scope>): <description>
```

Types: `feat`, `fix`, `chore`, `docs`, `refactor`, `test`, `style`, `perf`

Scope is optional but encouraged (e.g. `fix(hcl): ...`, `feat(workspace): ...`).

Include the issue number when applicable (e.g. `feat: add variables block (#21)`).

## Branch Naming

Use the same type prefixes as commits, followed by a short description:

```
<type>/<short-description>
```

Examples: `feat/hcl-variables`, `fix/resolver-escaping`, `chore/update-deps`

Optionally include the issue number: `feat/21-hcl-variables`

## Development

### Workflow

Use `just` recipes — do not run tools directly:

- `just preflight` — full validation gate (format, vet, tests)
- `just tidy` — auto-format and tidy modules
- `just test` — unit tests with the race detector

### Testing

Follow TDD: write failing tests first, then implement.

- Tests live beside the code they cover (`foo.go` / `foo_test.go`)
- Prefer table-driven tests and the standard `testing` package
- Registries are values, not globals: construct one per test rather than
  saving and restoring package state
- HCL fixtures go under `testdata/`

### Code Style

- Go 1.26+. `gofmt` is the only formatter.
- Doc comments on every exported identifier.
- Return errors; wrap with `%w` and add context at each layer.
- Optional behaviour is an optional interface, never a sentinel value.
- Keep the public API small. Unexported until a consumer needs it.

### Release Process

1. `just release (major|minor|patch)` — runs preflight, tags, and pushes
2. GitHub Actions creates a draft release
3. Human publishes the release
