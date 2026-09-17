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

// Build runs every op against the target in order. It stops at the first
// error unless the context carries ContinueOnError, in which case every
// op runs and the failures are returned joined.
func (b *Blueprint) Build(ctx context.Context, t Target) error {
	var errs []error
	for _, op := range b.Ops {
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
