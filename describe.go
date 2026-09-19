package spectrik

// OpInfo describes an op: the strategy applied and the spec it wraps.
type OpInfo struct {
	Strategy Strategy
	Spec     any
}

// Describer is implemented by Present, Ensure, and Absent so a consumer can
// report on an op without naming the project type it was built for. A plan
// or list command walks ops it did not construct, so it cannot assert
// Ensure[*MyProject] to reach the spec; it asserts Describer instead.
type Describer interface {
	Describe() OpInfo
}

// Describe implements Describer.
func (op Present[P]) Describe() OpInfo {
	return OpInfo{Strategy: StrategyPresent, Spec: op.Spec}
}

// Describe implements Describer.
func (op Ensure[P]) Describe() OpInfo {
	return OpInfo{Strategy: StrategyEnsure, Spec: op.Spec}
}

// Describe implements Describer.
func (op Absent[P]) Describe() OpInfo {
	return OpInfo{Strategy: StrategyAbsent, Spec: op.Spec}
}
