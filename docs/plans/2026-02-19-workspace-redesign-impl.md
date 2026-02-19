# Workspace Redesign Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the immutable `Workspace` with a mutable, configured workspace that accumulates HCL data via `load()`/`scan()` and resolves projects lazily on Mapping access.

**Architecture:** Workspace stores raw blueprint/project blocks in `_pending_blueprints` and `_pending_projects` dicts. `load(file)` parses one HCL file and extracts blocks (raising on duplicates). `scan(path)` discovers `.hcl` files and calls `load()`. Mapping access triggers full resolution (blueprints → projects) fresh each time. `hcl.scan()` becomes a convenience that returns a ready Workspace.

**Tech Stack:** Python 3.12+, Pydantic v2, python-hcl2, pytest

---

### Task 1: Rewrite Workspace constructor and internal state

**Files:**
- Modify: `src/spectrik/workspace.py` (full rewrite)
- Test: `tests/test_workspace.py`

**Step 1: Write failing tests for the new constructor**

Replace the existing `tests/test_workspace.py` entirely:

```python
"""Tests for spectrik.workspace."""

from __future__ import annotations

import pytest

from spectrik.projects import Project
from spectrik.workspace import Workspace


class TestWorkspaceConstruction:
    def test_default_project_type(self):
        ws = Workspace()
        assert ws._project_type is Project

    def test_custom_project_type(self):
        class Custom(Project):
            extra: str = ""

        ws = Workspace(project_type=Custom)
        assert ws._project_type is Custom

    def test_empty_workspace_len(self):
        ws = Workspace()
        assert len(ws) == 0

    def test_empty_workspace_iter(self):
        ws = Workspace()
        assert list(ws) == []

    def test_empty_workspace_contains(self):
        ws = Workspace()
        assert "anything" not in ws

    def test_getitem_empty_raises(self):
        ws = Workspace()
        with pytest.raises(KeyError):
            ws["missing"]

    def test_get_empty_returns_none(self):
        ws = Workspace()
        assert ws.get("missing") is None

    def test_repr_empty(self):
        ws = Workspace()
        assert "Workspace" in repr(ws)
        assert "blueprints=0" in repr(ws)
        assert "projects=0" in repr(ws)

    def test_repr_with_custom_type(self):
        class Custom(Project):
            extra: str = ""

        ws = Workspace(project_type=Custom)
        assert "Custom" in repr(ws)
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_workspace.py -v`
Expected: FAIL — constructor signature mismatch (currently requires `projects` dict)

**Step 3: Rewrite workspace.py with new constructor and empty Mapping**

Replace `src/spectrik/workspace.py` entirely:

```python
"""Workspace — a mutable, typed collection of HCL-loaded projects."""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from typing import Any, overload

from spectrik.projects import Project


class Workspace[P: Project](Mapping[str, P]):
    """Configured workspace that accumulates HCL data and resolves projects on access.

    Construct with an optional project_type (defaults to Project), then call
    load() or scan() to add HCL data. Projects are resolved fresh on each
    Mapping access.
    """

    def __init__(self, project_type: type[P] = Project) -> None:  # type: ignore[assignment]
        self._project_type = project_type
        self._pending_blueprints: dict[str, dict[str, Any]] = {}
        self._pending_projects: dict[str, dict[str, Any]] = {}

    def _resolve(self) -> dict[str, P]:
        """Resolve all pending blueprints and build typed project instances."""
        from spectrik.hcl import _build_project, _resolve_blueprint

        # Resolve blueprints
        resolved_bps: dict[str, Any] = {}
        for name in self._pending_blueprints:
            _resolve_blueprint(name, self._pending_blueprints, resolved_bps, set())

        # Build projects
        projects: dict[str, P] = {}
        for proj_name, proj_data in self._pending_projects.items():
            projects[proj_name] = _build_project(
                proj_name,
                proj_data,
                resolved_bps,
                project_type=self._project_type,
            )
        return projects

    def __getitem__(self, name: str) -> P:
        return self._resolve()[name]

    def __contains__(self, name: object) -> bool:
        return name in self._pending_projects

    def __iter__(self) -> Iterator[str]:
        return iter(self._resolve())

    def __len__(self) -> int:
        return len(self._pending_projects)

    @overload
    def get(self, name: str) -> P | None: ...
    @overload
    def get(self, name: str, default: P) -> P: ...
    @overload
    def get(self, name: str, default: None) -> P | None: ...
    def get(self, name: str, default: Any = None) -> P | None:
        return self._resolve().get(name, default)

    def filter(self, names: Iterable[str]) -> list[P]:
        """Return projects matching the given names, preserving input order."""
        resolved = self._resolve()
        return [p for n in names if (p := resolved.get(n)) is not None]

    def __repr__(self) -> str:
        type_name = self._project_type.__name__
        bp_count = len(self._pending_blueprints)
        proj_count = len(self._pending_projects)
        return f"Workspace(project_type={type_name}, blueprints={bp_count}, projects={proj_count})"
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_workspace.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/spectrik/workspace.py tests/test_workspace.py
git commit -m "refactor: rewrite Workspace with new constructor and lazy resolution"
```

