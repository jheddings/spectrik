# Mixed Project Types Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Support multiple `Project` subclasses in a single workspace via a project registry, mirroring the existing spec registry pattern.

**Architecture:** A `@spectrik.project("name")` decorator registers project classes in a global `_project_registry`. The HCL parser consults this registry to recognize block types. `ProjectRef` carries the registered type name and resolves to the correct class at access time. `Workspace` drops its generic type parameter and gains an enhanced `select()` method for type-based queries.

**Tech Stack:** Python 3.12+, Pydantic v2, pytest

---

## Chunk 1: Project Registry and Core Changes

### Task 1: Create the project registry and decorator

**Files:**
- Modify: `src/spectrik/projects.py:1-35`
- Modify: `src/spectrik/__init__.py:6` (add `project` export)
- Test: `tests/test_projects.py` (create)

- [ ] **Step 1: Write failing tests for the registry**

Create `tests/test_projects.py`:

```python
"""Tests for spectrik.projects — project registry."""

from __future__ import annotations

import pytest

from spectrik.projects import Project, _project_registry, project


@pytest.fixture(autouse=True)
def _clean_project_registry():
    saved = _project_registry.copy()
    yield
    _project_registry.clear()
    _project_registry.update(saved)


class TestProjectDecorator:
    def test_base_project_registered(self):
        assert "project" in _project_registry
        assert _project_registry["project"] is Project

    def test_register_custom_type(self):
        @project("railway")
        class RailwayProject(Project):
            token: str = ""

        assert "railway" in _project_registry
        assert _project_registry["railway"] is RailwayProject

    def test_decorator_returns_class_unchanged(self):
        @project("custom")
        class CustomProject(Project):
            pass

        assert CustomProject.__name__ == "CustomProject"

    def test_duplicate_name_raises(self):
        @project("dupe")
        class First(Project):
            pass

        with pytest.raises(ValueError, match="dupe"):
            @project("dupe")
            class Second(Project):
                pass
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `just test -- tests/test_projects.py -v`
Expected: FAIL — `_project_registry` and `project` don't exist yet

- [ ] **Step 3: Implement registry and decorator**

In `src/spectrik/projects.py`, first add the future annotations import at the top:

```python
from __future__ import annotations
```

Then add the registry and decorator below the existing imports (before the `Project` class):

```python
_project_registry: dict[str, type[Project]] = {}


def project(name: str):
    """Register a Project subclass as an HCL block type."""

    def decorator[T: Project](cls: type[T]) -> type[T]:
        if name in _project_registry:
            raise ValueError(
                f"Duplicate project type: '{name}' is already registered "
                f"to {_project_registry[name].__name__}"
            )
        _project_registry[name] = cls
        return cls

    return decorator
```

After the `Project` class definition, add the auto-registration:

```python
# Register base Project as the "project" block type
project("project")(Project)
```

- [ ] **Step 4: Export `project` from `__init__.py`**

Add to `src/spectrik/__init__.py`:

```python
from .projects import project as project
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `just test -- tests/test_projects.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/spectrik/projects.py src/spectrik/__init__.py tests/test_projects.py
git commit -m "feat: add project registry and @project decorator (#30)"
```

---

### Task 2: Add `type_name` to `ProjectRef` and update resolution

**Files:**
- Modify: `src/spectrik/workspace.py:90-115` (ProjectRef)
- Test: `tests/test_workspace.py`

- [ ] **Step 1: Write failing tests for typed ProjectRef resolution**

Add to `tests/test_workspace.py`, updating imports to include `_project_registry` and `project`:

```python
from spectrik.projects import Project, _project_registry, project


@pytest.fixture(autouse=True)
def _clean_project_registry():
    saved = _project_registry.copy()
    yield
    _project_registry.clear()
    _project_registry.update(saved)
```

Add a new test class:

