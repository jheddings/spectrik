# Design: Structured Build Result (#17)

## Problem

`Project.build()` and `Blueprint.build()` return `None`. Consumers have no
visibility into whether a build succeeded or failed without wrapping calls in
try/except. The first exception also halts the entire build with no option to
continue.

## Design

### `continue_on_error` on Context

Add `continue_on_error: bool = False` to `Context`, alongside `dry_run`.
This controls whether a spec failure halts the build or allows it to continue.

### Blueprint.build() returns bool

When `continue_on_error=False` (default), exceptions propagate as today.
Returns `True` on success.

When `continue_on_error=True`, catch exceptions per-spec, fire
`on_spec_failed` as today, and continue to the next op. Returns `False` if
any spec failed, `True` if all succeeded.

### Project.build() returns bool

Collects blueprint results. Returns `True` if all blueprints succeeded,
`False` if any failed. Signature changes from `-> None` to `-> bool`.

### SpecOp unchanged

`SpecOp.__call__()` still raises on failure and fires events as today.
The catch-and-continue logic lives in `Blueprint.build()`.

## Public API Change

`Project.build()` and `Blueprint.build()` return `bool` instead of `None`.
This is backward-compatible -- no existing consumer checks the return value
of a `-> None` method.

## What We're Not Doing

- No `BuildResult` or `SpecResult` objects. The existing event system
  already provides per-spec introspection for consumers who need it.
- No changes to `SpecOp.__call__` signatures.

## Testing

- Default behavior (`continue_on_error=False`): first failure raises,
  returns `True` on success
- Opt-in (`continue_on_error=True`): failures caught, build continues,
  returns `False`, events still fire
- Both modes: events fire correctly for all outcomes
