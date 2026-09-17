// Package spectrik provides a specification and blueprint model for
// declarative configuration-as-code tools.
//
// A Spec describes the desired state of a single resource. Strategies
// (Present, Ensure, Absent) decide when a spec is applied or removed.
// Blueprints group operations under a name so they can be reused, and
// Projects compose blueprints into a build target. Configuration is
// loaded from HCL files.
//
// The design is recorded in docs/adr/2026-09-17-go-port.md.
package spectrik