---

### Task 2: Add Workspace.load() instance method

**Files:**
- Modify: `src/spectrik/workspace.py`
- Test: `tests/test_workspace.py`

**Step 1: Write failing tests for load()**

Append to `tests/test_workspace.py`:

```python
from pathlib import Path

from spectrik.specs import Specification, _spec_registry
from spectrik.context import Context


class TrackingSpec(Specification["Project"]):
    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def equals(self, ctx: Context[Project]) -> bool:
        return False

    def apply(self, ctx: Context[Project]) -> None:
        pass

    def remove(self, ctx: Context[Project]) -> None:
        pass


def _write_hcl(tmp_path: Path, filename: str, content: str) -> Path:
    """Write an HCL file directly into tmp_path (flat structure)."""
    f = tmp_path / filename
    f.write_text(content)
    return f


@pytest.fixture(autouse=True)
def _clean_registry():
    saved = _spec_registry.copy()
    _spec_registry.clear()
    _spec_registry["widget"] = TrackingSpec
    yield
    _spec_registry.clear()
    _spec_registry.update(saved)


class TestWorkspaceLoad:
    def test_load_single_file_with_project(self, tmp_path):
        _write_hcl(tmp_path, "test.hcl", '''
            project "myproj" {
                description = "test"
            }
        ''')
        ws = Workspace()
        ws.load(tmp_path / "test.hcl")
        assert "myproj" in ws
        assert ws["myproj"].description == "test"

    def test_load_accepts_string_path(self, tmp_path):
        _write_hcl(tmp_path, "test.hcl", '''
            project "myproj" {
                description = "test"
            }
        ''')
        ws = Workspace()
        ws.load(str(tmp_path / "test.hcl"))
        assert "myproj" in ws

    def test_load_file_with_blueprint_and_project(self, tmp_path):
        _write_hcl(tmp_path, "test.hcl", '''
            blueprint "base" {
                ensure "widget" { color = "red" }
            }
            project "myproj" {
                use = ["base"]
            }
        ''')
        ws = Workspace()
        ws.load(tmp_path / "test.hcl")
        assert len(ws["myproj"].blueprints) == 1

    def test_load_multiple_files(self, tmp_path):
        _write_hcl(tmp_path, "a.hcl", '''
            blueprint "base" {
                ensure "widget" { color = "red" }
            }
        ''')
        _write_hcl(tmp_path, "b.hcl", '''
            project "myproj" {
                use = ["base"]
            }
        ''')
        ws = Workspace()
        ws.load(tmp_path / "a.hcl")
        ws.load(tmp_path / "b.hcl")
        assert len(ws["myproj"].blueprints) == 1

    def test_load_duplicate_blueprint_raises(self, tmp_path):
        _write_hcl(tmp_path, "a.hcl", '''
            blueprint "base" {
                ensure "widget" { color = "red" }
            }
        ''')
        _write_hcl(tmp_path, "b.hcl", '''
            blueprint "base" {
                ensure "widget" { color = "blue" }
            }
        ''')
        ws = Workspace()
        ws.load(tmp_path / "a.hcl")
        with pytest.raises(ValueError, match="base"):
            ws.load(tmp_path / "b.hcl")

    def test_load_duplicate_project_raises(self, tmp_path):
        _write_hcl(tmp_path, "a.hcl", '''
            project "myproj" { description = "first" }
        ''')
        _write_hcl(tmp_path, "b.hcl", '''
            project "myproj" { description = "second" }
        ''')
        ws = Workspace()
        ws.load(tmp_path / "a.hcl")
        with pytest.raises(ValueError, match="myproj"):
            ws.load(tmp_path / "b.hcl")

    def test_load_blueprint_only_file(self, tmp_path):
        _write_hcl(tmp_path, "test.hcl", '''
            blueprint "base" {
                ensure "widget" { color = "red" }
            }
        ''')
        ws = Workspace()
        ws.load(tmp_path / "test.hcl")
        assert len(ws) == 0  # no projects
        assert len(ws._pending_blueprints) == 1

    def test_repr_after_load(self, tmp_path):
        _write_hcl(tmp_path, "test.hcl", '''
            blueprint "base" {}
            project "myproj" { description = "test" }
        ''')
        ws = Workspace()
        ws.load(tmp_path / "test.hcl")
        assert "blueprints=1" in repr(ws)
        assert "projects=1" in repr(ws)
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_workspace.py::TestWorkspaceLoad -v`
Expected: FAIL — `load()` method does not exist yet

