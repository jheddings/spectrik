# HCL-Native Interpolation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace Jinja2 templating with post-parse `${...}` variable resolution and restructure the Workspace/HCL dependency.

**Architecture:** A new `Resolver` class in `resolve.py` walks parsed dicts and resolves `${...}` references against a context dict. `hcl.py` uses `Resolver` after `hcl2.loads()`. Workspace becomes format-agnostic — it accepts pre-parsed dicts and owns blueprint/project resolution logic. `hcl.py` depends on Workspace (one-way), not the reverse.

**Tech Stack:** Python 3.12+, Pydantic v2, python-hcl2, pytest

---

### Task 1: Create `Resolver` with basic variable substitution

**Files:**
- Create: `src/spectrik/resolve.py`
- Create: `tests/test_resolve.py`

**Step 1: Write failing tests for bare variable resolution**

```python
"""Tests for spectrik.resolve — variable interpolation on parsed dicts."""

import pytest

from spectrik.resolve import Resolver


class TestResolveRef:
    """Test _resolve_ref: dotted reference resolution against context."""

    def test_bare_reference(self):
        r = Resolver({"name": "myapp"})
        assert r._resolve_ref("name") == "myapp"

    def test_dotted_reference_dict(self):
        r = Resolver({"env": {"HOME": "/home/user"}})
        assert r._resolve_ref("env.HOME") == "/home/user"

    def test_dotted_reference_getattr(self):
        class Config:
            region = "us-east-1"

        r = Resolver({"config": Config()})
        assert r._resolve_ref("config.region") == "us-east-1"

    def test_deeply_nested(self):
        r = Resolver({"a": {"b": {"c": "deep"}}})
        assert r._resolve_ref("a.b.c") == "deep"

    def test_undefined_raises(self):
        r = Resolver({"name": "myapp"})
        with pytest.raises(ValueError, match="missing"):
            r._resolve_ref("missing")

    def test_undefined_nested_raises(self):
        r = Resolver({"env": {"HOME": "/home"}})
        with pytest.raises(ValueError, match="MISSING"):
            r._resolve_ref("env.MISSING")

    def test_callable_value(self):
        r = Resolver({"cwd": lambda: "/tmp/work"})
        assert r._resolve_ref("cwd") == "/tmp/work"

    def test_callable_not_invoked_on_intermediate(self):
        """Callables are only invoked on the final resolved value."""

        class Holder:
            value = "found"

        r = Resolver({"get_holder": lambda: Holder()})
        # get_holder is callable and final, so it gets called -> Holder instance
        # but then .value is not callable, just returned
        result = r._resolve_ref("get_holder")
        assert isinstance(result, Holder)
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_resolve.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'spectrik.resolve'`

**Step 3: Implement `Resolver._resolve_ref`**

```python
"""Resolver — walk parsed dicts and resolve ${...} variable interpolation."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class Resolver:
    """Resolve ${...} interpolation references against a context dict."""

    def __init__(self, context: dict[str, Any] | None = None) -> None:
        self._context = context or {}

    def _resolve_ref(self, ref: str) -> Any:
        """Resolve a dotted reference (e.g., 'env.HOME') against the context."""
        parts = ref.split(".")
        current: Any = self._context

        for part in parts:
            try:
                current = current[part]
            except (KeyError, TypeError):
                try:
                    current = getattr(current, part)
                except AttributeError:
                    raise ValueError(f"undefined variable '{ref}'")

        if callable(current) and not isinstance(current, type):
            current = current()

        return current
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_resolve.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/spectrik/resolve.py tests/test_resolve.py
git commit -m "feat: add Resolver with dotted reference resolution"
```

---

### Task 2: Add string interpolation (`_resolve_value`)

**Files:**
- Modify: `src/spectrik/resolve.py`
- Modify: `tests/test_resolve.py`

**Step 1: Write failing tests for string interpolation**

Add to `tests/test_resolve.py`:

