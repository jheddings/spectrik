---
title: A lefthook fixer job repairs the file and exits 0 unless --fail-on-changes is set
kind: fact
recorded: 2026-09-19
source: "Branch lefthook-hooks, replacing pre-commit with lefthook; independently hit during a sibling repository's migration"
verify: "`lefthook run --help` shows `--[no-]fail-on-changes` with `(default: false)`"
verified: 2026-09-19
tags: [ci, lefthook, git-hooks, silent-failure]
---

`lefthook run <hook> --all-files` exits 0 after one of its jobs has rewritten a file.
The `trailing-whitespace` job in `lefthook.yml` is a fixer — it repairs the file in
place and returns success — and in CI there is no commit to carry that repair, so it is
discarded with the runner.

Measured on this branch: a file with trailing whitespace staged, then `lefthook run
pre-commit --all-files --force --no-auto-install --no-stage-fixed` exits 0 with the file
repaired and nothing in the output saying anything changed. The same run with
`--fail-on-changes` exits 1.

**Why it matters:** the failure reads as success. `.github/workflows/precommit.yaml`
runs the hooks as a gate, so without the flag that step passes on exactly the commits it
exists to reject — a green tick while the defect lands on `main`.

**What to do:** keep `--fail-on-changes` on every CI invocation of `lefthook run`, and
add it in the same change as any new job that writes to a file. It is wanted only in
CI: a local `git commit` stages the repair through `stage_fixed` and is meant to pass.
