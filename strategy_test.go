package spectrik

import (
	"context"
	"errors"
	"testing"
)

// spy records what a fake spec was asked to do and scripts its answers.
type spy struct {
	applied, removed int
	equals, exists   bool
	equalsErr        error
	existsErr        error
	applyErr         error
	removeErr        error
}

// applySpec implements only Spec.
type applySpec struct{ *spy }

func (s applySpec) Apply(ctx context.Context, p *testProject) error {
	s.applied++
	return s.applyErr
}

// equalsSpec adds Comparer.
type equalsSpec struct{ applySpec }

func (s equalsSpec) Equals(ctx context.Context, p *testProject) (bool, error) {
	return s.equals, s.equalsErr
}

// existsSpec adds Exister.
type existsSpec struct{ applySpec }

func (s existsSpec) Exists(ctx context.Context, p *testProject) (bool, error) {
	return s.exists, s.existsErr
}

// removeSpec adds Exister and Remover.
type removeSpec struct{ existsSpec }

func (s removeSpec) Remove(ctx context.Context, p *testProject) error {
	s.removed++
	return s.removeErr
}

var (
	errEquals = errors.New("equals failed")
	errExists = errors.New("exists failed")
	errApply  = errors.New("apply failed")
	errRemove = errors.New("remove failed")
)

func newTarget() *testProject {
	return &testProject{Project: Project{Name: "red"}}
}

func TestEnsure(t *testing.T) {
	tests := []struct {
		name        string
		spec        func(*spy) Spec[*testProject]
		spy         spy
		dryRun      bool
		wantApplied int
		wantErr     error
	}{
		{
			name:        "applies when the spec cannot compare",
			spec:        func(s *spy) Spec[*testProject] { return applySpec{s} },
			wantApplied: 1,
		},
		{
			name:        "skips when state matches",
			spec:        func(s *spy) Spec[*testProject] { return equalsSpec{applySpec{s}} },
			spy:         spy{equals: true},
			wantApplied: 0,
		},
		{
			name:        "applies when state differs",
			spec:        func(s *spy) Spec[*testProject] { return equalsSpec{applySpec{s}} },
			spy:         spy{equals: false},
			wantApplied: 1,
		},
		{
			name:    "returns the comparison error without applying",
			spec:    func(s *spy) Spec[*testProject] { return equalsSpec{applySpec{s}} },
			spy:     spy{equalsErr: errEquals},
			wantErr: errEquals,
		},
		{
			name:        "returns the apply error",
			spec:        func(s *spy) Spec[*testProject] { return applySpec{s} },
			spy:         spy{applyErr: errApply},
			wantApplied: 1,
			wantErr:     errApply,
		},
		{
			name:        "dry run does not apply when state differs",
			spec:        func(s *spy) Spec[*testProject] { return equalsSpec{applySpec{s}} },
			spy:         spy{equals: false},
			dryRun:      true,
			wantApplied: 0,
		},
		{
			name:        "dry run does not apply when the spec cannot compare",
			spec:        func(s *spy) Spec[*testProject] { return applySpec{s} },
			dryRun:      true,
			wantApplied: 0,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			s := tt.spy
			op := Ensure[*testProject]{Spec: tt.spec(&s)}
			err := op.Run(WithDryRun(context.Background(), tt.dryRun), newTarget())

			if !errors.Is(err, tt.wantErr) {
				t.Fatalf("err = %v, want %v", err, tt.wantErr)
			}
			if s.applied != tt.wantApplied {
				t.Fatalf("applied = %d, want %d", s.applied, tt.wantApplied)
			}
		})
	}
}

