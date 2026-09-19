<!-- almanac-template: 5 -->

# Almanac

Operating knowledge for this repository, recorded by agents for agents and loaded on
demand.

An entry is something an agent working here needs to know and would not otherwise have:
a silent failure mode, a tool that lies, a constraint invisible from the code — or a
convention this repository requires that no amount of reading the code would reveal.
Entries are terse, atomic, and durable. One claim per file.

The **filenames are the index**, and they carry the whole retrieval mechanism. A listing
of claim-shaped slugs tells an agent what this repository already knows and what it will
be held to, without opening anything. Bodies load only when a title looks like it
applies.

Humans are welcome here, but the audience is the next agent — likely one with no memory
of this session, possibly running under a different tool.

## Using the almanac

**Read the listing first, before you need it.** `ls <almanac-dir>/` is the table of
contents: every filename is a claim. Do this when a session starts and when you enter an
unfamiliar area — not once you are stuck. The entries worth most are the ones you would
never think to search for, because you do not yet know they apply.

**Then carry the titles, not the bodies.** Load an entry when its title bears on what
you are about to do. That is the whole economy of the directory: an always-on index of
one line per claim, and a body read only on suspicion.

Three moments should send you back to the listing:

- **Before anything whose failure is silent or costly** — a migration, a deploy, a
  release, a change to CI, anything touching production.
- **The moment something behaves unexpectedly.** Grep before investigating, not after
  getting stuck. One keyword pass is enough; if nothing hits, move on.
- **Before you conclude something is undocumented.** Filenames state claims, so
  `grep -rl --exclude=README.md <keyword> <almanac-dir>/` usually settles it. Exclude
  this file deliberately: it is the contract, not a claim, and it will match almost any
  probe.

**Entries are assertions, not suggestions.** A `rule` is binding — follow it, and raise
a disagreement rather than resolving it yourself. A `fact` carrying a `verify` line can
be re-checked in seconds; run it before acting on anything expensive.

**If a fact contradicts what you are seeing, the entry is a suspect, not an authority.**
Reality wins. An entry that reality has refuted is worth deleting, and correcting one is
worth as much as adding one — a confidently-worded stale fact is worse than no fact,
because it gets acted on without re-derivation.

`<almanac-dir>` is wherever this file lives — conventionally `docs/almanac/`, but the
path is this repository's call. There is no index file to consult and none to maintain.

## Entry format

One claim per file. The filename is a kebab-case slug stating that claim, not the topic
— `migrations-out-of-order-are-silently-skipped.md`, not `migrations.md`;
`branch-names-carry-the-commit-type-prefix.md`, not `branching.md`. The filenames are
the index, so a slug that states a claim is readable knowledge on its own.

Every entry declares a `kind`, and the two behave differently under maintenance.

**`fact`** — something true about the subject that reality can refute. It carries a
`verify` line, and an audit re-runs it.

**`rule`** — something you are required to do here. Reality cannot refute a rule; only a
decision can change it. It carries no `verify` line and no audit.

The fastest test for which one you are holding: **can this be false without anyone
changing their mind?** Yes, `fact`. No, `rule`.

A fact:

```text
---
title: Out-of-order migrations are silently skipped on deploy
kind: fact
recorded: 2026-08-15
source: "PR #1129"
verify: "`grep -rn -- '--include-all' .github/workflows/` returns nothing"
verified: 2026-08-16
tags: [migrations, deploy, ci, silent-failure]
---

One or two sentences stating the fact plainly.

**Why it matters:** the consequence — what breaks, and whether it breaks loudly.

**What to do:** the corrective action, if there is one.
```

A rule:

```text
---
title: Branch names carry the commit type as a prefix
kind: rule
recorded: 2026-08-15
source: "CONTRIBUTING.md, migrated 2026-08-15"
tags: [git, branches, conventions]
---

**Applies when:** you are about to create a branch.

One or two sentences stating what is required, with an example.

**Why:** the reason the rule exists, and what goes wrong without it.
```

`title`, `kind`, `recorded`, and `source` are required. `source` is a PR, a commit, a
short description of the circumstances a fact was observed in, or — for a rule — where
the decision is recorded and when it moved here.

**`verify` and `verified` belong to facts only.** A check that a rule is being followed
measures compliance, not truth, and a failure would mean somebody broke the rule rather
than that the entry is wrong.

`verified` means exactly one thing: **someone ran the `verify` line on that date and the
claim held.** Never set it on the strength of having read the entry or edited nearby
code — a freshness signal that decouples from an actual re-check launders a stale fact
as a current one.

**Quote any value containing `#` or `:`.** Unquoted, `source: PR #1129` parses as `PR` —
YAML reads the rest as a comment, and nothing warns you. `verify` lines almost always
need quoting.

**No other fields.** Git supplies history and modification times, and every extra field
rots. In particular there is no `confidence` and no `status`: an entry you are not
confident about should not exist.

## Recording new entries

**The `almanac:record` skill does this work.** It owns the admission tests, the
fact/rule decision, how to write a `verify` line that fails when its claim fails, and
the procedure for writing an entry. This section tells you only when to reach for it.

Reach for it when you have just finished being surprised: a debugging session that ended
in "oh, _that's_ why," a green build that hid a real failure, a tool that behaved
differently than its documentation claims, or the discovery that an existing entry is
wrong. Also when a convention becomes binding here, or when you find one living
somewhere an agent will meet it too late to act on.

