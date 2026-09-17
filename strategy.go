package spectrik

import (
	"context"
	"errors"
)

// ErrNotRemovable is returned by Absent when the spec has no Remover.
var ErrNotRemovable = errors.New("spec does not support removal")

// Present applies the spec only if the resource does not already exist.
type Present[P Target] struct {
	Spec Spec[P]
}

// Run implements Op.
func (op Present[P]) Run(ctx context.Context, t Target) error {
	p, err := As[P](t)
	if err != nil {
		return err
	}
	exists, err := exists(ctx, op.Spec, p)
	if err != nil {
		return err
	}
	if exists || IsDryRun(ctx) {
		return nil
	}
	return op.Spec.Apply(ctx, p)
}

// Ensure applies the spec unless the current state already matches. A spec
// without Comparer is always applied, since equality is unknown.
type Ensure[P Target] struct {
	Spec Spec[P]
}

// Run implements Op.
func (op Ensure[P]) Run(ctx context.Context, t Target) error {
	p, err := As[P](t)
	if err != nil {
		return err
	}
	if c, ok := op.Spec.(Comparer[P]); ok {
		same, err := c.Equals(ctx, p)
		if err != nil {
			return err
		}
		if same {
			return nil
		}
	}
	if IsDryRun(ctx) {
		return nil
	}
	return op.Spec.Apply(ctx, p)
}

// Absent removes the resource if it exists.
type Absent[P Target] struct {
	Spec Spec[P]
}

// Run implements Op.
func (op Absent[P]) Run(ctx context.Context, t Target) error {
	p, err := As[P](t)
	if err != nil {
		return err
	}
	r, ok := op.Spec.(Remover[P])
	if !ok {
		return ErrNotRemovable
	}
	exists, err := exists(ctx, op.Spec, p)
	if err != nil {
		return err
	}
	if !exists || IsDryRun(ctx) {
		return nil
	}
	return r.Remove(ctx, p)
}

// exists reports whether the spec's resource exists, falling back from
// Exister to Comparer, and finally assuming it is absent.
func exists[P Target](ctx context.Context, s Spec[P], p P) (bool, error) {
	switch v := s.(type) {
	case Exister[P]:
		return v.Exists(ctx, p)
	case Comparer[P]:
		return v.Equals(ctx, p)
	}
	return false, nil
}
