package spectrik

import (
	"context"
	"errors"
	"fmt"
	"testing"
)

// recorder captures hook calls as "name" or "name:detail" strings.
type recorder struct {
	calls  []string
	events []Event
}

func (r *recorder) hooks() *Hooks {
	note := func(name string) func(Event) {
		return func(e Event) {
			r.calls = append(r.calls, name)
			r.events = append(r.events, e)
		}
	}
	return &Hooks{
		SpecStart:   note("start"),
		SpecApplied: note("applied"),
		SpecRemoved: note("removed"),
		SpecFinish:  note("finish"),
		SpecSkipped: func(e Event, reason string) {
			r.calls = append(r.calls, "skipped:"+reason)
			r.events = append(r.events, e)
		},
		SpecFailed: func(e Event, err error) {
			r.calls = append(r.calls, "failed:"+err.Error())
			r.events = append(r.events, e)
		},
	}
}

func TestHooksFireInOrder(t *testing.T) {
	tests := []struct {
		name   string
		op     func(*spy) Op
		spy    spy
		dryRun bool
		want   string
	}{
		{
			name: "ensure applies",
			op:   func(s *spy) Op { return Ensure[*testProject]{Spec: equalsSpec{applySpec{s}}} },
			spy:  spy{equals: false},
			want: "start,applied,finish",
		},
		{
			name: "ensure skips when up to date",
			op:   func(s *spy) Op { return Ensure[*testProject]{Spec: equalsSpec{applySpec{s}}} },
			spy:  spy{equals: true},
			want: "start,skipped:up to date,finish",
		},
		{
			name:   "ensure dry run",
			op:     func(s *spy) Op { return Ensure[*testProject]{Spec: equalsSpec{applySpec{s}}} },
			spy:    spy{equals: false},
			dryRun: true,
			want:   "start,skipped:dry run; would apply,finish",
		},
		{
			name:   "ensure dry run with unknown equality",
			op:     func(s *spy) Op { return Ensure[*testProject]{Spec: applySpec{s}} },
			dryRun: true,
			want:   "start,skipped:dry run; would apply (equality unknown),finish",
		},
		{
			name: "ensure reports apply failure",
			op:   func(s *spy) Op { return Ensure[*testProject]{Spec: applySpec{s}} },
			spy:  spy{applyErr: errApply},
			want: "start,failed:apply failed,finish",
		},
		{
			name: "present skips an existing resource",
			op:   func(s *spy) Op { return Present[*testProject]{Spec: existsSpec{applySpec{s}}} },
			spy:  spy{exists: true},
			want: "start,skipped:already exists,finish",
		},
		{
			name: "present applies a missing resource",
			op:   func(s *spy) Op { return Present[*testProject]{Spec: existsSpec{applySpec{s}}} },
			spy:  spy{exists: false},
			want: "start,applied,finish",
		},
		{
			name:   "present dry run",
			op:     func(s *spy) Op { return Present[*testProject]{Spec: existsSpec{applySpec{s}}} },
			spy:    spy{exists: false},
			dryRun: true,
			want:   "start,skipped:dry run; would apply,finish",
		},
		{
			name: "absent removes an existing resource",
			op:   func(s *spy) Op { return Absent[*testProject]{Spec: removeSpec{existsSpec{applySpec{s}}}} },
			spy:  spy{exists: true},
			want: "start,removed,finish",
		},
		{
			name: "absent skips a missing resource",
			op:   func(s *spy) Op { return Absent[*testProject]{Spec: removeSpec{existsSpec{applySpec{s}}}} },
			spy:  spy{exists: false},
			want: "start,skipped:not present,finish",
		},
		{
			name:   "absent dry run",
			op:     func(s *spy) Op { return Absent[*testProject]{Spec: removeSpec{existsSpec{applySpec{s}}}} },
			spy:    spy{exists: true},
			dryRun: true,
			want:   "start,skipped:dry run; would remove,finish",
		},
		{
			name: "absent reports a non-removable spec",
			op:   func(s *spy) Op { return Absent[*testProject]{Spec: existsSpec{applySpec{s}}} },
			spy:  spy{exists: true},
			want: "start,failed:spec does not support removal,finish",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			s := tt.spy
			rec := &recorder{}
			ctx := WithHooks(WithDryRun(context.Background(), tt.dryRun), rec.hooks())

			_ = tt.op(&s).Run(ctx, newTarget())

			if got := join(rec.calls); got != tt.want {
				t.Fatalf("hooks = %s, want %s", got, tt.want)
			}
		})
	}
}

func TestHooksReportWrongTargetAsFailure(t *testing.T) {
	s := spy{}
	rec := &recorder{}
	ctx := WithHooks(context.Background(), rec.hooks())
	wrong := &otherProject{Project: Project{Name: "beta"}}

	_ = Ensure[*testProject]{Spec: applySpec{&s}}.Run(ctx, wrong)

	const want = `start,failed:project "beta" is *spectrik.otherProject, want *spectrik.testProject,finish`
	if got := join(rec.calls); got != want {
		t.Fatalf("hooks = %s, want %s", got, want)
	}
}

func TestEventCarriesStrategySpecAndTarget(t *testing.T) {
	s := spy{}
	spec := equalsSpec{applySpec{&s}}
	rec := &recorder{}
	ctx := WithHooks(context.Background(), rec.hooks())
	tgt := newTarget()

	if err := (Ensure[*testProject]{Spec: spec}).Run(ctx, tgt); err != nil {
		t.Fatal(err)
	}

	for _, e := range rec.events {
		if e.Strategy != StrategyEnsure {
			t.Fatalf("Strategy = %q, want %q", e.Strategy, StrategyEnsure)
		}
		if got, ok := e.Spec.(equalsSpec); !ok || got != spec {
			t.Fatalf("Spec = %#v, want the spec that was run", e.Spec)
		}
		if e.Target != tgt {
			t.Fatalf("Target = %v, want the target that was built", e.Target)
		}
	}
}

func TestPartialHooksAreSafe(t *testing.T) {
	var applied int
	ctx := WithHooks(context.Background(), &Hooks{
		SpecApplied: func(Event) { applied++ },
	})
	s := spy{}

	if err := (Ensure[*testProject]{Spec: applySpec{&s}}).Run(ctx, newTarget()); err != nil {
		t.Fatal(err)
	}
	if applied != 1 {
		t.Fatalf("SpecApplied called %d times, want 1", applied)
	}
}

func TestNoHooksIsSafe(t *testing.T) {
	s := spy{applyErr: errors.New("boom")}
	err := Ensure[*testProject]{Spec: applySpec{&s}}.Run(context.Background(), newTarget())
	if err == nil || err.Error() != "boom" {
		t.Fatalf("err = %v, want boom", err)
	}
}

func TestSpecPointerIsUsableAsMapKey(t *testing.T) {
	spec := &labelSpec{Name: "bug", seen: new([]string)}
	started := map[any]bool{}
	ctx := WithHooks(context.Background(), &Hooks{
		SpecStart: func(e Event) { started[e.Spec] = true },
	})

	if err := (Ensure[*testProject]{Spec: spec}).Run(ctx, newTarget()); err != nil {
		t.Fatal(err)
	}
	if !started[spec] {
		t.Fatalf("spec pointer not found as key; keys = %v", fmt.Sprint(started))
	}
}
