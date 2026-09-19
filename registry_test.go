package spectrik

import (
	"context"
	"errors"
	"strings"
	"testing"
)

// labelSpec is a consumer-style spec with one configurable field.
type labelSpec struct {
	Name string
	seen *[]string
}

func (s *labelSpec) Apply(ctx context.Context, p *testProject) error {
	*s.seen = append(*s.seen, "label:"+s.Name)
	return nil
}

func (s *labelSpec) Exists(ctx context.Context, p *testProject) (bool, error) {
	return false, nil
}

func (s *labelSpec) Remove(ctx context.Context, p *testProject) error {
	return nil
}

func newTestRegistry() *Registry {
	reg := NewRegistry()
	RegisterSpec(reg, "label", func() Spec[*testProject] { return &labelSpec{} })
	return reg
}

func TestNewOpWrapsSpecInStrategy(t *testing.T) {
	tests := []struct {
		strategy Strategy
		isWanted func(Op) bool
	}{
		{StrategyPresent, func(op Op) bool { _, ok := op.(Present[*testProject]); return ok }},
		{StrategyEnsure, func(op Op) bool { _, ok := op.(Ensure[*testProject]); return ok }},
		{StrategyAbsent, func(op Op) bool { _, ok := op.(Absent[*testProject]); return ok }},
	}
	reg := newTestRegistry()

	for _, tt := range tests {
		t.Run(string(tt.strategy), func(t *testing.T) {
			op, err := reg.NewOp("label", tt.strategy, nil)
			if err != nil {
				t.Fatal(err)
			}
			if !tt.isWanted(op) {
				t.Fatalf("op is %T, want the %s strategy over *labelSpec", op, tt.strategy)
			}
		})
	}
}

func TestNewOpDecodesTheSpecBeforeWrapping(t *testing.T) {
	var seen []string
	reg := newTestRegistry()

	op, err := reg.NewOp("label", StrategyEnsure, func(spec any) error {
		s := spec.(*labelSpec)
		s.Name = "bug"
		s.seen = &seen
		return nil
	})
	if err != nil {
		t.Fatal(err)
	}
	if err := op.Run(context.Background(), newTarget()); err != nil {
		t.Fatal(err)
	}
	if got, want := join(seen), "label:bug"; got != want {
		t.Fatalf("ran %s, want %s", got, want)
	}
}

func TestNewOpRejectsAbsentForNonRemovableSpec(t *testing.T) {
	reg := NewRegistry()
	RegisterSpec(reg, "plain", func() Spec[*testProject] { return applySpec{&spy{}} })

	_, err := reg.NewOp("plain", StrategyAbsent, nil)
	if !errors.Is(err, ErrNotRemovable) {
		t.Fatalf("err = %v, want ErrNotRemovable", err)
	}
	if got, want := err.Error(), "spec plain: spec does not support removal"; got != want {
		t.Fatalf("error = %q, want %q", got, want)
	}
}

func TestNewOpReturnsDecodeError(t *testing.T) {
	reg := newTestRegistry()
	errDecode := errors.New("bad attribute")

	_, err := reg.NewOp("label", StrategyEnsure, func(spec any) error { return errDecode })
	if !errors.Is(err, errDecode) {
		t.Fatalf("err = %v, want %v", err, errDecode)
	}
	if got, want := err.Error(), "spec label: bad attribute"; got != want {
		t.Fatalf("error = %q, want %q", got, want)
	}
}

func TestNewOpRejectsUnknownSpec(t *testing.T) {
	reg := newTestRegistry()

	_, err := reg.NewOp("widget", StrategyEnsure, nil)
	if err == nil {
		t.Fatal("expected an error")
	}
	if !strings.Contains(err.Error(), `unknown spec type "widget"`) {
		t.Fatalf("error = %q", err)
	}
}

func TestNewOpRejectsUnknownStrategy(t *testing.T) {
	reg := newTestRegistry()

	_, err := reg.NewOp("label", Strategy("maybe"), nil)
	if err == nil {
		t.Fatal("expected an error")
	}
	if !strings.Contains(err.Error(), `unknown strategy "maybe"`) {
		t.Fatalf("error = %q", err)
	}
}

func TestNewProjectConstructsAndDecodes(t *testing.T) {
	reg := NewRegistry()
	RegisterProject(reg, "github", func() *testProject { return &testProject{} })

	tgt, err := reg.NewProject("github", func(p any) error {
		p.(*testProject).Owner = "acme"
		return nil
	})
	if err != nil {
		t.Fatal(err)
	}
	got, ok := tgt.(*testProject)
	if !ok {
		t.Fatalf("project is %T, want *testProject", tgt)
	}
	if got.Owner != "acme" {
		t.Fatalf("Owner = %q, want %q", got.Owner, "acme")
	}
}

func TestNewProjectReturnsDecodeError(t *testing.T) {
	reg := NewRegistry()
	RegisterProject(reg, "github", func() *testProject { return &testProject{} })
	errDecode := errors.New("bad attribute")

	_, err := reg.NewProject("github", func(any) error { return errDecode })
	if !errors.Is(err, errDecode) {
		t.Fatalf("err = %v, want %v", err, errDecode)
	}
	if got, want := err.Error(), "project type github: bad attribute"; got != want {
		t.Fatalf("error = %q, want %q", got, want)
	}
}

func TestNewProjectRejectsUnknownType(t *testing.T) {
	reg := NewRegistry()

	_, err := reg.NewProject("railway", nil)
	if err == nil {
		t.Fatal("expected an error")
	}
	if !strings.Contains(err.Error(), `unknown project type "railway"`) {
		t.Fatalf("error = %q", err)
	}
}

func TestProjectTypesAreSorted(t *testing.T) {
	reg := NewRegistry()
	RegisterProject(reg, "railway", func() *otherProject { return &otherProject{} })
	RegisterProject(reg, "github", func() *testProject { return &testProject{} })

	if got, want := join(reg.ProjectTypes()), "github,railway"; got != want {
		t.Fatalf("ProjectTypes = %s, want %s", got, want)
	}
}

func TestRegisterProjectPanicsOnDuplicate(t *testing.T) {
	reg := NewRegistry()
	RegisterProject(reg, "github", func() *testProject { return &testProject{} })

	defer func() {
		r := recover()
		if r == nil {
			t.Fatal("expected a panic")
		}
		if msg, _ := r.(string); !strings.Contains(msg, `project type "github" already registered`) {
			t.Fatalf("panic = %v", r)
		}
	}()
	RegisterProject(reg, "github", func() *testProject { return &testProject{} })
}

func TestRegisterSpecPanicsOnDuplicate(t *testing.T) {
	reg := newTestRegistry()

	defer func() {
		r := recover()
		if r == nil {
			t.Fatal("expected a panic")
		}
		if msg, _ := r.(string); !strings.Contains(msg, `spec type "label" already registered`) {
			t.Fatalf("panic = %v", r)
		}
	}()
	RegisterSpec(reg, "label", func() Spec[*testProject] { return &labelSpec{} })
}
