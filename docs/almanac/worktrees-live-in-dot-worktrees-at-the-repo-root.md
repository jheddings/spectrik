---
title: Worktrees live in .worktrees/ at the repo root, never under .claude/
kind: rule
recorded: 2026-09-18
source: "Maintainer decision, 2026-09-18, adopting a layout already proven in a sibling project"
tags: [git, worktrees, workflow, conventions]
---

**Applies when:** you are about to create a git worktree.

Create it at `.worktrees/<name>`, relative to the primary repository root:

```text
git worktree add -b <branch> .worktrees/<name> <base>
```

Never create one under `.claude/`, and never nest a worktree inside another worktree.
Tear it down when its branch is merged or abandoned — `git worktree remove`, then `git
worktree prune` — and ask before removing a worktree you did not create, because a
concurrent session may be working in it.

**Why:** `.claude/` belongs to one agent's tooling, and a worktree is not tool state —
it is a checkout that any tool, editor, or human may need to open, so burying it under a
vendor directory hides it from everything except the agent that made it. One predictable
top-level location also makes `git worktree list` legible and lets a single `.gitignore`
line cover every worktree at once.

**Worktrees created before this rule are at `.claude/worktrees/`** and were deliberately
left in place rather than moved while sessions were live. They are not the convention;
do not add to them.
