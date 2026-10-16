# AGENTS.md — spectrik

Instructions shared by every agent working in this repository, whatever tool
it runs under.

Codex loads this file directly; Claude Code imports it through
`.claude/CLAUDE.md`. Keep shared repository guidance here and tool-specific
settings in their native configuration.

## The almanac

`docs/almanac/` holds this repository's operating knowledge — durable facts
about how things actually behave here, and the rules this repository
requires. One claim per file, and the filenames are the index.

That listing is the index and there is no other. A convention this
repository requires is an entry in `docs/almanac/`, not a section of this
file, and nothing restates one here once it is an entry.

- **List it when a session starts** — `ls docs/almanac/` — and carry the
  titles. Load a body only when its title bears on what you are about to do.
- **Grep it the moment something behaves unexpectedly**, before
  investigating rather than after getting stuck. One keyword pass is enough;
  if nothing hits, move on.
- **Consult it before anything whose failure is silent or costly** — a
  release, a change to CI, anything touching published API surface or
  downstream consumers.
- **Follow `docs/almanac/README.md` when recording.** It carries the entry
  format, the admission tests, and where things go that do not belong here.
- **Before finishing a branch, say out loud whether the work taught an
  almanac-worthy claim.** Most branches teach none, and answering "no" is a
  complete answer.

An entry is an assertion, not a suggestion. A `kind: rule` entry is binding:
follow it, and raise a disagreement rather than resolving it yourself. A
`kind: fact` entry is a suspect the moment reality contradicts it — reality
wins, and correcting a stale entry is worth as much as adding one.

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

- **Do not skip git hooks** (`--no-verify`) unless explicitly asked.
- **No breaking changes without consideration.** This is a published
  library with downstream consumers. Changing the public API surface
  requires careful thought.
- **No secrets in code** — tokens, keys, and credentials stay in GitHub
  Secrets or local env files (which are gitignored).

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
index; see "The almanac" above for how to use it.

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