```python
class TestResolveValue:
    """Test _resolve_value: interpolation within string values."""

    def test_no_interpolation(self):
        r = Resolver({"name": "app"})
        assert r._resolve_value("plain string") == "plain string"

    def test_single_full_interpolation_preserves_type_int(self):
        r = Resolver({"count": 42})
        assert r._resolve_value("${count}") == 42

    def test_single_full_interpolation_preserves_type_bool(self):
        r = Resolver({"flag": True})
        assert r._resolve_value("${flag}") is True

    def test_single_full_interpolation_preserves_type_list(self):
        r = Resolver({"items": [1, 2, 3]})
        assert r._resolve_value("${items}") == [1, 2, 3]

    def test_embedded_interpolation_stringifies(self):
        r = Resolver({"name": "app"})
        assert r._resolve_value("hello-${name}") == "hello-app"

    def test_multiple_interpolations(self):
        r = Resolver({"host": "localhost", "port": 8080})
        assert r._resolve_value("${host}:${port}") == "localhost:8080"

    def test_dotted_in_string(self):
        r = Resolver({"env": {"HOME": "/home/user"}})
        assert r._resolve_value("${env.HOME}/.config") == "/home/user/.config"

    def test_undefined_raises(self):
        r = Resolver({})
        with pytest.raises(ValueError, match="missing"):
            r._resolve_value("${missing}")

    def test_callable_in_string(self):
        r = Resolver({"cwd": lambda: "/tmp"})
        assert r._resolve_value("${cwd}/data") == "/tmp/data"

    def test_escaped_dollar_not_interpolated(self):
        """$${...} should produce literal ${...}."""
        r = Resolver({"name": "app"})
        assert r._resolve_value("$${name}") == "${name}"

    def test_double_brace_passthrough(self):
        """${{ ... }} (e.g., GitHub Actions) is not ${...} syntax — left alone."""
        r = Resolver({"github": {"token": "secret"}})
        assert r._resolve_value("${{ github.token }}") == "${{ github.token }}"

    def test_mixed_interpolation_and_double_brace(self):
        """Real-world: spectrik vars alongside GitHub Actions expressions."""
        r = Resolver({"name": "myapp"})
        result = r._resolve_value("${name} uses ${{ github.token }}")
        assert result == "myapp uses ${{ github.token }}"
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_resolve.py::TestResolveValue -v`
Expected: FAIL — `AttributeError: 'Resolver' object has no attribute '_resolve_value'`

**Step 3: Implement `_resolve_value`**

Add to `Resolver` class in `src/spectrik/resolve.py`:

```python
import re

_INTERP_PATTERN = re.compile(r"\$\$\{|(\$\{([^}]+)\})")
```

```python
    def _resolve_value(self, value: str) -> str | Any:
        """Resolve ${...} interpolations in a single string value.

        If the entire string is a single ${ref}, returns the resolved object
        directly (preserving type). If ${ref} is embedded in a larger string,
        the resolved value is stringified. Use $${...} for literal ${...}.
        """
        # Fast path: no interpolation
        if "${" not in value:
            return value

        # Check if the entire string is a single interpolation
        match = re.fullmatch(r"\$\{([^}]+)\}", value)
        if match:
            return self._resolve_ref(match.group(1).strip())

        # Mixed string: replace each interpolation with its stringified value
        def _replace(m: re.Match) -> str:
            if m.group(0) == "$${":
                return "${"
            ref = m.group(2).strip()
            return str(self._resolve_ref(ref))

        return _INTERP_PATTERN.sub(_replace, value)
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_resolve.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/spectrik/resolve.py tests/test_resolve.py
git commit -m "feat: add string interpolation with type preservation"
```

---

### Task 3: Add dict/list walking (`resolve`)

**Files:**
- Modify: `src/spectrik/resolve.py`
- Modify: `tests/test_resolve.py`

**Step 1: Write failing tests for dict walking**

Add to `tests/test_resolve.py`:

