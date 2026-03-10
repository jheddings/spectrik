# spectrik

A generic specification and blueprint pattern for declarative configuration-as-code tools.

## Overview

spectrik provides a reusable framework for building tools that apply declarative
configurations to external systems. It includes:

- **Specification** — an abstract base class for defining desired-state resources
- **SpecOp strategies** — `Present`, `Ensure`, and `Absent` wrappers that control
  when specs are applied or removed
- **Blueprint** — a named, ordered collection of spec operations
- **Project** — a top-level build target that orchestrates blueprints, with
  support for multiple project types in a single workspace
- **Workspace** — a lazy-resolving collection of projects built from parsed
  configuration files
- **Lifecycle hooks** — `@pre_build` and `@post_build` decorators for setup
  and teardown on project subclasses
- **HCL loading engine** — parse `.hcl` files into blueprints and projects with
  decorator-based registration

## Installation

```bash
pip install spectrik
```

## Quick Start

```python
import spectrik
from spectrik.hcl import scan

# Register a custom project type
@spectrik.project("myapp")
class MyProject(spectrik.Project):
    api_key: str = ""

# Register specs for HCL block decoding
@spectrik.spec("widget")
class Widget(spectrik.Specification["MyProject"]):
    color: str = "red"

    def equals(self, ctx):
        return current_color() == self.color

    def apply(self, ctx):
        set_color(self.color)

    def remove(self, ctx):
        reset_color()

# Load from HCL files and build
ws = scan("./configs")
ws["myapp"].build(dry_run=True)
```

## Core Concepts

### Specifications

A `Specification[P]` defines a single desired-state resource. Subclasses
implement:

- `apply(ctx)` — create or update the resource (required)
- `equals(ctx)` — return `True` if current state matches desired state
  (optional; defaults to `NotImplemented`)
- `exists(ctx)` — return `True` if the resource exists (optional; defaults
  to the result of `equals()`)
- `remove(ctx)` — delete the resource (optional; raises `NotImplementedError`
  by default for irreversible resources)

When `equals()` is not implemented (e.g., for specs managing secrets or
opaque values), the `Ensure` strategy always applies and logs that
equality is unknown. `Present` and `Absent` fall back to `exists()`.

### SpecOp Strategies

Strategies wrap a spec with conditional execution logic:

| Strategy  | Behavior |
| --------- | -------- |
| `Present` | Apply only if the resource doesn't exist |
| `Ensure`  | Apply if current state doesn't match (or equality is unknown) |
| `Absent`  | Remove if the resource exists |

All strategies support dry-run mode, fire Context events, and handle
errors consistently.

### Projects and Registration

The base `Project` class is a Pydantic model that orchestrates blueprints.
Consumer apps subclass it with domain-specific fields and register it
using `@spectrik.project()`:

```python
@spectrik.project("railway")
class RailwayProject(spectrik.Project):
    token: str = ""
    service_id: str = ""
```

The block type name in HCL maps to the registered project class. Multiple
project types can coexist in a single workspace:

```hcl
railway "api" {
    token      = "${env.RAILWAY_TOKEN}"
    service_id = "abc123"

    use = ["deploy"]
}

project "docs" {
    use = ["static-site"]
}
```

The base `Project` class is automatically registered as the `"project"`
block type.

### Lifecycle Hooks

Project subclasses can define lifecycle hooks using decorators. Hooks run
during `Project.build()` — after construction but before (or after) spec
execution.

```python
@spectrik.project("railway")
class RailwayProject(spectrik.Project):
    token: str = ""

    @spectrik.pre_build
    def resolve_secrets(self, ctx: spectrik.Context) -> None:
        if not self.token:
            raise RuntimeError(f"Project '{self.name}' requires 'token'")
        self.token = resolve_secret(self.token)

    @spectrik.post_build
    def cleanup(self, ctx: spectrik.Context) -> None:
        close_api_client()
```

- `@pre_build` — runs before any specs execute. Raising an exception
  aborts the build. Use this for credential resolution, connection setup,
  or field validation that can't happen at construction time.
- `@post_build` — always runs after specs complete (even on failure),
  like a `finally` block. Use this for cleanup.

Multiple hooks of the same type run in MRO order (base class first).

### Context and Events

`Context` carries runtime state through the build pipeline:

```python
ctx = spectrik.Context(target=project, dry_run=True, continue_on_error=False)
```

- `target` — the project instance being built
- `dry_run` — when `True`, specs report what they would do without making
  changes
- `continue_on_error` — when `True`, the build continues past spec failures

Context provides events for observing spec execution:

```python
ctx.on_spec_start += lambda ctx, op: print(f"Starting {op.spec}")
ctx.on_spec_applied += lambda ctx, op: print(f"Applied {op.spec}")
ctx.on_spec_skipped += lambda ctx, op, reason: print(f"Skipped: {reason}")
ctx.on_spec_failed += lambda ctx, op, err: print(f"Failed: {err}")
ctx.on_spec_finish += lambda ctx, op: print(f"Finished {op.spec}")
ctx.on_spec_removed += lambda ctx, op: print(f"Removed {op.spec}")
```

Events are for external observation (progress bars, logging, metrics).
For project-level setup and teardown, use lifecycle hooks instead.

### Workspace

A `Workspace` is a lazy-resolving `Mapping[str, Project]` built from
parsed HCL files. Projects are resolved fresh on each access.

```python
ws = scan("./configs")

# Access by name
project = ws["myapp"]

# Query by type or name
railway_projects = ws.select(project_type=RailwayProject)
specific = ws.select(name="api")
subset = ws.select(names=["api", "docs"])
```

## HCL Support

spectrik uses [HCL](https://github.com/hashicorp/hcl) as its configuration
language.

```python
import spectrik.hcl as hcl

ws = hcl.scan("./configs", context={
    "env": os.environ,
    "name": "myapp",
    "cwd": os.getcwd,
})

ws["myapp"].build()
```

### Interpolation

String values in HCL files support `${...}` variable interpolation. Pass a
context dict when loading, and spectrik resolves references after parsing.

```hcl
project "app" {
    description = "${name}"
    home        = "${env.HOME}/.config/${name}"
    workdir     = "${cwd}/data"
}
```

Dotted references walk the context using attribute or key access, so dicts,
dataclasses, and Pydantic models all work naturally. If a context value is
callable, it is invoked at resolution time — useful for values like
`"cwd": os.getcwd`.

### Escaping

Use `$$` to produce a literal `$` in the output. This is needed when HCL
values contain template syntax meant for other tools:

| You write in HCL        | Output after interpolation     |
| ----------------------- | ------------------------------ |
| `${name}`               | Resolved from context          |
| `$${name}`              | Literal `${name}`              |
| `$${{ secrets.TOKEN }}` | Literal `${{ secrets.TOKEN }}` |

For example, to embed a GitHub Actions workflow that mixes spectrik
variables with Actions expressions:

```hcl
blueprint "deploy" {
    present "file" {
        path    = ".github/workflows/deploy.yaml"
        content = <<-EOF
        name: Deploy
        on: [push]
        jobs:
          build:
            runs-on: ubuntu-latest
            steps:
              - uses: actions/checkout@v4
              - run: echo "Deploying ${app_name}"
                env:
                  TOKEN: $${{ secrets.GITHUB_TOKEN }}
        EOF
    }
}
```

In this example, `${app_name}` is resolved by spectrik while
`$${{ secrets.GITHUB_TOKEN }}` produces the literal `${{ secrets.GITHUB_TOKEN }}`
that GitHub Actions expects.

## License

MIT
