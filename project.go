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

// Build runs every blueprint of the target in order. It stops at the first
// failing blueprint unless the context carries ContinueOnError, in which
// case every blueprint runs and the failures are returned joined.
//
// Build is a function rather than a method on Project because an embedded
// Project cannot see the consumer struct that embeds it, and ops need that
// outer struct.
func Build(ctx context.Context, t Target) error {
	base := t.Base()
	var errs []error
	for _, bp := range base.Blueprints {
		err := bp.Build(ctx, t)
		if err == nil {
			continue
		}
		err = fmt.Errorf("project %s: %w", base.Name, err)
		if !ContinueOnError(ctx) {
			return err
		}
		errs = append(errs, err)
	}
	return errors.Join(errs...)
}