```python
class TestResolve:
    """Test resolve: recursive dict/list walking."""

    def test_simple_dict(self):
        r = Resolver({"name": "app"})
        data = {"title": "${name}"}
        assert r.resolve(data) == {"title": "app"}

    def test_nested_dict(self):
        r = Resolver({"host": "localhost"})
        data = {"server": {"address": "${host}"}}
        assert r.resolve(data) == {"server": {"address": "localhost"}}

    def test_list_values(self):
        r = Resolver({"x": "a", "y": "b"})
        data = {"items": ["${x}", "${y}"]}
        assert r.resolve(data) == {"items": ["a", "b"]}

    def test_list_of_dicts(self):
        r = Resolver({"name": "app"})
        data = {"entries": [{"label": "${name}"}]}
        assert r.resolve(data) == {"entries": [{"label": "app"}]}

    def test_non_string_values_untouched(self):
        r = Resolver({"name": "app"})
        data = {"count": 5, "flag": True, "ratio": 3.14, "empty": None}
        assert r.resolve(data) == {"count": 5, "flag": True, "ratio": 3.14, "empty": None}

    def test_original_dict_not_mutated(self):
        r = Resolver({"name": "app"})
        data = {"title": "${name}"}
        r.resolve(data)
        assert data == {"title": "${name}"}

    def test_empty_dict(self):
        r = Resolver({"name": "app"})
        assert r.resolve({}) == {}

    def test_empty_context(self):
        r = Resolver()
        data = {"title": "no interpolation"}
        assert r.resolve(data) == {"title": "no interpolation"}
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_resolve.py::TestResolve -v`
Expected: FAIL — `AttributeError: 'Resolver' object has no attribute 'resolve'`

**Step 3: Implement `resolve`**

Add to `Resolver` class in `src/spectrik/resolve.py`:

```python
    def resolve(self, data: dict[str, Any]) -> dict[str, Any]:
        """Recursively walk a parsed dict and resolve all ${...} interpolations."""
        return self._walk(data)

    def _walk(self, obj: Any) -> Any:
        if isinstance(obj, dict):
            return {k: self._walk(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self._walk(item) for item in obj]
        if isinstance(obj, str):
            return self._resolve_value(obj)
        return obj
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_resolve.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/spectrik/resolve.py tests/test_resolve.py
git commit -m "feat: add recursive dict walking for interpolation"
```

---

### Task 4: Move resolution logic from `hcl.py` to `workspace.py`

This task restructures the dependency: Workspace owns blueprint/project resolution, HCL is a pure loader.

**Files:**
- Modify: `src/spectrik/workspace.py`
- Modify: `src/spectrik/hcl.py`
- Modify: `tests/test_workspace.py`

**Step 1: Run existing tests to confirm green baseline**

Run: `uv run pytest tests/ -v`
Expected: All 98 tests PASS

**Step 2: Move `_decode_spec`, `_parse_ops`, `_resolve_blueprint`, `_build_project` from `hcl.py` to `workspace.py`**

Cut from `src/spectrik/hcl.py` (lines 65-159): the four functions `_decode_spec`, `_parse_ops`, `_resolve_blueprint`, `_build_project` and the `_STRATEGY_MAP` constant.

Add to `src/spectrik/workspace.py` — the functions become module-level private functions. Add the necessary imports:

```python
from .blueprints import Blueprint
from .spec import _spec_registry
from .specop import Absent, Ensure, Present, SpecOp
```

Add `_STRATEGY_MAP` and the four functions (`_decode_spec`, `_parse_ops`, `_resolve_blueprint`, `_build_project`) as they were, unchanged.

**Step 3: Update `workspace.py` `_resolve` to call local functions**

Change `Workspace._resolve()` to call the local functions directly instead of importing from `hcl`:

```python
    def _resolve(self) -> dict[str, P]:
        """Resolve all pending blueprints and build typed project instances."""
        logger.debug(
            "Resolving %d blueprint(s) and %d project(s)",
            len(self._pending_blueprints),
            len(self._pending_projects),
        )

        resolved_bps: dict[str, Any] = {}
        for name in self._pending_blueprints:
            _resolve_blueprint(name, self._pending_blueprints, resolved_bps, set())

        projects: dict[str, P] = {}
        for proj_name, proj_data in self._pending_projects.items():
            projects[proj_name] = _build_project(
                proj_name,
                proj_data,
                resolved_bps,
                project_type=self._project_type,
            )
        return projects
```

