package spectrik

import (
	"context"
	"errors"
	"testing"
)

func TestBlueprintBuilderSetsNameAndDescription(t *testing.T) {
	bp := NewBlueprint[*testProject]("dotfiles").
		Description("symlinks and shell config").
		Compose()

	if got, want := bp.Name, "dotfiles"; got != want {
		t.Fatalf("Name = %q, want %q", got, want)
	}
	if got, want := bp.Description, "symlinks and shell config"; got != want {
		t.Fatalf("Description = %q, want %q", got, want)
	}
}

func TestBlueprintBuilderWrapsSpecsInStrategies(t *testing.T) {
	spec := applySpec{&spy{}}
	removable := removeSpec{existsSpec{applySpec{&spy{}}}}

	bp := NewBlueprint[*testProject]("strategies").
		Present(spec).
		Ensure(spec).
		Absent(removable).
		Compose()

	if len(bp.Ops) != 3 {
		t.Fatalf("len(Ops) = %d, want 3", len(bp.Ops))
	}
	if _, ok := bp.Ops[0].(Present[*testProject]); !ok {
		t.Fatalf("Ops[0] = %T, want Present[*spectrik.testProject]", bp.Ops[0])
	}
	if _, ok := bp.Ops[1].(Ensure[*testProject]); !ok {
		t.Fatalf("Ops[1] = %T, want Ensure[*spectrik.testProject]", bp.Ops[1])
	}
	if _, ok := bp.Ops[2].(Absent[*testProject]); !ok {
		t.Fatalf("Ops[2] = %T, want Absent[*spectrik.testProject]", bp.Ops[2])
	}
}

func TestBlueprintBuilderKeepsOpsInCallOrder(t *testing.T) {
	var log []string
	bp := NewBlueprint[*testProject]("ordered").
		Op(recordOp{label: "one", log: &log}).
		Op(recordOp{label: "two", log: &log}).
		Op(recordOp{label: "three", log: &log}).
		Compose()

	if err := bp.Build(context.Background(), newTarget()); err != nil {
		t.Fatal(err)
	}
	if got, want := join(log), "one,two,three"; got != want {
		t.Fatalf("ran %s, want %s", got, want)
	}
}

func TestBlueprintBuilderIncludeFlattensOpsInPlace(t *testing.T) {
	var log []string
	base := NewBlueprint[*testProject]("base").
		Op(recordOp{label: "base-one", log: &log}).
		Op(recordOp{label: "base-two", log: &log}).
		Compose()

	bp := NewBlueprint[*testProject]("outer").
		Op(recordOp{label: "before", log: &log}).
		Include(base).
		Op(recordOp{label: "after", log: &log}).
		Compose()

	if err := bp.Build(context.Background(), newTarget()); err != nil {
		t.Fatal(err)
	}
	if got, want := join(log), "before,base-one,base-two,after"; got != want {
		t.Fatalf("ran %s, want %s", got, want)
	}
}

func TestBlueprintBuilderIncludeDoesNotAliasTheIncludedBlueprint(t *testing.T) {
	var log []string
	base := NewBlueprint[*testProject]("base").
		Op(recordOp{label: "base-one", log: &log}).
		Compose()

	NewBlueprint[*testProject]("outer").
		Include(base).
		Op(recordOp{label: "after", log: &log}).
		Compose()

	if got := len(base.Ops); got != 1 {
		t.Fatalf("len(base.Ops) = %d, want 1; Include mutated the included blueprint", got)
	}
}

func TestBlueprintBuilderAbsentPanicsOnSpecWithoutRemover(t *testing.T) {
	defer func() {
		r := recover()
		if r == nil {
			t.Fatal("expected a panic")
		}
		const want = `spectrik: spec spectrik.applySpec does not support removal`
		if got, ok := r.(string); !ok || got != want {
			t.Fatalf("panic = %v, want %q", r, want)
		}
	}()

	NewBlueprint[*testProject]("bad").Absent(applySpec{&spy{}}).Compose()
}

