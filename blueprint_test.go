package spectrik

import (
	"context"
	"errors"
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