**Step 4: Strip resolution functions from `hcl.py`**

Remove `_STRATEGY_MAP`, `_decode_spec`, `_parse_ops`, `_resolve_blueprint`, `_build_project` from `hcl.py`. Remove the now-unused imports (`Blueprint`, `_spec_registry`, `Absent`, `Ensure`, `Present`, `SpecOp`). Remove the `TYPE_CHECKING` block that imported `Workspace`.

`hcl.py` should now only contain `load()` and `scan()`.

**Step 5: Update `hcl.scan()` to import Workspace directly**

```python
from .workspace import Workspace
```

This is now a top-level import (no circular dependency since Workspace no longer imports from hcl).

**Step 6: Update `Workspace.load()` to accept a dict**

Change `Workspace.load()` to accept a `dict[str, Any]` instead of a file path:

```python
    def load(self, data: dict[str, Any]) -> None:
        """Extract blueprint and project blocks from a parsed data dict.

        Raises ValueError if any blueprint or project name is already loaded.
        """
        for bp_block in data.get("blueprint", []):
            for bp_name, bp_data in bp_block.items():
                if bp_name in self._pending_blueprints:
                    raise ValueError(f"Duplicate blueprint: '{bp_name}'")
                logger.debug("Found blueprint '%s'", bp_name)
                self._pending_blueprints[bp_name] = bp_data

        for proj_block in data.get("project", []):
            for proj_name, proj_data in proj_block.items():
                if proj_name in self._pending_projects:
                    raise ValueError(f"Duplicate project: '{proj_name}'")
                logger.debug("Found project '%s'", proj_name)
                self._pending_projects[proj_name] = proj_data
```

**Step 7: Remove `Workspace.scan()` and `context` parameter**

Remove the `scan()` method from Workspace. Remove `context` from `__init__` and the `_context` attribute.

```python
    def __init__(
        self,
        project_type: type[P] = Project,  # type: ignore[assignment]
    ) -> None:
        self._project_type = project_type
        self._pending_blueprints: dict[str, dict[str, Any]] = {}
        self._pending_projects: dict[str, dict[str, Any]] = {}
```

**Step 8: Update `hcl.scan()` to handle file discovery and loading**

```python
def scan[P: Project](
    path: str | Path,
    *,
    project_type: type[P] = Project,  # type: ignore[assignment]
    recurse: bool = True,
    context: dict[str, Any] | None = None,
) -> Workspace[P]:
    """Scan a directory for .hcl files and return a ready Workspace."""
    from .workspace import Workspace

    directory = Path(path)
    ws: Workspace[P] = Workspace(project_type=project_type)

    if not directory.is_dir():
        logger.warning("Directory '%s' does not exist; skipping scan", directory)
        return ws

    logger.info("Scanning '%s' (recurse=%s)", directory, recurse)
    pattern_func = directory.rglob if recurse else directory.glob
    for hcl_file in sorted(pattern_func("*.hcl")):
        ws.load(load(hcl_file, context=context))

    return ws
```

**Step 9: Update `tests/test_workspace.py`**

Key changes to tests:
- All `ws.load(file_path)` calls become `ws.load(hcl.load(file_path))` (import `spectrik.hcl as hcl` at top)
- All `ws.scan(dir_path)` calls become looping with `hcl.load()` or use `hcl.scan()` directly
- Remove `TestWorkspaceContext` class entirely (context is no longer on Workspace)
- Remove `TestWorkspaceScan` class entirely (scan is no longer on Workspace)
- Adjust `TestWorkspaceLoad` to pass dicts instead of file paths
- Keep `TestWorkspaceConstruction` tests but remove context-related tests

**Step 10: Run all tests**

