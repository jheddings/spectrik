package spectrik_test

import (
	"context"
	"fmt"

	"github.com/jheddings/spectrik"
	"github.com/zclconf/go-cty/cty"
)

// Machine is a consumer project type: spectrik.Project plus its own fields.
type Machine struct {
	spectrik.Project
	Hostname string `hcl:"hostname,optional"`
}

// Note is a consumer spec. Its methods receive the concrete project type.
type Note struct {
	Text string `hcl:"text"`
}

func (n *Note) Apply(ctx context.Context, m *Machine) error {
	fmt.Printf("apply %q on %s\n", n.Text, m.Hostname)
	return nil
}

func newRegistry() *spectrik.Registry {
	reg := spectrik.NewRegistry()
	spectrik.RegisterProject(reg, "machine", func() *Machine { return &Machine{} })
	spectrik.RegisterSpec(reg, "note", func() spectrik.Spec[*Machine] { return &Note{} })
	return reg
}

func loadExample() (*spectrik.Workspace, error) {
	env := cty.ObjectVal(map[string]cty.Value{"USER": cty.StringVal("jason")})
	return spectrik.Load("testdata/example", spectrik.Options{
		Registry:  newRegistry(),
		Variables: map[string]cty.Value{"env": env},
	})
}

func Example() {
	ws, err := loadExample()
	if err != nil {
		fmt.Println(err)
		return
	}

	ctx := context.Background()
	for _, name := range ws.Projects() {
		proj, err := ws.Project(name)
		if err != nil {
			fmt.Println(err)
			return
		}
		if err := spectrik.Build(ctx, proj); err != nil {
			fmt.Println(err)
		}
	}
	// Output:
	// apply "hello jason" on desktop
	// apply "hello jason" on laptop
	// apply "inline!" on laptop
}

func Example_dryRun() {
	ws, err := loadExample()
	if err != nil {
		fmt.Println(err)
		return
	}

	ctx := spectrik.WithDryRun(context.Background(), true)
	ctx = spectrik.WithHooks(ctx, &spectrik.Hooks{
		SpecSkipped: func(e spectrik.Event, reason string) {
			fmt.Printf("%s %s: %s\n", e.Target.Base().Name, e.Strategy, reason)
		},
	})

	proj, _ := ws.Project("laptop")
	if err := spectrik.Build(ctx, proj); err != nil {
		fmt.Println(err)
	}
	// Output:
	// laptop ensure: dry run; would apply (equality unknown)
	// laptop ensure: dry run; would apply (equality unknown)
}

// Blueprints and projects can also be built in Go instead of loaded from
// HCL, for tests, generated configuration, or tools that compose a target
// from another source.

func ExampleNewBlueprint() {
	base := spectrik.NewBlueprint[*Machine]("base").
		Ensure(&Note{Text: "from base"}).
		Build()

	greet := spectrik.NewBlueprint[*Machine]("greet").
		Description("say hello").
		Include(base).
		Ensure(&Note{Text: "hello jason"}).
		Build()

	laptop := spectrik.NewProject(&Machine{Hostname: "laptop"}, "laptop").Use(greet).Build()
	if err := spectrik.Build(context.Background(), laptop); err != nil {
		fmt.Println(err)
	}
	// Output:
	// apply "from base" on laptop
	// apply "hello jason" on laptop
}

func ExampleNewProject() {
	greet := spectrik.NewBlueprint[*Machine]("greet").
		Ensure(&Note{Text: "hello jason"}).
		Build()

	laptop := spectrik.NewProject(&Machine{Hostname: "laptop"}, "laptop").
		Description("Jason's laptop.").
		Use(greet).
		Ensure(&Note{Text: "inline!"}).
		Build()

	if err := spectrik.Build(context.Background(), laptop); err != nil {
		fmt.Println(err)
	}
	// Output:
	// apply "hello jason" on laptop
	// apply "inline!" on laptop
}

func ExampleBlueprintBuilder_EnsureDeferred() {
	// hostname is not known while the chain is written.
	var hostname string

	greet := spectrik.NewBlueprint[*Machine]("greet").
		EnsureDeferred(func() spectrik.Spec[*Machine] {
			return &Note{Text: "hello from " + hostname}
		}).
		Build()

	hostname = "laptop"

	laptop := spectrik.NewProject(&Machine{Hostname: "laptop"}, "laptop").Use(greet).Build()
	if err := spectrik.Build(context.Background(), laptop); err != nil {
		fmt.Println(err)
	}
	// Output:
	// apply "hello from laptop" on laptop
}