func TestBlueprintBuilderBuildsAnEmptyBlueprint(t *testing.T) {
	bp := NewBlueprint[*testProject]("empty").Compose()

	if bp.Name != "empty" {
		t.Fatalf("Name = %q, want %q", bp.Name, "empty")
	}
	if len(bp.Ops) != 0 {
		t.Fatalf("len(Ops) = %d, want 0", len(bp.Ops))
	}
	if err := bp.Build(context.Background(), newTarget()); err != nil {
		t.Fatal(err)
	}
}

func TestProjectBuilderSetsNameAndDescription(t *testing.T) {
	p := NewProject(&testProject{}, "red").
		Description("the red machine").
		Construct()

	if got, want := p.Name, "red"; got != want {
		t.Fatalf("Name = %q, want %q", got, want)
	}
	if got, want := p.Description, "the red machine"; got != want {
		t.Fatalf("Description = %q, want %q", got, want)
	}
}

func TestProjectBuilderReturnsTheConcreteTarget(t *testing.T) {
	p := NewProject(&testProject{Owner: "risefamily"}, "red").Construct()

	if got, want := p.Owner, "risefamily"; got != want {
		t.Fatalf("Owner = %q, want %q; builder did not return the concrete target", got, want)
	}
}

func TestProjectBuilderUseAppendsBlueprintsInOrder(t *testing.T) {
	var log []string
	one := NewBlueprint[*testProject]("one").Op(recordOp{label: "one", log: &log}).Compose()
	two := NewBlueprint[*testProject]("two").Op(recordOp{label: "two", log: &log}).Compose()

	p := NewProject(&testProject{}, "red").Use(one).Use(two).Construct()

	if got := len(p.Blueprints); got != 2 {
		t.Fatalf("len(Blueprints) = %d, want 2", got)
	}
	if err := Build(context.Background(), p); err != nil {
		t.Fatal(err)
	}
	if got, want := join(log), "one,two"; got != want {
		t.Fatalf("ran %s, want %s", got, want)
	}
}

func TestProjectBuilderCollectsLooseOpsIntoAnInlineBlueprint(t *testing.T) {
	var log []string
	bp := NewBlueprint[*testProject]("used").Op(recordOp{label: "used", log: &log}).Compose()

	p := NewProject(&testProject{}, "red").
		Op(recordOp{label: "loose", log: &log}).
		Use(bp).
		Construct()

	if got := len(p.Blueprints); got != 2 {
		t.Fatalf("len(Blueprints) = %d, want 2", got)
	}
	if got, want := p.Blueprints[1].Name, "red:inline"; got != want {
		t.Fatalf("inline blueprint name = %q, want %q", got, want)
	}
	if err := Build(context.Background(), p); err != nil {
		t.Fatal(err)
	}
	// Inline ops run after every blueprint the project uses, matching how
	// the HCL loader orders `use` against inline strategy blocks.
	if got, want := join(log), "used,loose"; got != want {
		t.Fatalf("ran %s, want %s", got, want)
	}
}

func TestProjectBuilderAddsNoInlineBlueprintWithoutLooseOps(t *testing.T) {
	bp := NewBlueprint[*testProject]("used").Compose()

	p := NewProject(&testProject{}, "red").Use(bp).Construct()

	if got := len(p.Blueprints); got != 1 {
		t.Fatalf("len(Blueprints) = %d, want 1", got)
	}
}

func TestProjectBuilderWrapsLooseSpecsInStrategies(t *testing.T) {
	spec := applySpec{&spy{}}
	removable := removeSpec{existsSpec{applySpec{&spy{}}}}

	p := NewProject(&testProject{}, "red").
		Present(spec).
		Ensure(spec).
		Absent(removable).
		Construct()

	if got := len(p.Blueprints); got != 1 {
		t.Fatalf("len(Blueprints) = %d, want 1", got)
	}
	ops := p.Blueprints[0].Ops
	if len(ops) != 3 {
		t.Fatalf("len(Ops) = %d, want 3", len(ops))
	}
	if _, ok := ops[0].(Present[*testProject]); !ok {
		t.Fatalf("Ops[0] = %T, want Present[*spectrik.testProject]", ops[0])
	}
	if _, ok := ops[1].(Ensure[*testProject]); !ok {
		t.Fatalf("Ops[1] = %T, want Ensure[*spectrik.testProject]", ops[1])
	}
	if _, ok := ops[2].(Absent[*testProject]); !ok {
		t.Fatalf("Ops[2] = %T, want Absent[*spectrik.testProject]", ops[2])
	}
}

