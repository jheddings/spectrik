# Design: Progress Callbacks for Spec Execution (#20)

## Problem

Consumers use Rich spinners and progress indicators but can only report at
the project level. There's no way to hook into per-spec execution for
granular progress reporting without subclassing or monkey-patching.

## Solution

Add a lightweight `Event` class (adapted from juliet) and emit per-spec
lifecycle events from the SpecOp build chain via `Context`.

## Event Class

New module `src/spectrik/event.py` — a callable list with `+=`/`-=`
handler registration. Adapted from juliet's `Event` pattern.

## Events on Context

Six `Event` attributes initialized in `Context.__init__`:

| Event | Signature | When |
|---|---|---|
| `on_spec_start` | `(ctx, op)` | Before any logic runs |
| `on_spec_finish` | `(ctx, op)` | After everything (finally block) |
| `on_spec_applied` | `(ctx, op)` | Spec was applied |
| `on_spec_removed` | `(ctx, op)` | Spec was removed |
| `on_spec_skipped` | `(ctx, op, reason)` | Skipped — includes dry-run |
| `on_spec_failed` | `(ctx, op, error)` | Exception caught, then re-raised |

### Execution Sequence

```
on_spec_start(ctx, op)
try:
    → on_spec_applied / on_spec_removed / on_spec_skipped / on_spec_failed
except:
    on_spec_failed(ctx, op, error)
    raise
finally:
    on_spec_finish(ctx, op)
```

### Skip Reasons

- Present strategy: `"already exists"`
- Ensure strategy: `"up to date"`
- Absent strategy: `"not present"`
- Dry-run present/ensure: `"dry run; would apply"`
- Dry-run absent: `"dry run; would remove"`

## SpecOp Changes

Each strategy (`Present`, `Ensure`, `Absent`) wraps its `__call__` with
`start`/`finish` events and fires the appropriate outcome event. Existing
logging is preserved.

## Project.build() Change

Accept an optional `ctx` parameter so consumers can pre-configure event
handlers before build runs. Falls back to creating a new Context if not
provided.

## Public API

Export `Event` from `__init__.py`.

## Consumer Usage

```python
project = MyProject(name="example", ...)
ctx = Context(target=project)
ctx.on_spec_applied += lambda ctx, op: print(f"Applied {type(op.spec).__name__}")
ctx.on_spec_skipped += lambda ctx, op, reason: print(f"Skipped: {reason}")
project.build(ctx=ctx)
```
