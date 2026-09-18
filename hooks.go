package spectrik

import "context"

// Event identifies the spec execution a hook is being told about. Spec is
// the consumer's spec value, so a pointer spec can be used as a map key to
// correlate Start with the events that follow.
type Event struct {
	Strategy Strategy
	Spec     any
	Target   Target
}

// Hooks is a set of optional callbacks fired by strategies as they run,
// in the style of net/http/httptrace.ClientTrace. Any field may be nil.
// Every run fires SpecStart first and SpecFinish last; exactly one of
// SpecApplied, SpecRemoved, SpecSkipped, or SpecFailed fires in between.
type Hooks struct {
	SpecStart   func(Event)
	SpecApplied func(Event)
	SpecRemoved func(Event)
	SpecSkipped func(e Event, reason string)
	SpecFailed  func(e Event, err error)
	SpecFinish  func(Event)
}

// WithHooks returns a context whose strategy runs report to h.
func WithHooks(ctx context.Context, h *Hooks) context.Context {
	return context.WithValue(ctx, hooksKey, h)
}

// hooksFrom returns the hooks attached to ctx, or nil. All the firing
// helpers below accept a nil receiver, so callers never need to check.
func hooksFrom(ctx context.Context) *Hooks {
	h, _ := ctx.Value(hooksKey).(*Hooks)
	return h
}

func (h *Hooks) start(e Event) {
	if h != nil && h.SpecStart != nil {
		h.SpecStart(e)
	}
}

func (h *Hooks) applied(e Event) {
	if h != nil && h.SpecApplied != nil {
		h.SpecApplied(e)
	}
}

func (h *Hooks) removed(e Event) {
	if h != nil && h.SpecRemoved != nil {
		h.SpecRemoved(e)
	}
}

func (h *Hooks) skipped(e Event, reason string) {
	if h != nil && h.SpecSkipped != nil {
		h.SpecSkipped(e, reason)
	}
}

func (h *Hooks) failed(e Event, err error) {
	if h != nil && h.SpecFailed != nil {
		h.SpecFailed(e, err)
	}
}

func (h *Hooks) finish(e Event) {
	if h != nil && h.SpecFinish != nil {
		h.SpecFinish(e)
	}
}
