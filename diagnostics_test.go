package spectrik

import (
	"errors"
	"fmt"
	"strings"
	"testing"

	"github.com/hashicorp/hcl/v2"
)

// diagsFrom returns the diagnostics behind a load error.
func diagsFrom(t *testing.T, err error) hcl.Diagnostics {
	t.Helper()
	if err == nil {
		t.Fatal("expected an error")
	}
	var diags hcl.Diagnostics
	if !errors.As(err, &diags) {
		t.Fatalf("err is %T, want hcl.Diagnostics", err)
	}
	return diags
}

// projectsUsing returns HCL declaring n projects that all use one blueprint.
func projectsUsing(n int, blueprint string) string {
	var b strings.Builder
	for i := range n {
		fmt.Fprintf(&b, "project %q { use = [%q] }\n", fmt.Sprintf("p%d", i), blueprint)
	}
	return b.String()
}

func TestLoadReportsEachProblemOnce(t *testing.T) {
	for _, projects := range []int{1, 3, 6} {
		t.Run(fmt.Sprintf("%d projects", projects), func(t *testing.T) {
			_, err := loadFiles(t, map[string]string{
				"base.hcl": `
blueprint "base" {
  ensure "widget" {
    size = 1
  }
}
`,
				"projects.hcl": projectsUsing(projects, "base"),
			}, Options{})

			diags := diagsFrom(t, err)
			if len(diags) != 1 {
				t.Fatalf("got %d diagnostics, want 1:\n%s", len(diags), diags)
			}
		})
	}
}

func TestLoadStillReportsDistinctProblems(t *testing.T) {
	_, err := loadFiles(t, map[string]string{
		"config.hcl": `
blueprint "base" {
  ensure "widget" {
    size = 1
  }
  ensure "gadget" {
    size = 2
  }
}
project "a" { use = ["base"] }
project "b" { use = ["base"] }
`,
	}, Options{})

	diags := diagsFrom(t, err)
	if len(diags) != 2 {
		t.Fatalf("got %d diagnostics, want 2 (one per unknown spec type):\n%s", len(diags), diags)
	}
}

func TestEveryDiagnosticHasADetail(t *testing.T) {
	cases := map[string]map[string]string{
		"unknown spec type": {
			"config.hcl": `
project "a" {
  ensure "widget" {}
}
`,
		},
		"unknown blueprint": {
			"config.hcl": `project "a" { use = ["nope"] }`,
		},
		"circular include": {
			"config.hcl": `
blueprint "a" { include = ["b"] }
blueprint "b" { include = ["a"] }
`,
		},
		"duplicate blueprint": {
			"a.hcl": `blueprint "base" {}`,
			"b.hcl": `blueprint "base" {}`,
		},
		"duplicate project": {
			"a.hcl": `project "red" {}`,
			"b.hcl": `other "red" {}`,
		},
		"absent without remover": {
			"config.hcl": `
project "a" {
  absent "plain" {}
}
`,
		},
	}

	for name, files := range cases {
		t.Run(name, func(t *testing.T) {
			reg := newLoadRegistry()
			RegisterSpec(reg, "plain", func() Spec[*testProject] { return &plainSpec{} })

			_, err := loadFiles(t, files, Options{Registry: reg})

			for _, d := range diagsFrom(t, err) {
				if d.Detail == "" {
					t.Errorf("diagnostic %q has no Detail, which renders as a dangling %q: %s",
						d.Summary, "; ", d.Error())
				}
				if strings.HasSuffix(strings.TrimSpace(d.Error()), ";") {
					t.Errorf("diagnostic renders with a dangling separator: %q", d.Error())
				}
			}
		})
	}
}
