---
title: The module proxy holds a Python-era v1.0.0, so v1.0.x are retracted
kind: fact
recorded: 2026-10-10
source: "v0.6.0 consumer upgrades, 2026-10-10; Python commit 1c1ff84 was tagged v1.0.0"
verify: "`curl -s https://proxy.golang.org/github.com/jheddings/spectrik/@v/v1.0.0.mod` prints only `module github.com/jheddings/spectrik`, a go.mod the proxy synthesized because that tree has none"
verified: 2026-10-10
tags: [release, tags, go-modules, proxy, silent-failure]
---

`proxy.golang.org` serves `v1.0.0` of this module, and it is the Python package's tree
(commit `1c1ff84`, "bump version to 1.0.0"). The tag was deleted from GitHub, but the
proxy keeps every version it has seen. Before the retraction, `go get -u`, `@latest`, and
dependency bots resolved to it and moved Go consumers onto a tree with no Go code in it.

**Why it matters:** Go reads retractions only from the go.mod of the highest version, so
a `retract` in a v0.x release does nothing while v1.0.0 exists. The fix is
`retract [v1.0.0, v1.0.1]` in `go.mod`, carried by a `v1.0.1` tag that sits on a commit
**off `main`**. If it sat on `main`, `just release` would derive the next version from
v1.0.1 rather than from the v0.x line. That hand-made tag was a one-time,
operator-approved exception to
[version tags are created only by just release](version-tags-are-created-only-by-just-release.md).

**What to do:**
- Keep the `retract` directive in `go.mod`.
- Never tag `v1.0.0` or `v1.0.1` again. `just release` refuses any version the proxy
  already has.
- A real Go v1 starts at `v1.1.0` or later.
