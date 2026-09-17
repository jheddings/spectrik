package spectrik

import (
	"os"
	"strings"

	"github.com/zclconf/go-cty/cty"
)

// EnvVars returns the process environment as an HCL object value, for use
// as the `env` variable: Options{Variables: {"env": EnvVars()}} lets
// configuration write "${env.HOME}".
func EnvVars() cty.Value {
	vars := make(map[string]cty.Value)
	for _, kv := range os.Environ() {
		k, v, ok := strings.Cut(kv, "=")
		if !ok || k == "" {
			continue
		}
		vars[k] = cty.StringVal(v)
	}
	return cty.ObjectVal(vars)
}
