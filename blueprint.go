package spectrik

import (
	"context"
	"fmt"
)

// Blueprint is a named, ordered, reusable collection of operations.
type Blueprint struct {
	Name string
	Ops  []Op
}

// Build runs every op against the target in order, stopping at the first
// error.
func (b *Blueprint) Build(ctx context.Context, t Target) error {
	for _, op := range b.Ops {
		if err := op.Run(ctx, t); err != nil {
			return fmt.Errorf("blueprint %s: %w", b.Name, err)
		}
	}
	return nil
}
