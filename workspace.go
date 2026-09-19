package spectrik

import (
	"errors"
	"fmt"
	"maps"
	"reflect"
	"slices"

	"github.com/hashicorp/hcl/v2"
	"github.com/hashicorp/hcl/v2/gohcl"
)

// Workspace holds the blueprints and projects loaded from a directory of
// HCL files. Projects and blueprints are resolved fresh on every access,
// so a target that a build mutated does not leak into the next build.
type Workspace struct {
	registry   *Registry
	blueprints map[string]*blueprintRef
	projects   map[string]*projectRef
}

// blueprintRef is a parsed blueprint block awaiting resolution.
type blueprintRef struct {
	name        string
	description string
	includes    []string
	includeAttr *hcl.Attribute
	ops         hcl.Blocks
	ctx         *hcl.EvalContext
	defRange    hcl.Range
}

// projectRef is a parsed project block awaiting resolution.
type projectRef struct {
	name        string
	typeName    string
	description string
	use         []string
	useAttr     *hcl.Attribute
	ops         hcl.Blocks
	remain      hcl.Body
	ctx         *hcl.EvalContext
	defRange    hcl.Range
}

func newWorkspace(reg *Registry) *Workspace {
	return &Workspace{
		registry:   reg,
		blueprints: make(map[string]*blueprintRef),
		projects:   make(map[string]*projectRef),
	}
}

// Blueprints returns the names of every loaded blueprint, sorted.
func (w *Workspace) Blueprints() []string {
	return slices.Sorted(maps.Keys(w.blueprints))
}

// Projects returns the names of every loaded project, sorted.
func (w *Workspace) Projects() []string {
	return slices.Sorted(maps.Keys(w.projects))
}

// Blueprint resolves the named blueprint, including everything it
// includes, into a fresh Blueprint. The returned Ops slice is freshly
// built, so a caller may reorder or wrap its entries in place.
func (w *Workspace) Blueprint(name string) (*Blueprint, error) {
	if _, ok := w.blueprints[name]; !ok {
		return nil, fmt.Errorf("unknown blueprint %q", name)
	}
	bp, diags := w.resolveBlueprint(name, nil, map[string]bool{})
	if diags := dedupeDiags(diags); diags.HasErrors() {
		return nil, diags
	}
	return bp, nil
}

// Project resolves the named project into a fresh target of its registered
// project type, with its blueprints resolved and its attributes decoded.
//
// Every call returns a new target holding new Blueprint values with new Ops
// slices, so a caller may wrap or replace ops in place, and a target
// mutated by one build never reaches the next.
func (w *Workspace) Project(name string) (Target, error) {
	if _, ok := w.projects[name]; !ok {
		return nil, fmt.Errorf("unknown project %q", name)
	}
	t, diags := w.resolveProject(name)
	if diags := dedupeDiags(diags); diags.HasErrors() {
		return nil, diags
	}
	return t, nil
}

func (w *Workspace) addBlueprint(block *hcl.Block, ctx *hcl.EvalContext) hcl.Diagnostics {
	name := block.Labels[0]
	if prev, dup := w.blueprints[name]; dup {
		return hcl.Diagnostics{duplicateDiag("blueprint", name, block.DefRange, prev.defRange)}
	}
	content, diags := block.Body.Content(blueprintSchema)
	if diags.HasErrors() {
		return diags
	}
	ref := &blueprintRef{name: name, ops: content.Blocks, ctx: ctx, defRange: block.DefRange}
	diags = append(diags, decodeString(content.Attributes["description"], ctx, &ref.description)...)
	ref.includeAttr = content.Attributes["include"]
	diags = append(diags, decodeStrings(ref.includeAttr, ctx, &ref.includes)...)
	if diags.HasErrors() {
		return diags
	}
	w.blueprints[name] = ref
	return diags
}

