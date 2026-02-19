# Workspace Loader Cleanup

**Date:** 2026-02-18
**Status:** Approved

## Problem

The current `ProjectLoader` API requires consumers to pass a project type and
a `resolve_attrs` callback to a constructor, then call `.load()` on the result.
This feels un-Pythonic — the type parameter reads like Java, and `resolve_attrs`
is an opaque callback disconnected from the domain it serves.

Both consumers use `resolve_attrs` for fundamentally different things:

- **kodex**: structural transformation — renames `source` to `value` and wraps
  `op://` URIs in lazy 1Password resolver callables
- **machina**: string interpolation — replaces `${HOME}` and `${CWD}` in all
  string values

These are distinct concerns forced through a single generic callback.

## Design

Eliminate `ProjectLoader` and `resolve_attrs` entirely. Replace with:

### `Workspace.load(project_type, base_path)` classmethod

Single entry point for loading HCL into a typed workspace. No separate loader
class, no callbacks.

```python
workspace = Workspace.load(KodexProject, hcl_path)
```

### Built-in variable interpolation

spectrik handles string variable expansion during HCL loading:

- **`${env.VAR}`** — reads any environment variable (e.g., `${env.HOME}`,
  `${env.USER}`, `${env.TMPDIR}`)
- **`${CWD}`** — resolves to `os.getcwd()` (not an env var)

The loader walks all string attribute values and expands matching patterns.
Unknown `${env.VAR}` references where the env var is unset expand to empty
string (with a warning log).

### Specs own their value semantics

App-specific attribute transformations move into the specs themselves. For
kodex's 1Password pattern:

- HCL changes from `source = "op://..."` to `value = "op://..."`
- `RepoSecret` detects `op://` URIs in its `value` field and resolves them
  lazily (via Pydantic validator or in the existing `_real_value()` method)

This keeps domain logic in the spec where it belongs, not in a loading hook.

## Consumer API

### kodex

```python
# kodex/cli/__init__.py
import kodex.specs  # noqa: F401 — register specs
workspace = Workspace.load(KodexProject, hcl_path)
```

kodex's `hcl.py` module (which only contained `_resolve_attrs` and the loader
instance) goes away entirely.

### machina

```python
# machina/cli/__init__.py
import machina.specs  # noqa: F401
workspace = Workspace.load(MachinaProject, hcl_dir)
```

machina's `hcl.py` module (which contained `_resolve_vars`, `_init_vars()`,
`_RESOLVE_VARS` dict, and the loader instance) goes away entirely.

### HCL files

machina HCL changes from `${HOME}` to `${env.HOME}`:

```hcl
# before
fonts_target = "${HOME}/Library/Fonts"

# after
fonts_target = "${env.HOME}/Library/Fonts"
```

kodex HCL changes from `source` to `value`:

```hcl
# before
present "secret" {
  name   = "PYPI_TOKEN"
  source = "op://Home Lab/om756s3ftucxfhebwpz2e5c72m/credential"
}

# after
present "secret" {
  name  = "PYPI_TOKEN"
  value = "op://Home Lab/om756s3ftucxfhebwpz2e5c72m/credential"
}
```

## What changes in spectrik

- `Workspace` gains a `load` classmethod that orchestrates
  blueprints → projects → workspace
- The HCL engine gains built-in `${env.VAR}` and `${CWD}` interpolation,
  applied to all string values during spec attribute decoding
- `ProjectLoader` class is removed
- `resolve_attrs` parameter is removed from all loading functions
- Low-level `load_blueprints()` / `load_projects()` remain as lower-level API

## What changes in consumers

### kodex

- Remove `src/kodex/hcl.py` (or reduce to just the import)
- Rename `source` to `value` in all HCL files
- Update `RepoSecret` spec to detect and resolve `op://` URIs in its `value`
  field directly
- Replace `loader.load(path)` with `Workspace.load(KodexProject, path)`

### machina

- Remove `src/machina/hcl.py` (or reduce to just the import)
- Change `${HOME}` to `${env.HOME}` and `${CWD}` to `${CWD}` in HCL files
- Replace `loader.load(path)` with `Workspace.load(MachinaProject, path)`

## What stays the same

- Spec registration via `@spectrik.spec()` decorator
- `Blueprint`, `SpecOp`, `Context` models
- `Project` base model and subclassing pattern
- `Workspace` as a `Mapping[str, P]` (all existing methods)
- Low-level `load_blueprints()` / `load_projects()` for edge cases

## Design decisions

**Why remove `resolve_attrs` instead of improving it:** The two consumers use
it for completely different things (structural transformation vs string
interpolation). Neither pattern benefits from a generic callback — one is better
handled by the spec itself, the other is better handled as a built-in loader
feature.

**Why `${env.VAR}` instead of `${VAR}`:** Namespacing avoids collisions with
future built-in variables and makes it explicit that the value comes from the
environment. `${CWD}` is a built-in because it's not an env var.

**Why specs own value resolution:** The spec already knows what its attributes
mean. `RepoSecret` knows `value` might be a URI that needs resolving — that's
domain logic, not loading logic. Moving it into the spec keeps the loading
pipeline generic.

**Why not `Workspace[KodexProject].load(path)` syntax:** Overriding
`__class_getitem__` to return a loadable object breaks `Workspace[T]` as a
type annotation. Since we don't yet know how consumers will use the type in
annotations, preserving standard generic behavior is safer.

**Why not extensible variable resolution (yet):** Only two consumers exist,
both satisfied by `${env.VAR}` and `${CWD}`. Adding a classmethod or
decorator for custom variables is straightforward later if needed — YAGNI.
