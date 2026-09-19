---
title: Registries are values with no package-level default, so tests need no global cleanup
kind: fact
recorded: 2026-09-18
source: "CLAUDE.md § Testing and § Architecture, checked against registry.go 2026-09-18"
verify: "`grep -rn '^var ' *.go | grep -v _test.go` shows no registry variable, and `grep -n 'func RegisterSpec' registry.go` shows it takes an explicit `*Registry`"
verified: 2026-09-19
tags: [testing, registry, go, python-port]
---

There is no package-level registry and no default registry instance. `NewRegistry()`
returns a `*Registry`, and `RegisterSpec` and `RegisterProject` both take one
explicitly. No project type is registered by default either.

**Why it matters:** the Python implementation did the opposite — a module-level
`_spec_registry` that every test had to save, clear, and restore, or bleed state into
the next test. That scaffolding is still visible in `main`'s history and in the ADR's
account of why the Go design changed. Carrying it over produces fixtures that guard
nothing, and reasoning as though a global exists produces tests that appear isolated for
the wrong reason.

**What to do:** construct a fresh registry per test and pass it in. There is no global
state to reset between tests, so no setup or teardown fixture is needed for it.
