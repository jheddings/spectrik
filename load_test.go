package spectrik

import (
	"testing"
)

func TestEnvVarsExposesEnvironment(t *testing.T) {
	t.Setenv("SPECTRIK_TEST_VALUE", "hello")

	env := EnvVars()

	if !env.Type().IsObjectType() {
		t.Fatalf("EnvVars() is %s, want an object", env.Type().FriendlyName())
	}
	got := env.GetAttr("SPECTRIK_TEST_VALUE")
	if got.AsString() != "hello" {
		t.Fatalf("env.SPECTRIK_TEST_VALUE = %q, want %q", got.AsString(), "hello")
	}
}
