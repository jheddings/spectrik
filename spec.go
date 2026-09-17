package spectrik

import "context"

// Spec describes the desired state of one resource on a project of type P.
// Apply is the only required method; comparison, existence, and removal
// are optional interfaces that strategies detect by type assertion.
type Spec[P Target] interface {
	// Apply creates or updates the resource so it matches the spec.
	Apply(ctx context.Context, t P) error
}

// Comparer is implemented by specs that can tell whether the current state
// already matches the desired state. Specs that cannot, such as those
// managing secrets, leave it out and Ensure always applies.
type Comparer[P Target] interface {
	Equals(ctx context.Context, t P) (bool, error)
}

// Exister is implemented by specs that can tell whether the resource exists
// at all, independent of whether it matches. When absent, strategies fall
// back to Comparer, and then to assuming the resource is absent.
type Exister[P Target] interface {
	Exists(ctx context.Context, t P) (bool, error)
}

// Remover is implemented by specs whose resource can be deleted. Specs for
// irreversible resources leave it out, and Absent reports ErrNotRemovable.
type Remover[P Target] interface {
	Remove(ctx context.Context, t P) error
}
