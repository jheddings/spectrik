---
title: main accepts direct pushes — nothing on GitHub prevents one
kind: fact
recorded: 2026-09-18
source: "Checked while initializing the almanac, 2026-09-18"
verify: "`gh api repos/jheddings/spectrik/branches/main/protection` returns 404 Branch not protected, and `gh api repos/jheddings/spectrik/rulesets` returns []"
verified: 2026-09-21
tags: [git, github, main, guardrails, silent-failure]
---

`main` has no branch protection rule and no repository ruleset. A `git push` to `main`
succeeds, immediately and silently, with no review, no required check, and nothing to
undo it.

**Why it matters:** the only guard is local. The `no-commit-to-main` job in
`lefthook.yaml` refuses a commit made on `main`, but it runs only where the hooks are
installed, `--no-verify` skips it, and it never sees a push — a commit made on a branch
and pushed with `git push origin HEAD:main` gets through untouched. Past the hook, the
usual signal that you are doing something forbidden — the command failing — never
arrives. Worse, `main` is what downstream consumers resolve, so a bad push is live
before anyone notices.

**What to do:** work on a branch or a worktree and open a PR, every time. Before any
push, confirm what you are pushing to — `git rev-parse --abbrev-ref HEAD`. Note that
`just release` ends in `git push && git push --tags`, so running it from `main` pushes
`main`.
