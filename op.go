package spectrik

import "context"

// Op is a runnable operation: a spec wrapped in a strategy. It is not
// generic, so a blueprint can hold ops for different project types.
type Op interface {
	Run(ctx context.Context, t Target) error
}
