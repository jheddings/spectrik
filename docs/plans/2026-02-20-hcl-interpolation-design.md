# HCL-Native Interpolation Design

**Date:** 2026-02-20
**Status:** Approved
**Branch:** hcl-interp

## Problem

Jinja2 pre-processing of HCL files causes syntax conflicts with downstream
content that uses similar delimiters (e.g., GitHub Actions `${{ }}`). The
current workaround of wrapping files in `{% raw %}` blocks leaks templating
concerns into configuration files.

## Solution

Replace Jinja2 with HCL-native `${...}` interpolation using post-parse
variable resolution. This avoids delimiter conflicts since `${...}` is
native HCL syntax that python-hcl2 already parses.

## Design

### New Module: `resolve.py`

A reusable, format-agnostic resolver that walks parsed dicts and resolves
`${...}` references against a context dict.

**`Resolver` class:**

- `__init__(context: dict[str, Any] | None = None)` — stores the context
- `resolve(data: dict[str, Any]) -> dict[str, Any]` — recursively walk
  dict/list structures, resolve `${...}` in string values
- `_resolve_value(value: str) -> str | Any` — resolve interpolations in a
  single string
- `_resolve_ref(ref: str) -> Any` — resolve a dotted reference against the
  context

**Reference resolution:**

- Bare references with dots as attribute/item access: `${name}`,
  `${env.HOME}`, `${config.db.host}`
- Dotted paths walk the context: split on `.`, try `getattr` first then
  `__getitem__` at each step
- Works with dicts, dataclasses, Pydantic models, `os.environ`, etc.

**Type preservation:**

- If a value is entirely a single `${ref}` (e.g., `"${count}"` where count
  is `5`), the resolved value preserves the Python type (returns `5`, not
  `"5"`)
- If `${ref}` is embedded in a larger string (e.g., `"port-${count}"`),
  the resolved value is stringified (`"port-5"`)

**Callable context values:**

- If the final resolved value in the context is callable, invoke it at
  resolution time and use the return value
- Enables dynamic values like `"cwd": os.getcwd` (function reference, not
  invocation)
- Callables are only invoked on the final resolved value, not on
  intermediate steps in a dotted path

**Error handling:**

- Strict mode: undefined references raise immediately
- Error messages include the variable name (file path added by the caller)

### Changes to `hcl.py`

Replace Jinja2 pipeline with `Resolver`:

- **Remove** Jinja2 import and all Jinja2 rendering
- **Pipeline:** read file -> `hcl2.loads()` -> `Resolver.resolve()` ->
  return dict
- `load(file, *, context=None)` — signature unchanged, no API break for
  callers
- `scan(path, *, project_type, recurse, context)` — convenience function
  that creates a Workspace, discovers `.hcl` files, loads each with
  context, returns the populated Workspace
- **Drop `jinja2` from `pyproject.toml` dependencies**

### Changes to `workspace.py`

Workspace becomes format-agnostic:

- **Remove `context` parameter** — context is a loader concern, not a
  container concern
- **`load(data: dict)`** — accepts a pre-parsed, already-resolved dict and
  extracts blueprint/project blocks (no file I/O, no format knowledge)
- **Remove `scan()` method** — file discovery is format-specific, stays in
  `hcl.py`
- **Move resolution logic into Workspace** — `_resolve_blueprint`,
  `_build_project`, `_parse_ops`, `_decode_spec` move from `hcl.py` into
  Workspace (or shared internal module). These are format-independent.

**Dependency direction:** `hcl.py` imports Workspace (one-way). Workspace
has no knowledge of HCL or any file format.

### Usage Patterns

```python
# Convenience entry point
ws = hcl.scan("./configs", project_type=MyProject, context={"env": os.environ})

# Manual loading
ws = Workspace(project_type=MyProject)
for f in hcl_files:
    ws.load(hcl.load(f, context={"env": os.environ}))

# Dynamic context values
context = {
    "cwd": os.getcwd,           # callable, invoked at resolution time
    "name": "myapp",            # static string
    "env": os.environ,          # dict-like, ${env.HOME} via __getitem__
    "config": my_dataclass,     # dataclass, ${config.region} via getattr
}
ws = hcl.scan("./configs", project_type=MyProject, context=context)

# Future: other formats feed the same Workspace
ws = Workspace(project_type=MyProject)
ws.load(yaml.safe_load(some_file.read_text()))
```

### What Is NOT Included

- No HCL-level variable/locals blocks (Python context is sufficient)
- No functions in interpolation syntax (no `${upper(var.name)}`)
- No conditionals or for-expressions
- No pipe/filter syntax

These can be added later without breaking changes if a real need emerges.

## Testing

- **Resolver unit tests** — bare refs, dotted paths, callables, type
  preservation, embedded interpolation, multiple interpolations per string,
  nested structures, strict error messages
- **HCL tests updated** — switch from `{{ }}` to `${...}` syntax, remove
  Jinja2-specific tests (conditionals, loops, filters, raw blocks)
- **Workspace tests updated** — remove context parameter, test `load(dict)`
  interface, verify resolution logic after move
- **Integration tests** — end-to-end pipeline with HCL scanning and
  building
