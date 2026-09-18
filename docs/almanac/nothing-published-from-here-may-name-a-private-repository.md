---
title: Nothing published from this repository may name a private one
kind: rule
recorded: 2026-09-18
source: "CLAUDE.md § Guardrails, migrated 2026-09-18 after a private repository name reached a public commit message, three entry source fields, and a PR description in one sitting"
tags: [public, privacy, commits, pull-requests, conventions]
---

**Applies when:** you are about to write anything that leaves this machine — a commit
message, a branch name, a PR title or description, an issue, a review comment, a code
comment, a docstring, or an almanac entry.

This repository is public. Do not name a private repository, an internal hostname, a
private URL, or a filesystem path that reveals private work. This holds even when the
private thing is where the idea came from and naming it would be the honest citation.

**Borrowing the content is fine; naming the source is not.** When you adapt a decision,
a convention, or a technique from somewhere private, attribute it to the decision itself
— "maintainer decision, 2026-09-14" — rather than to the repository you read it in. The
substance transfers; the provenance does not. An entry's `source:` field is the easiest
place to get this wrong, because citing an origin is exactly what the field asks for.

**Why:** the failure is silent and close to irreversible. No hook checks this, so
nothing fails and the push succeeds. Merges to `main` are squashed, so a leaked name in
a commit body or PR title cannot be removed afterwards without a history rewrite, and a
PR description is public the moment it is submitted. Readers outside the project cannot
resolve the reference anyway, so it costs them nothing to remove and costs you a rewrite
to leave in.
