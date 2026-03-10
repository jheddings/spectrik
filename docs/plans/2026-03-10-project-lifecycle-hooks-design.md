# Project Lifecycle Hooks

**Issue**: #29
**Date**: 2026-03-10
**Status**: Proposed

## Problem

Project subclasses often need to perform setup before specs run (e.g.,
validating required fields, resolving secret references) and cleanup
afterward (e.g., closing connections). Today this logic is duplicated in
every spec file as a `_resolve_project()` helper, called at the top of
each `apply()` / `equals()` / `remove()` method.

This is not a validation concern — pydantic validators fire at
construction time, but fields may contain opaque references (like
`op://VAULT/...`) that require side-effectful resolution at execution
time. The preparation must happen lazily, after construction but before
spec execution.

## Solution

Add `@pre_build` and `@post_build` decorators that mark methods on a
`Project` subclass as lifecycle hooks. `Project.build()` discovers and
calls them at the appropriate points.

### Decorator API

```python
import spectrik

class RailwayProject(Project):
    token: str = ""
    project_id: str = ""

    @spectrik.pre_build
    def resolve_secrets(self, ctx: Context) -> None:
        if not self.token:
            raise RuntimeError(f"Project '{self.name}' requires 'token'")
        self.token = resolve_secret(self.token)
        self.project_id = resolve_secret(self.project_id)

    @spectrik.post_build
    def cleanup(self, ctx: Context) -> None:
        close_api_client()
```

### Decorator Implementation

Each decorator is a simple marker that sets an attribute on the method.
No metaclass magic — `Project.build()` discovers hooks by inspecting
the class MRO for marked methods.

```python
def pre_build(method):
    """Mark a Project method to run before blueprint execution."""
    method._spectrik_hook = "pre_build"
    return method

def post_build(method):
    """Mark a Project method to run after blueprint execution."""
    method._spectrik_hook = "post_build"
    return method
```

### Discovery

A helper collects hooks from the class hierarchy:

```python
def _collect_hooks(instance: Project, hook_name: str) -> list[Callable]:
    seen = set()
    hooks = []
    for cls in type(instance).__mro__:
        for attr in vars(cls).values():
            if (
                callable(attr)
                and getattr(attr, "_spectrik_hook", None) == hook_name
                and id(attr) not in seen
            ):
                seen.add(id(attr))
                hooks.append(attr.__get__(instance))
    return hooks
```

Hooks run in MRO order (base class hooks first, then subclass). Multiple
hooks of the same type on the same class run in declaration order.

### Execution Semantics

`Project.build()` wraps blueprint execution with hook calls:

```python
def build(self, *, ctx: Context | None = None, **kwargs) -> bool:
    if ctx is None:
        ctx = Context(target=self, **kwargs)

    logger.info("Building project '%s'", self.name)

    for hook in _collect_hooks(self, "pre_build"):
        hook(ctx)  # raises → build aborts, falls through to post_build

    try:
        results = [bp.build(ctx) for bp in self.blueprints]
        return all(results)
    finally:
        for hook in _collect_hooks(self, "post_build"):
            hook(ctx)
```

**Error handling:**

- `@pre_build` raising an exception aborts the build immediately.
  No specs execute. `@post_build` hooks still run (via `finally`).
- `@post_build` always runs, regardless of build success or failure.
  This mirrors the `try/finally` pattern already used in `SpecOp`.

### Public API

- `spectrik.pre_build` — decorator
- `spectrik.post_build` — decorator

Both re-exported from `__init__.py`.

### What Stays the Same

- Context events (`on_spec_start`, `on_spec_finish`, etc.) — these are
  observability for external consumers, not lifecycle control. Hooks and
  events serve different audiences.
- `SpecOp` strategies — unchanged.
- `Blueprint.build()` — unchanged.
- Existing projects without hooks — unaffected.

### Future Extensibility

The decorator pattern naturally extends to additional hook points
(`@pre_spec`, `@post_spec`, per-blueprint hooks) if use cases emerge.
These are explicitly out of scope for now — no known consumer needs them.

### Scope

Only `@pre_build` and `@post_build` are included. Per-spec hooks are
deferred until a concrete use case appears.
