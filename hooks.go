package spectrik

import "context"

// Event identifies the spec execution a hook is being told about.
//
// Spec is the consumer's own spec value, and it is the same value for every
// event of one op, so a pointer spec is usable as a map key to correlate
// SpecStart with the events that follow it.
type Event struct {
	Strategy Strategy
	Spec     any
	Target   Target
}

// Stage names a part of a build that runs outside any spec.
type Stage string

// The stages a LifecycleFailed hook can report.
const (
	StagePreBuild  Stage = "pre-build"
	StagePostBuild Stage = "post-build"
)

// Hooks is a set of optional callbacks fired by strategies as they run,
// in the style of net/http/httptrace.ClientTrace. Any field may be nil.
// Every run fires SpecStart first and SpecFinish last; exactly one of
// SpecApplied, SpecRemoved, SpecSkipped, or SpecFailed fires in between.
//
// LifecycleFailed is fired by Build, not by a strategy, when a target's
// PreBuild or PostBuild returns an error. Together with SpecFailed it
// accounts for every failure Build returns, so a consumer reporting
// results needs Build's error only to learn whether the build failed.
//
// Ops run one at a time, in order, on the goroutine that called Build, and
// hooks are called from that same goroutine. A Hooks value therefore needs
// no locking of its own, and at most one op is in flight at any moment.
type Hooks struct {
	SpecStart   func(Event)
	SpecApplied func(Event)
	SpecRemoved func(Event)
	SpecSkipped func(e Event, reason string)
	SpecFailed  func(e Event, err error)
	SpecFinish  func(Event)

	LifecycleFailed func(t Target, stage Stage, err error)
}

// WithHooks returns a context whose strategy runs report to h.
//
// If ctx already carries hooks, h is layered over them rather than
// replacing them, as httptrace.WithClientTrace does: each event calls h's
// callback first, then the existing one. This lets independent observers,
// such as a progress display and a logger, each attach their own Hooks. A
// nil h returns ctx unchanged.
func WithHooks(ctx context.Context, h *Hooks) context.Context {
	if h == nil {
		return ctx
	}
	if old := hooksFrom(ctx); old != nil {
		h = layer(h, old)
	}
	return context.WithValue(ctx, hooksKey, h)
}

// layer returns hooks that call first's callbacks, then second's.
func layer(first, second *Hooks) *Hooks {
	return &Hooks{
		SpecStart:   chain(first.SpecStart, second.SpecStart),
		SpecApplied: chain(first.SpecApplied, second.SpecApplied),
		SpecRemoved: chain(first.SpecRemoved, second.SpecRemoved),
		SpecSkipped: chain2(first.SpecSkipped, second.SpecSkipped),
		SpecFailed:  chain2(first.SpecFailed, second.SpecFailed),
		SpecFinish:  chain(first.SpecFinish, second.SpecFinish),

		LifecycleFailed: chainLifecycle(first.LifecycleFailed, second.LifecycleFailed),
	}
}

// chain calls a then b, either of which may be nil.
func chain(a, b func(Event)) func(Event) {
	switch {
	case a == nil:
		return b
	case b == nil:
		return a
	}
	return func(e Event) {
		a(e)
		b(e)
	}
}

// chain2 is chain for the callbacks that carry a detail beside the event.
func chain2[T any](a, b func(Event, T)) func(Event, T) {
	switch {
	case a == nil:
		return b
	case b == nil:
		return a
	}
	return func(e Event, v T) {
		a(e, v)
		b(e, v)
	}
}

// chainLifecycle is chain for LifecycleFailed, which reports a target
// rather than an event.
func chainLifecycle(a, b func(Target, Stage, error)) func(Target, Stage, error) {
	switch {
	case a == nil:
		return b
	case b == nil:
		return a
	}
	return func(t Target, s Stage, err error) {
		a(t, s, err)
		b(t, s, err)
	}
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

func (h *Hooks) lifecycleFailed(t Target, stage Stage, err error) {
	if h != nil && h.LifecycleFailed != nil {
		h.LifecycleFailed(t, stage, err)
	}
}
