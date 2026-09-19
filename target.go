package spectrik

import "fmt"

// Target is anything a spec can operate on: any struct that embeds Project.
type Target interface {
	Base() *Project
}

// As narrows a Target to the concrete project type P. Strategies call it
// before handing the target to a Spec[P], so consumer specs never need to.
func As[P Target](t Target) (P, error) {
	p, ok := t.(P)
	if !ok {
		var zero P
		return zero, fmt.Errorf("project %q is %T, want %T", t.Base().Name, t, zero)
	}
	return p, nil
}