func TestPresent(t *testing.T) {
	tests := []struct {
		name        string
		spec        func(*spy) Spec[*testProject]
		spy         spy
		dryRun      bool
		wantApplied int
		wantErr     error
	}{
		{
			name:        "skips when the resource exists",
			spec:        func(s *spy) Spec[*testProject] { return existsSpec{applySpec{s}} },
			spy:         spy{exists: true},
			wantApplied: 0,
		},
		{
			name:        "applies when the resource is missing",
			spec:        func(s *spy) Spec[*testProject] { return existsSpec{applySpec{s}} },
			spy:         spy{exists: false},
			wantApplied: 1,
		},
		{
			name:        "falls back to Equals when the spec has no Exists",
			spec:        func(s *spy) Spec[*testProject] { return equalsSpec{applySpec{s}} },
			spy:         spy{equals: true},
			wantApplied: 0,
		},
		{
			name:        "assumes absent when the spec has neither",
			spec:        func(s *spy) Spec[*testProject] { return applySpec{s} },
			wantApplied: 1,
		},
		{
			name:    "returns the existence error without applying",
			spec:    func(s *spy) Spec[*testProject] { return existsSpec{applySpec{s}} },
			spy:     spy{existsErr: errExists},
			wantErr: errExists,
		},
		{
			name:        "dry run does not apply a missing resource",
			spec:        func(s *spy) Spec[*testProject] { return existsSpec{applySpec{s}} },
			spy:         spy{exists: false},
			dryRun:      true,
			wantApplied: 0,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			s := tt.spy
			op := Present[*testProject]{Spec: tt.spec(&s)}
			err := op.Run(WithDryRun(context.Background(), tt.dryRun), newTarget())

			if !errors.Is(err, tt.wantErr) {
				t.Fatalf("err = %v, want %v", err, tt.wantErr)
			}
			if s.applied != tt.wantApplied {
				t.Fatalf("applied = %d, want %d", s.applied, tt.wantApplied)
			}
		})
	}
}

func TestAbsent(t *testing.T) {
	tests := []struct {
		name        string
		spec        func(*spy) Spec[*testProject]
		spy         spy
		dryRun      bool
		wantRemoved int
		wantErr     error
	}{
		{
			name:        "removes when the resource exists",
			spec:        func(s *spy) Spec[*testProject] { return removeSpec{existsSpec{applySpec{s}}} },
			spy:         spy{exists: true},
			wantRemoved: 1,
		},
		{
			name:        "skips when the resource is missing",
			spec:        func(s *spy) Spec[*testProject] { return removeSpec{existsSpec{applySpec{s}}} },
			spy:         spy{exists: false},
			wantRemoved: 0,
		},
		{
			name:        "returns the remove error",
			spec:        func(s *spy) Spec[*testProject] { return removeSpec{existsSpec{applySpec{s}}} },
			spy:         spy{exists: true, removeErr: errRemove},
			wantRemoved: 1,
			wantErr:     errRemove,
		},
		{
			name:        "dry run does not remove an existing resource",
			spec:        func(s *spy) Spec[*testProject] { return removeSpec{existsSpec{applySpec{s}}} },
			spy:         spy{exists: true},
			dryRun:      true,
			wantRemoved: 0,
		},
		{
			name:    "fails when the spec does not support removal",
			spec:    func(s *spy) Spec[*testProject] { return existsSpec{applySpec{s}} },
			spy:     spy{exists: true},
			wantErr: ErrNotRemovable,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			s := tt.spy
			op := Absent[*testProject]{Spec: tt.spec(&s)}
			err := op.Run(WithDryRun(context.Background(), tt.dryRun), newTarget())

			if !errors.Is(err, tt.wantErr) {
				t.Fatalf("err = %v, want %v", err, tt.wantErr)
			}
			if s.removed != tt.wantRemoved {
				t.Fatalf("removed = %d, want %d", s.removed, tt.wantRemoved)
			}
			if s.applied != 0 {
				t.Fatalf("applied = %d, want 0", s.applied)
			}
		})
	}
}

func TestStrategyRejectsWrongTargetType(t *testing.T) {
	s := spy{}
	ops := []Op{
		Ensure[*testProject]{Spec: applySpec{&s}},
		Present[*testProject]{Spec: applySpec{&s}},
		Absent[*testProject]{Spec: removeSpec{existsSpec{applySpec{&s}}}},
	}
	wrong := &otherProject{Project: Project{Name: "beta"}}

	for _, op := range ops {
		err := op.Run(context.Background(), wrong)
		if err == nil {
			t.Fatalf("%T: expected an error", op)
		}
		const want = `project "beta" is *spectrik.otherProject, want *spectrik.testProject`
		if err.Error() != want {
			t.Fatalf("%T: error = %q, want %q", op, err, want)
		}
	}
	if s.applied != 0 || s.removed != 0 {
		t.Fatalf("spec was invoked on a wrong-typed target")
	}
}
