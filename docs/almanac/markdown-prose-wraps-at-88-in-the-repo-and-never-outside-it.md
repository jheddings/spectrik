---
title: Markdown prose wraps at 88 columns in the repo, and is never hand-wrapped outside it
kind: rule
recorded: 2026-09-18
source: "Maintainer decision, 2026-09-18, settling a width this repository had only ever hand-drifted"
tags: [markdown, formatting, conventions]
---

**Applies when:** you are about to write or edit prose — in a repository `.md` file, or
in a PR description, issue body, or review comment.

Inside the repository, wrap markdown prose at 88 columns. **No formatter enforces
this.** There is no `.mdformat.toml` here, `just check` runs only `gofmt` and `go vet`,
and pre-commit checks only trailing whitespace and YAML, so the width is yours to hold
by hand.

New files get 88. **An existing file wrapped narrower keeps its own width** — match what
is around you rather than reflowing it. `CLAUDE.md` and the older `docs/` files sit at
roughly 72 to 78, and rewrapping one to 88 turns a one-line edit into a diff across the
whole file, burying the change you actually made.

Outside the repository the rule inverts. PR descriptions, issue bodies, and review
comments pass through no formatter at all, and GitHub renders their line breaks
literally rather than reflowing them. Write each paragraph as one continuous line and
let the browser wrap.

**Why:** hand-wrapping outside the repository produces visibly ragged text that cannot
be fixed after posting. Inside it, an unenforced width drifts silently — the prose
written before this rule sits anywhere between 72 and 78 columns — and a file whose
paragraphs disagree about where lines end produces reflow noise in every later diff that
touches it.
