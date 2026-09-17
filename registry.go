package spectrik

import (
	"fmt"
	"maps"
	"slices"
)

// Strategy names how a spec is applied. The values are the HCL block types.
type Strategy string

const (
	StrategyPresent Strategy = "present"
	StrategyEnsure  Strategy = "ensure"
	StrategyAbsent  Strategy = "absent"
)

// Decoder fills a freshly constructed spec or project from configuration.
// The HCL loader supplies one that decodes a block body; tests can set
// fields directly. It receives a pointer to the struct.
type Decoder func(v any) error

// opFactory builds an op for a registered spec type. It closes over the
// spec's project type, which keeps the registry itself non-generic.
type opFactory func(strategy Strategy, decode Decoder) (Op, error)

// projectFactory builds a target for a registered project type.
type projectFactory func(decode Decoder) (Target, error)

// Registry maps the names used in HCL blocks to spec and project types.
type Registry struct {
	specs    map[string]opFactory
	projects map[string]projectFactory
}

// NewRegistry returns an empty registry. No project type is registered by
// default; a consumer that wants plain `project` blocks registers
// *Project under that name itself.
func NewRegistry() *Registry {
	return &Registry{
		specs:    make(map[string]opFactory),
		projects: make(map[string]projectFactory),
	}
}

// RegisterSpec registers a constructor for the spec type name. It is a
// function rather than a method because Go methods cannot have their own
// type parameters. Registering a name twice panics, as net/http does for
// a duplicate pattern.
func RegisterSpec[P Target](r *Registry, name string, newSpec func() Spec[P]) {
	if _, dup := r.specs[name]; dup {
		panic(fmt.Sprintf("spectrik: spec type %q already registered", name))
	}
	r.specs[name] = func(strategy Strategy, decode Decoder) (Op, error) {
		spec := newSpec()
		if decode != nil {
			if err := decode(spec); err != nil {
				return nil, fmt.Errorf("spec %s: %w", name, err)
			}
		}
		switch strategy {
		case StrategyPresent:
			return Present[P]{Spec: spec}, nil
		case StrategyEnsure:
			return Ensure[P]{Spec: spec}, nil
		case StrategyAbsent:
			return Absent[P]{Spec: spec}, nil
		}
		return nil, fmt.Errorf("spec %s: unknown strategy %q", name, strategy)
	}
}

// NewOp constructs the named spec, decodes it, and wraps it in the
// strategy. A nil decode leaves the spec at its constructed defaults.
func (r *Registry) NewOp(name string, strategy Strategy, decode Decoder) (Op, error) {
	factory, ok := r.specs[name]
	if !ok {
		return nil, fmt.Errorf("unknown spec type %q", name)
	}
	return factory(strategy, decode)
}

// RegisterProject registers a constructor for the project type name, which
// is the HCL block type consumers write to declare a project of that kind.
// Registering a name twice panics.
func RegisterProject[P Target](r *Registry, name string, newProject func() P) {
	if _, dup := r.projects[name]; dup {
		panic(fmt.Sprintf("spectrik: project type %q already registered", name))
	}
	r.projects[name] = func(decode Decoder) (Target, error) {
		p := newProject()
		if decode != nil {
			if err := decode(p); err != nil {
				return nil, fmt.Errorf("project type %s: %w", name, err)
			}
		}
		return p, nil
	}
}

// NewProject constructs a target of the named project type and decodes it.
// A nil decode leaves it at its constructed defaults.
func (r *Registry) NewProject(name string, decode Decoder) (Target, error) {
	factory, ok := r.projects[name]
	if !ok {
		return nil, fmt.Errorf("unknown project type %q", name)
	}
	return factory(decode)
}

// ProjectTypes returns the registered project type names, sorted.
func (r *Registry) ProjectTypes() []string {
	return slices.Sorted(maps.Keys(r.projects))
}
