package spectrik

import (
	"context"
	"testing"
)

func TestDryRunDefaultsToFalse(t *testing.T) {
	if IsDryRun(context.Background()) {
		t.Fatal("IsDryRun = true on a bare context, want false")
	}
}

func TestWithDryRunSetsFlag(t *testing.T) {
	ctx := WithDryRun(context.Background(), true)
	if !IsDryRun(ctx) {
		t.Fatal("IsDryRun = false after WithDryRun(true)")
	}
}

func TestWithDryRunCanBeCleared(t *testing.T) {
	ctx := WithDryRun(context.Background(), true)
	ctx = WithDryRun(ctx, false)
	if IsDryRun(ctx) {
		t.Fatal("IsDryRun = true after WithDryRun(false)")
	}
}

func TestDryRunInheritedByChildContext(t *testing.T) {
	ctx := WithDryRun(context.Background(), true)
	child, cancel := context.WithCancel(ctx)
	defer cancel()
	if !IsDryRun(child) {
		t.Fatal("child context lost the dry-run flag")
	}
}

func TestContextValuesDoNotCollide(t *testing.T) {
	h := &Hooks{}

	ctx := WithHooks(WithContinueOnError(WithDryRun(context.Background(), true), true), h)
	if !IsDryRun(ctx) || !ContinueOnError(ctx) || hooksFrom(ctx) != h {
		t.Fatalf("dryRun=%t continue=%t hooks=%p; every value should survive", IsDryRun(ctx), ContinueOnError(ctx), hooksFrom(ctx))
	}

	ctx = WithDryRun(WithContinueOnError(WithHooks(context.Background(), h), true), true)
	if !IsDryRun(ctx) || !ContinueOnError(ctx) || hooksFrom(ctx) != h {
		t.Fatalf("dryRun=%t continue=%t hooks=%p; every value should survive regardless of order", IsDryRun(ctx), ContinueOnError(ctx), hooksFrom(ctx))
	}
}

func TestContinueOnErrorDefaultsToFalse(t *testing.T) {
	if ContinueOnError(context.Background()) {
		t.Fatal("ContinueOnError = true on a bare context, want false")
	}
}

func TestWithContinueOnErrorSetsFlag(t *testing.T) {
	ctx := WithContinueOnError(context.Background(), true)
	if !ContinueOnError(ctx) {
		t.Fatal("ContinueOnError = false after WithContinueOnError(true)")
	}
}
