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

## License

MIT
