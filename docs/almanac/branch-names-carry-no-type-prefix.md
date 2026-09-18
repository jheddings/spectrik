---
title: Branch names are a plain description, with no type prefix or issue number
kind: rule
recorded: 2026-09-18
source: "Maintainer decision, 2026-09-14, confirmed for this repository 2026-09-18; replaces CLAUDE.md § Branch Naming, which required a type prefix"
tags: [git, branches, conventions]
---

**Applies when:** you are about to create a branch.

Name it for what the change does, and nothing else:

```text
<short-description>
```

Examples: `go-port`, `almanac-init`, `hcl-variables`, `update-deps`. No `feat/`, `fix/`,
or `chore/` prefix, and no issue number.

**Why:** the type and the issue number already live in the commit message, per
[`commit-messages-use-conventional-commit-format`][commits], and merges to `main` are
squashed, so the commit is the record that survives. Repeating them in the branch name
duplicates metadata into a string that is deleted after merge, and a prefix that
disagrees with the commit's type is worse than no prefix at all.

**This repository's history predates the rule, and so did its own documentation.** Every
human branch through 2026-08-12 carries a prefix — `feat/29-project-lifecycle-hooks`,
`fix/75-heredoc-values`, `chore/renovate-presets` — because `CLAUDE.md § Branch Naming`
required one until this entry replaced it. The two branches in flight when the rule
arrived, `feat/go-port` and `docs/almanac-init`, carry prefixes for the same reason and
were deliberately not renamed. None of them are the convention; do not copy them.

[commits]: commit-messages-use-conventional-commit-format.md