func TestProjectBuilderAbsentPanicsOnSpecWithoutRemover(t *testing.T) {
	defer func() {
		if r := recover(); r == nil {
			t.Fatal("expected a panic")
		}
	}()

	NewProject(&testProject{}, "red").Absent(applySpec{&spy{}}).Construct()
}

func TestBuiltProjectAppliesItsSpecs(t *testing.T) {
	s := &spy{}
	bp := NewBlueprint[*testProject]("dotfiles").Ensure(applySpec{s}).Compose()

	p := NewProject(&testProject{}, "red").Use(bp).Construct()

	if err := Build(context.Background(), p); err != nil {
		t.Fatal(err)
	}
	if s.applied != 1 {
		t.Fatalf("applied = %d, want 1", s.applied)
	}
}

func TestBuiltProjectHonoursDryRun(t *testing.T) {
	s := &spy{}
	bp := NewBlueprint[*testProject]("dotfiles").Ensure(applySpec{s}).Compose()

	p := NewProject(&testProject{}, "red").Use(bp).Construct()

	if err := Build(WithDryRun(context.Background(), true), p); err != nil {
		t.Fatal(err)
	}
	if s.applied != 0 {
		t.Fatalf("applied = %d, want 0", s.applied)
	}
}

func TestDeferredDoesNotBuildTheSpecWhileChaining(t *testing.T) {
	calls := 0
	NewBlueprint[*testProject]("late").
		EnsureDeferred(func() Spec[*testProject] {
			calls++
			return applySpec{&spy{}}
		}).
		Compose()

	if calls != 0 {
		t.Fatalf("constructor ran %d times while building the chain, want 0", calls)
	}
}

func TestDeferredBuildsTheSpecOnFirstRun(t *testing.T) {
	calls := 0
	s := &spy{}
	bp := NewBlueprint[*testProject]("late").
		EnsureDeferred(func() Spec[*testProject] {
			calls++
			return applySpec{s}
		}).
		Compose()

	if err := bp.Build(context.Background(), newTarget()); err != nil {
		t.Fatal(err)
	}
	if calls != 1 {
		t.Fatalf("constructor ran %d times, want 1", calls)
	}
	if s.applied != 1 {
		t.Fatalf("applied = %d, want 1", s.applied)
	}
}

func TestDeferredBuildsTheSpecOnlyOnceAcrossRuns(t *testing.T) {
	calls := 0
	bp := NewBlueprint[*testProject]("late").
		EnsureDeferred(func() Spec[*testProject] {
			calls++
			return applySpec{&spy{}}
		}).
		Compose()

	for range 3 {
		if err := bp.Build(context.Background(), newTarget()); err != nil {
			t.Fatal(err)
		}
	}
	if calls != 1 {
		t.Fatalf("constructor ran %d times, want 1", calls)
	}
}

func TestDeferredHonoursOptionalInterfacesOnTheResolvedSpec(t *testing.T) {
	// A naive wrapper would hide Comparer from Ensure and force an apply.
	s := &spy{equals: true}
	bp := NewBlueprint[*testProject]("late").
		EnsureDeferred(func() Spec[*testProject] { return equalsSpec{applySpec{s}} }).
		Compose()

	if err := bp.Build(context.Background(), newTarget()); err != nil {
		t.Fatal(err)
	}
	if s.applied != 0 {
		t.Fatalf("applied = %d, want 0; Comparer on the resolved spec was ignored", s.applied)
	}
}

func TestDeferredAbsentRemovesThroughTheResolvedRemover(t *testing.T) {
	s := &spy{exists: true}
	bp := NewBlueprint[*testProject]("late").
		AbsentDeferred(func() Spec[*testProject] { return removeSpec{existsSpec{applySpec{s}}} }).
		Compose()

	if err := bp.Build(context.Background(), newTarget()); err != nil {
		t.Fatal(err)
	}
	if s.removed != 1 {
		t.Fatalf("removed = %d, want 1", s.removed)
	}
}

