# Optional `equals()` with `NotImplemented` Default

**Issue**: #19
**Date**: 2026-03-10
**Status**: Approved

## Problem

Specs that manage sensitive values (secrets, tokens, API keys) cannot
implement `equals()` meaningfully because external systems never expose
the secret value. Every consumer independently hardcodes `equals() → False`
as a workaround. This is a universal pattern across any spec wrapping a
secret store.

## Solution

Make `equals()` non-abstract with a default implementation returning
`NotImplemented`. The `Ensure` strategy recognizes this sentinel and
always applies, with distinct logging.

### Specification Changes

- `equals()` becomes non-abstract, default returns `NotImplemented`
- Specs that can check equality override it (as today)
- Specs that can't just don't implement it

```python
class Specification[P](ABC):
    def equals(self, ctx: Context[P]) -> bool:
        """Current state matches desired state.

        Override in subclasses that can check equality. The default
        returns NotImplemented, signaling that equality cannot be
        determined (e.g., for sensitive values like secrets).
        """
        return NotImplemented
```

### Ensure Strategy Changes

- `Ensure` checks the return value of `equals()`
- `NotImplemented` → always apply (distinct log: "equality unknown")
- `True` → skip (as today)
- `False` → apply (as today)
- No build failure — `NotImplemented` is a normal, expected signal

### exists() Default

`exists()` currently defaults to `self.equals(ctx)`. Since `equals()` can
now return `NotImplemented`, `exists()` treats `NotImplemented` as `False`
(resource existence unknown → assume doesn't exist). This keeps `Present`
and `Absent` strategies working correctly.

### Logging/Events

- Existing `on_spec_skipped` and `on_spec_applied` events are sufficient
- `Ensure` logs a distinct message when applying due to `NotImplemented`
  vs `False` (e.g., "equality check not supported" vs "state differs")
- Dry-run output distinguishes the two cases

### What Stays the Same

- `Present` and `Absent` strategies — unaffected (use `exists()`)
- `Project.build()` — untouched
- No new classes, decorators, or flags
- Not a breaking change — existing specs that implement `equals()` work
  identically
