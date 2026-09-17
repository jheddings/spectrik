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
	return run(ctx, StrategyPresent, op.Spec, t, func(p P, h *Hooks, e Event) error {
		exists, err := exists(ctx, op.Spec, p)
		if err != nil {
			return err
		}
		switch {
		case exists:
			h.skipped(e, "already exists")
		case IsDryRun(ctx):
			h.skipped(e, "dry run; would apply")
		default:
			if err := op.Spec.Apply(ctx, p); err != nil {
				return err
			}
			h.applied(e)
		}
		return nil
	})
}

// Ensure applies the spec unless the current state already matches. A spec
// without Comparer is always applied, since equality is unknown.
type Ensure[P Target] struct {
	Spec Spec[P]
}

// Run implements Op.
func (op Ensure[P]) Run(ctx context.Context, t Target) error {
	return run(ctx, StrategyEnsure, op.Spec, t, func(p P, h *Hooks, e Event) error {
		reason := "dry run; would apply (equality unknown)"
		if c, ok := op.Spec.(Comparer[P]); ok {
			same, err := c.Equals(ctx, p)
			if err != nil {
				return err
			}
			if same {
				h.skipped(e, "up to date")
				return nil
			}
			reason = "dry run; would apply"
		}
		if IsDryRun(ctx) {
			h.skipped(e, reason)
			return nil
		}
		if err := op.Spec.Apply(ctx, p); err != nil {
			return err
		}
		h.applied(e)
		return nil
	})
}

// Absent removes the resource if it exists.
type Absent[P Target] struct {
	Spec Spec[P]
}

// Run implements Op.
func (op Absent[P]) Run(ctx context.Context, t Target) error {
	return run(ctx, StrategyAbsent, op.Spec, t, func(p P, h *Hooks, e Event) error {
		r, ok := op.Spec.(Remover[P])
		if !ok {
			return ErrNotRemovable
		}
		exists, err := exists(ctx, op.Spec, p)
		if err != nil {
			return err
		}
		switch {
		case !exists:
			h.skipped(e, "not present")
		case IsDryRun(ctx):
			h.skipped(e, "dry run; would remove")
		default:
			if err := r.Remove(ctx, p); err != nil {
				return err
			}
			h.removed(e)
		}
		return nil
	})
}

// run is the shared frame around a strategy: it narrows the target, fires
// the start and finish hooks, and reports any error through the failed
// hook before returning it.
func run[P Target](ctx context.Context, s Strategy, spec Spec[P], t Target, body func(P, *Hooks, Event) error) (err error) {
	h := hooksFrom(ctx)
	e := Event{Strategy: s, Spec: spec, Target: t}
	h.start(e)
	defer func() {
		if err != nil {
			h.failed(e, err)
		}
		h.finish(e)
	}()

	p, err := As[P](t)
	if err != nil {
		return err
	}
	return body(p, h, e)
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
