package spectrik

import (
	"context"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/zclconf/go-cty/cty"
	"github.com/zclconf/go-cty/cty/function"
	"github.com/zclconf/go-cty/cty/function/stdlib"
)

func TestEnvVarsExposesEnvironment(t *testing.T) {
	t.Setenv("SPECTRIK_TEST_VALUE", "hello")

	env := EnvVars()

	if !env.Type().IsObjectType() {
		t.Fatalf("EnvVars() is %s, want an object", env.Type().FriendlyName())
	}
	got := env.GetAttr("SPECTRIK_TEST_VALUE")
	if got.AsString() != "hello" {
		t.Fatalf("env.SPECTRIK_TEST_VALUE = %q, want %q", got.AsString(), "hello")
	}
}

// noteSpec is a consumer-style spec decoded from HCL. Apply records what it
// received on the target so tests can inspect it after a build.
type noteSpec struct {
	Text  string `hcl:"text"`
	Count int    `hcl:"count,optional"`
	Flag  *bool  `hcl:"flag,optional"`
}

func (s *noteSpec) Apply(ctx context.Context, p *testProject) error {
	entry := "note:" + s.Text
	if s.Count != 0 {
		entry += fmt.Sprintf("#%d", s.Count)
	}
	if s.Flag != nil {
		entry += fmt.Sprintf("?%t", *s.Flag)
	}
	p.log = append(p.log, entry)
	return nil
}

func (s *noteSpec) Exists(ctx context.Context, p *testProject) (bool, error) {
	return false, nil
}

func (s *noteSpec) Remove(ctx context.Context, p *testProject) error {
	p.log = append(p.log, "remove:"+s.Text)
	return nil
}

func newLoadRegistry() *Registry {
	reg := NewRegistry()
	RegisterProject(reg, "project", func() *testProject { return &testProject{} })
	RegisterProject(reg, "other", func() *otherProject { return &otherProject{} })
	RegisterSpec(reg, "note", func() Spec[*testProject] { return &noteSpec{} })
	return reg
}

// loadFiles writes the given files under a temp dir and loads it.
func loadFiles(t *testing.T, files map[string]string, opts Options) (*Workspace, error) {
	t.Helper()
	dir := t.TempDir()
	for name, content := range files {
		path := filepath.Join(dir, name)
		if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(path, []byte(content), 0o644); err != nil {
			t.Fatal(err)
		}
	}
	if opts.Registry == nil {
		opts.Registry = newLoadRegistry()
	}
	return Load(dir, opts)
}

func mustLoad(t *testing.T, files map[string]string) *Workspace {
	t.Helper()
	ws, err := loadFiles(t, files, Options{})
	if err != nil {
		t.Fatal(err)
	}
	return ws
}

// buildProject resolves and builds a project, returning the concrete target.
func buildProject(t *testing.T, ws *Workspace, name string) *testProject {
	t.Helper()
	tgt, err := ws.Project(name)
	if err != nil {
		t.Fatal(err)
	}
	if err := Build(context.Background(), tgt); err != nil {
		t.Fatal(err)
	}
	return tgt.(*testProject)
}

func assertErrorContains(t *testing.T, err error, wants ...string) {
	t.Helper()
	if err == nil {
		t.Fatalf("expected an error containing %q", wants)
	}
	for _, want := range wants {
		if !strings.Contains(err.Error(), want) {
			t.Fatalf("error %q does not contain %q", err, want)
		}
	}
}

// ---- happy path ----

func TestLoadBlueprintAndProject(t *testing.T) {
	ws := mustLoad(t, map[string]string{
		"blueprints.hcl": `
blueprint "base" {
  description = "the basics"
  ensure "note" { text = "one" }
  ensure "note" { text = "two" }
}
`,
		"projects.hcl": `
project "red" {
  description = "the app"
  use = ["base"]
}
`,
	})

	proj := buildProject(t, ws, "red")

	if got, want := join(proj.log), "note:one,note:two"; got != want {
		t.Fatalf("ran %s, want %s", got, want)
	}
	if proj.Name != "red" || proj.Description != "the app" {
		t.Fatalf("project = %+v", proj.Project)
	}
	bp, err := ws.Blueprint("base")
	if err != nil {
		t.Fatal(err)
	}
	if bp.Name != "base" || bp.Description != "the basics" || len(bp.Ops) != 2 {
		t.Fatalf("blueprint = %+v", bp)
	}
}

