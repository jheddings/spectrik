package spectrik

import "testing"

// testProject is a consumer-style project type used across the test suite.
// Specs in loader tests append to log so a test can see what ran.
type testProject struct {
	Project
	Owner string `hcl:"owner,optional"`
	log   []string
}

// otherProject is a second project type for wrong-target cases.
type otherProject struct {
	Project
}

func TestEmbeddedProjectSatisfiesTarget(t *testing.T) {
	var tgt Target = &testProject{Project: Project{Name: "red"}}

	if got := tgt.Base().Name; got != "red" {
		t.Fatalf("Base().Name = %q, want %q", got, "red")
	}
}

func TestAsNarrowsToConcreteType(t *testing.T) {
	var tgt Target = &testProject{Project: Project{Name: "red"}, Owner: "acme"}

	got, err := As[*testProject](tgt)
	if err != nil {
		t.Fatal(err)
	}
	if got.Owner != "acme" {
		t.Fatalf("Owner = %q, want %q", got.Owner, "acme")
	}
}

func TestAsRejectsWrongType(t *testing.T) {
	var tgt Target = &testProject{Project: Project{Name: "red"}}

	_, err := As[*otherProject](tgt)
	if err == nil {
		t.Fatal("expected an error")
	}
	const want = `project "red" is *spectrik.testProject, want *spectrik.otherProject`
	if err.Error() != want {
		t.Fatalf("error = %q, want %q", err, want)
	}
}
