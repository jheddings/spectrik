# Jinja2 Templating for HCL Files

**Date:** 2026-02-20
**Status:** Approved

## Problem

The current variable interpolation system (`${env.VAR}`, `${CWD}`) is a
regex-based post-parse substitution that only operates on flat string
attributes inside spec blocks. It has no public extension point — the
`_BUILTIN_VARS` dict is private — and consumers cannot add custom variables
or use any kind of expression logic.

This was intentional (YAGNI) when only two consumers existed, but as spectrik
matures as a public library, the interpolation story needs to be both more
flexible and more principled. The current system also can't handle structural
templating — conditionally including spec blocks, looping over values, or
generating HCL structure dynamically.

## Design

Replace the regex-based interpolation with Jinja2 **pre-processing** of
entire HCL files. The pipeline becomes:

```
Read raw file text → Jinja2 render with context → python-hcl2 parse → resolve
```

This follows the same pattern as Helm (Jinja2/Go templates over YAML) and
gives consumers full control over what variables and expressions are available.

### Pipeline Change

**Before:**

```
file.open() → hcl2.load() → _decode_spec() calls _interpolate_attrs()
```

**After:**

```
file.read_text() → jinja2.Template(text).render(context) → hcl2.loads(rendered) → _decode_spec()
```

Interpolation moves from post-parse (inside `_decode_spec`) to pre-parse
(inside `load()`). The entire file is a Jinja2 template, not just individual
field values.

### API Changes

`load()`, `scan()`, and `Workspace` gain a `context` parameter:

```python
# hcl.load() — low-level
data = spectrik.hcl.load(path, context={"env": os.environ})

# hcl.scan() — convenience
workspace = spectrik.hcl.scan(
    "/configs",
    project_type=MyProject,
    context={"env": os.environ, "cwd": os.getcwd()},
)

# Workspace — incremental loading
ws = Workspace(project_type=MyProject, context={"platform": "darwin"})
ws.scan("/configs")
ws.load(Path("/extra.hcl"))
```

The `context` parameter is a `dict[str, Any]` passed directly to Jinja2's
`Template.render()`. Default is an empty dict — spectrik provides no built-in
variables. Consumers supply everything they need.

### Jinja2 Configuration

- **Undefined**: `jinja2.StrictUndefined` — referencing an undefined variable
  raises immediately rather than silently producing empty string
- **Autoescape**: Disabled (HCL is not HTML)
- **Keep trailing newline**: Enabled
- **Delimiters**: Standard Jinja2 (`{{ }}`, `{% %}`, `{# #}`) — these do not
  conflict with HCL syntax

### Error Handling

Jinja2 errors (undefined variables, syntax errors) are caught and re-raised
with the source file path included, so consumers can identify which HCL file
has the problem.

### HCL File Syntax

With Jinja2 pre-processing, HCL files can use the full Jinja2 feature set:

```hcl
{# Variable substitution #}
ensure "symlink" {
    target = "{{ env.HOME }}/.config/myapp"
    source = "{{ cwd }}/configs"
}

{# Conditionals #}
{% if platform == "darwin" %}
ensure "homebrew" {
    cask = "iterm2"
}
{% endif %}

{# Loops #}
{% for pkg in packages %}
ensure "package" {
    name = "{{ pkg }}"
}
{% endfor %}
```

### Dependency

Jinja2 becomes a hard dependency of spectrik (added to `pyproject.toml`).
It is lightweight, well-maintained, and has no transitive dependencies beyond
MarkupSafe.

## What Gets Removed

All regex-based interpolation machinery in `hcl.py`:

- `_VAR_PATTERN` regex
- `_BUILTIN_VARS` dict
- `_expand_var()` function
- `_interpolate_value()` function
- `_interpolate_attrs()` function
- The `_interpolate_attrs(attrs)` call inside `_decode_spec()`
- All tests for the old interpolation system

## What Changes in `hcl.py`

- `load()` gains a `context` parameter; reads file as text, renders through
  Jinja2, then parses with `hcl2.loads()` (string-based, not file-based)
- `scan()` gains a `context` parameter, passed through to `Workspace`
- `_decode_spec()` no longer calls `_interpolate_attrs()` — values arrive
  already rendered

## What Changes in `Workspace`

- Constructor gains a `context: dict[str, Any] = {}` parameter, stored on
  the instance
- `load()` passes `self.context` to `hcl.load()`
- Resolution pipeline passes `self.context` through to any internal loading

## What Changes in Consumers

Consumers that relied on `${env.VAR}` or `${CWD}` must:

1. Pass their variables via `context={"env": os.environ, "cwd": os.getcwd()}`
2. Update HCL files from `${env.HOME}` to `{{ env.HOME }}` syntax

This is a breaking change. spectrik is pre-1.0, so this is acceptable.

## Design Decisions

**Why Jinja2 instead of a custom resolver registry:** A registry only handles
named variable substitution. Jinja2 gives conditionals, loops, filters, and
template inheritance — structural templating that a registry cannot express.
The Helm precedent shows this pattern works well for declarative config.

**Why pre-parse instead of post-parse:** Post-parse interpolation can only
substitute into existing string values. Pre-parse templating can generate
entire HCL blocks conditionally or via loops, which is the key capability
gain.

**Why empty default context:** spectrik is a library, not an application. It
should not be opinionated about what variables exist. Consumers know their
domain — machina needs `env` and `cwd`, kodex might need vault references,
a Kubernetes tool needs cluster context. Each consumer passes exactly what
it needs.

**Why StrictUndefined:** Silent empty-string expansion (Jinja2's default)
causes hard-to-debug configuration errors. Failing fast on undefined
variables is the safer default for infrastructure-as-code tooling.

**Why hard dependency:** Jinja2 is the standard Python templating library,
has minimal transitive dependencies, and is required for the core loading
pipeline — not an optional feature. Making it optional would add complexity
for no practical benefit.
