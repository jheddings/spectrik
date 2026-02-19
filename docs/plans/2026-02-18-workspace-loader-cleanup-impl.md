# Workspace Loader Cleanup Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace `ProjectLoader` and `resolve_attrs` with `Workspace.load()` classmethod and built-in `${env.VAR}` / `${CWD}` variable interpolation.

**Architecture:** Variable interpolation is a private function in `hcl.py` that walks string values during spec decoding. `Workspace.load()` is a classmethod that orchestrates the existing `load_blueprints()` / `load_projects()` pipeline. `ProjectLoader` and all `resolve_attrs` parameters are removed.

**Tech Stack:** Python 3.12+, Pydantic v2, python-hcl2, pytest

---

### Task 1: Add variable interpolation

**Files:**
- Modify: `src/spectrik/hcl.py`
- Test: `tests/test_hcl.py`

**Step 1: Write the failing tests**

Add a new `TestVariableInterpolation` class at the end of `tests/test_hcl.py`.
These tests exercise variable expansion within spec attributes during blueprint
loading.

```python
class TestVariableInterpolation:
    def test_env_var_expansion(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SPECTRIK_TEST_VAR", "/test/path")
        _write_hcl(
            tmp_path,
            "blueprints",
            "test.hcl",
            """
            blueprint "interp" {
                ensure "widget" {
                    color = "${env.SPECTRIK_TEST_VAR}/sub"
                }
            }
        """,
        )
        bps = load_blueprints(tmp_path)
        op = bps["interp"].ops[0]
        assert op.spec.kwargs["color"] == "/test/path/sub"

    def test_cwd_expansion(self, tmp_path):
        _write_hcl(
            tmp_path,
            "blueprints",
            "test.hcl",
            """
            blueprint "interp" {
                ensure "widget" {
                    color = "${CWD}/file"
                }
            }
        """,
        )
        import os

        bps = load_blueprints(tmp_path)
        op = bps["interp"].ops[0]
        assert op.spec.kwargs["color"] == f"{os.getcwd()}/file"

    def test_unknown_env_var_expands_to_empty(self, tmp_path, monkeypatch):
        monkeypatch.delenv("SPECTRIK_NONEXISTENT", raising=False)
        _write_hcl(
            tmp_path,
            "blueprints",
            "test.hcl",
            """
            blueprint "interp" {
                ensure "widget" {
                    color = "${env.SPECTRIK_NONEXISTENT}"
                }
            }
        """,
        )
        bps = load_blueprints(tmp_path)
        op = bps["interp"].ops[0]
        assert op.spec.kwargs["color"] == ""

    def test_multiple_vars_in_one_string(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SPECTRIK_A", "hello")
        monkeypatch.setenv("SPECTRIK_B", "world")
        _write_hcl(
            tmp_path,
            "blueprints",
            "test.hcl",
            """
            blueprint "interp" {
                ensure "widget" {
                    color = "${env.SPECTRIK_A}-${env.SPECTRIK_B}"
                }
            }
        """,
        )
        bps = load_blueprints(tmp_path)
        op = bps["interp"].ops[0]
        assert op.spec.kwargs["color"] == "hello-world"

    def test_no_vars_unchanged(self, tmp_path):
        _write_hcl(
            tmp_path,
            "blueprints",
            "test.hcl",
            """
            blueprint "interp" {
                ensure "widget" {
                    color = "plain-value"
                }
            }
        """,
        )
        bps = load_blueprints(tmp_path)
        op = bps["interp"].ops[0]
        assert op.spec.kwargs["color"] == "plain-value"

    def test_non_string_values_unchanged(self, tmp_path):
        _write_hcl(
            tmp_path,
            "blueprints",
            "test.hcl",
            """
            blueprint "interp" {
                ensure "widget" {
                    color = 42
                }
            }
        """,
        )
        bps = load_blueprints(tmp_path)
        op = bps["interp"].ops[0]
        assert op.spec.kwargs["color"] == 42

    def test_vars_in_project_attrs(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SPECTRIK_TEST_VAR", "resolved")
        _write_hcl(
            tmp_path,
            "projects",
            "test.hcl",
            """
            project "myproj" {
                ensure "widget" {
                    color = "${env.SPECTRIK_TEST_VAR}"
                }
            }
        """,
        )
        projs = load_projects(tmp_path, blueprints={})
        op = projs["myproj"].blueprints[0].ops[0]
        assert op.spec.kwargs["color"] == "resolved"
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_hcl.py::TestVariableInterpolation -v`
Expected: FAIL — variables not expanded yet