A candidate is worth recording only if it is all three:

1. **Durable** — still true in six months. How the system _behaves_ and what this
   repository _requires_ both qualify. What we are _currently doing_ does not.
2. **Actionable** — a future agent does something differently for knowing it, at a
   moment you can name. If nothing changes, it is background reading.
3. **Costly to miss** — non-obvious in the moment, or silent and expensive when missed.
   If a competent agent works it out in two minutes, or the mistake is caught loudly the
   first time, leave it out. Failures that look like success are the highest-value
   entries there are.

And it must be true for **this almanac's subject** — this repository, unless the local
block below declares otherwise. For a repository that reads: _would this hold for CI and
for everyone who clones it?_ A claim true only of one person's machine, or of how one
person likes to work, belongs in that agent's private memory however well it passes the
three tests.

Two more things the skill will hold you to, worth knowing before you start. **The title
is the gate** — bodies load lazily, so an entry whose filename does not fire at the
right moment does not exist. And **a rule moved from another document is a move, not a
copy**; leave no second version behind, because two copies diverge and the stale one
wins whichever is read first.

### What doesn't belong here

<!-- almanac:local -->

Prose in this directory wraps at **88 columns**, matching this file. No formatter
enforces it; match the surrounding text by hand.

| If it is...                                        | It goes...                                                    |
| -------------------------------------------------- | ------------------------------------------------------------- |
| Designed intent — how a subsystem is meant to work | `docs/adr/`, or `CLAUDE.md § Architecture` for the core model |
| A spec or implementation plan                      | `docs/specs/` for specs, `docs/plans/` for plans              |
| The status of in-flight work                       | A GitHub issue or PR                                          |
| Your own working preferences                       | Your agent's private memory                                   |
| A fact about your machine, not this repo           | Your agent's private memory                                   |

<!-- /almanac:local -->

Notice which row is **absent**: a rule you are required to follow is not routed
elsewhere. Rules are entries, declared `kind: rule`. What remains excluded is everything
an agent cannot act on at a nameable moment — intent, plans, status — plus everything
true for you and not for the subject.

The design-doc boundary is the one that blurs, so apply it as **intent vs.
requirement**: an architecture note explains how a mechanism was _meant_ to work, and
reading it changes nothing you are about to type. A rule tells you what to type. Same
topic, different job.

### If you cannot load the skill

Some tools read this file but cannot load skills. If you are one of them, **do not write
the entry.** The method is not reconstructable from this contract, an agent cannot
review its own entry, and a plausible entry that is subtly wrong costs more than no
entry at all — it gets trusted instead of checked.

Say so instead, plainly, and stop:

> This finding belongs in the almanac: `the claim, in one sentence`. I cannot record it
> properly without the `almanac` plugin — install it and run `almanac:record`. The
> evidence is in this session's transcript.

That is the whole fallback. Reporting an unrecorded finding is a good outcome; inventing
an entry is not.

## Maintaining the almanac

**Nothing writes here unreviewed, and nothing writes here automatically.** Entries ride
in the PR diff and get reviewed like code — an agent cannot validate its own entry,
because whatever led it to write something wrong would equally lead it to approve it.
There is no background summarizer and no session-end capture.

**Finishing.** Noticing and recording are two different acts, and the second is the one
that gets skipped. Before opening a PR, ask explicitly — _did this branch teach us
anything an entry should carry?_ Answer it out loud, even when the answer is no. Most
branches produce no entry.

**Correcting a fact.** Fix or delete it in the PR where you found it wrong. When a fix
supersedes an entry rather than refuting it, update `recorded` and note what changed.

**Correcting a rule is not an agent's call.** A `kind: rule` entry is changed only by
whoever can change the decision behind it. Observing that nobody follows a rule is
evidence about people, not about the rule. Raise it; do not resolve it.

**Rules cannot be audited, and that is the standing cost of keeping them here.** A fact
has a `verify` line, so an audit re-runs it and a stale fact gets caught. A rule has
nothing to re-run, so it decays in exactly the way this directory exists to prevent.
Review the `kind: rule` entries by hand whenever the surrounding process changes.

**Parallel sessions.** Concurrent worktrees write here at once, so the design avoids
contention: no index file to append to, one claim per file, and duplicates preferred
over conflicts. If you suspect an entry exists but cannot find it, write yours anyway —
a reviewer merging two entries is a minor cleanup; a hand-resolved conflict in a shared
index silently drops content.

## Method vs. local convention

This file is the **local** contract: the subject, the entry format, the destinations
table, the wrap width. The **method** — the admission tests, the fact/rule decision, how
to write a `verify` line, how to re-check a stale entry — is carried by the skills, so
it is maintained in one place and travels between repositories.

**Where a skill and this file disagree about method, the skill wins. Where they disagree
about a convention this file claims as local, this file wins.** That is the reverse of
the obvious anti-drift instinct, and the reason matters: if each repository's README
outranked the shared method, one stale local copy would silently override a corrected
rule, and drift would resolve with the _worse_ copy winning.

The tests above appear here in compressed form so an agent can tell, before loading
anything, whether a finding is worth pursuing. The skill carries them in full. A
difference in wording is expected; a difference in substance is a bug worth reporting.