func TestLoadMapsStrategyBlocksToOps(t *testing.T) {
	ws := mustLoad(t, map[string]string{
		"blueprints.hcl": `
blueprint "base" {
  present "note" { text = "p" }
  ensure  "note" { text = "e" }
  absent  "note" { text = "a" }
}
`,
	})

	bp, err := ws.Blueprint("base")
	if err != nil {
		t.Fatal(err)
	}
	if _, ok := bp.Ops[0].(Present[*testProject]); !ok {
		t.Fatalf("ops[0] is %T, want Present", bp.Ops[0])
	}
	if _, ok := bp.Ops[1].(Ensure[*testProject]); !ok {
		t.Fatalf("ops[1] is %T, want Ensure", bp.Ops[1])
	}
	if _, ok := bp.Ops[2].(Absent[*testProject]); !ok {
		t.Fatalf("ops[2] is %T, want Absent", bp.Ops[2])
	}
}

func TestLoadDecodesTypedAttributes(t *testing.T) {
	ws := mustLoad(t, map[string]string{
		"blueprints.hcl": `
blueprint "base" {
  ensure "note" {
    text  = "typed"
    count = 3
    flag  = true
  }
}
`,
		"projects.hcl": `project "red" { use = ["base"] }`,
	})

	proj := buildProject(t, ws, "red")

	if got, want := join(proj.log), "note:typed#3?true"; got != want {
		t.Fatalf("ran %s, want %s", got, want)
	}
}

func TestLoadInlineOpsFollowUsedBlueprints(t *testing.T) {
	ws := mustLoad(t, map[string]string{
		"config.hcl": `
blueprint "base" {
  ensure "note" { text = "from-blueprint" }
}

project "red" {
  ensure "note" { text = "inline" }
  use = ["base"]
}
`,
	})

	proj := buildProject(t, ws, "red")

	if got, want := join(proj.log), "note:from-blueprint,note:inline"; got != want {
		t.Fatalf("ran %s, want %s", got, want)
	}
	if got, want := len(proj.Blueprints), 2; got != want {
		t.Fatalf("blueprints = %d, want %d", got, want)
	}
	if got, want := proj.Blueprints[1].Name, "red:inline"; got != want {
		t.Fatalf("inline blueprint name = %q, want %q", got, want)
	}
}

func TestLoadIncludeOrdersIncludedOpsFirst(t *testing.T) {
	ws := mustLoad(t, map[string]string{
		"blueprints.hcl": `
blueprint "extended" {
  include = ["base"]
  ensure "note" { text = "extended" }
}

blueprint "base" {
  include = ["core"]
  ensure "note" { text = "base" }
}

blueprint "core" {
  ensure "note" { text = "core" }
}
`,
		"projects.hcl": `project "red" { use = ["extended"] }`,
	})

	proj := buildProject(t, ws, "red")

	if got, want := join(proj.log), "note:core,note:base,note:extended"; got != want {
		t.Fatalf("ran %s, want %s", got, want)
	}
}

func TestLoadMixedProjectTypes(t *testing.T) {
	ws := mustLoad(t, map[string]string{
		"projects.hcl": `
project "red"  { owner = "risefamily" }
other   "beta" {}
`,
	})

	if got, want := join(ws.Projects()), "beta,red"; got != want {
		t.Fatalf("Projects() = %s, want %s", got, want)
	}
	red, err := ws.Project("red")
	if err != nil {
		t.Fatal(err)
	}
	if p, ok := red.(*testProject); !ok || p.Owner != "risefamily" {
		t.Fatalf("red = %#v, want *testProject with owner", red)
	}
	beta, err := ws.Project("beta")
	if err != nil {
		t.Fatal(err)
	}
	if _, ok := beta.(*otherProject); !ok {
		t.Fatalf("beta is %T, want *otherProject", beta)
	}
}

