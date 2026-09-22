package spectrik

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"testing"
)

// recordOp appends its label to a shared log when run, or fails on demand.
type recordOp struct {
	label string
	log   *[]string
	err   error
}

func (op recordOp) Run(ctx context.Context, t Target) error {
	*op.log = append(*op.log, op.label)
	return op.err
}

var errOp = errors.New("op failed")

func TestBlueprintRunsOpsInOrder(t *testing.T) {
	var log []string
	bp := &Blueprint{Name: "base", Ops: []Op{
		recordOp{label: "one", log: &log},
		recordOp{label: "two", log: &log},
		recordOp{label: "three", log: &log},
	}}

	if err := bp.Build(context.Background(), newTarget()); err != nil {
		t.Fatal(err)
	}
	if got, want := join(log), "one,two,three"; got != want {
		t.Fatalf("ran %s, want %s", got, want)
	}
}

func TestBlueprintStopsAtFirstError(t *testing.T) {
	var log []string
	bp := &Blueprint{Name: "base", Ops: []Op{
		recordOp{label: "one", log: &log},
		recordOp{label: "two", log: &log, err: errOp},
		recordOp{label: "three", log: &log},
	}}

	err := bp.Build(context.Background(), newTarget())
	if !errors.Is(err, errOp) {
		t.Fatalf("err = %v, want %v", err, errOp)
	}
	if got, want := err.Error(), "blueprint base: op failed"; got != want {
		t.Fatalf("error = %q, want %q", got, want)
	}
	if got, want := join(log), "one,two"; got != want {
		t.Fatalf("ran %s, want %s", got, want)
	}
}

func join(parts []string) string { return strings.Join(parts, ",") }

func TestBlueprintContinuesOnErrorAndJoinsFailures(t *testing.T) {
	var log []string
	errTwo := errors.New("two failed")
	errThree := errors.New("three failed")
	bp := &Blueprint{Name: "base", Ops: []Op{
		recordOp{label: "one", log: &log},
		recordOp{label: "two", log: &log, err: errTwo},
		recordOp{label: "three", log: &log, err: errThree},
		recordOp{label: "four", log: &log},
	}}

	err := bp.Build(WithContinueOnError(context.Background(), true), newTarget())
	if !errors.Is(err, errTwo) || !errors.Is(err, errThree) {
		t.Fatalf("err = %v, want both failures", err)
	}
	if got, want := join(log), "one,two,three,four"; got != want {
		t.Fatalf("ran %s, want %s", got, want)
	}
	if got, want := err.Error(), "blueprint base: two failed\nblueprint base: three failed"; got != want {
		t.Fatalf("error = %q, want %q", got, want)
	}
}

func TestBlueprintContinueOnErrorReturnsNilWhenAllSucceed(t *testing.T) {
	var log []string
	bp := &Blueprint{Name: "base", Ops: []Op{recordOp{label: "one", log: &log}}}

	if err := bp.Build(WithContinueOnError(context.Background(), true), newTarget()); err != nil {
		t.Fatalf("err = %v, want nil", err)
	}
}

func TestBlueprintStopsWhenContextIsCancelled(t *testing.T) {
	for _, cont := range []bool{false, true} {
		t.Run(fmt.Sprintf("continue=%v", cont), func(t *testing.T) {
			var log []string
			ctx, cancel := context.WithCancel(WithContinueOnError(context.Background(), cont))
			defer cancel()
			bp := &Blueprint{Name: "base", Ops: []Op{
				recordOp{label: "one", log: &log},
				opFunc(func(context.Context, Target) error {
					log = append(log, "two")
					cancel()
					return nil
				}),
				recordOp{label: "three", log: &log},
				recordOp{label: "four", log: &log},
			}}

			err := bp.Build(ctx, newTarget())
			if !errors.Is(err, context.Canceled) {
				t.Fatalf("err = %v, want %v", err, context.Canceled)
			}
			if got, want := err.Error(), "blueprint base: context canceled"; got != want {
				t.Fatalf("error = %q, want %q", got, want)
			}
			if got, want := join(log), "one,two"; got != want {
				t.Fatalf("ran %s, want %s", got, want)
			}
		})
	}
}

func TestBlueprintKeepsEarlierFailuresWhenCancelled(t *testing.T) {
	var log []string
	ctx, cancel := context.WithCancel(WithContinueOnError(context.Background(), true))
	defer cancel()
	bp := &Blueprint{Name: "base", Ops: []Op{
		recordOp{label: "one", log: &log, err: errOp},
		opFunc(func(context.Context, Target) error {
			cancel()
			return nil
		}),
		recordOp{label: "three", log: &log},
	}}

	err := bp.Build(ctx, newTarget())
	if !errors.Is(err, errOp) || !errors.Is(err, context.Canceled) {
		t.Fatalf("err = %v, want the op failure and the cancellation", err)
	}
	if got, want := join(log), "one"; got != want {
		t.Fatalf("ran %s, want %s", got, want)
	}
}

func TestBlueprintRunsNothingWhenAlreadyCancelled(t *testing.T) {
	var log []string
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	bp := &Blueprint{Name: "base", Ops: []Op{recordOp{label: "one", log: &log}}}

	if err := bp.Build(ctx, newTarget()); !errors.Is(err, context.Canceled) {
		t.Fatalf("err = %v, want %v", err, context.Canceled)
	}
	if len(log) != 0 {
		t.Fatalf("ran %s, want nothing", join(log))
	}
}