func (w *Workspace) addProject(block *hcl.Block, ctx *hcl.EvalContext) hcl.Diagnostics {
	name := block.Labels[0]
	if prev, dup := w.projects[name]; dup {
		return hcl.Diagnostics{duplicateDiag("project", name, block.DefRange, prev.defRange)}
	}
	content, remain, diags := block.Body.PartialContent(projectSchema)
	if diags.HasErrors() {
		return diags
	}
	ref := &projectRef{
		name: name, typeName: block.Type, ops: content.Blocks,
		remain: remain, ctx: ctx, defRange: block.DefRange,
	}
	diags = append(diags, decodeString(content.Attributes["description"], ctx, &ref.description)...)
	ref.useAttr = content.Attributes["use"]
	diags = append(diags, decodeStrings(ref.useAttr, ctx, &ref.use)...)
	if diags.HasErrors() {
		return diags
	}
	w.projects[name] = ref
	return diags
}

// validate resolves everything once so that configuration errors surface
// at load time rather than on first access.
func (w *Workspace) validate() hcl.Diagnostics {
	var diags hcl.Diagnostics
	for _, name := range w.Blueprints() {
		_, d := w.resolveBlueprint(name, nil, map[string]bool{})
		diags = append(diags, d...)
	}
	for _, name := range w.Projects() {
		_, d := w.resolveProject(name)
		diags = append(diags, d...)
	}
	return dedupeDiags(diags)
}

// dedupeDiags drops diagnostics that repeat an earlier one. Validation
// resolves each blueprint standalone and again through every project that
// uses it, so without this one bad block is reported once per consumer.
func dedupeDiags(diags hcl.Diagnostics) hcl.Diagnostics {
	if len(diags) < 2 {
		return diags
	}
	seen := make(map[string]bool, len(diags))
	out := make(hcl.Diagnostics, 0, len(diags))
	for _, d := range diags {
		key := fmt.Sprintf("%d\x00%s\x00%s\x00%s", d.Severity, d.Subject, d.Summary, d.Detail)
		if seen[key] {
			continue
		}
		seen[key] = true
		out = append(out, d)
	}
	return out
}

// resolveBlueprint builds a Blueprint from its ref, resolving includes
// depth-first so included ops come before the blueprint's own. subject is
// the range of the reference that led here, for diagnostics.
func (w *Workspace) resolveBlueprint(name string, subject *hcl.Range, resolving map[string]bool) (*Blueprint, hcl.Diagnostics) {
	ref, ok := w.blueprints[name]
	if !ok {
		return nil, hcl.Diagnostics{{
			Severity: hcl.DiagError,
			Summary:  fmt.Sprintf("unknown blueprint %q", name),
			Detail:   "Blueprints are referenced by the name given in their block label.",
			Subject:  subject,
		}}
	}
	if resolving[name] {
		return nil, hcl.Diagnostics{{
			Severity: hcl.DiagError,
			Summary:  fmt.Sprintf("circular include: blueprint %q includes itself", name),
			Detail: "A blueprint cannot include itself, directly or through the " +
				"blueprints it includes. Break the cycle by moving the shared " +
				"operations into a blueprint that includes neither.",
			Subject: subject,
		}}
	}
	resolving[name] = true
	defer delete(resolving, name)

	bp := &Blueprint{Name: ref.name, Description: ref.description}
	var diags hcl.Diagnostics
	for _, inc := range ref.includes {
		sub, subDiags := w.resolveBlueprint(inc, &ref.includeAttr.Range, resolving)
		diags = append(diags, subDiags...)
		if subDiags.HasErrors() {
			continue
		}
		bp.Ops = append(bp.Ops, sub.Ops...)
	}
	ops, opDiags := w.decodeOps(ref.ops, ref.ctx)
	diags = append(diags, opDiags...)
	bp.Ops = append(bp.Ops, ops...)
	return bp, diags
}

