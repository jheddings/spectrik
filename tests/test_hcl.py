"""Tests for spectrik.hcl."""

from __future__ import annotations

import os
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


# -- Variable interpolation tests --


class TestVariableInterpolation:
    def test_env_var_expansion(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SPECTRIK_TEST_VAR", "/test/path")
        _write_hcl(
            tmp_path,
            ".",
            "test.hcl",
            """
            blueprint "interp" {
                ensure "widget" {
                    color = "${env.SPECTRIK_TEST_VAR}/sub"
                }
            }
            project "p" { use = ["interp"] }
        """,
        )
        ws = scan(tmp_path)
        op = ws["p"].blueprints[0].ops[0]
        assert isinstance(op.spec, TrackingSpec)
        assert op.spec.kwargs["color"] == "/test/path/sub"

    def test_cwd_expansion(self, tmp_path):
        _write_hcl(
            tmp_path,
            ".",
            "test.hcl",
            """
            blueprint "interp" {
                ensure "widget" {
                    color = "${CWD}/file"
                }
            }
            project "p" { use = ["interp"] }
        """,
        )
        ws = scan(tmp_path)
        op = ws["p"].blueprints[0].ops[0]
        assert isinstance(op.spec, TrackingSpec)
        assert op.spec.kwargs["color"] == f"{os.getcwd()}/file"

    def test_unknown_env_var_expands_to_empty(self, tmp_path, monkeypatch):
        monkeypatch.delenv("SPECTRIK_NONEXISTENT", raising=False)
        _write_hcl(
            tmp_path,
            ".",
            "test.hcl",
            """
            blueprint "interp" {
                ensure "widget" {
                    color = "${env.SPECTRIK_NONEXISTENT}"
                }
            }
            project "p" { use = ["interp"] }
        """,
        )
        ws = scan(tmp_path)
        op = ws["p"].blueprints[0].ops[0]
        assert isinstance(op.spec, TrackingSpec)
        assert op.spec.kwargs["color"] == ""

    def test_multiple_vars_in_one_string(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SPECTRIK_A", "hello")
        monkeypatch.setenv("SPECTRIK_B", "world")
        _write_hcl(
            tmp_path,
            ".",
            "test.hcl",
            """
            blueprint "interp" {
                ensure "widget" {
                    color = "${env.SPECTRIK_A}-${env.SPECTRIK_B}"
                }
            }
            project "p" { use = ["interp"] }
        """,
        )
        ws = scan(tmp_path)
        op = ws["p"].blueprints[0].ops[0]
        assert isinstance(op.spec, TrackingSpec)
        assert op.spec.kwargs["color"] == "hello-world"

    def test_no_vars_unchanged(self, tmp_path):
        _write_hcl(
            tmp_path,
            ".",
            "test.hcl",
            """
            blueprint "interp" {
                ensure "widget" {
                    color = "plain-value"
                }
            }
            project "p" { use = ["interp"] }
        """,
        )
        ws = scan(tmp_path)
        op = ws["p"].blueprints[0].ops[0]
        assert isinstance(op.spec, TrackingSpec)
        assert op.spec.kwargs["color"] == "plain-value"

    def test_non_string_values_unchanged(self, tmp_path):
        _write_hcl(
            tmp_path,
            ".",
            "test.hcl",
            """
            blueprint "interp" {
                ensure "widget" {
                    color = 42
                }
            }
            project "p" { use = ["interp"] }
        """,
        )
        ws = scan(tmp_path)
        op = ws["p"].blueprints[0].ops[0]
        assert isinstance(op.spec, TrackingSpec)
        assert op.spec.kwargs["color"] == 42

    def test_vars_in_project_inline_specs(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SPECTRIK_TEST_VAR", "resolved")
        _write_hcl(
            tmp_path,
            ".",
            "test.hcl",
            """
            project "myproj" {
                ensure "widget" {
                    color = "${env.SPECTRIK_TEST_VAR}"
                }
            }
        """,
        )
        ws = scan(tmp_path)
        op = ws["myproj"].blueprints[0].ops[0]
        assert isinstance(op.spec, TrackingSpec)
        assert op.spec.kwargs["color"] == "resolved"
