---
title: Tests are written before the code they cover
kind: rule
recorded: 2026-09-18
source: "CLAUDE.md § Testing, migrated 2026-09-18"
tags: [testing, tdd, conventions]
---

**Applies when:** you are about to implement a feature or a bugfix.

Write a failing test first, watch it fail for the reason you expect, then write the code
that makes it pass. Tests live beside the code they cover — `foo.go` and `foo_test.go` —
and prefer table-driven cases on the standard `testing` package. HCL fixtures go under
`testdata/`.

**Why:** this is a library whose behaviour is its product, and the Python
implementation's test suite is the behavioural reference the port is checked against. A
test written after the fact tends to assert what the code does rather than what it
should do, which is exactly the distinction a port depends on.
