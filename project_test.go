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

// lifecycleProject implements both lifecycle interfaces and records the order.
type lifecycleProject struct {
	Project
	log     *[]string
	preErr  error
	postErr error
}

func (p *lifecycleProject) PreBuild(ctx context.Context) error {
	*p.log = append(*p.log, "pre")
	return p.preErr
}

func (p *lifecycleProject) PostBuild(ctx context.Context) error {
	*p.log = append(*p.log, "post")
	return p.postErr
}

func newLifecycleProject(log *[]string) *lifecycleProject {
	return &lifecycleProject{
		Project: Project{Name: "red", Blueprints: []*Blueprint{
			{Name: "first", Ops: []Op{recordOp{label: "a", log: log}}},
		}},
		log: log,
	}
}

func TestBuildRunsPreBuildBeforeAndPostBuildAfter(t *testing.T) {
	var log []string
	tgt := newLifecycleProject(&log)

	if err := Build(context.Background(), tgt); err != nil {
		t.Fatal(err)
	}
	if got, want := join(log), "pre,a,post"; got != want {
		t.Fatalf("ran %s, want %s", got, want)
	}
}

func TestBuildAbortsWhenPreBuildFails(t *testing.T) {
	var log []string
	errPre := errors.New("no token")
	tgt := newLifecycleProject(&log)
	tgt.preErr = errPre

	err := Build(context.Background(), tgt)
	if !errors.Is(err, errPre) {
		t.Fatalf("err = %v, want %v", err, errPre)
	}
	if got, want := err.Error(), "project red: pre-build: no token"; got != want {
		t.Fatalf("error = %q, want %q", got, want)
	}
	if got, want := join(log), "pre,post"; got != want {
		t.Fatalf("ran %s, want %s (post-build runs even when pre-build fails)", got, want)
	}
}

func TestBuildRunsPostBuildAfterFailureAndJoinsErrors(t *testing.T) {
	var log []string
	errPost := errors.New("cleanup failed")
	tgt := newLifecycleProject(&log)
	tgt.Blueprints[0].Ops[0] = recordOp{label: "a", log: &log, err: errOp}
	tgt.postErr = errPost

	err := Build(context.Background(), tgt)
	if !errors.Is(err, errOp) || !errors.Is(err, errPost) {
		t.Fatalf("err = %v, want both the build and post-build failures", err)
	}
	want := "project red: blueprint first: op failed\nproject red: post-build: cleanup failed"
	if got := err.Error(); got != want {
		t.Fatalf("error = %q, want %q", got, want)
	}
	if got, want := join(log), "pre,a,post"; got != want {
		t.Fatalf("ran %s, want %s", got, want)
	}
}

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

func TestBuildStopsBetweenBlueprintsWhenCancelled(t *testing.T) {
	var log []string
	ctx, cancel := context.WithCancel(WithContinueOnError(context.Background(), true))
	defer cancel()
	tgt := newLifecycleProject(&log)
	tgt.Blueprints = []*Blueprint{
		{Name: "first", Ops: []Op{opFunc(func(context.Context, Target) error {
			log = append(log, "a")
			cancel()
			return nil
		})}},
		{Name: "second", Ops: []Op{recordOp{label: "b", log: &log}}},
		{Name: "third", Ops: []Op{recordOp{label: "c", log: &log}}},
	}

	err := Build(ctx, tgt)
	if !errors.Is(err, context.Canceled) {
		t.Fatalf("err = %v, want %v", err, context.Canceled)
	}
	// One cancellation, not one per blueprint left unstarted.
	if got, want := err.Error(), "project red: context canceled"; got != want {
		t.Fatalf("error = %q, want %q", got, want)
	}
	if got, want := join(log), "pre,a,post"; got != want {
		t.Fatalf("ran %s, want %s (post-build still runs)", got, want)
	}
}

// lifecycleRecorder captures LifecycleFailed and SpecFailed calls.
type lifecycleRecorder struct {
	calls   []string
	targets []Target
	errs    []error
}

func (r *lifecycleRecorder) hooks() *Hooks {
	return &Hooks{
		LifecycleFailed: func(t Target, stage Stage, err error) {
			r.calls = append(r.calls, string(stage)+":"+err.Error())
			r.targets = append(r.targets, t)
			r.errs = append(r.errs, err)
		},
		SpecFailed: func(e Event, err error) {
			r.calls = append(r.calls, "spec:"+err.Error())
		},
	}
}

func TestLifecycleFailedReportsPreBuild(t *testing.T) {
	var log []string
	errPre := errors.New("no token")
	tgt := newLifecycleProject(&log)
	tgt.preErr = errPre
	rec := &lifecycleRecorder{}

	_ = Build(WithHooks(context.Background(), rec.hooks()), tgt)
	if got, want := join(rec.calls), "pre-build:no token"; got != want {
		t.Fatalf("hooks = %s, want %s", got, want)
	}
	if rec.errs[0] != errPre {
		t.Fatalf("err = %v, want the PreBuild error itself", rec.errs[0])
	}
	if rec.targets[0] != tgt {
		t.Fatalf("target = %v, want the target that was built", rec.targets[0])
	}
}

func TestLifecycleFailedReportsPostBuild(t *testing.T) {
	var log []string
	tgt := newLifecycleProject(&log)
	tgt.postErr = errors.New("cleanup failed")
	rec := &lifecycleRecorder{}

	_ = Build(WithHooks(context.Background(), rec.hooks()), tgt)
	if got, want := join(rec.calls), "post-build:cleanup failed"; got != want {
		t.Fatalf("hooks = %s, want %s", got, want)
	}
}

func TestLifecycleFailedAndSpecFailedAccountForEveryFailure(t *testing.T) {
	var log []string
	tgt := newLifecycleProject(&log)
	tgt.Blueprints[0].Ops[0] = Ensure[*lifecycleProject]{Spec: failSpec{errors.New("boom")}}
	tgt.postErr = errors.New("cleanup failed")
	rec := &lifecycleRecorder{}

	err := Build(WithHooks(context.Background(), rec.hooks()), tgt)
	if err == nil {
		t.Fatal("err = nil, want the joined failures")
	}
	if got, want := join(rec.calls), "spec:boom,post-build:cleanup failed"; got != want {
		t.Fatalf("hooks = %s, want %s", got, want)
	}
}

func TestLifecycleFailedIsSilentOnSuccess(t *testing.T) {
	var log []string
	rec := &lifecycleRecorder{}

	if err := Build(WithHooks(context.Background(), rec.hooks()), newLifecycleProject(&log)); err != nil {
		t.Fatal(err)
	}
	if len(rec.calls) != 0 {
		t.Fatalf("hooks = %s, want none", join(rec.calls))
	}
}

// failSpec is a spec whose Apply always fails.
type failSpec struct{ err error }

func (s failSpec) Apply(context.Context, *lifecycleProject) error { return s.err }