func TestProjectIsFreshOnEachAccess(t *testing.T) {
	ws := mustLoad(t, map[string]string{
		"projects.hcl": `project "red" { owner = "original" }`,
	})

	first, _ := ws.Project("red")
	first.(*testProject).Owner = "mutated"

	second, _ := ws.Project("red")
	if got := second.(*testProject).Owner; got != "original" {
		t.Fatalf("second access saw %q, want a fresh instance", got)
	}
}

func TestLoadNamesAreSorted(t *testing.T) {
	ws := mustLoad(t, map[string]string{
		"b.hcl": `
blueprint "zeta" {}
project "zulu" {}
`,
		"a.hcl": `
blueprint "alpha" {}
project "apple" {}
`,
	})

	if got, want := join(ws.Blueprints()), "alpha,zeta"; got != want {
		t.Fatalf("Blueprints() = %s, want %s", got, want)
	}
	if got, want := join(ws.Projects()), "apple,zulu"; got != want {
		t.Fatalf("Projects() = %s, want %s", got, want)
	}
}

func TestLoadRecursesIntoSubdirectories(t *testing.T) {
	ws := mustLoad(t, map[string]string{
		"blueprints/base.hcl": `blueprint "base" {}`,
		"projects/red.hcl":    `project "red" { use = ["base"] }`,
	})

	if got, want := join(ws.Projects()), "red"; got != want {
		t.Fatalf("Projects() = %s, want %s", got, want)
	}
}

func TestLoadEmptyDirectory(t *testing.T) {
	ws, err := loadFiles(t, nil, Options{})
	if err != nil {
		t.Fatal(err)
	}
	if len(ws.Projects()) != 0 || len(ws.Blueprints()) != 0 {
		t.Fatalf("workspace not empty: %v %v", ws.Projects(), ws.Blueprints())
	}
}

func TestLoadMissingDirectoryFails(t *testing.T) {
	_, err := Load(filepath.Join(t.TempDir(), "nope"), Options{Registry: newLoadRegistry()})
	if err == nil {
		t.Fatal("expected an error")
	}
	if !errors.Is(err, os.ErrNotExist) {
		t.Fatalf("err = %v, want ErrNotExist", err)
	}
}

// ---- interpolation and variables ----

func TestLoadVariableBlocks(t *testing.T) {
	ws := mustLoad(t, map[string]string{
		"config.hcl": `
variable "greeting" {
  value = "hi"
}

variables {
  times = 2
  who   = "${var.greeting}-there"
}

blueprint "base" {
  ensure "note" {
    text  = "${var.who}"
    count = var.times
  }
}

project "red" { use = ["base"] }
`,
	})

	proj := buildProject(t, ws, "red")

	if got, want := join(proj.log), "note:hi-there#2"; got != want {
		t.Fatalf("ran %s, want %s", got, want)
	}
}

func TestLoadVariablesAreFileScoped(t *testing.T) {
	ws := mustLoad(t, map[string]string{
		"alpha.hcl": `
variable "item" { value = "alpha-item" }
project "alpha" {
  ensure "note" { text = "${var.item}" }
}
`,
		"beta.hcl": `
variable "item" { value = "beta-item" }
project "beta" {
  ensure "note" { text = "${var.item}" }
}
`,
	})

	alpha := buildProject(t, ws, "alpha")
	beta := buildProject(t, ws, "beta")

	if got, want := join(alpha.log), "note:alpha-item"; got != want {
		t.Fatalf("alpha ran %s, want %s", got, want)
	}
	if got, want := join(beta.log), "note:beta-item"; got != want {
		t.Fatalf("beta ran %s, want %s", got, want)
	}
}

func TestLoadCallerVariables(t *testing.T) {
	env := cty.ObjectVal(map[string]cty.Value{"HOME": cty.StringVal("/home/red")})
	ws, err := loadFiles(t, map[string]string{
		"config.hcl": `
project "red" {
  ensure "note" { text = "${env.HOME}/.config" }
}
`,
	}, Options{Variables: map[string]cty.Value{"env": env}})
	if err != nil {
		t.Fatal(err)
	}

	proj := buildProject(t, ws, "red")

	if got, want := join(proj.log), "note:/home/red/.config"; got != want {
		t.Fatalf("ran %s, want %s", got, want)
	}
}

