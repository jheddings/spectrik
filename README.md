# spectrik

A generic specification and blueprint pattern for declarative configuration-as-code tools.

## Overview

spectrik provides a reusable framework for building tools that apply declarative
configurations to external systems. It includes:

- **Specification** — an abstract base class for defining desired-state resources
- **SpecOp strategies** — `Present`, `Ensure`, and `Absent` wrappers that control
  when specs are applied or removed
- **Blueprint** — a named, ordered collection of spec operations
- **Project** — a top-level build target that orchestrates blueprints
- **HCL loading engine** — parse `.hcl` files into blueprints and projects with
  decorator-based spec registration

## Installation

```bash
pip install spectrik
```

## Quick Start

```python
import spectrik
from spectrik.hcl import load_blueprints, load_projects

# Register specs for HCL block decoding
@spectrik.spec("widget")
class Widget(spectrik.Specification["MyProject"]):
    def __init__(self, *, color: str):
        self.color = color

    def equals(self, ctx):
        ...

    def apply(self, ctx):
        ...

    def remove(self, ctx):
        ...

# Load from HCL files
blueprints = load_blueprints(Path("hcl"))
projects = load_projects(Path("hcl"), blueprints, project_type=MyProject)

# Build a project
projects["myapp"].build(dry_run=True)
```

## HCL Support

spectrik uses [HCL](https://github.com/hashicorp/hcl) as its configuration
language. Load `.hcl` files into a `Workspace` to define blueprints and
projects:

```python
import spectrik.hcl as hcl

ws = hcl.scan("./configs", project_type=MyProject, context={
    "env": os.environ,
    "name": "myapp",
    "cwd": os.getcwd,
})

ws["myapp"].build()
```

For manual control, parse individual files and feed them to a Workspace:

```python
from spectrik import Workspace

ws = Workspace(project_type=MyProject)
ws.load(hcl.load(Path("blueprints.hcl"), context={...}))
ws.load(hcl.load(Path("projects.hcl"), context={...}))
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

| You write in HCL | Output after interpolation |
|---|---|
| `${name}` | Resolved from context |
| `$${name}` | Literal `${name}` |
| `$${{ secrets.TOKEN }}` | Literal `${{ secrets.TOKEN }}` |

In **heredoc strings** (`<<-EOF`), `${{ }}` patterns pass through without
escaping because they are not valid interpolation syntax. This makes
heredocs ideal for embedding content like GitHub Actions workflows:

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
                  TOKEN: ${{ secrets.GITHUB_TOKEN }}
        EOF
    }
}
```

In this example, `${app_name}` is resolved by spectrik while
`${{ secrets.GITHUB_TOKEN }}` passes through unchanged for GitHub Actions.
In quoted strings, use `$${{ }}` instead to achieve the same result.

## License

MIT