// resolveProject builds a fresh target from its ref.
func (w *Workspace) resolveProject(name string) (Target, hcl.Diagnostics) {
	ref := w.projects[name]
	t, err := w.registry.NewProject(ref.typeName, func(p any) error {
		return decodeBody(ref.remain, ref.ctx, p)
	})
	if err != nil {
		return nil, asDiagnostics(err, ref.defRange,
			"The project type comes from the block type. Register it with "+
				"spectrik.RegisterProject before loading.")
	}

	base := t.Base()
	base.Name = ref.name
	base.Description = ref.description

	var diags hcl.Diagnostics
	for _, use := range ref.use {
		bp, bpDiags := w.resolveBlueprint(use, &ref.useAttr.Range, map[string]bool{})
		diags = append(diags, bpDiags...)
		if bpDiags.HasErrors() {
			continue
		}
		base.Blueprints = append(base.Blueprints, bp)
	}
	ops, opDiags := w.decodeOps(ref.ops, ref.ctx)
	diags = append(diags, opDiags...)
	if len(ops) > 0 {
		base.Blueprints = append(base.Blueprints, &Blueprint{Name: name + ":inline", Ops: ops})
	}
	return t, diags
}

// decodeOps turns strategy blocks into ops through the registry.
func (w *Workspace) decodeOps(blocks hcl.Blocks, ctx *hcl.EvalContext) ([]Op, hcl.Diagnostics) {
	var ops []Op
	var diags hcl.Diagnostics
	for _, block := range blocks {
		op, err := w.registry.NewOp(block.Labels[0], Strategy(block.Type), func(spec any) error {
			return decodeBody(block.Body, ctx, spec)
		})
		if err != nil {
			diags = append(diags, asDiagnostics(err, block.DefRange,
				"The spec type comes from the block label. Register it with "+
					"spectrik.RegisterSpec before loading, and use absent only "+
					"with a spec that implements Remover.")...)
			continue
		}
		ops = append(ops, op)
	}
	return ops, diags
}

// decodeBody decodes an HCL body into v, which must be a non-nil pointer
// to a struct. gohcl panics on anything else, so the check happens here
// and reports a registration mistake as an ordinary load error.
func decodeBody(body hcl.Body, ctx *hcl.EvalContext, v any) error {
	rv := reflect.ValueOf(v)
	if rv.Kind() != reflect.Pointer || rv.IsNil() {
		return fmt.Errorf("must be a pointer, got %T", v)
	}
	if d := gohcl.DecodeBody(body, ctx, v); d.HasErrors() {
		return d
	}
	return nil
}

// asDiagnostics passes hcl diagnostics through and wraps any other error
// in a diagnostic pointing at subject. The detail is always set, because
// hcl renders a diagnostic as "subject: summary; detail" and an empty
// detail leaves a dangling separator.
func asDiagnostics(err error, subject hcl.Range, detail string) hcl.Diagnostics {
	var diags hcl.Diagnostics
	if errors.As(err, &diags) {
		return diags
	}
	return hcl.Diagnostics{{
		Severity: hcl.DiagError,
		Summary:  err.Error(),
		Detail:   detail,
		Subject:  &subject,
	}}
}

func duplicateDiag(kind, name string, this, prev hcl.Range) *hcl.Diagnostic {
	return &hcl.Diagnostic{
		Severity: hcl.DiagError,
		Summary:  fmt.Sprintf("duplicate %s %q", kind, name),
		Detail:   fmt.Sprintf("Already defined at %s.", prev),
		Subject:  &this,
	}
}

func decodeString(attr *hcl.Attribute, ctx *hcl.EvalContext, dst *string) hcl.Diagnostics {
	if attr == nil {
		return nil
	}
	return gohcl.DecodeExpression(attr.Expr, ctx, dst)
}

func decodeStrings(attr *hcl.Attribute, ctx *hcl.EvalContext, dst *[]string) hcl.Diagnostics {
	if attr == nil {
		return nil
	}
	return gohcl.DecodeExpression(attr.Expr, ctx, dst)
}