func TestLoadCallerVarMergesWithFileVariables(t *testing.T) {
	global := cty.ObjectVal(map[string]cty.Value{"shared": cty.StringVal("global")})
	ws, err := loadFiles(t, map[string]string{
		"config.hcl": `
variable "local" { value = "file" }
project "red" {
  ensure "note" { text = "${var.shared}+${var.local}" }
}
`,
	}, Options{Variables: map[string]cty.Value{"var": global}})
	if err != nil {
		t.Fatal(err)
	}

	proj := buildProject(t, ws, "red")

	if got, want := join(proj.log), "note:global+file"; got != want {
		t.Fatalf("ran %s, want %s", got, want)
	}
}

func TestLoadCallerFunctions(t *testing.T) {
	ws, err := loadFiles(t, map[string]string{
		"config.hcl": `
project "red" {
  ensure "note" { text = upper("shout") }
}
`,
	}, Options{Functions: map[string]function.Function{"upper": stdlib.UpperFunc}})
	if err != nil {
		t.Fatal(err)
	}

	proj := buildProject(t, ws, "red")

	if got, want := join(proj.log), "note:SHOUT"; got != want {
		t.Fatalf("ran %s, want %s", got, want)
	}
}

func TestLoadHeredocIsDedented(t *testing.T) {
	ws := mustLoad(t, map[string]string{
		"config.hcl": `
project "red" {
  ensure "note" {
    text = <<-EOF
      line one
      line two
    EOF
  }
}
`,
	})

	proj := buildProject(t, ws, "red")

	if got, want := join(proj.log), "note:line one\nline two\n"; got != want {
		t.Fatalf("ran %q, want %q", got, want)
	}
}

func TestLoadEscapedInterpolationPassesThrough(t *testing.T) {
	ws := mustLoad(t, map[string]string{
		"config.hcl": `
project "red" {
  ensure "note" { text = "$${{ secrets.GITHUB_TOKEN }}" }
}
`,
	})

	proj := buildProject(t, ws, "red")

	if got, want := join(proj.log), "note:${{ secrets.GITHUB_TOKEN }}"; got != want {
		t.Fatalf("ran %q, want %q", got, want)
	}
}

// ---- errors ----

func TestLoadUnknownSpecType(t *testing.T) {
	_, err := loadFiles(t, map[string]string{
		"blueprints.hcl": `
blueprint "base" {
  ensure "widget" { size = 1 }
}
`,
	}, Options{})

	assertErrorContains(t, err, `unknown spec type "widget"`, "blueprints.hcl:3,3")
}

// plainSpec implements only Apply, so it cannot be used with absent.
type plainSpec struct {
	Text string `hcl:"text,optional"`
}

func (s *plainSpec) Apply(ctx context.Context, p *testProject) error { return nil }

func TestLoadAbsentOnNonRemovableSpecFails(t *testing.T) {
	reg := newLoadRegistry()
	RegisterSpec(reg, "plain", func() Spec[*testProject] { return &plainSpec{} })

	_, err := loadFiles(t, map[string]string{
		"config.hcl": `
project "red" {
  absent "plain" {}
}
`,
	}, Options{Registry: reg})

	assertErrorContains(t, err, "spec plain: spec does not support removal", "config.hcl:3,3")
}

func TestLoadRejectsValueTypeSpec(t *testing.T) {
	reg := newLoadRegistry()
	RegisterSpec(reg, "byvalue", func() Spec[*testProject] { return applySpec{&spy{}} })

	_, err := loadFiles(t, map[string]string{
		"config.hcl": `
project "red" {
  ensure "byvalue" {}
}
`,
	}, Options{Registry: reg})

	assertErrorContains(t, err, "spec byvalue: must be a pointer, got spectrik.applySpec", "config.hcl:3,3")
}

// valueProject satisfies Target by value, which gohcl cannot decode into.
type valueProject struct{ *Project }

func TestLoadRejectsValueTypeProject(t *testing.T) {
	reg := newLoadRegistry()
	RegisterProject(reg, "byvalue", func() valueProject { return valueProject{&Project{}} })

	_, err := loadFiles(t, map[string]string{
		"config.hcl": `byvalue "red" {}`,
	}, Options{Registry: reg})

	assertErrorContains(t, err, "project type byvalue: must be a pointer, got spectrik.valueProject", "config.hcl:1,1")
}

