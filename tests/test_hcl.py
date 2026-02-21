"""Tests for spectrik.hcl."""

from __future__ import annotations

from pathlib import Path

import pytest

from spectrik.context import Context
from spectrik.hcl import load, scan
from spectrik.projects import Project
from spectrik.spec import Specification, _spec_registry
from spectrik.workspace import Workspace

# -- Test fixtures --


class SampleProject(Project):
    repo: str = ""
    homepage: str = ""


class TrackingSpec(Specification["SampleProject"]):
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.applied = False

    def equals(self, ctx: Context[SampleProject]) -> bool:
        return False

    def apply(self, ctx: Context[SampleProject]) -> None:
        self.applied = True

    def remove(self, ctx: Context[SampleProject]) -> None:
        pass


def _write_hcl(tmp_path: Path, subdir: str, filename: str, content: str) -> Path:
    d = tmp_path / subdir
    d.mkdir(parents=True, exist_ok=True)
    f = d / filename
    f.write_text(content)
    return f


@pytest.fixture(autouse=True)
def _clean_registry():
    """Clear spec registry before and after each test."""
    saved = _spec_registry.copy()
    _spec_registry.clear()

    # Register our test spec
    _spec_registry["widget"] = TrackingSpec

    yield

    _spec_registry.clear()
    _spec_registry.update(saved)


# -- Low-level API tests --


class TestLoad:
    def test_load_single_file(self, tmp_path):
        _write_hcl(
            tmp_path,
            ".",
            "test.hcl",
            """
            blueprint "my-bp" {
                ensure "widget" {
                    color = "red"
                }
            }
        """,
        )
        result = load(tmp_path / "test.hcl")
        assert "blueprint" in result

    def test_load_with_context_renders_variables(self, tmp_path):
        _write_hcl(
            tmp_path,
            ".",
            "test.hcl",
            """
            project "p" {
                description = "${greeting}"
            }
        """,
        )
        result = load(tmp_path / "test.hcl", context={"greeting": "hello"})
        assert result["project"][0]["p"]["description"] == "hello"

    def test_load_without_context_passes_through(self, tmp_path):
        _write_hcl(
            tmp_path,
            ".",
            "test.hcl",
            """
            project "p" {
                description = "plain"
            }
        """,
        )
        result = load(tmp_path / "test.hcl")
        assert result["project"][0]["p"]["description"] == "plain"

    def test_load_empty_context_passes_through(self, tmp_path):
        _write_hcl(
            tmp_path,
            ".",
            "test.hcl",
            """
            project "p" {
                description = "plain"
            }
        """,
        )
        result = load(tmp_path / "test.hcl", context={})
        assert result["project"][0]["p"]["description"] == "plain"

    def test_load_undefined_var_raises_with_filepath(self, tmp_path):
        _write_hcl(
            tmp_path,
            ".",
            "bad.hcl",
            """
        project "p" {
            description = "${missing_var}"
        }
    """,
        )
        with pytest.raises(ValueError, match="bad.hcl"):
            load(tmp_path / "bad.hcl", context={"something_else": "x"})


# -- hcl.scan() convenience function tests --