**Step 3: Implement variable interpolation**

Add two private functions to `src/spectrik/hcl.py`, right after the
`_STRATEGY_MAP` definition (line 23):

```python
import os
import re

_VAR_PATTERN = re.compile(r"\$\{(?:env\.(\w+)|(\w+))\}")

_BUILTIN_VARS: dict[str, Callable[[], str]] = {
    "CWD": os.getcwd,
}


def _expand_var(match: re.Match) -> str:
    """Expand a single ${...} variable reference."""
    env_name = match.group(1)
    builtin_name = match.group(2)
    if env_name is not None:
        value = os.environ.get(env_name, "")
        if not value:
            logger.warning("Environment variable '%s' is not set", env_name)
        return value
    if builtin_name is not None and builtin_name in _BUILTIN_VARS:
        return _BUILTIN_VARS[builtin_name]()
    logger.warning("Unknown variable '%s'", builtin_name)
    return match.group(0)


def _interpolate_value(value: Any) -> Any:
    """Expand ${env.VAR} and ${CWD} references in a string value."""
    if isinstance(value, str) and "${" in value:
        return _VAR_PATTERN.sub(_expand_var, value)
    return value


def _interpolate_attrs(attrs: dict[str, Any]) -> dict[str, Any]:
    """Expand variable references in all attribute values."""
    return {k: _interpolate_value(v) for k, v in attrs.items()}
```

Then update `_decode_spec()` to call `_interpolate_attrs` instead of
`resolve_attrs`. For now, apply interpolation **in addition to** the existing
`resolve_attrs` callback (we remove resolve_attrs in a later task):

Replace the body of `_decode_spec()` with:

```python
def _decode_spec(
    spec_name: str,
    attrs: dict[str, Any],
    *,
    resolve_attrs: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
) -> Any:
    """Decode a spec block into a Specification instance using the registry."""
    if spec_name not in _spec_registry:
        raise ValueError(f"Unknown spec type: '{spec_name}'")
    attrs = _interpolate_attrs(attrs)
    if resolve_attrs:
        attrs = resolve_attrs(attrs)
    spec_cls = _spec_registry[spec_name]
    return spec_cls(**attrs)
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_hcl.py::TestVariableInterpolation -v`
Expected: PASS (all 7 tests)

**Step 5: Run full test suite**

Run: `uv run pytest -v`
Expected: All existing tests still pass

**Step 6: Commit**

```bash
git add src/spectrik/hcl.py tests/test_hcl.py
git commit -m "feat: add built-in variable interpolation for HCL loading"
```

---

### Task 2: Add Workspace.load() classmethod

**Files:**
- Modify: `src/spectrik/workspace.py`
- Test: `tests/test_hcl.py`

**Step 1: Write the failing tests**

Add a new `TestWorkspaceLoad` class at the end of `tests/test_hcl.py`
(in the HCL test file since `.load()` depends on HCL loading):