func TestLoadUnknownBlockType(t *testing.T) {
	_, err := loadFiles(t, map[string]string{
		"config.hcl": `
widget "x" {}
`,
	}, Options{})

	assertErrorContains(t, err, "Unsupported block type", "config.hcl:2,1")
}

func TestLoadUnknownSpecAttribute(t *testing.T) {
	_, err := loadFiles(t, map[string]string{
		"config.hcl": `
project "red" {
  ensure "note" {
    text  = "x"
    bogus = 1
  }
}
`,
	}, Options{})

	assertErrorContains(t, err, "Unsupported argument", `"bogus"`, "config.hcl:5,5")
}

func TestLoadMissingRequiredAttribute(t *testing.T) {
	_, err := loadFiles(t, map[string]string{
		"config.hcl": `
project "red" {
  ensure "note" {}
}
`,
	}, Options{})

	assertErrorContains(t, err, "Missing required argument", `"text"`)
}

func TestLoadRejectsUnknownProjectAttribute(t *testing.T) {
	_, err := loadFiles(t, map[string]string{
		"config.hcl": `
other "beta" {
  bogus = "x"
}
`,
	}, Options{})

	assertErrorContains(t, err, "Unsupported argument", `"bogus"`, "config.hcl:3,3")
}

func TestLoadUnknownBlueprintInUse(t *testing.T) {
	_, err := loadFiles(t, map[string]string{
		"config.hcl": `
project "red" {
  use = ["nope"]
}
`,
	}, Options{})

	assertErrorContains(t, err, `unknown blueprint "nope"`, "config.hcl:3,3")
}

func TestLoadUnknownBlueprintInInclude(t *testing.T) {
	_, err := loadFiles(t, map[string]string{
		"config.hcl": `
blueprint "base" {
  include = ["nope"]
}
`,
	}, Options{})

	assertErrorContains(t, err, `unknown blueprint "nope"`, "config.hcl:3,3")
}

func TestLoadCircularInclude(t *testing.T) {
	_, err := loadFiles(t, map[string]string{
		"config.hcl": `
blueprint "a" { include = ["b"] }
blueprint "b" { include = ["a"] }
`,
	}, Options{})

	assertErrorContains(t, err, "circular include", `"a"`)
}

func TestWorkspaceUnknownBlueprintRequested(t *testing.T) {
	ws := mustLoad(t, map[string]string{"config.hcl": `blueprint "base" {}`})

	_, err := ws.Blueprint("nope")

	assertErrorContains(t, err, `unknown blueprint "nope"`)
}

func TestLoadDuplicateBlueprintName(t *testing.T) {
	_, err := loadFiles(t, map[string]string{
		"a.hcl": `blueprint "base" {}`,
		"b.hcl": `blueprint "base" {}`,
	}, Options{})

	assertErrorContains(t, err, `duplicate blueprint "base"`, "a.hcl:1,1")
}

func TestLoadDuplicateProjectName(t *testing.T) {
	_, err := loadFiles(t, map[string]string{
		"a.hcl": `project "red" {}`,
		"b.hcl": `other "red" {}`,
	}, Options{})

	assertErrorContains(t, err, `duplicate project "red"`, "a.hcl:1,1")
}

func TestLoadVariableWithoutValue(t *testing.T) {
	_, err := loadFiles(t, map[string]string{
		"config.hcl": `variable "x" {}`,
	}, Options{})

	assertErrorContains(t, err, "Missing required argument", `"value"`)
}

func TestLoadUndefinedVariableReference(t *testing.T) {
	_, err := loadFiles(t, map[string]string{
		"config.hcl": `
project "red" {
  ensure "note" { text = "${var.missing}" }
}
`,
	}, Options{})

	assertErrorContains(t, err, "config.hcl:3")
}

func TestLoadUnknownProjectRequested(t *testing.T) {
	ws := mustLoad(t, map[string]string{"config.hcl": `project "red" {}`})

	_, err := ws.Project("blue")

	assertErrorContains(t, err, `unknown project "blue"`)
}

func TestLoadRequiresRegistry(t *testing.T) {
	_, err := Load(t.TempDir(), Options{})
	if err == nil {
		t.Fatal("expected an error")
	}
}
