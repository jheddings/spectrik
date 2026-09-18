---
title: Version tags are created only by just release, never by hand
kind: rule
recorded: 2026-09-18
source: "CLAUDE.md § Guardrails, migrated 2026-09-18"
tags: [release, tags, ci, conventions]
---

**Applies when:** you are about to cut a release, or are tempted to reach for `git tag`.

Run `just release (major|minor|patch)`. Do not create, move, or delete a version tag by
hand.

**Why:** the recipe is a gate, not a convenience. It runs `preflight` and `repo-guard`
first, so a release cannot be cut from a failing tree or a dirty one, and it derives the
next version from the last tag rather than from your memory of it. A hand-made tag skips
both checks and still fires `.github/workflows/release.yaml`, which drafts a GitHub
release from whatever it was pointed at.

A pushed tag is also far harder to retract than it looks. This repository is a Go
module, and the public module proxy caches a version permanently and immutably once it
has seen it — deleting the tag on GitHub does not unpublish it. A wrong tag is corrected
by releasing another version, never by replacing the one you pushed.