**Step 3: Implement load() method**

Add to `Workspace` class in `src/spectrik/workspace.py`:

```python
def load(self, file: str | Path) -> None:
    """Parse a single HCL file and extract blueprint/project blocks.

    Raises ValueError if any blueprint or project name is already loaded.
    """
    from spectrik.hcl import load as hcl_load

    path = Path(file)
    doc = hcl_load(path)

    # Extract blueprint blocks
    for bp_block in doc.get("blueprint", []):
        for bp_name, bp_data in bp_block.items():
            if bp_name in self._pending_blueprints:
                raise ValueError(f"Duplicate blueprint: '{bp_name}'")
            self._pending_blueprints[bp_name] = bp_data

    # Extract project blocks
    for proj_block in doc.get("project", []):
        for proj_name, proj_data in proj_block.items():
            if proj_name in self._pending_projects:
                raise ValueError(f"Duplicate project: '{proj_name}'")
            self._pending_projects[proj_name] = proj_data
```

Also add at the top of the file:

```python
from pathlib import Path
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_workspace.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/spectrik/workspace.py tests/test_workspace.py
git commit -m "feat: add Workspace.load() instance method with duplicate detection"
```

---

### Task 3: Add Workspace.scan() instance method

**Files:**
- Modify: `src/spectrik/workspace.py`
- Test: `tests/test_workspace.py`

**Step 1: Write failing tests for scan()**

Append to `tests/test_workspace.py`:

