---
title: Commit messages use Conventional Commits format
kind: rule
recorded: 2026-09-18
source: "CLAUDE.md § Commit Conventions, migrated 2026-09-18"
tags: [git, commits, conventions]
---

**Applies when:** you are about to write a commit message, or a PR title.

Commit subjects follow `<type>(<scope>): <description>`. Types are `feat`, `fix`,
`chore`, `docs`, `refactor`, `test`, `style`, `perf`. Scope is optional but encouraged —
`fix(hcl): reject absent on non-removable specs`. Include the issue number when there is
one: `feat: add variables block (#21)`.

Wrap message bodies at 72 columns. They are read in terminals that do not reflow, so
they are the one exception to this repository's other prose wrapping rules.

**Why:** merge commits are disabled here — merges to `main` are squashed, and GitHub
composes the squash commit from the PR title. A title that does not follow the
convention lands verbatim in `main`'s history, where it cannot be corrected without a
rewrite. This is a published library, so that history is what downstream consumers read
when working out what changed.
