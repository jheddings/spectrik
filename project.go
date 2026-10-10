package spectrik

import (
	"context"
	"errors"
	"fmt"
)

// Project is the common data every build target carries. Consumer tools
// embed it in their own project struct to add domain-specific fields.
type Project struct {
	Name        string
	Description string
	Blueprints  []*Blueprint
}

// Base returns the embedded Project. Embedding Project is what makes a
// consumer's struct satisfy Target.
func (p *Project) Base() *Project { return p }

// PreBuilder is implemented by project types that need setup before any
// spec runs, such as resolving credentials. An error aborts the build.
type PreBuilder interface {
	PreBuild(ctx context.Context) error
}

// PostBuilder is implemented by project types that need teardown after the
// build. PostBuild always runs, even when PreBuild or a blueprint failed,
// and its error is joined with the build error.
type PostBuilder interface {
	PostBuild(ctx context.Context) error
}

// Build runs the target's lifecycle hooks and every blueprint in order. It
// stops at the first failing blueprint unless the context carries
// ContinueOnError, in which case every blueprint runs and the failures are
// returned joined. A PreBuild or PostBuild failure is also reported to the
// context's LifecycleFailed hook.
//
// Build checks ctx before each blueprint, as Blueprint.Build does before
// each op, so a cancelled build stops at the next op boundary and reports
// the cancellation once. PostBuild still runs.
//
// Everything runs on the calling goroutine: blueprints in order, and within
// each blueprint its ops in order, one at a time. Build starts no goroutine
// of its own, so hooks and specs need no locking against each other.
//
// Build is a function rather than a method on Project because an embedded
// Project cannot see the consumer struct that embeds it, and ops need that
// outer struct.
func Build(ctx context.Context, t Target) (err error) {
	base := t.Base()
	h := hooksFrom(ctx)

	if post, ok := t.(PostBuilder); ok {
		defer func() {
			if perr := post.PostBuild(ctx); perr != nil {
				h.lifecycleFailed(t, StagePostBuild, perr)
				err = errors.Join(err, fmt.Errorf("project %s: %s: %w", base.Name, StagePostBuild, perr))
			}
		}()
	}

	if pre, ok := t.(PreBuilder); ok {
		if err := pre.PreBuild(ctx); err != nil {
			h.lifecycleFailed(t, StagePreBuild, err)
			return fmt.Errorf("project %s: %s: %w", base.Name, StagePreBuild, err)
		}
	}

	var errs []error
	for _, bp := range base.Blueprints {
		if err := ctx.Err(); err != nil {
			errs = append(errs, fmt.Errorf("project %s: %w", base.Name, err))
			break
		}
		err := bp.Build(ctx, t)
		if err == nil {
			continue
		}
		err = fmt.Errorf("project %s: %w", base.Name, err)
		if !ContinueOnError(ctx) {
			return err
		}
		errs = append(errs, err)
		if ctx.Err() != nil {
			// No later blueprint would start an op.
			break
		}
	}
	return errors.Join(errs...)
}
