# spectrik

A specification and blueprint model for declarative configuration-as-code
tools, written in Go.

> **Status:** this is the in-progress Go port of the Python `spectrik`
> package. The Python package remains available on PyPI at its last
> release. The port's rationale and design decisions are recorded in
> [docs/adr/2026-09-17-go-port.md](docs/adr/2026-09-17-go-port.md).

## Overview

spectrik gives a tool a small, fixed vocabulary for describing desired
state and applying it:

- **Spec** — the desired state of one resource, with the logic to check
  and change it
- **Strategy** — `Present`, `Ensure`, and `Absent` wrappers that decide
  when a spec is applied or removed, including dry-run handling
- **Blueprint** — a named, ordered, reusable collection of operations
- **Project** — a build target that composes blueprints, which consumer
  tools extend with their own fields
- **Workspace** — the projects and blueprints loaded from a directory of
  HCL files

Consumers register their spec and project types, point spectrik at a
directory of `.hcl` files, and build the projects they select.

## Installation

```sh
go get github.com/jheddings/spectrik
```

## License

MIT. See [LICENSE](LICENSE).
