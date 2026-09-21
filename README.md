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

## Quick Start

Define a project type by embedding `spectrik.Project`, and a spec whose
methods take that project type:

```go
type Machine struct {
    spectrik.Project
    Hostname string `hcl:"hostname,optional"`
}

type Symlink struct {
    Link   string `hcl:"link"`
    Target string `hcl:"target"`
}

func (s *Symlink) Equals(ctx context.Context, m *Machine) (bool, error) {
    cur, err := os.Readlink(s.Link)
    return err == nil && cur == s.Target, nil
}

func (s *Symlink) Apply(ctx context.Context, m *Machine) error {
    return os.Symlink(s.Target, s.Link)
}
```

Register both, load a directory of HCL, and build:

```go
reg := spectrik.NewRegistry()
spectrik.RegisterProject(reg, "machine", func() *Machine { return &Machine{} })
spectrik.RegisterSpec(reg, "symlink", func() spectrik.Spec[*Machine] { return &Symlink{} })

ws, err := spectrik.Load("./hcl", spectrik.Options{
    Registry:  reg,
    Variables: map[string]cty.Value{"env": spectrik.EnvVars()},
})

ctx := spectrik.WithDryRun(context.Background(), dryRun)
for _, name := range ws.Projects() {
    proj, err := ws.Project(name)
    err = spectrik.Build(ctx, proj)
}
```

With HCL like:

```hcl
blueprint "dotfiles" {
  ensure "symlink" {
    link   = "${env.HOME}/.zshrc"
    target = "${env.HOME}/dotfiles/zshrc"
  }
}

machine "laptop" {
  hostname = "laptop"
  use      = ["dotfiles"]
}
```

`Present`, `Ensure`, and `Absent` decide when a spec runs; `Comparer`,
`Exister`, and `Remover` are optional interfaces a spec implements when it
can. `WithHooks` attaches callbacks for progress output, and calling it again
layers another set beside the first; `WithContinueOnError` keeps a build going
past a failing spec.

## License

MIT. See [LICENSE](LICENSE).
