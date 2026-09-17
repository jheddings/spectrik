package spectrik

// Blueprint is a named, ordered, reusable collection of operations.
type Blueprint struct {
	Name string
	Ops  []Op
}