class TestScan:
    def test_scan_returns_workspace(self, tmp_path):
        _write_hcl(
            tmp_path,
            ".",
            "test.hcl",
            """
            project "myproj" { description = "test" }
        """,
        )
        ws = scan(tmp_path)
        assert isinstance(ws, Workspace)
        assert "myproj" in ws

    def test_scan_with_custom_project_type(self, tmp_path):
        _write_hcl(
            tmp_path,
            ".",
            "test.hcl",
            """
            project "myproj" {
                repo = "owner/repo"
                homepage = "https://example.com"
            }
        """,
        )
        ws = scan(tmp_path, project_type=SampleProject)
        proj = ws["myproj"]
        assert isinstance(proj, SampleProject)
        assert proj.repo == "owner/repo"

    def test_scan_recurse_true(self, tmp_path):
        _write_hcl(
            tmp_path,
            ".",
            "top.hcl",
            """
            project "top" { description = "top" }
        """,
        )
        _write_hcl(
            tmp_path,
            "sub",
            "nested.hcl",
            """
            project "nested" { description = "nested" }
        """,
        )
        ws = scan(tmp_path, recurse=True)
        assert "top" in ws
        assert "nested" in ws

    def test_scan_recurse_false(self, tmp_path):
        _write_hcl(
            tmp_path,
            ".",
            "top.hcl",
            """
            project "top" { description = "top" }
        """,
        )
        _write_hcl(
            tmp_path,
            "sub",
            "nested.hcl",
            """
            project "nested" { description = "nested" }
        """,
        )
        ws = scan(tmp_path, recurse=False)
        assert "top" in ws
        assert "nested" not in ws

    def test_scan_empty_dir(self, tmp_path):
        ws = scan(tmp_path)
        assert len(ws) == 0

    def test_scan_missing_dir(self, tmp_path):
        ws = scan(tmp_path / "nonexistent")
        assert len(ws) == 0

    def test_scan_with_context(self, tmp_path):
        _write_hcl(
            tmp_path,
            ".",
            "test.hcl",
            """
            project "p" {
                description = "${greeting}"
            }
        """,
        )
        ws = scan(tmp_path, context={"greeting": "hello"})
        assert ws["p"].description == "hello"

    def test_scan_with_blueprints_and_projects(self, tmp_path):
        _write_hcl(
            tmp_path,
            ".",
            "test.hcl",
            """
            blueprint "base" {
                ensure "widget" { color = "red" }
            }
            project "myproj" {
                use = ["base"]
            }
        """,
        )
        ws = scan(tmp_path)
        assert len(ws["myproj"].blueprints) == 1


# -- Interpolation feature tests --


class TestInterpolation:
    """Test ${...} interpolation in HCL files."""

    def test_simple_variable(self, tmp_path):
        _write_hcl(
            tmp_path,
            ".",
            "test.hcl",
            """
            project "app" {
                description = "${greeting}"
            }
        """,
        )
        result = load(tmp_path / "test.hcl", context={"greeting": "hello"})
        assert result["project"][0]["app"]["description"] == "hello"

    def test_dotted_reference(self, tmp_path):
        _write_hcl(
            tmp_path,
            ".",
            "test.hcl",
            """
            project "app" {
                description = "${config.region}"
            }
        """,
        )
        result = load(tmp_path / "test.hcl", context={"config": {"region": "us-east-1"}})
        assert result["project"][0]["app"]["description"] == "us-east-1"

    def test_embedded_interpolation(self, tmp_path):
        _write_hcl(
            tmp_path,
            ".",
            "test.hcl",
            """
            project "app" {
                description = "${env.HOME}/.config/${name}"
            }
        """,
        )
        result = load(
            tmp_path / "test.hcl",
            context={"env": {"HOME": "/home/user"}, "name": "myapp"},
        )
        assert result["project"][0]["app"]["description"] == "/home/user/.config/myapp"

    def test_callable_context(self, tmp_path):
        _write_hcl(
            tmp_path,
            ".",
            "test.hcl",
            """
            project "app" {
                description = "${cwd}/data"
            }
        """,
        )
        result = load(tmp_path / "test.hcl", context={"cwd": lambda: "/tmp/work"})
        assert result["project"][0]["app"]["description"] == "/tmp/work/data"

    def test_undefined_raises_with_filepath(self, tmp_path):
        _write_hcl(
            tmp_path,
            ".",
            "test.hcl",
            """
            project "app" {
                description = "${missing}"
            }
        """,
        )
        with pytest.raises(ValueError, match=str(tmp_path)):
            load(tmp_path / "test.hcl", context={"other": "x"})

    def test_no_context_leaves_dollar_braces(self, tmp_path):
        """Without context, ${...} strings pass through from hcl2 as-is."""
        _write_hcl(
            tmp_path,
            ".",
            "test.hcl",
            """
            project "app" {
                description = "${name}"
            }
        """,
        )
        result = load(tmp_path / "test.hcl")
        assert result["project"][0]["app"]["description"] == "${name}"

    def test_nested_in_list(self, tmp_path):
        """Interpolation works inside list values."""
        _write_hcl(
            tmp_path,
            ".",
            "test.hcl",
            """
            project "app" {
                use = ["${bp_name}"]
            }
        """,
        )
        result = load(tmp_path / "test.hcl", context={"bp_name": "base"})
        assert result["project"][0]["app"]["use"] == ["base"]
