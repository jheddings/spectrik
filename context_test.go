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
