# Workspace Redesign

**Date:** 2026-02-19
**Status:** PROPOSED
**Branch:** workspace-loader (builds on current work)

## Problem

The current Workspace is an immutable result object created by a classmethod.
Consumers must call `Workspace.load(project_type, path)` in a single shot,
which assumes a fixed directory structure (`blueprints/` + `projects/`
subdirectories) and offers no incremental loading. Both machina and kodex
wrap spectrik's HCL functions in their own `hcl.py` modules to customize
loading — boilerplate that spectrik should eliminate.

## Design

### Workspace API

Workspace becomes a mutable, configured object that accumulates HCL data
and resolves projects lazily on access.

```python
class Workspace[P: Project](Mapping[str, P]):

    def __init__(self, project_type: type[P] = Project) -> None: ...

    def load(self, file: str | Path) -> None: ...
    def scan(self, path: str | Path, *, recurse: bool = True) -> None: ...

    # Mapping protocol — resolves projects fresh on each access
    def __getitem__(self, name: str) -> P: ...
    def __contains__(self, name: object) -> bool: ...
    def __iter__(self) -> Iterator[str]: ...
    def __len__(self) -> int: ...
    def get(self, name: str, default=None) -> P | None: ...

    # Convenience
    def filter(self, names: Iterable[str]) -> list[P]: ...

    # Debug-friendly repr (does not trigger resolution)
    def __repr__(self) -> str: ...
    # e.g. Workspace(project_type=KodexProject, blueprints=3, projects=5)
```

**Key behaviors:**

- `load(file)` parses a single `.hcl` file, extracts blueprint and project
  blocks, stores them as pending data. Raises `ValueError` on duplicate
  blueprint or project names.
- `scan(path, recurse=True)` discovers `.hcl` files in a directory and
  calls `load()` for each. With `recurse=True` uses `rglob("*.hcl")`;
  with `recurse=False` uses `glob("*.hcl")`. Files processed in sorted
  order for determinism.
- `load()` and `scan()` accept `str | Path`, converting internally.
- Mapping access (iteration, subscript, len, etc.) triggers full resolution:
  blueprints are resolved (with include handling), then projects are built
  as typed `P` instances. Resolution is fresh each time — no caching.
- `__repr__` shows pending blueprint/project counts without triggering
  resolution.

### Internal State

```python
self._project_type: type[P]
self._pending_blueprints: dict[str, dict[str, Any]]  # name -> raw HCL block
self._pending_projects: dict[str, dict[str, Any]]     # name -> raw HCL block
```

### Resolution Flow

Triggered on any Mapping access:

1. Resolve all `_pending_blueprints` — handle `include` references, detect
   circular dependencies → `dict[str, Blueprint]`
2. For each entry in `_pending_projects`, build a typed `P` instance using
   resolved blueprints (inline ops, `use` references, pass-through fields)
3. Return the requested data — no result caching

### Directory Structure

No subdirectory convention. Any `.hcl` file can contain both `blueprint`
and `project` blocks. Consumers organize files however they want.

### Duplicate Detection

At load time (not resolution time):

- Blueprint block with a name already in `_pending_blueprints` → `ValueError`
- Project block with a name already in `_pending_projects` → `ValueError`

### hcl.py Changes

- `hcl.load()` — stays public, thin wrapper around `hcl2.load()`
- `hcl.scan()` — new signature: `scan(path, project_type=Project, recurse=True)`
  returns a ready `Workspace` instance (convenience function)
- `load_blueprints()`, `load_projects()` — removed (Workspace handles
  orchestration)
- Internal helpers (`_collect_pending_blueprints`, `_resolve_blueprint`,
  `_parse_ops`, `_decode_spec`, `_build_project`) — stay, called from
  Workspace resolution
- Variable interpolation — stays in hcl.py, applied during resolution

### Public API

`__init__.py` re-exports remain the same. `Workspace` is already exported.
`hcl` module accessed as `import spectrik.hcl`.

## Consumer Usage

### Machina (default Project type)

```python
import machina.specs  # noqa: F401
import spectrik.hcl as hcl

# Quick path
workspace = hcl.scan(hcl_path)

# Or incremental
from spectrik import Workspace
ws = Workspace()
ws.scan(hcl_path)
```

### Kodex (custom Project type)

```python
import kodex.specs  # noqa: F401
import spectrik.hcl as hcl

# Quick path
workspace = hcl.scan(hcl_path, project_type=KodexProject)

# Or incremental
from spectrik import Workspace
ws = Workspace(project_type=KodexProject)
ws.scan(hcl_path)
ws["my-repo"].repo  # typed as KodexProject
```

## Testing

Key test scenarios:

1. Load single file with blueprints and projects (flat structure)
2. Scan with `recurse=True` across nested directories
3. Scan with `recurse=False` on a single directory
4. Duplicate blueprint name across files → `ValueError`
5. Duplicate project name across files → `ValueError`
6. Blueprint includes resolved across files loaded separately
7. Fresh resolution on each access (no caching)
8. `str | Path` acceptance on both `load()` and `scan()`
9. `__repr__` shows counts without triggering resolution
10. `hcl.scan()` convenience returns ready Workspace

## Future Considerations

- If fresh-resolution-per-access becomes a performance concern, add
  cache-with-invalidation (invalidate on `load()`/`scan()`). This is a
  backward-compatible enhancement — not needed now.
