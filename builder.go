package spectrik

import (
	"context"
	"fmt"
	"sync"
)

// Blueprints and projects are normally loaded from HCL. The builders in
// this file are the programmatic equivalent, for consumers that compose
// configuration in Go: tests, generated configuration, and tools that
// build a target from something other than a file. They produce ordinary
// *Blueprint and Target values, so both paths meet at the same model.
//
// A builder is generic over the project type so the strategy methods take
// a Spec[P] and infer P from the chain rather than from every call. Ops
// for other project types still go in through Op, which is untyped.
//
// Unlike Workspace, which decodes a fresh spec from the retained HCL block
// on every access, a builder stores the spec value it is given. A blueprint
// reused across several projects hands them the same spec pointers, so a
// spec that mutates itself during Apply would carry that state between
// builds. Specs that hold configuration only, which is all of them today,
// are unaffected; one that does not should be built per project.

// BlueprintBuilder assembles a Blueprint for project type P. Create one
// with NewBlueprint, chain calls onto it, and finish with Compose. A builder
// is single-use and is not safe for concurrent use.
type BlueprintBuilder[P Target] struct {
	bp *Blueprint
}

// NewBlueprint starts a blueprint named name. The project type must be
// given explicitly, since nothing in the arguments implies it:
//
//	spectrik.NewBlueprint[*Machine]("dotfiles").
//	    Ensure(&Symlink{Link: "~/.zshrc", Target: "~/dotfiles/zshrc"}).
//	    Compose()
func NewBlueprint[P Target](name string) *BlueprintBuilder[P] {
	return &BlueprintBuilder[P]{bp: &Blueprint{Name: name}}
}

// Description sets the blueprint's description.
func (b *BlueprintBuilder[P]) Description(desc string) *BlueprintBuilder[P] {
	b.bp.Description = desc
	return b
}

// Op appends an already-wrapped op. It is the escape hatch for ops of a
// different project type, which the strategy methods cannot express.
func (b *BlueprintBuilder[P]) Op(op Op) *BlueprintBuilder[P] {
	b.bp.Ops = append(b.bp.Ops, op)
	return b
}

// Present appends the spec wrapped in the Present strategy, which applies
// it only if the resource does not already exist.
func (b *BlueprintBuilder[P]) Present(spec Spec[P]) *BlueprintBuilder[P] {
	return b.Op(Present[P]{Spec: spec})
}

// Ensure appends the spec wrapped in the Ensure strategy, which applies it
// unless the current state already matches.
func (b *BlueprintBuilder[P]) Ensure(spec Spec[P]) *BlueprintBuilder[P] {
	return b.Op(Ensure[P]{Spec: spec})
}

// Absent appends the spec wrapped in the Absent strategy, which removes
// the resource if it exists. It panics if the spec has no Remover, because
// that is a mistake in the calling code rather than a runtime condition;
// the loader reports the same mistake in HCL as a diagnostic.
func (b *BlueprintBuilder[P]) Absent(spec Spec[P]) *BlueprintBuilder[P] {
	mustRemove[P](spec)
	return b.Op(absentOp[P](spec))
}

// PresentDeferred is Present with the spec built when the op first runs.
func (b *BlueprintBuilder[P]) PresentDeferred(newSpec func() Spec[P]) *BlueprintBuilder[P] {
	return b.Op(deferOp(newSpec, presentOp[P]))
}

// EnsureDeferred is Ensure with the spec built when the op first runs.
func (b *BlueprintBuilder[P]) EnsureDeferred(newSpec func() Spec[P]) *BlueprintBuilder[P] {
	return b.Op(deferOp(newSpec, ensureOp[P]))
}

// AbsentDeferred is Absent with the spec built when the op first runs.
// Unlike Absent it cannot reject a spec with no Remover up front, since
// there is no spec yet; such a spec fails the run with ErrNotRemovable.
func (b *BlueprintBuilder[P]) AbsentDeferred(newSpec func() Spec[P]) *BlueprintBuilder[P] {
	return b.Op(deferOp(newSpec, absentOp[P]))
}

// Include appends a copy of every op in bp, flattening it into this
// blueprint at the point of the call. It matches the `include` attribute
// in HCL: the included blueprint is a source of ops, not a nested unit,
// and it is left unchanged.
func (b *BlueprintBuilder[P]) Include(bp *Blueprint) *BlueprintBuilder[P] {
	b.bp.Ops = append(b.bp.Ops, bp.Ops...)
	return b
}

// Compose returns the assembled blueprint. It is named for what it
// returns rather than Build, which throughout this package means running
// a blueprint or project against a target.
func (b *BlueprintBuilder[P]) Compose() *Blueprint {
	return b.bp
}

// ProjectBuilder assembles a build target of type P. Create one with
// NewProject, chain calls onto it, and finish with Construct. A builder is
// single-use and is not safe for concurrent use.
type ProjectBuilder[P Target] struct {
	target P
	base   *Project
	inline []Op
}

// NewProject starts a project named name around an existing target, which
// carries whatever domain-specific fields the consumer's type adds:
//
//	spectrik.NewProject(&Machine{Hostname: "laptop"}, "laptop").
//	    Description("Jason's laptop.").
//	    Use(dotfiles).
//	    Construct()
//
// The target is populated in place and returned by Construct, so P is inferred
// from it and never has to be written out.
func NewProject[P Target](target P, name string) *ProjectBuilder[P] {
	base := target.Base()
	base.Name = name
	return &ProjectBuilder[P]{target: target, base: base}
}