Run: `uv run pytest tests/ -v`
Expected: All tests pass (some Jinja2-specific tests may still pass since Jinja2 hasn't been removed yet)

**Step 11: Commit**

```bash
git add src/spectrik/workspace.py src/spectrik/hcl.py tests/test_workspace.py
git commit -m "refactor: move resolution logic to Workspace, make it format-agnostic"
```

---

### Task 5: Wire `Resolver` into `hcl.load()` and remove Jinja2

**Files:**
- Modify: `src/spectrik/hcl.py`
- Modify: `pyproject.toml`
- Modify: `tests/test_hcl.py`

**Step 1: Update `hcl.load()` to use `Resolver` instead of Jinja2**

```python
"""HCL loading engine — parse .hcl files into dicts."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import hcl2

from .resolve import Resolver

logger = logging.getLogger(__name__)


def load(
    file: Path,
    *,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Load and parse a single HCL file, resolving ${...} interpolations."""
    text = file.read_text()
    try:
        data = hcl2.loads(text)  # type: ignore[reportPrivateImportUsage]
    except Exception as exc:
        raise ValueError(f"{file}: {exc}") from exc
    if context:
        resolver = Resolver(context)
        try:
            data = resolver.resolve(data)
        except ValueError as exc:
            raise ValueError(f"{file}: {exc}") from exc
    return data
```

**Step 2: Remove Jinja2 from dependencies**

In `pyproject.toml`, change line 10 from:
```toml
    "jinja2>=3.1.6",
```
Remove that line entirely.

**Step 3: Sync dependencies**

Run: `uv sync`

**Step 4: Update `tests/test_hcl.py`**

Replace `TestJinja2Features` with `TestInterpolation`:

```python
class TestInterpolation:
    """Test ${...} interpolation in HCL files."""

    def test_simple_variable(self, tmp_path):
        hcl_file = _write_hcl(
            tmp_path,
            "test.hcl",
            '''
            project "app" {
                description = "${greeting}"
            }
            ''',
        )
        result = hcl.load(hcl_file, context={"greeting": "hello"})
        assert result["project"][0]["app"]["description"] == "hello"

    def test_dotted_reference(self, tmp_path):
        hcl_file = _write_hcl(
            tmp_path,
            "test.hcl",
            '''
            project "app" {
                description = "${config.region}"
            }
            ''',
        )
        result = hcl.load(hcl_file, context={"config": {"region": "us-east-1"}})
        assert result["project"][0]["app"]["description"] == "us-east-1"

    def test_embedded_interpolation(self, tmp_path):
        hcl_file = _write_hcl(
            tmp_path,
            "test.hcl",
            '''
            project "app" {
                description = "${env.HOME}/.config/${name}"
            }
            ''',
        )
        result = hcl.load(
            hcl_file,
            context={"env": {"HOME": "/home/user"}, "name": "myapp"},
        )
        assert result["project"][0]["app"]["description"] == "/home/user/.config/myapp"

    def test_callable_context(self, tmp_path):
        hcl_file = _write_hcl(
            tmp_path,
            "test.hcl",
            '''
            project "app" {
                description = "${cwd}/data"
            }
            ''',
        )
        result = hcl.load(hcl_file, context={"cwd": lambda: "/tmp/work"})
        assert result["project"][0]["app"]["description"] == "/tmp/work/data"

    def test_undefined_raises_with_filepath(self, tmp_path):
        hcl_file = _write_hcl(
            tmp_path,
            "test.hcl",
            '''
            project "app" {
                description = "${missing}"
            }
            ''',
        )
        with pytest.raises(ValueError, match=str(hcl_file)):
            hcl.load(hcl_file, context={})

    def test_no_context_leaves_dollar_braces(self, tmp_path):
        """Without context, ${...} strings pass through from hcl2 as-is."""
        hcl_file = _write_hcl(
            tmp_path,
            "test.hcl",
            '''
            project "app" {
                description = "${name}"
            }
            ''',
        )
        result = hcl.load(hcl_file)
        assert result["project"][0]["app"]["description"] == "${name}"

    def test_double_brace_template_passthrough(self, tmp_path):
        """${{ ... }} (GitHub Actions syntax) passes through untouched."""
        hcl_file = _write_hcl(
            tmp_path,
            "test.hcl",
            '''
            project "app" {
                token = "${{ github.token }}"
            }
            ''',
        )
        result = hcl.load(hcl_file, context={"name": "app"})
        assert result["project"][0]["app"]["token"] == "${{ github.token }}"
```

Update `TestLoad` — change Jinja2 tests to use `${...}` syntax:
- `test_load_with_context_renders_variables` — change `{{ greeting }}` to `${greeting}`
- `test_load_undefined_var_raises_with_filepath` — change `{{ missing_var }}` to `${missing_var}`
- Remove `test_load_jinja2_syntax_error_raises_with_filepath` (no longer applicable)

Update `TestScan`:
- `test_scan_with_context` — change `{{ greeting }}` to `${greeting}`

**Step 5: Run all tests**

Run: `uv run pytest tests/ -v`
Expected: All tests pass

**Step 6: Run preflight**

Run: `make preflight`
Expected: All checks pass (ruff, pyright, tests)

**Step 7: Commit**

```bash
git add src/spectrik/hcl.py pyproject.toml tests/test_hcl.py uv.lock
git commit -m "feat: replace Jinja2 with HCL-native interpolation"
```

---

### Task 6: Update integration tests

**Files:**
- Modify: `tests/test_integration.py`

**Step 1: Update Jinja2-specific integration test**

Replace `test_full_pipeline_with_jinja2_context` with `test_full_pipeline_with_interpolation`:

```python
    def test_full_pipeline_with_interpolation(self, tmp_path):
        """End-to-end with ${...} interpolation."""
        config_hcl = tmp_path / "config.hcl"
        config_hcl.write_text(
            '''
            project "${prefix}-app" {
                description = "Generated app"
                ensure "counter" {}
            }
            '''
        )
        ws = hcl.scan(tmp_path, context={"prefix": "test"})
        assert "test-app" in ws
        ws["test-app"].build()
        assert CountingSpec.apply_count == 1
```

Note: The old test used Jinja2 `{% for %}` loops to generate multiple projects. Since we no longer support structural templating, this test verifies interpolation in project names and values instead.

Also update any other test that uses Jinja2 syntax — check `test_full_pipeline` and `test_hcl_scan_convenience` to confirm they don't use `{{ }}` (they don't based on the exploration).

