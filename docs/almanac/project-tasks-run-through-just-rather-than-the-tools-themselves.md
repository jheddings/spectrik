---
title: Project tasks run through just, not the underlying tools
kind: rule
recorded: 2026-09-18
source: "CLAUDE.md § Workflow, migrated 2026-09-18"
tags: [tooling, just, workflow, conventions]
---

**Applies when:** you are about to run a build, format, vet, test, or release command.

Use the `.justfile` recipes rather than invoking the tool directly:

- `just preflight` — the full gate: `check` then `test`
- `just check` — `gofmt -l` and `go vet ./...`
- `just tidy` — `go mod tidy` and `gofmt -w .`
- `just test` — `go test -race ./...`

**Why:** the recipes are the contract CI runs against, so a bare `go test` can pass
while `just test` fails — the recipe adds `-race`, and a data race is invisible without
it. The recipes are also where setup is attached: `just tidy` depends on `setup`, which
installs the pre-commit hooks. Running the tools directly quietly skips all of that.
