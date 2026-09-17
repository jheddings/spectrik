package spectrik

import "fmt"

// Strategy names how a spec is applied. The values are the HCL block types.
type Strategy string

const (
	StrategyPresent Strategy = "present"
	StrategyEnsure  Strategy = "ensure"
	StrategyAbsent  Strategy = "absent"
)

// Decoder fills a freshly constructed spec from configuration. The HCL
// loader supplies one that decodes a block body; tests can set fields
// directly. It receives a pointer to the spec struct.
type Decoder func(spec any) error

// opFactory builds an op for a registered spec type. It closes over the
// spec's project type, which keeps the registry itself non-generic.
type opFactory func(strategy Strategy, decode Decoder) (Op, error)

// Registry maps spec type names, as used in HCL blocks, to constructors.
type Registry struct {
	specs map[string]opFactory
}

// NewRegistry returns an empty registry.
func NewRegistry() *Registry {
	return &Registry{specs: make(map[string]opFactory)}
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