**Step 2: Run all tests**

Run: `uv run pytest tests/ -v`
Expected: All tests pass

**Step 3: Commit**

```bash
git add tests/test_integration.py
git commit -m "test: update integration tests for HCL-native interpolation"
```

---

### Task 7: Final cleanup and preflight

**Files:**
- Modify: `src/spectrik/hcl.py` (if any leftover jinja2 references)
- Review: all source files for stale comments or imports

**Step 1: Search for any remaining Jinja2 references**

Search all files under `src/` and `tests/` for `jinja2`, `Jinja2`, `{{`, `{%`, `{#`. Remove or update any found.

**Step 2: Verify jinja2 is not importable from the project**

Run: `uv run python -c "import jinja2"` — should fail if properly removed from dependencies.

**Step 3: Run full preflight**

Run: `make preflight`
Expected: All checks pass (ruff, pyright, yamllint, tests)

**Step 4: Commit any cleanup**

```bash
git add -A
git commit -m "chore: remove remaining Jinja2 references"
```

---

## Summary of Changes

| File | Action |
|---|---|
| `src/spectrik/resolve.py` | **New** — `Resolver` class |
| `src/spectrik/hcl.py` | **Modified** — use Resolver, strip resolution functions, remove Jinja2 |
| `src/spectrik/workspace.py` | **Modified** — owns resolution logic, `load(dict)`, no context/scan |
| `pyproject.toml` | **Modified** — remove jinja2 dependency |
| `tests/test_resolve.py` | **New** — Resolver unit tests |
| `tests/test_hcl.py` | **Modified** — `${...}` syntax, remove Jinja2 tests |
| `tests/test_workspace.py` | **Modified** — dict-based load, remove context/scan tests |
| `tests/test_integration.py` | **Modified** — update interpolation test |
