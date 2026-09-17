package spectrik

import (
	"context"
	"errors"
	"testing"
)

func TestBuildRunsBlueprintsInOrder(t *testing.T) {
	var log []string
	tgt := &testProject{Project: Project{Name: "red", Blueprints: []*Blueprint{
		{Name: "first", Ops: []Op{recordOp{label: "a", log: &log}}},
		{Name: "second", Ops: []Op{recordOp{label: "b", log: &log}, recordOp{label: "c", log: &log}}},
	}}}

	if err := Build(context.Background(), tgt); err != nil {
		t.Fatal(err)
	}
	if got, want := join(log), "a,b,c"; got != want {
		t.Fatalf("ran %s, want %s", got, want)
	}
}

func TestBuildStopsAtFirstFailingBlueprint(t *testing.T) {
	var log []string
	tgt := &testProject{Project: Project{Name: "red", Blueprints: []*Blueprint{
		{Name: "first", Ops: []Op{recordOp{label: "a", log: &log, err: errOp}}},
		{Name: "second", Ops: []Op{recordOp{label: "b", log: &log}}},
	}}}

	err := Build(context.Background(), tgt)
	if !errors.Is(err, errOp) {
		t.Fatalf("err = %v, want %v", err, errOp)
	}
	if got, want := err.Error(), "project red: blueprint first: op failed"; got != want {
		t.Fatalf("error = %q, want %q", got, want)
	}
	if got, want := join(log), "a"; got != want {
		t.Fatalf("ran %s, want %s", got, want)
	}
}

func TestBuildPassesTheOuterTargetToOps(t *testing.T) {
	var seen Target
	capture := opFunc(func(ctx context.Context, t Target) error {
		seen = t
		return nil
	})
	tgt := &testProject{Project: Project{Name: "red", Blueprints: []*Blueprint{
		{Name: "first", Ops: []Op{capture}},
	}}}

	if err := Build(context.Background(), tgt); err != nil {
		t.Fatal(err)
	}
	if seen != tgt {
		t.Fatalf("op received %T, want the *testProject that was built", seen)
	}
}

// opFunc adapts a function to Op.
type opFunc func(ctx context.Context, t Target) error

func (f opFunc) Run(ctx context.Context, t Target) error { return f(ctx, t) }

func TestBuildContinuesAcrossBlueprintsOnError(t *testing.T) {
	var log []string
	errA := errors.New("a failed")
	errC := errors.New("c failed")
	tgt := &testProject{Project: Project{Name: "red", Blueprints: []*Blueprint{
		{Name: "first", Ops: []Op{recordOp{label: "a", log: &log, err: errA}}},
		{Name: "second", Ops: []Op{recordOp{label: "b", log: &log}}},
		{Name: "third", Ops: []Op{recordOp{label: "c", log: &log, err: errC}}},
	}}}

	err := Build(WithContinueOnError(context.Background(), true), tgt)
	if !errors.Is(err, errA) || !errors.Is(err, errC) {
		t.Fatalf("err = %v, want both failures", err)
	}
	if got, want := join(log), "a,b,c"; got != want {
		t.Fatalf("ran %s, want %s", got, want)
	}
	want := "project red: blueprint first: a failed\nproject red: blueprint third: c failed"
	if got := err.Error(); got != want {
		t.Fatalf("error = %q, want %q", got, want)
	}
}
