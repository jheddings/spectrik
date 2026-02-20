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
                description = "{{ greeting }}"
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
            description = "{{ missing_var }}"
        }
    """,
        )
        with pytest.raises(ValueError, match="bad.hcl"):
            load(tmp_path / "bad.hcl", context={})

    def test_load_jinja2_syntax_error_raises_with_filepath(self, tmp_path):
        _write_hcl(
            tmp_path,
            ".",
            "bad.hcl",
            """
        project "p" {
            description = "{% if %}"
        }
    """,
        )
        with pytest.raises(ValueError, match="bad.hcl"):
            load(tmp_path / "bad.hcl", context={})


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
                description = "{{ greeting }}"
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


# -- Jinja2 structural feature tests --


class TestJinja2Features:
    """Test Jinja2 structural templating in HCL files."""

    def test_conditional_includes_block(self, tmp_path):
        _write_hcl(
            tmp_path,
            ".",
            "test.hcl",
            """
            project "base" {
                description = "always"
            }
            {% if include_extra %}
            project "extra" {
                description = "conditional"
            }
            {% endif %}
        """,
        )
        ws = scan(tmp_path, context={"include_extra": True})
        assert "base" in ws
        assert "extra" in ws

    def test_conditional_excludes_block(self, tmp_path):
        _write_hcl(
            tmp_path,
            ".",
            "test.hcl",
            """
            project "base" {
                description = "always"
            }
            {% if include_extra %}
            project "extra" {
                description = "conditional"
            }
            {% endif %}
        """,
        )
        ws = scan(tmp_path, context={"include_extra": False})
        assert "base" in ws
        assert "extra" not in ws

    def test_loop_generates_blocks(self, tmp_path):
        _write_hcl(
            tmp_path,
            ".",
            "test.hcl",
            """
            {% for name in projects %}
            project "{{ name }}" {
                description = "generated"
            }
            {% endfor %}
        """,
        )
        ws = scan(tmp_path, context={"projects": ["alpha", "beta", "gamma"]})
        assert len(ws) == 3
        assert "alpha" in ws
        assert "beta" in ws
        assert "gamma" in ws

    def test_comment_stripped(self, tmp_path):
        _write_hcl(
            tmp_path,
            ".",
            "test.hcl",
            """
            {# This Jinja2 comment should not appear in output #}
            project "p" {
                description = "test"
            }
        """,
        )
        ws = scan(tmp_path, context={})
        assert ws["p"].description == "test"

    def test_nested_context_access(self, tmp_path):
        _write_hcl(
            tmp_path,
            ".",
            "test.hcl",
            """
            project "p" {
                description = "{{ config.region }}"
            }
        """,
        )
        ws = scan(tmp_path, context={"config": {"region": "us-east-1"}})
        assert ws["p"].description == "us-east-1"

    def test_jinja2_filter(self, tmp_path):
        _write_hcl(
            tmp_path,
            ".",
            "test.hcl",
            """
            project "p" {
                description = "{{ name | upper }}"
            }
        """,
        )
        ws = scan(tmp_path, context={"name": "hello"})
        assert ws["p"].description == "HELLO"