```python
class TestWorkspaceScan:
    def test_scan_finds_hcl_files(self, tmp_path):
        _write_hcl(tmp_path, "a.hcl", '''
            project "alpha" { description = "a" }
        ''')
        _write_hcl(tmp_path, "b.hcl", '''
            project "beta" { description = "b" }
        ''')
        ws = Workspace()
        ws.scan(tmp_path)
        assert "alpha" in ws
        assert "beta" in ws

    def test_scan_accepts_string_path(self, tmp_path):
        _write_hcl(tmp_path, "test.hcl", '''
            project "myproj" { description = "test" }
        ''')
        ws = Workspace()
        ws.scan(str(tmp_path))
        assert "myproj" in ws

    def test_scan_recurse_true(self, tmp_path):
        sub = tmp_path / "subdir"
        sub.mkdir()
        _write_hcl(tmp_path, "top.hcl", '''
            project "top" { description = "top" }
        ''')
        (sub / "nested.hcl").write_text('''
            project "nested" { description = "nested" }
        ''')
        ws = Workspace()
        ws.scan(tmp_path, recurse=True)
        assert "top" in ws
        assert "nested" in ws

    def test_scan_recurse_false(self, tmp_path):
        sub = tmp_path / "subdir"
        sub.mkdir()
        _write_hcl(tmp_path, "top.hcl", '''
            project "top" { description = "top" }
        ''')
        (sub / "nested.hcl").write_text('''
            project "nested" { description = "nested" }
        ''')
        ws = Workspace()
        ws.scan(tmp_path, recurse=False)
        assert "top" in ws
        assert "nested" not in ws

    def test_scan_sorted_order(self, tmp_path):
        _write_hcl(tmp_path, "z.hcl", '''
            project "zulu" { description = "z" }
        ''')
        _write_hcl(tmp_path, "a.hcl", '''
            project "alpha" { description = "a" }
        ''')
        ws = Workspace()
        ws.scan(tmp_path)
        # Both loaded successfully (sorted processing means deterministic)
        assert len(ws) == 2

    def test_scan_empty_dir(self, tmp_path):
        ws = Workspace()
        ws.scan(tmp_path)
        assert len(ws) == 0

    def test_scan_missing_dir(self, tmp_path):
        ws = Workspace()
        ws.scan(tmp_path / "nonexistent")
        assert len(ws) == 0

    def test_scan_ignores_non_hcl_files(self, tmp_path):
        _write_hcl(tmp_path, "test.hcl", '''
            project "myproj" { description = "test" }
        ''')
        (tmp_path / "readme.txt").write_text("not hcl")
        ws = Workspace()
        ws.scan(tmp_path)
        assert len(ws) == 1
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_workspace.py::TestWorkspaceScan -v`
Expected: FAIL — `scan()` method does not exist yet

**Step 3: Implement scan() method**

Add to `Workspace` class in `src/spectrik/workspace.py`:

```python
def scan(self, path: str | Path, *, recurse: bool = True) -> None:
    """Discover .hcl files in a directory and load each one.

    With recurse=True (default), walks subdirectories. Files are
    processed in sorted order for deterministic behavior.
    """
    directory = Path(path)
    if not directory.is_dir():
        return

    if recurse:
        hcl_files = sorted(directory.rglob("*.hcl"))
    else:
        hcl_files = sorted(directory.glob("*.hcl"))

    for hcl_file in hcl_files:
        self.load(hcl_file)
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_workspace.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/spectrik/workspace.py tests/test_workspace.py
git commit -m "feat: add Workspace.scan() with recursive directory walking"
```

---

### Task 4: Add Workspace.filter() and remaining Mapping tests

**Files:**
- Modify: `tests/test_workspace.py`

**Step 1: Write tests for filter and Mapping access with loaded data**

Append to `tests/test_workspace.py`:

