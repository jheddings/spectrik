# Mixed Project Types in a Single Workspace

**Issue**: #30
**Date**: 2026-03-10
**Status**: Approved

## Problem

Consumers managing infrastructure across multiple providers need separate
workspaces, separate `hcl.scan()` calls, and duplicated CLI scaffolding per
provider. The provider-specific logic is already isolated in project classes
and specs — the forced separation at the workspace level is pure overhead.

## Solution

A project registry (parallel to the existing spec registry) that lets
multiple `Project` subclasses coexist in a single workspace. HCL block type
names map to registered project classes.

### HCL Example

```hcl
railway "alpha" {
  token = var.railway_token
  ensure "railway_variable" { ... }
}

supabase "staging" {
  token = var.supabase_token
  ensure "supabase_vault_secret" { ... }
}

project "simple" {
  ensure "some_spec" { ... }
}
```

## Design

### Project Registry

New `@spectrik.project("name")` decorator, mirroring `@spectrik.spec("name")`.

- Stores classes in a global `_project_registry` dict
- Base `Project` is auto-registered as `"project"` using the same decorator
- Consumers register subclasses before calling `scan()`:

```python
@spectrik.project("railway")
class RailwayProject(Project):
    token: str
```

### HCL Parsing Changes

- `parse()` consults `_project_registry` to recognize block types — any
  registered name is treated as a project block
- `ProjectRef` gains a `type_name: str` field to carry the registered name
  through to resolution
- `blueprint` remains a reserved block type, handled separately
- Unrecognized top-level block types raise `ValueError`, consistent
  with current behavior for non-`project`/`blueprint` blocks

### Lazy Resolution

- `ProjectRef.resolve()` looks up the class from `_project_registry` using
  `type_name` instead of `workspace.project_type`
- Same lazy pattern as `OperationRef` — registry lookup at access time, not
  parse time
- Consumers must import their project modules (triggering decorators) before
  calling `scan()`, same constraint as the spec registry

### Workspace Changes

**Removed:**
- Generic type parameter `Workspace[P]` — becomes plain `Workspace`
- `project_type` constructor parameter and property
- `project_type` parameter from `scan()`

**Updated `select()` method:**
```python
def select(
    self,
    *,
    name: str | None = None,
    names: Iterable[str] | None = None,
    project_type: type[Project] | None = None,
) -> list[Project]:
```

- `select(name="alpha")` — single project by name (returns a list)
- `select(names=["alpha", "beta"])` — multiple by name
- `select(project_type=RailwayProject)` — all of a type
- `select()` — all projects
- Combinations work (e.g., filter by type and names)
- `name` and `names` merge if both provided

**`filter(names)` becomes a wrapper** around `select(names=names)`.

**Preserved:**
- `Mapping[str, Project]` behavior (`ws["name"]`, iteration, `len()`)
- `ws.get()`, `ws.blueprints`

### What Stays the Same

- Blueprint and spec resolution — untouched
- Variable resolution pipeline — untouched
- `Project.build()` — untouched
- Lazy resolution pattern — untouched

## Breaking Changes

This is a major version bump. Consumer migration:

| Before | After |
|---|---|
| `scan(path, project_type=X)` | `@spectrik.project("x")` on the class, then `scan(path)` |
| `Workspace[CustomProject]` | `Workspace` (holds `Project`) |
| `ws.project_type` | Removed — use `select(project_type=X)` |
| HCL: `project "name" { custom_field = ... }` | HCL: `x "name" { custom_field = ... }` |
