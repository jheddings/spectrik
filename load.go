package spectrik

import (
	"errors"
	"fmt"
	"io/fs"
	"os"
	"path/filepath"
	"sort"
	"strings"

	"github.com/hashicorp/hcl/v2"
	"github.com/hashicorp/hcl/v2/hclparse"
	"github.com/zclconf/go-cty/cty"
	"github.com/zclconf/go-cty/cty/function"
)

// Options configures Load.
type Options struct {
	// Registry supplies the spec and project types that HCL blocks decode
	// into. It is required.
	Registry *Registry

	// Variables are made available to every expression by name, for
	// example {"env": EnvVars()} to allow "${env.HOME}". A "var" entry is
	// merged beneath each file's own variable blocks.
	Variables map[string]cty.Value

	// Functions are made available to every expression. None are provided
	// by default.
	Functions map[string]function.Function
}

// EnvVars returns the process environment as an HCL object value, for use
// as the `env` variable: Options{Variables: {"env": EnvVars()}} lets
// configuration write "${env.HOME}".
func EnvVars() cty.Value {
	vars := make(map[string]cty.Value)
	for _, kv := range os.Environ() {
		k, v, ok := strings.Cut(kv, "=")
		if !ok || k == "" {
			continue
		}
		vars[k] = cty.StringVal(v)
	}
	return cty.ObjectVal(vars)
}

// Load parses every .hcl file under dir, recursively, into a Workspace.
// Every blueprint and project is validated before Load returns, so unknown
// spec types, bad attributes, and dangling references fail here with
// positions. The returned error is an hcl.Diagnostics when the problem is
// in the configuration.
func Load(dir string, opts Options) (*Workspace, error) {
	if opts.Registry == nil {
		return nil, errors.New("spectrik: Load requires a Registry")
	}
	info, err := os.Stat(dir)
	if err != nil {
		return nil, fmt.Errorf("spectrik: %w", err)
	}
	if !info.IsDir() {
		return nil, fmt.Errorf("spectrik: %s is not a directory", dir)
	}

	var paths []string
	err = filepath.WalkDir(dir, func(path string, d fs.DirEntry, err error) error {
		if err != nil {
			return err
		}
		if !d.IsDir() && filepath.Ext(path) == ".hcl" {
			paths = append(paths, path)
		}
		return nil
	})
	if err != nil {
		return nil, fmt.Errorf("spectrik: %w", err)
	}

	ws := newWorkspace(opts.Registry)
	parser := hclparse.NewParser()
	var diags hcl.Diagnostics
	for _, path := range paths {
		file, fileDiags := parser.ParseHCLFile(path)
		diags = append(diags, fileDiags...)
		if fileDiags.HasErrors() {
			continue
		}
		diags = append(diags, ws.addFile(file, opts)...)
	}
	if diags.HasErrors() {
		return nil, diags
	}
	if diags := ws.validate(); diags.HasErrors() {
		return nil, diags
	}
	return ws, nil
}

var topLevelBlocks = []hcl.BlockHeaderSchema{
	{Type: "variable", LabelNames: []string{"name"}},
	{Type: "variables"},
	{Type: "blueprint", LabelNames: []string{"name"}},
}

var strategyBlocks = []hcl.BlockHeaderSchema{
	{Type: string(StrategyPresent), LabelNames: []string{"type"}},
	{Type: string(StrategyEnsure), LabelNames: []string{"type"}},
	{Type: string(StrategyAbsent), LabelNames: []string{"type"}},
}

var blueprintSchema = &hcl.BodySchema{
	Attributes: []hcl.AttributeSchema{
		{Name: "description"},
		{Name: "include"},
	},
	Blocks: strategyBlocks,
}

var projectSchema = &hcl.BodySchema{
	Attributes: []hcl.AttributeSchema{
		{Name: "description"},
		{Name: "use"},
	},
	Blocks: strategyBlocks,
}

var variableSchema = &hcl.BodySchema{
	Attributes: []hcl.AttributeSchema{{Name: "value", Required: true}},
}

// addFile reads one parsed file into the workspace: variables first, in
// order, then blueprint and project blocks bound to this file's eval
// context.
func (w *Workspace) addFile(file *hcl.File, opts Options) hcl.Diagnostics {
	schema := &hcl.BodySchema{Blocks: topLevelBlocks}
	for _, typeName := range w.registry.ProjectTypes() {
		schema.Blocks = append(schema.Blocks, hcl.BlockHeaderSchema{Type: typeName, LabelNames: []string{"name"}})
	}
	content, diags := file.Body.Content(schema)
	if diags.HasErrors() {
		return diags
	}

	vars := make(map[string]cty.Value)
	ctx := evalContext(opts, vars)
	for _, block := range content.Blocks {
		switch block.Type {
		case "variable":
			value, valDiags := evalVariable(block, ctx)
			diags = append(diags, valDiags...)
			if valDiags.HasErrors() {
				continue
			}
			vars[block.Labels[0]] = value
			ctx = evalContext(opts, vars)
		case "variables":
			attrs, attrDiags := block.Body.JustAttributes()
			diags = append(diags, attrDiags...)
			for _, attr := range sortedAttributes(attrs) {
				value, valDiags := attr.Expr.Value(ctx)
				diags = append(diags, valDiags...)
				if valDiags.HasErrors() {
					continue
				}
				vars[attr.Name] = value
				ctx = evalContext(opts, vars)
			}
		}
	}
	if diags.HasErrors() {
		return diags
	}

	for _, block := range content.Blocks {
		switch block.Type {
		case "variable", "variables":
			continue
		case "blueprint":
			diags = append(diags, w.addBlueprint(block, ctx)...)
		default:
			diags = append(diags, w.addProject(block, ctx)...)
		}
	}
	return diags
}

// evalContext builds the context for one file: the caller's variables and
// functions, with the file's own variables merged over any caller "var".
func evalContext(opts Options, fileVars map[string]cty.Value) *hcl.EvalContext {
	variables := make(map[string]cty.Value, len(opts.Variables)+1)
	for k, v := range opts.Variables {
		variables[k] = v
	}

	merged := make(map[string]cty.Value)
	if global, ok := opts.Variables["var"]; ok && global.CanIterateElements() {
		for k, v := range global.AsValueMap() {
			merged[k] = v
		}
	}
	for k, v := range fileVars {
		merged[k] = v
	}
	if len(merged) > 0 {
		variables["var"] = cty.ObjectVal(merged)
	}

	return &hcl.EvalContext{Variables: variables, Functions: opts.Functions}
}

func evalVariable(block *hcl.Block, ctx *hcl.EvalContext) (cty.Value, hcl.Diagnostics) {
	content, diags := block.Body.Content(variableSchema)
	if diags.HasErrors() {
		return cty.NilVal, diags
	}
	value, valDiags := content.Attributes["value"].Expr.Value(ctx)
	return value, append(diags, valDiags...)
}

// sortedAttributes returns attributes in source order so that later
// entries in a variables block can reference earlier ones.
func sortedAttributes(attrs hcl.Attributes) []*hcl.Attribute {
	out := make([]*hcl.Attribute, 0, len(attrs))
	for _, a := range attrs {
		out = append(out, a)
	}
	sort.Slice(out, func(i, j int) bool {
		return out[i].Range.Start.Byte < out[j].Range.Start.Byte
	})
	return out
}