// Description sets the project's description.
func (b *ProjectBuilder[P]) Description(desc string) *ProjectBuilder[P] {
	b.base.Description = desc
	return b
}

// Use appends a blueprint to the project, as the `use` attribute does in
// HCL. Blueprints run in the order they are added.
func (b *ProjectBuilder[P]) Use(bp *Blueprint) *ProjectBuilder[P] {
	b.base.Blueprints = append(b.base.Blueprints, bp)
	return b
}

// Op appends an op directly to the project rather than to a blueprint. It
// is the escape hatch for ops of a different project type, which the
// strategy methods cannot express. See Construct for where these ops run.
func (b *ProjectBuilder[P]) Op(op Op) *ProjectBuilder[P] {
	b.inline = append(b.inline, op)
	return b
}

// Present appends the spec to the project wrapped in the Present strategy.
func (b *ProjectBuilder[P]) Present(spec Spec[P]) *ProjectBuilder[P] {
	return b.Op(Present[P]{Spec: spec})
}

// Ensure appends the spec to the project wrapped in the Ensure strategy.
func (b *ProjectBuilder[P]) Ensure(spec Spec[P]) *ProjectBuilder[P] {
	return b.Op(Ensure[P]{Spec: spec})
}

// Absent appends the spec to the project wrapped in the Absent strategy.
// It panics if the spec has no Remover, as BlueprintBuilder.Absent does.
func (b *ProjectBuilder[P]) Absent(spec Spec[P]) *ProjectBuilder[P] {
	mustRemove[P](spec)
	return b.Op(absentOp[P](spec))
}

// PresentDeferred is Present with the spec built when the op first runs.
func (b *ProjectBuilder[P]) PresentDeferred(newSpec func() Spec[P]) *ProjectBuilder[P] {
	return b.Op(deferOp(newSpec, presentOp[P]))
}

// EnsureDeferred is Ensure with the spec built when the op first runs.
func (b *ProjectBuilder[P]) EnsureDeferred(newSpec func() Spec[P]) *ProjectBuilder[P] {
	return b.Op(deferOp(newSpec, ensureOp[P]))
}

// AbsentDeferred is Absent with the spec built when the op first runs, with
// the same caveat as BlueprintBuilder.AbsentDeferred.
func (b *ProjectBuilder[P]) AbsentDeferred(newSpec func() Spec[P]) *ProjectBuilder[P] {
	return b.Op(deferOp(newSpec, absentOp[P]))
}

// Construct returns the populated target. It is named for what it does
// rather than Build, which throughout this package means running a
// blueprint or project against a target.
//
// Ops added directly to the project are collected into one blueprint named
// "<project>:inline", appended after every blueprint the project uses.
// That is the same shape and the same ordering the HCL loader gives to
// strategy blocks written inline in a project block.
func (b *ProjectBuilder[P]) Construct() P {
	if len(b.inline) > 0 {
		b.base.Blueprints = append(b.base.Blueprints, &Blueprint{
			Name: b.base.Name + ":inline",
			Ops:  b.inline,
		})
		b.inline = nil
	}
	return b.target
}

// The strategy constructors, as function values the deferred path can hold.
func presentOp[P Target](spec Spec[P]) Op { return Present[P]{Spec: spec} }
func ensureOp[P Target](spec Spec[P]) Op  { return Ensure[P]{Spec: spec} }
func absentOp[P Target](spec Spec[P]) Op  { return Absent[P]{Spec: spec} }

// mustRemove panics unless spec can be removed. The eager Absent methods
// call it so the mistake surfaces where it is written, as the loader
// reports the same mistake in HCL at load time.
func mustRemove[P Target](spec Spec[P]) {
	if _, ok := spec.(Remover[P]); !ok {
		panic(fmt.Sprintf("spectrik: spec %T does not support removal", spec))
	}
}

// deferredOp builds its spec on first run rather than when the chain is
// written, for a spec whose values are not known yet: a flag, a config file
// read at startup, a resolved secret.
//
// It resolves once and keeps the result, so the strategy sees one spec
// instance and Event.Spec stays usable as a correlation key. Resolution is
// guarded because a blueprint may be shared by projects built concurrently,
// even though a single build runs its ops one at a time.
//
// Wrapping the resolved spec rather than forwarding to it is what keeps the
// optional interfaces working: the strategy type-asserts the real spec, so
// a deferred spec's Comparer, Exister, and Remover are all still found.
type deferredOp[P Target] struct {
	newSpec func() Spec[P]
	wrap    func(Spec[P]) Op
	once    sync.Once
	op      Op
}

// deferOp returns an op that builds its spec on first use and wraps it with
// wrap. Taking the strategy as a constructor leaves no room for an unknown
// one.
func deferOp[P Target](newSpec func() Spec[P], wrap func(Spec[P]) Op) Op {
	return &deferredOp[P]{newSpec: newSpec, wrap: wrap}
}

func (d *deferredOp[P]) resolve() Op {
	d.once.Do(func() { d.op = d.wrap(d.newSpec()) })
	return d.op
}

// Run implements Op.
func (d *deferredOp[P]) Run(ctx context.Context, t Target) error {
	return d.resolve().Run(ctx, t)
}

// Describe implements Describer, reporting the resolved spec. It resolves
// the spec if a run has not already done so.
func (d *deferredOp[P]) Describe() OpInfo {
	return d.resolve().(Describer).Describe()
}