```python
class TestWorkspaceLoad:
    def test_load_returns_workspace(self, tmp_path):
        _write_hcl(
            tmp_path,
            "projects",
            "test.hcl",
            """
            project "myproj" {
                description = "test"
            }
        """,
        )
        ws = Workspace.load(Project, tmp_path)
        assert isinstance(ws, Workspace)

    def test_load_contains_projects(self, tmp_path):
        _write_hcl(
            tmp_path,
            "projects",
            "test.hcl",
            """
            project "myproj" {
                description = "test"
            }
        """,
        )
        ws = Workspace.load(Project, tmp_path)
        assert "myproj" in ws
        assert ws["myproj"].description == "test"

    def test_load_custom_project_type(self, tmp_path):
        _write_hcl(
            tmp_path,
            "projects",
            "test.hcl",
            """
            project "myproj" {
                repo = "owner/repo"
                homepage = "https://example.com"
            }
        """,
        )
        ws = Workspace.load(SampleProject, tmp_path)
        proj = ws["myproj"]
        assert isinstance(proj, SampleProject)
        assert proj.repo == "owner/repo"

    def test_load_resolves_blueprints(self, tmp_path):
        _write_hcl(
            tmp_path,
            "blueprints",
            "test.hcl",
            """
            blueprint "base" {
                ensure "widget" { color = "red" }
            }
        """,
        )
        _write_hcl(
            tmp_path,
            "projects",
            "test.hcl",
            """
            project "myproj" {
                use = ["base"]
            }
        """,
        )
        ws = Workspace.load(Project, tmp_path)
        assert len(ws["myproj"].blueprints) == 1

    def test_load_empty_dir(self, tmp_path):
        (tmp_path / "blueprints").mkdir()
        (tmp_path / "projects").mkdir()
        ws = Workspace.load(Project, tmp_path)
        assert len(ws) == 0

    def test_load_with_variable_interpolation(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SPECTRIK_TEST_VAR", "expanded")
        _write_hcl(
            tmp_path,
            "projects",
            "test.hcl",
            """
            project "myproj" {
                ensure "widget" {
                    color = "${env.SPECTRIK_TEST_VAR}"
                }
            }
        """,
        )
        ws = Workspace.load(Project, tmp_path)
        op = ws["myproj"].blueprints[0].ops[0]
        assert op.spec.kwargs["color"] == "expanded"
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_hcl.py::TestWorkspaceLoad -v`
Expected: FAIL — `Workspace.load()` does not exist

**Step 3: Implement Workspace.load()**

In `src/spectrik/workspace.py`, add the classmethod. Use a late import to
avoid circular dependency (workspace → hcl → workspace):

```python
from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from pathlib import Path
from typing import Any, overload

from spectrik.projects import Project


class Workspace[P: Project](Mapping[str, P]):
    """Typed, read-only collection of projects returned by Workspace.load()."""

    def __init__(self, projects: dict[str, P]) -> None:
        self._projects = dict(projects)

    @classmethod
    def load[T: Project](cls, project_type: type[T], base_path: Path) -> Workspace[T]:
        """Load blueprints and projects from base_path, return a Workspace."""
        from spectrik.hcl import load_blueprints, load_projects

        blueprints = load_blueprints(base_path)
        projects = load_projects(base_path, blueprints, project_type=project_type)
        return Workspace(projects)

    # ... existing methods unchanged ...
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_hcl.py::TestWorkspaceLoad -v`
Expected: PASS (all 6 tests)

**Step 5: Run full test suite**

Run: `uv run pytest -v`
Expected: All tests pass

**Step 6: Commit**

```bash
git add src/spectrik/workspace.py tests/test_hcl.py
git commit -m "feat: add Workspace.load() classmethod"
```

---

### Task 3: Remove resolve_attrs and ProjectLoader

**Files:**
- Modify: `src/spectrik/hcl.py`
- Modify: `src/spectrik/__init__.py`
- Modify: `tests/test_hcl.py`

**Step 1: Update tests — remove resolve_attrs tests and migrate ProjectLoader tests**

In `tests/test_hcl.py`:

- **Remove** `TestLoad.test_load_with_resolve_attrs` (tests resolve_attrs on
  `load()` which is being removed)
- **Remove** `TestLoadBlueprints.test_resolve_attrs_callback` (tests
  resolve_attrs on `load_blueprints()`)
- **Remove** `TestProjectLoader` class entirely (replaced by
  `TestWorkspaceLoad`)
- **Update import**: remove `ProjectLoader` from the import line

Updated import line:

```python
from spectrik.hcl import load, load_blueprints, load_projects, scan
```

**Step 2: Run tests to verify the removals compile**

Run: `uv run pytest tests/test_hcl.py -v`
Expected: PASS (all remaining tests pass — removed tests no longer run)

**Step 3: Remove resolve_attrs from hcl.py**

Remove the `resolve_attrs` parameter from every function in `src/spectrik/hcl.py`:

- `load()` — remove `resolve_attrs` parameter (and the unused body reference)
- `scan()` — remove `resolve_attrs` parameter (and the `resolve_attrs=` kwarg
  passed to `load()`)
