package spectrik

import "context"

type contextKey int

const dryRunKey contextKey = iota

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
