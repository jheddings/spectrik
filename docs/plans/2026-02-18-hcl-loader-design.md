# HCL Loader Redesign

**Date:** 2026-02-18
**Status:** Proposed

## Problem

Both consumers of spectrik (kodex and machina) follow the same boilerplate
pattern for HCL loading:

1. Side-effect import to register specs
2. Call `load_blueprints()` with a resolve_attrs callback
3. Call `load_projects()` with the same callback, passing blueprints through
4. Store the resulting projects somewhere (global dict, Click context, etc.)
5. Hand-roll accessor functions or inline dict filtering

Blueprints are never used after loading — they're an internal concept of HCL
composition. Consumers always operate on the resulting domain-specific projects.

The current API forces consumers to manage intermediate state (blueprints) and
reimplement the same registry patterns.

## Design

Two new public types in spectrik:

### `ProjectLoader[P: Project]`

Configured once per app with the project type and optional attribute resolver.
Separates "how my app interprets HCL" (configuration) from "load from this
path" (operation).

```python
class ProjectLoader[P: Project]:
    def __init__(
        self,
        project_type: type[P],
        resolve_attrs: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    ):
        self.project_type = project_type
        self.resolve_attrs = resolve_attrs

    def load(self, base_path: Path) -> Workspace[P]:
        blueprints = load_blueprints(base_path, resolve_attrs=self.resolve_attrs)
        projects = load_projects(
            base_path, blueprints,
            project_type=self.project_type,
            resolve_attrs=self.resolve_attrs,
        )
        return Workspace(projects)
```

### `Workspace[P: Project]`

A `Mapping[str, P]` collection returned by the loader. Follows standard Python
mapping protocol — iterates keys, supports `[]`, `in`, `len()`, and provides
`.keys()`, `.values()`, `.items()` via the ABC. Adds a `.filter()` convenience
method.

```python
class Workspace[P: Project](Mapping[str, P]):
    def __init__(self, projects: dict[str, P]):
        self._projects = projects

    def __getitem__(self, name: str) -> P:
        return self._projects[name]

    def __contains__(self, name: object) -> bool:
        return name in self._projects

    def __iter__(self) -> Iterator[str]:
        return iter(self._projects)

    def __len__(self) -> int:
        return len(self._projects)

    def get(self, name: str, default: P | None = None) -> P | None:
        return self._projects.get(name, default)

    def filter(self, names: Iterable[str]) -> list[P]:
        return [p for n in names if (p := self._projects.get(n)) is not None]
```

## Consumer API

### kodex

```python
# kodex/hcl.py
import kodex.specs  # noqa: F401 — register specs with spectrik

loader = ProjectLoader(KodexProject, resolve_attrs=_resolve_attrs)

# kodex/cli/__init__.py
workspace = loader.load(hcl_path)

# kodex/cli/apply.py
for name, project in workspace.items():
    project.build(dry_run=True)

workspace["kodex"]              # KodexProject (KeyError if missing)
workspace.get("kodex")          # KodexProject | None
workspace.filter(["a", "b"])    # list[KodexProject]
"kodex" in workspace            # True
len(workspace)                  # int
```

### machina

```python
# machina/hcl.py
import machina.specs  # noqa: F401

_init_vars()
loader = ProjectLoader(MachinaProject, resolve_attrs=resolve_attrs)

# machina/cli/__init__.py
workspace = loader.load(hcl_dir)
ctx.obj["workspace"] = workspace
```

## What changes

### spectrik

- New file: `spectrik/workspace.py` — contains `Workspace[P]`
- New class in `spectrik/hcl.py` — `ProjectLoader[P]`
- Re-export `ProjectLoader` and `Workspace` from `spectrik/__init__.py`
- Existing `load_blueprints()` and `load_projects()` remain as lower-level API

### kodex

- `src/kodex/hcl.py` — replace `load_hcl()` function with `ProjectLoader` instance
- `src/kodex/projects.py` — remove `_projects` global registry and accessor
  functions (`get_project`, `all_projects`, `filter_projects`); keep only
  `KodexProject` class definition
- `src/kodex/cli/__init__.py` — call `loader.load()`, store workspace
- `src/kodex/cli/apply.py` and `sync.py` — use workspace instead of registry
- `tests/test_hcl.py` — update to use `ProjectLoader` / `Workspace`

### machina

- `src/machina/hcl.py` — replace `load()` function with `ProjectLoader` instance
- `src/machina/cli/__init__.py` — store `workspace` instead of separate
  `blueprints` + `projects` dicts
- `src/machina/cli/apply.py` — use workspace iteration / filtering

## What stays the same

- Spec registration via `@spectrik.spec()` decorator — consumers still own the
  import side effect
- `resolve_attrs` callback — remains app-specific (1Password secrets in kodex,
  variable substitution in machina)
- Low-level `load_blueprints()` / `load_projects()` functions — available for
  edge cases but not needed by typical consumers
- `Blueprint`, `SpecOp`, `Context` — unchanged

## Design decisions

**Why a class for the loader, not a function:** The project type and
resolve_attrs are app-level configuration, not per-call parameters. The loader
separates "how my app interprets HCL" from "load from this path." This makes
the `load(path)` call clean and keeps configuration stable.

**Why Mapping, not custom iteration:** Python's `Mapping` ABC follows the
principle of least surprise — `for x in mapping` yields keys, `.values()`
yields values, `.items()` yields pairs. Custom iteration protocols confuse
consumers who expect standard Python behavior.

**Why blueprints are hidden:** Neither consumer uses blueprints after loading.
They exist solely for HCL composition. Exposing them adds API surface without
value.
