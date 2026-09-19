package spectrik

import (
	"context"
	"testing"
)

func TestStrategiesDescribeThemselves(t *testing.T) {
	spec := &labelSpec{Name: "bug", seen: new([]string)}

	tests := []struct {
		op   Op
		want Strategy
	}{
		{Present[*testProject]{Spec: spec}, StrategyPresent},
		{Ensure[*testProject]{Spec: spec}, StrategyEnsure},
		{Absent[*testProject]{Spec: spec}, StrategyAbsent},
	}

	for _, tt := range tests {
		t.Run(string(tt.want), func(t *testing.T) {
			d, ok := tt.op.(Describer)
			if !ok {
				t.Fatalf("%T does not implement Describer", tt.op)
			}
			info := d.Describe()
			if info.Strategy != tt.want {
				t.Errorf("Strategy = %q, want %q", info.Strategy, tt.want)
			}
			if info.Spec != spec {
				t.Errorf("Spec = %#v, want the spec the op wraps", info.Spec)
			}
		})
	}
}

func TestDescribeReachesSpecWithoutKnowingProjectType(t *testing.T) {
	ws := mustLoad(t, map[string]string{
		"config.hcl": `
project "red" {
  ensure "note" { text = "one" }
  absent "note" { text = "two" }
}
`,
	})

	proj, err := ws.Project("red")
	if err != nil {
		t.Fatal(err)
	}

	// A plan or list command walks ops it did not build, so it cannot name
	// the project type to assert Ensure[*testProject].
	var got []string
	for _, bp := range proj.Base().Blueprints {
		for _, op := range bp.Ops {
			d, ok := op.(Describer)
			if !ok {
				t.Fatalf("%T does not implement Describer", op)
			}
			info := d.Describe()
			note, ok := info.Spec.(*noteSpec)
			if !ok {
				t.Fatalf("Spec is %T, want *noteSpec", info.Spec)
			}
			got = append(got, string(info.Strategy)+":"+note.Text)
		}
	}

	if want := "ensure:one,absent:two"; join(got) != want {
		t.Fatalf("described %s, want %s", join(got), want)
	}
}

func TestProjectReturnsFreshOpSlices(t *testing.T) {
	ws := mustLoad(t, map[string]string{
		"config.hcl": `
blueprint "base" {
  ensure "note" {
    text = "one"
  }
}
project "red" { use = ["base"] }
`,
	})

	first, err := ws.Project("red")
	if err != nil {
		t.Fatal(err)
	}
	// Consumers wrap ops in place, so the next resolve must not see it.
	sentinel := opFunc(func(ctx context.Context, t Target) error { return nil })
	first.Base().Blueprints[0].Ops[0] = sentinel

	second, err := ws.Project("red")
	if err != nil {
		t.Fatal(err)
	}
	if _, wrapped := second.Base().Blueprints[0].Ops[0].(opFunc); wrapped {
		t.Fatal("second resolve shares its op slice with the first")
	}
}