```python
class TestWorkspaceMapping:
    """Test Mapping protocol with loaded HCL data."""

    def test_values(self, tmp_path):
        _write_hcl(tmp_path, "test.hcl", '''
            project "a" { description = "alpha" }
            project "b" { description = "beta" }
        ''')
        ws = Workspace()
        ws.load(tmp_path / "test.hcl")
        names = sorted(p.name for p in ws.values())
        assert names == ["a", "b"]

    def test_items(self, tmp_path):
        _write_hcl(tmp_path, "test.hcl", '''
            project "a" { description = "alpha" }
        ''')
        ws = Workspace()
        ws.load(tmp_path / "test.hcl")
        pairs = list(ws.items())
        assert len(pairs) == 1
        assert pairs[0][0] == "a"
        assert pairs[0][1].description == "alpha"

    def test_keys(self, tmp_path):
        _write_hcl(tmp_path, "test.hcl", '''
            project "a" { description = "alpha" }
            project "b" { description = "beta" }
        ''')
        ws = Workspace()
        ws.load(tmp_path / "test.hcl")
        assert sorted(ws.keys()) == ["a", "b"]

    def test_fresh_resolution_each_access(self, tmp_path):
        _write_hcl(tmp_path, "test.hcl", '''
            project "a" { description = "alpha" }
        ''')
        ws = Workspace()
        ws.load(tmp_path / "test.hcl")
        proj1 = ws["a"]
        proj2 = ws["a"]
        # Fresh resolution means different object instances
        assert proj1 is not proj2
        assert proj1.name == proj2.name

    def test_filter_with_loaded_data(self, tmp_path):
        _write_hcl(tmp_path, "test.hcl", '''
            project "a" { description = "alpha" }
            project "b" { description = "beta" }
            project "c" { description = "gamma" }
        ''')
        ws = Workspace()
        ws.load(tmp_path / "test.hcl")
        result = ws.filter(["a", "c"])
        assert len(result) == 2
        assert result[0].name == "a"
        assert result[1].name == "c"

    def test_filter_skips_missing(self, tmp_path):
        _write_hcl(tmp_path, "test.hcl", '''
            project "a" { description = "alpha" }
        ''')
        ws = Workspace()
        ws.load(tmp_path / "test.hcl")
        result = ws.filter(["a", "missing"])
        assert len(result) == 1

    def test_filter_empty_names(self, tmp_path):
        _write_hcl(tmp_path, "test.hcl", '''
            project "a" { description = "alpha" }
        ''')
        ws = Workspace()
        ws.load(tmp_path / "test.hcl")
        assert ws.filter([]) == []

    def test_custom_project_type(self, tmp_path):
        class Custom(Project):
            repo: str = ""

        _write_hcl(tmp_path, "test.hcl", '''
            project "myproj" {
                repo = "owner/repo"
            }
        ''')
        ws = Workspace(project_type=Custom)
        ws.load(tmp_path / "test.hcl")
        proj = ws["myproj"]
        assert isinstance(proj, Custom)
        assert proj.repo == "owner/repo"
```

**Step 2: Run tests to verify they pass**

Run: `uv run pytest tests/test_workspace.py::TestWorkspaceMapping -v`
Expected: PASS (these use already-implemented functionality)

**Step 3: Commit**

```bash
git add tests/test_workspace.py
git commit -m "test: add Mapping protocol and filter tests for new Workspace"
```

---

### Task 5: Update hcl.scan() to return Workspace

**Files:**
- Modify: `src/spectrik/hcl.py`
- Test: `tests/test_hcl.py`

**Step 1: Write failing tests for new hcl.scan()**

The current `test_hcl.py` tests for `scan()`, `load_blueprints()`, and `load_projects()` need updating. Replace the `TestScan`, `TestLoadBlueprints`, `TestLoadProjects`, and `TestWorkspaceLoad` classes. Keep `TestLoad` and `TestVariableInterpolation` as-is (they test internal helpers that still exist).

Update the import at the top of `tests/test_hcl.py`:

```python
from spectrik.hcl import load, scan
```

Remove imports of `load_blueprints`, `load_projects`.

Replace `TestScan` with:

