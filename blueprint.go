package spectrik

import (
	"context"
	"errors"
	"fmt"
)

// Blueprint is a named, ordered, reusable collection of operations.
type Blueprint struct {
	Name        string
	Description string
	Ops         []Op
}

// Build runs every op against the target in order, one at a time, on the
// calling goroutine. It stops at the first error unless the context carries
// ContinueOnError, in which case every op runs and the failures are
// returned joined.
//
// Build checks ctx before each op. Once ctx is done no further op starts,
// whatever ContinueOnError says, and ctx.Err() is joined to any failures
// already collected. An op left unstarted fires no hooks.
func (b *Blueprint) Build(ctx context.Context, t Target) error {
	var errs []error
	for _, op := range b.Ops {
		if err := ctx.Err(); err != nil {
			errs = append(errs, fmt.Errorf("blueprint %s: %w", b.Name, err))
			break
		}
		err := op.Run(ctx, t)
		if err == nil {
			continue
		}
		err = fmt.Errorf("blueprint %s: %w", b.Name, err)
		if !ContinueOnError(ctx) {
			return err
		}
		errs = append(errs, err)
	}
	return errors.Join(errs...)
}