func TestDeferredAbsentReportsNotRemovableAtRun(t *testing.T) {
	// Absent panics at chain time; AbsentDeferred cannot, because the spec
	// does not exist yet, so it falls back to the strategy's run-time error.
	bp := NewBlueprint[*testProject]("late").
		AbsentDeferred(func() Spec[*testProject] { return applySpec{&spy{}} }).
		Compose()

	err := bp.Build(context.Background(), newTarget())
	if !errors.Is(err, ErrNotRemovable) {
		t.Fatalf("err = %v, want %v", err, ErrNotRemovable)
	}
}

func TestDeferredDescribesTheResolvedSpec(t *testing.T) {
	spec := applySpec{&spy{}}
	bp := NewBlueprint[*testProject]("late").
		PresentDeferred(func() Spec[*testProject] { return spec }).
		Compose()

	d, ok := bp.Ops[0].(Describer)
	if !ok {
		t.Fatalf("Ops[0] = %T, want a Describer", bp.Ops[0])
	}
	info := d.Describe()
	if info.Strategy != StrategyPresent {
		t.Fatalf("Strategy = %q, want %q", info.Strategy, StrategyPresent)
	}
	if info.Spec != Spec[*testProject](spec) {
		t.Fatalf("Spec = %v, want the resolved spec %v", info.Spec, spec)
	}
}

func TestDeferredReportsTheSameSpecToEveryHookEvent(t *testing.T) {
	// Event.Spec is documented as a correlation key, so every event for one
	// op must carry the same value.
	bp := NewBlueprint[*testProject]("late").
		EnsureDeferred(func() Spec[*testProject] { return applySpec{&spy{}} }).
		Compose()

	var seen []any
	ctx := WithHooks(context.Background(), &Hooks{
		SpecStart:   func(e Event) { seen = append(seen, e.Spec) },
		SpecApplied: func(e Event) { seen = append(seen, e.Spec) },
		SpecFinish:  func(e Event) { seen = append(seen, e.Spec) },
	})

	if err := bp.Build(ctx, newTarget()); err != nil {
		t.Fatal(err)
	}
	if len(seen) != 3 {
		t.Fatalf("saw %d events, want 3", len(seen))
	}
	for i, got := range seen {
		if got != seen[0] {
			t.Fatalf("event %d spec = %v, want %v", i, got, seen[0])
		}
	}
	if seen[0] == nil {
		t.Fatal("Event.Spec is nil; hooks saw the wrapper, not the resolved spec")
	}
}

func TestProjectBuilderDeferredWrapsInStrategies(t *testing.T) {
	p := NewProject(&testProject{}, "red").
		PresentDeferred(func() Spec[*testProject] { return applySpec{&spy{}} }).
		EnsureDeferred(func() Spec[*testProject] { return applySpec{&spy{}} }).
		AbsentDeferred(func() Spec[*testProject] { return removeSpec{existsSpec{applySpec{&spy{}}}} }).
		Construct()

	ops := p.Blueprints[0].Ops
	if len(ops) != 3 {
		t.Fatalf("len(Ops) = %d, want 3", len(ops))
	}
	want := []Strategy{StrategyPresent, StrategyEnsure, StrategyAbsent}
	for i, op := range ops {
		d, ok := op.(Describer)
		if !ok {
			t.Fatalf("Ops[%d] = %T, want a Describer", i, op)
		}
		if got := d.Describe().Strategy; got != want[i] {
			t.Fatalf("Ops[%d] strategy = %q, want %q", i, got, want[i])
		}
	}
}

func TestProjectBuilderDeferredAppliesAtBuildTime(t *testing.T) {
	s := &spy{}
	late := ""
	p := NewProject(&testProject{}, "red").
		EnsureDeferred(func() Spec[*testProject] {
			late = "resolved"
			return applySpec{s}
		}).
		Construct()

	if late != "" {
		t.Fatalf("constructor ran during Construct(), want it deferred to the run")
	}
	if err := Build(context.Background(), p); err != nil {
		t.Fatal(err)
	}
	if late != "resolved" || s.applied != 1 {
		t.Fatalf("late = %q, applied = %d, want %q and 1", late, s.applied, "resolved")
	}
}