```python
class TestScan:
    def test_scan_returns_workspace(self, tmp_path):
        _write_hcl(tmp_path, ".", "test.hcl", '''
            project "myproj" { description = "test" }
        ''')
        ws = scan(tmp_path)
        assert isinstance(ws, Workspace)
        assert "myproj" in ws

    def test_scan_with_custom_project_type(self, tmp_path):
        _write_hcl(tmp_path, ".", "test.hcl", '''
            project "myproj" {
                repo = "owner/repo"
                homepage = "https://example.com"
            }
        ''')
        ws = scan(tmp_path, project_type=SampleProject)
        proj = ws["myproj"]
        assert isinstance(proj, SampleProject)
        assert proj.repo == "owner/repo"

    def test_scan_recurse_true(self, tmp_path):
        _write_hcl(tmp_path, ".", "top.hcl", '''
            project "top" { description = "top" }
        ''')
        _write_hcl(tmp_path, "sub", "nested.hcl", '''
            project "nested" { description = "nested" }
        ''')
        ws = scan(tmp_path, recurse=True)
        assert "top" in ws
        assert "nested" in ws

    def test_scan_recurse_false(self, tmp_path):
        _write_hcl(tmp_path, ".", "top.hcl", '''
            project "top" { description = "top" }
        ''')
        _write_hcl(tmp_path, "sub", "nested.hcl", '''
            project "nested" { description = "nested" }
        ''')
        ws = scan(tmp_path, recurse=False)
        assert "top" in ws
        assert "nested" not in ws

    def test_scan_empty_dir(self, tmp_path):
        ws = scan(tmp_path)
        assert len(ws) == 0

    def test_scan_missing_dir(self, tmp_path):
        ws = scan(tmp_path / "nonexistent")
        assert len(ws) == 0

    def test_scan_with_blueprints_and_projects(self, tmp_path):
        _write_hcl(tmp_path, ".", "test.hcl", '''
            blueprint "base" {
                ensure "widget" { color = "red" }
            }
            project "myproj" {
                use = ["base"]
            }
        ''')
        ws = scan(tmp_path)
        assert len(ws["myproj"].blueprints) == 1
```

Remove `TestLoadBlueprints`, `TestLoadProjects`, and `TestWorkspaceLoad` classes entirely (their functionality is covered by the new Workspace tests and the updated `scan()` tests).

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_hcl.py::TestScan -v`
Expected: FAIL — `scan()` returns `list[dict]` not `Workspace`

**Step 3: Rewrite hcl.scan() and remove load_blueprints/load_projects**

In `src/spectrik/hcl.py`, replace the `scan()` function:

```python
def scan[P: Project](
    path: str | Path,
    *,
    project_type: type[P] = Project,  # type: ignore[assignment]
    recurse: bool = True,
) -> Workspace[P]:
    """Scan a directory for .hcl files and return a ready Workspace.

    Convenience function that creates a Workspace, scans the path,
    and returns it. Equivalent to:

        ws = Workspace(project_type=project_type)
        ws.scan(path, recurse=recurse)
    """
    from spectrik.workspace import Workspace

    ws = Workspace(project_type=project_type)
    ws.scan(path, recurse=recurse)
    return ws
```

Remove the `load_blueprints()` and `load_projects()` functions entirely (lines 151–187). The internal helpers (`_collect_pending_blueprints`, `_resolve_blueprint`, `_parse_ops`, `_decode_spec`, `_build_project`) stay — they are called from `Workspace._resolve()`.

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_hcl.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/spectrik/hcl.py tests/test_hcl.py
git commit -m "refactor: rewrite hcl.scan() to return Workspace, remove load_blueprints/load_projects"
```

---

### Task 6: Update integration tests

**Files:**
- Modify: `tests/test_integration.py`

**Step 1: Rewrite integration tests to use new Workspace API**

Replace `tests/test_integration.py`:

