package spectrik

import "context"

// contextKey is the type for every value this package stores in a context.
// All keys live in this one const block so they can never collide.
type contextKey int

const (
	dryRunKey contextKey = iota
	continueKey
	hooksKey
)

// WithDryRun returns a context in which strategies report what they would
// do without calling Apply or Remove. Specs never observe the flag.
func WithDryRun(ctx context.Context, dryRun bool) context.Context {
	return context.WithValue(ctx, dryRunKey, dryRun)
}

// IsDryRun reports whether ctx was created with WithDryRun(ctx, true).
func IsDryRun(ctx context.Context) bool {
	v, _ := ctx.Value(dryRunKey).(bool)
	return v
}

// WithContinueOnError returns a context in which Build and Blueprint.Build
// run every op even after one fails, returning the joined failures at the
// end. The default is to stop at the first error.
func WithContinueOnError(ctx context.Context, cont bool) context.Context {
	return context.WithValue(ctx, continueKey, cont)
}

// ContinueOnError reports whether ctx was created with
// WithContinueOnError(ctx, true).
func ContinueOnError(ctx context.Context) bool {
	v, _ := ctx.Value(continueKey).(bool)
	return v
}
