package spectrik

// Project is the common data every build target carries. Consumer tools
// embed it in their own project struct to add domain-specific fields.
type Project struct {
	Name        string
	Description string
	Blueprints  []*Blueprint
}

// Base returns the embedded Project. Embedding Project is what makes a
// consumer's struct satisfy Target.
func (p *Project) Base() *Project { return p }