```python
"""End-to-end integration test for spectrik."""

from __future__ import annotations

from pathlib import Path

from spectrik import Blueprint, Context, Ensure, Project, Specification, Workspace
from spectrik.specs import _spec_registry


class AppProject(Project):
    repo: str = ""


class CountingSpec(Specification["AppProject"]):
    apply_count = 0
    remove_count = 0

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        CountingSpec.apply_count = 0
        CountingSpec.remove_count = 0

    def equals(self, ctx: Context[AppProject]) -> bool:
        return False

    def apply(self, ctx: Context[AppProject]) -> None:
        CountingSpec.apply_count += 1

    def remove(self, ctx: Context[AppProject]) -> None:
        CountingSpec.remove_count += 1


def _write_hcl(tmp_path: Path, filename: str, content: str) -> Path:
    f = tmp_path / filename
    f.write_text(content)
    return f


class TestEndToEnd:
    def setup_method(self):
        self._saved = _spec_registry.copy()
        _spec_registry.clear()
        _spec_registry["counter"] = CountingSpec

    def teardown_method(self):
        _spec_registry.clear()
        _spec_registry.update(self._saved)

    def test_full_pipeline(self, tmp_path):
        """Load HCL via Workspace, build project, verify specs executed."""
        _write_hcl(tmp_path, "blueprints.hcl", '''
            blueprint "base" {
                ensure "counter" { id = "1" }
                ensure "counter" { id = "2" }
            }
        ''')
        _write_hcl(tmp_path, "projects.hcl", '''
            project "myapp" {
                description = "Test app"
                repo = "owner/myapp"
                use = ["base"]
                ensure "counter" { id = "3" }
            }
        ''')

        ws = Workspace(project_type=AppProject)
        ws.scan(tmp_path)

        proj = ws["myapp"]
        assert proj.repo == "owner/myapp"

        proj.build()
        assert CountingSpec.apply_count == 3

    def test_full_pipeline_dry_run(self, tmp_path):
        """Dry run should not apply any specs."""
        _write_hcl(tmp_path, "config.hcl", '''
            blueprint "base" {
                ensure "counter" { id = "1" }
            }
            project "myapp" {
                use = ["base"]
            }
        ''')

        ws = Workspace(project_type=AppProject)
        ws.scan(tmp_path)

        ws["myapp"].build(dry_run=True)
        assert CountingSpec.apply_count == 0

    def test_hcl_scan_convenience(self, tmp_path):
        """Test hcl.scan() convenience function."""
        import spectrik.hcl as hcl

        _write_hcl(tmp_path, "config.hcl", '''
            blueprint "base" {
                ensure "counter" { id = "1" }
            }
            project "myapp" {
                use = ["base"]
                repo = "owner/myapp"
            }
        ''')

        ws = hcl.scan(tmp_path, project_type=AppProject)
        proj = ws["myapp"]
        assert isinstance(proj, AppProject)
        assert proj.repo == "owner/myapp"

        proj.build()
        assert CountingSpec.apply_count == 1

    def test_programmatic_api(self):
        """Test building specs/blueprints/projects without HCL."""
        s = CountingSpec(id="manual")
        bp = Blueprint(name="manual-bp", ops=[Ensure(s)])
        proj = AppProject(name="manual-proj", repo="test/repo", blueprints=[bp])
        proj.build()
        assert CountingSpec.apply_count == 1
```

**Step 2: Run tests to verify they pass**

Run: `uv run pytest tests/test_integration.py -v`
Expected: PASS

**Step 3: Commit**

```bash
git add tests/test_integration.py
git commit -m "refactor: update integration tests for new Workspace API"
```

---

### Task 7: Run preflight and clean up

**Files:**
- Possibly modify: any files flagged by ruff/pyright

**Step 1: Run the full preflight**

Run: `make preflight`
Expected: PASS — all pre-commit hooks and tests pass

**Step 2: Fix any issues**

If ruff or pyright flag anything, fix it. Common things to check:
- Unused imports in `test_hcl.py` (removed `load_blueprints`, `load_projects`)
- Type narrowing issues with the generic `project_type` default

**Step 3: Commit any fixes**

```bash
git add -u
git commit -m "fix: address ruff/pyright issues from workspace redesign"
```

**Step 4: Verify final state**

Run: `make preflight`
Expected: PASS — clean