- `_decode_spec()` — remove `resolve_attrs` parameter and the
  `if resolve_attrs:` block
- `_parse_ops()` — remove `resolve_attrs` parameter and the `resolve_attrs=`
  kwarg passed to `_decode_spec()`
- `_resolve_blueprint()` — remove `resolve_attrs` parameter and the
  `resolve_attrs=` kwarg passed to `_parse_ops()` and recursive call
- `load_blueprints()` — remove `resolve_attrs` parameter and the
  `resolve_attrs=` kwarg passed to `_resolve_blueprint()`
- `_build_project()` — remove `resolve_attrs` parameter and the
  `resolve_attrs=` kwarg passed to `_parse_ops()`
- `load_projects()` — remove `resolve_attrs` parameter and the
  `resolve_attrs=` kwarg passed to `_build_project()`

Remove the `ProjectLoader` class entirely (lines 207–232).

Remove the `Callable` import from `collections.abc` if no longer used (check
if `_BUILTIN_VARS` type annotation uses it — if so, keep it).

**Step 4: Remove ProjectLoader from __init__.py**

In `src/spectrik/__init__.py`, remove the line:

```python
from spectrik.hcl import ProjectLoader as ProjectLoader
```

**Step 5: Run full test suite**

Run: `uv run pytest -v`
Expected: All tests pass

**Step 6: Run preflight**

Run: `make preflight`
Expected: Clean (ruff, pyright, yamllint, all tests pass)

**Step 7: Commit**

```bash
git add src/spectrik/hcl.py src/spectrik/__init__.py tests/test_hcl.py
git commit -m "refactor: remove ProjectLoader and resolve_attrs"
```

---

### Task 4: Update integration tests to use Workspace.load()

**Files:**
- Modify: `tests/test_integration.py`

**Step 1: Update the integration tests**

In `tests/test_integration.py`, update `test_full_pipeline` and
`test_full_pipeline_dry_run` to use `Workspace.load()` instead of calling
`load_blueprints()` / `load_projects()` separately:

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


def _write_hcl(tmp_path: Path, subdir: str, filename: str, content: str) -> Path:
    d = tmp_path / subdir
    d.mkdir(parents=True, exist_ok=True)
    f = d / filename
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
        """Load HCL via Workspace.load(), build project, verify specs executed."""
        _write_hcl(
            tmp_path,
            "blueprints",
            "base.hcl",
            """
            blueprint "base" {
                ensure "counter" { id = "1" }
                ensure "counter" { id = "2" }
            }
        """,
        )
        _write_hcl(
            tmp_path,
            "projects",
            "app.hcl",
            """
            project "myapp" {
                description = "Test app"
                repo = "owner/myapp"
                use = ["base"]
                ensure "counter" { id = "3" }
            }
        """,
        )

        ws = Workspace.load(AppProject, tmp_path)
        proj = ws["myapp"]
        assert proj.repo == "owner/myapp"

        proj.build()
        assert CountingSpec.apply_count == 3

    def test_full_pipeline_dry_run(self, tmp_path):
        """Dry run should not apply any specs."""
        _write_hcl(
            tmp_path,
            "blueprints",
            "base.hcl",
            """
            blueprint "base" {
                ensure "counter" { id = "1" }
            }
        """,
        )
        _write_hcl(
            tmp_path,
            "projects",
            "app.hcl",
            """
            project "myapp" {
                use = ["base"]
            }
        """,
        )

        ws = Workspace.load(AppProject, tmp_path)
        ws["myapp"].build(dry_run=True)
        assert CountingSpec.apply_count == 0

    def test_programmatic_api(self):
        """Test building specs/blueprints/projects without HCL."""
        s = CountingSpec(id="manual")
        bp = Blueprint(name="manual-bp", ops=[Ensure(s)])
        proj = AppProject(name="manual-proj", repo="test/repo", blueprints=[bp])
        proj.build()
        assert CountingSpec.apply_count == 1
```

**Step 2: Run tests**

Run: `uv run pytest tests/test_integration.py -v`
Expected: PASS

**Step 3: Run preflight**

Run: `make preflight`
Expected: Clean

**Step 4: Commit**

```bash
git add tests/test_integration.py
git commit -m "refactor: update integration tests to use Workspace.load()"
```
