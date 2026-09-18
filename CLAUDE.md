# CLAUDE.md — spectrik

Also read `AGENTS.md` — it carries instructions shared by every agent
working here, including the almanac.

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

- **Do not skip pre-commit hooks** (`--no-verify`) unless explicitly asked.
- **No breaking changes without consideration.** This is a published
  library with downstream consumers. Changing the public API surface
  requires careful thought.
- **No secrets in code** — tokens, keys, and credentials stay in GitHub
  Secrets or local env files (which are gitignored).

## Architecture

The library is a single flat package, `spectrik`, following the layout of
its predecessor `go-spec`. One concern per file, with a matching
`_test.go` beside it.

- **Spec** — interface for a desired-state resource. `Apply` is required;
  comparison, existence, and removal are optional interfaces detected by
  type assertion.
- **Strategies** — `Present`, `Ensure`, `Absent` implement `Op` and decide
  _when_ a spec runs. Dry-run is handled here, not in specs.
- **Blueprint** — named, ordered collection of ops, composed by `include`.
- **Project** — top-level build target that composes blueprints by `use`.
  Consumers embed it in their own struct to add fields.
- **Context** — runtime state (target, dry-run, hooks) passed to specs.
- **Registry** — maps HCL block names to spec and project types. A
  `*Registry` value passed explicitly to `RegisterSpec` / `RegisterProject`;
  no default registry, and no project type registered by default.
- **HCL loading** — built on `hashicorp/hcl/v2` and `gohcl`. Blocks decode
  straight into typed structs; `${...}` is real HCL expression evaluation.

Anything not yet decided is listed under "Design decisions to settle" in
the ADR. Settle it there first, then implement.

## Conventions

This repository's conventions — commits, branches, markdown, worktrees,
releases, testing, tooling — are recorded in `docs/almanac/`, one entry
each, and those entries are the only copy. `ls docs/almanac/` is the
index; see `AGENTS.md` for how to use it.

## Development

### Code Style

- Go 1.26+. `gofmt` is the only formatter.
- Doc comments on every exported identifier.
- Return errors; wrap with `%w` and add context at each layer.
- Optional behaviour is an optional interface, never a sentinel value.
- Keep the public API small. Unexported until a consumer needs it.

### Release Process

Cutting a release is `just release (major|minor|patch)`; see
`docs/almanac/` for the rule and why tags are never made by hand. Pushing
the tag triggers `.github/workflows/release.yaml`, which drafts a GitHub
release. A human reviews and publishes it.