```python
class TestProjectRefTypeName:
    def test_resolve_uses_registry_type(self):
        @project("custom")
        class CustomProject(Project):
            token: str = ""

        ws = Workspace()
        ref = ProjectRef(
            name="myproj", type_name="custom",
            use=[], ops=[], attrs={"token": "abc"},
        )
        ws.add(ref)
        proj = ws["myproj"]
        assert isinstance(proj, CustomProject)
        assert proj.token == "abc"

    def test_resolve_default_project_type(self):
        ws = Workspace()
        ref = ProjectRef(name="myproj", type_name="project", use=[], ops=[])
        ws.add(ref)
        proj = ws["myproj"]
        assert isinstance(proj, Project)

    def test_resolve_unknown_type_raises(self):
        ws = Workspace()
        ref = ProjectRef(name="myproj", type_name="unknown", use=[], ops=[])
        ws.add(ref)
        with pytest.raises(ValueError, match="Unknown project type"):
            ws["myproj"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `just test -- tests/test_workspace.py::TestProjectRefTypeName -v`
Expected: FAIL — `type_name` field doesn't exist on `ProjectRef`

- [ ] **Step 3: Update `ProjectRef`**

In `src/spectrik/workspace.py`, modify the `ProjectRef` dataclass:

Note: `type_name` defaults to `"project"` so that existing code (e.g., `_parse_project`
in `hcl.py`) continues to work before Task 4 updates it to pass `type_name` explicitly.

```python
@dataclass
class ProjectRef(WorkspaceRef):
    """A project reference — a named build target with blueprints and inline ops."""

    use: list[str]
    ops: list[OperationRef]
    type_name: str = "project"
    description: str = ""
    attrs: dict[str, Any] = field(default_factory=dict)

    def resolve(self, workspace: Workspace) -> Project:
        from .projects import _project_registry

        if self.type_name not in _project_registry:
            raise ValueError(
                f"Unknown project type: '{self.type_name}'"
                " — ensure the module registering this project type is imported"
            )

        project_cls = _project_registry[self.type_name]

        blueprints: list[Blueprint] = []

        for bp_name in self.use:
            bp_ref = workspace.blueprints[bp_name]
            blueprints.append(bp_ref.resolve(workspace))

        inline_ops = [op.resolve(workspace) for op in self.ops]
        if inline_ops:
            blueprints.append(Blueprint(name=f"{self.name}:inline", ops=inline_ops))

        return project_cls(
            name=self.name,
            description=self.description,
            blueprints=blueprints,
            **self.attrs,
        )
