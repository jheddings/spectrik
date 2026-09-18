# AGENTS.md — spectrik

Instructions shared by every agent working in this repository, whatever tool
it runs under.

## The almanac

`docs/almanac/` holds this repository's operating knowledge — durable facts
about how things actually behave here, and the rules this repository
requires. One claim per file, and the filenames are the index.

That listing is the index and there is no other. A convention this
repository requires is an entry in `docs/almanac/`, not a section of this
file, and nothing restates one here once it is an entry.

- **List it when a session starts** — `ls docs/almanac/` — and carry the
  titles. Load a body only when its title bears on what you are about to do.
- **Grep it the moment something behaves unexpectedly**, before
  investigating rather than after getting stuck. One keyword pass is enough;
  if nothing hits, move on.
- **Consult it before anything whose failure is silent or costly** — a
  release, a change to CI, anything touching published API surface or
  downstream consumers.
- **Follow `docs/almanac/README.md` when recording.** It carries the entry
  format, the admission tests, and where things go that do not belong here.
- **Before finishing a branch, say out loud whether the work taught an
  almanac-worthy claim.** Most branches teach none, and answering "no" is a
  complete answer.

An entry is an assertion, not a suggestion. A `kind: rule` entry is binding:
follow it, and raise a disagreement rather than resolving it yourself. A
`kind: fact` entry is a suspect the moment reality contradicts it — reality
wins, and correcting a stale entry is worth as much as adding one.