```

- [ ] **Step 4: Run the new tests**

Run: `just test -- tests/test_workspace.py::TestProjectRefTypeName -v`
Expected: PASS

- [ ] **Step 5: Fix existing tests that construct `ProjectRef` without `type_name`**

Every `ProjectRef(...)` in `tests/test_workspace.py` needs `type_name="project"` added. Update all existing occurrences — there are roughly 15 call sites. For example:

```python
# Before
ProjectRef(name="myproj", use=[], ops=[], description="test")
# After
ProjectRef(name="myproj", type_name="project", use=[], ops=[], description="test")
```

Also add the `_clean_project_registry` fixture (autouse) to the file if not already present.

- [ ] **Step 6: Run full workspace tests**

Run: `just test -- tests/test_workspace.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/spectrik/workspace.py tests/test_workspace.py
git commit -m "feat(workspace): add type_name to ProjectRef for registry-based resolution (#30)"
```

---

### Task 3: Remove generic from `Workspace`, update `select()`

**Files:**
- Modify: `src/spectrik/workspace.py:118-203`
- Test: `tests/test_workspace.py`

- [ ] **Step 1: Write failing tests for new `select()` signature**

Add to `tests/test_workspace.py`:

```python
class TestSelectExtended:
    def test_select_by_single_name(self):
        ws = Workspace()
        ws.add(
            ProjectRef(name="a", type_name="project", use=[], ops=[]),
            ProjectRef(name="b", type_name="project", use=[], ops=[]),
        )
        result = ws.select(name="a")
        assert len(result) == 1
        assert result[0].name == "a"

    def test_select_by_project_type(self):
        @project("typed")
        class TypedProject(Project):
            pass

        ws = Workspace()
        ws.add(
            ProjectRef(name="a", type_name="project", use=[], ops=[]),
            ProjectRef(name="b", type_name="typed", use=[], ops=[]),
        )
        result = ws.select(project_type=TypedProject)
        assert len(result) == 1
        assert result[0].name == "b"
        assert isinstance(result[0], TypedProject)

    def test_select_by_name_and_type(self):
        @project("typed2")
        class TypedProject2(Project):
            pass

        ws = Workspace()
        ws.add(
            ProjectRef(name="a", type_name="typed2", use=[], ops=[]),
            ProjectRef(name="b", type_name="typed2", use=[], ops=[]),
            ProjectRef(name="c", type_name="project", use=[], ops=[]),
        )
        result = ws.select(name="a", project_type=TypedProject2)
        assert len(result) == 1
        assert result[0].name == "a"

    def test_select_by_names_and_type(self):
        @project("typed3")
        class TypedProject3(Project):
            pass

        ws = Workspace()
        ws.add(
            ProjectRef(name="a", type_name="typed3", use=[], ops=[]),
            ProjectRef(name="b", type_name="project", use=[], ops=[]),
            ProjectRef(name="c", type_name="typed3", use=[], ops=[]),
        )
        result = ws.select(names=["a", "c"], project_type=TypedProject3)
        assert len(result) == 2

    def test_select_name_and_names_merge(self):
        ws = Workspace()
        ws.add(
            ProjectRef(name="a", type_name="project", use=[], ops=[]),
            ProjectRef(name="b", type_name="project", use=[], ops=[]),
            ProjectRef(name="c", type_name="project", use=[], ops=[]),
        )
        result = ws.select(name="a", names=["b"])
        assert len(result) == 2
        names = {p.name for p in result}
        assert names == {"a", "b"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `just test -- tests/test_workspace.py::TestSelectExtended -v`
Expected: FAIL — `select()` doesn't accept `name` or `project_type` kwargs

- [ ] **Step 3: Remove generic, update `Workspace` class**

Replace the `Workspace` class in `src/spectrik/workspace.py`:

```python
class Workspace(Mapping[str, Project]):
    """Configured workspace that holds refs and resolves projects on access."""

    def __init__(self) -> None:
        self._blueprint_refs: dict[str, BlueprintRef] = {}
        self._project_refs: dict[str, ProjectRef] = {}

    @property
    def blueprints(self) -> Mapping[str, BlueprintRef]:
        return self._blueprint_refs

    @property
    def projects(self) -> Mapping[str, ProjectRef]:
        return self._project_refs

    def add(self, *refs: WorkspaceRef) -> None:
        """Add one or more refs to the workspace."""
        for ref in refs:
            match ref:
                case BlueprintRef():
                    if ref.name in self._blueprint_refs:
                        raise ValueError(f"Duplicate blueprint: '{ref.name}'")
                    logger.debug("Added blueprint '%s'", ref.name)
                    self._blueprint_refs[ref.name] = ref
                case ProjectRef():
                    if ref.name in self._project_refs:
                        raise ValueError(f"Duplicate project: '{ref.name}'")
                    logger.debug("Added project '%s'", ref.name)
                    self._project_refs[ref.name] = ref
                case _:
                    raise TypeError(
                        f"Unsupported ref type: {type(ref).__name__}. "
                        f"Expected BlueprintRef or ProjectRef."
                    )

    def __iadd__(self, ref: WorkspaceRef) -> Self:
        self.add(ref)
        return self

    def __getitem__(self, name: str) -> Project:
        return self._project_refs[name].resolve(self)

    def __contains__(self, name: object) -> bool:
        return name in self._project_refs

    def __iter__(self) -> Iterator[str]:
        return iter(self._project_refs)

    def __len__(self) -> int:
        return len(self._project_refs)

    @overload
    def get(self, name: str) -> Project | None: ...
    @overload
    def get(self, name: str, default: Project) -> Project: ...
    @overload
    def get(self, name: str, default: None) -> Project | None: ...
    def get(self, name: str, default: Any = None) -> Project | None:
        if name not in self._project_refs:
            return default
        return self._project_refs[name].resolve(self)

    def filter(self, names: Iterable[str]) -> list[Project]:
        """Return projects matching the given names, preserving input order."""
        return self.select(names=names)

    def select(
        self,
        *,
        name: str | None = None,
        names: Iterable[str] | None = None,
        project_type: type[Project] | None = None,
    ) -> list[Project]:
        """Return projects matching the given criteria.

        All filters are combined (intersection). With no filters, returns
        all projects.
        """
        # Determine candidate names
        target_names: list[str] | None = None
        if name is not None or names is not None:
            merged: list[str] = []
            if name is not None:
                merged.append(name)
            if names is not None:
                merged.extend(names)
            target_names = merged

        if target_names is not None:
            projects = [
                self._project_refs[n].resolve(self)
                for n in target_names
                if n in self._project_refs
            ]
        else:
            projects = list(self.values())

        if project_type is not None:
            projects = [p for p in projects if isinstance(p, project_type)]

        return projects

    def __repr__(self) -> str:
        bp_count = len(self._blueprint_refs)
        proj_count = len(self._project_refs)
        return f"Workspace(blueprints={bp_count}, projects={proj_count})"
```

- [ ] **Step 4: Update existing workspace tests**

Remove or update tests that reference the old API:
- `TestWorkspaceConstruction.test_default_project_type` — remove (no more `_project_type`)
- `TestWorkspaceConstruction.test_custom_project_type` — remove
- `TestWorkspaceConstruction.test_repr_with_custom_type` — remove
- `TestWorkspaceMapping.test_custom_project_type` — move to `TestProjectRefTypeName`, use registry
- Update `TestWorkspaceMapping.test_select_with_names` — change `ws.select(["a", "c"])` to `ws.select(names=["a", "c"])`
- Update `TestWorkspaceMapping.test_select_without_names` — no change needed
- Update `TestWorkspaceMapping.test_select_with_none` — change `ws.select(None)` to `ws.select()` (the old positional arg is gone)
- Update `TestWorkspaceMapping.test_select_with_empty_list` — change `ws.select([])` to `ws.select(names=[])`, and update assertion: empty names list with no other filters should return empty list (no longer returns all)

- [ ] **Step 5: Run full workspace tests**

Run: `just test -- tests/test_workspace.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/spectrik/workspace.py tests/test_workspace.py
git commit -m "feat(workspace): remove generic type, add select() with name/type filters (#30)"
```

---

## Chunk 2: HCL Pipeline and Integration

### Task 4: Update `parse()` to consult the project registry

**Files:**
- Modify: `src/spectrik/hcl.py:127-151`
- Test: `tests/test_hcl.py`

- [ ] **Step 1: Write failing tests for registry-based parsing**

Add to `tests/test_hcl.py`:

```python
from spectrik.projects import _project_registry, project


@pytest.fixture(autouse=True)
def _clean_project_registry():
    saved = _project_registry.copy()
    yield
    _project_registry.clear()
    _project_registry.update(saved)
```

Add a new test class:

```python
class TestParseRegisteredTypes:
    def test_parse_registered_project_type(self, tmp_path):
        @project("railway")
        class RailwayProject(Project):
            token: str = ""

        _write_hcl(
            tmp_path, ".", "test.hcl",
            """
            railway "alpha" {
                token = "abc"
                ensure "widget" { color = "red" }
            }
            """,
        )
        refs = parse(tmp_path / "test.hcl")
        assert len(refs) == 1
        ref = refs[0]
        assert isinstance(ref, ProjectRef)
        assert ref.name == "alpha"
        assert ref.type_name == "railway"
        assert ref.attrs == {"token": "abc"}

    def test_parse_mixed_types(self, tmp_path):
        @project("railway")
        class RailwayProject(Project):
            token: str = ""

        _write_hcl(
            tmp_path, ".", "test.hcl",
            """
            project "simple" {
                description = "basic"
            }
            railway "alpha" {
                token = "abc"
            }
            """,
        )
        refs = parse(tmp_path / "test.hcl")
        proj_refs = [r for r in refs if isinstance(r, ProjectRef)]
        assert len(proj_refs) == 2
        types = {r.type_name for r in proj_refs}
        assert types == {"project", "railway"}

    def test_parse_unregistered_block_raises(self, tmp_path):
        _write_hcl(
            tmp_path, ".", "test.hcl",
            """
            unknown_thing "x" {
                value = "y"
            }
            """,
        )
        with pytest.raises(ValueError, match="Unsupported block type"):
            parse(tmp_path / "test.hcl")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `just test -- tests/test_hcl.py::TestParseRegisteredTypes -v`
Expected: FAIL — `parse()` doesn't recognize `railway` blocks

- [ ] **Step 3: Update `parse()` in `hcl.py`**

```python
def parse(
    file: Path,
    *,
    context: dict[str, Any] | None = None,
) -> list[WorkspaceRef]:
    """Parse an HCL file into workspace refs."""
    from .projects import _project_registry

    data = load(file, context=context)
    refs: list[WorkspaceRef] = []

    for block_type in data:
        if block_type == "blueprint":
            refs.extend(
                _parse_blueprint(name, block_data, source=file)
                for name, block_data in _iter_blocks(data, block_type)
            )
        elif block_type in _project_registry:
            refs.extend(
                _parse_project(name, block_data, type_name=block_type, source=file)
                for name, block_data in _iter_blocks(data, block_type)
            )
        else:
            raise ValueError(f"Unsupported block type: '{block_type}'")

    return refs
```

- [ ] **Step 4: Update `_parse_project()` to accept `type_name`**

```python
def _parse_project(
    name: str,
    data: dict[str, Any],
    *,
    type_name: str = "project",
    source: Path | None = None,
) -> ProjectRef:
    """Translate an HCL project block into a ProjectRef."""
    skip_keys = {"use", "include", "description"} | _STRATEGY_NAMES
    return ProjectRef(
        name=name,
        type_name=type_name,
        use=data.get("use", []),
        ops=_parse_ops(data, source=source),
        description=data.get("description", ""),
        attrs={k: v for k, v in data.items() if k not in skip_keys},
    )
```

- [ ] **Step 5: Run the new tests**

Run: `just test -- tests/test_hcl.py::TestParseRegisteredTypes -v`
Expected: PASS

- [ ] **Step 6: Update existing `test_parse_unsupported_block_raises`**

The existing test in `TestParse` already tests this. Verify it still passes — it should, since the error message is the same.

- [ ] **Step 7: Run full HCL tests**

Run: `just test -- tests/test_hcl.py -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add src/spectrik/hcl.py tests/test_hcl.py
git commit -m "feat(hcl): parse registered project types from block names (#30)"
```

---

### Task 5: Update `scan()` to remove `project_type` parameter

**Files:**
- Modify: `src/spectrik/hcl.py:154-176`
- Test: `tests/test_hcl.py`

- [ ] **Step 1: Update `scan()` signature**

```python
def scan(
    path: str | Path,
    *,
    recurse: bool = True,
    context: dict[str, Any] | None = None,
) -> Workspace:
    """Scan a directory for .hcl files and return a ready Workspace."""

    directory = Path(path)
    ws = Workspace()

    if not directory.is_dir():
        logger.warning("Directory '%s' does not exist; skipping scan", directory)
        return ws

    logger.info("Scanning '%s' (recurse=%s)", directory, recurse)
    glob = directory.rglob if recurse else directory.glob

    for hcl_file in glob("*.hcl"):
        ws.add(*parse(hcl_file, context=context))

    return ws
```

- [ ] **Step 2: Update existing `test_hcl.py` tests**

- Remove `SampleProject` class (no longer needed for `scan()` tests)
- Update `test_scan_with_custom_project_type`: rewrite to use `@project("sample")` decorator and HCL block `sample "myproj" { ... }` instead of `project_type=SampleProject`
- Remove all `project_type=SampleProject` and `project_type=AppProject` arguments from `scan()` calls
- For tests that only use base `Project`, no changes needed

- [ ] **Step 3: Run full HCL tests**

Run: `just test -- tests/test_hcl.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add src/spectrik/hcl.py tests/test_hcl.py
git commit -m "feat(hcl): remove project_type parameter from scan() (#30)"
```

---

### Task 6: Update integration tests

**Files:**
- Modify: `tests/test_integration.py`

- [ ] **Step 1: Update integration tests to use project registry**

Key changes:
- Add `@project("app")` decorator to `AppProject`
- Add `_clean_project_registry` fixture (save/restore)
- Change HCL blocks from `project "myapp"` to `app "myapp"`
- Remove all `project_type=AppProject` from `hcl.scan()` calls
- `test_programmatic_api` stays unchanged (no HCL involved)

- [ ] **Step 2: Add mixed-type integration test**

```python
def test_mixed_project_types(self, tmp_path):
    """Multiple project types coexist in one workspace."""
    @project("other")
    class OtherProject(Project):
        endpoint: str = ""

    _write_hcl(
        tmp_path, "apps.hcl",
        """
        app "web" {
            repo = "owner/web"
            ensure "counter" { id = "1" }
        }
        """,
    )
    _write_hcl(
        tmp_path, "services.hcl",
        """
        other "api" {
            endpoint = "https://api.example.com"
            ensure "counter" { id = "2" }
        }
        """,
    )

    ws = hcl.scan(tmp_path)
    assert len(ws) == 2

    web = ws["web"]
    assert isinstance(web, AppProject)
    assert web.repo == "owner/web"

    api = ws["api"]
    assert isinstance(api, OtherProject)
    assert api.endpoint == "https://api.example.com"

    # select by type
    apps = ws.select(project_type=AppProject)
    assert len(apps) == 1
    assert apps[0].name == "web"

    # build all
    for proj in ws.values():
        proj.build()
    assert CountingSpec.apply_count == 2
```

- [ ] **Step 3: Run integration tests**

Run: `just test -- tests/test_integration.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add tests/test_integration.py
git commit -m "test: update integration tests for mixed project types (#30)"
```

---

### Task 7: Run preflight and clean up

- [ ] **Step 1: Run full preflight**

Run: `just preflight`
Expected: All checks pass (pre-commit + full test suite)

- [ ] **Step 2: Fix any issues found by preflight**

Address linting, type-checking, or test failures.

- [ ] **Step 3: Commit any fixes**

```bash
git commit -m "chore: fix lint/type issues from preflight (#30)"
```
