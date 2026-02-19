"""Tests for spectrik.workspace."""

from __future__ import annotations

from pathlib import Path

import pytest

from spectrik.context import Context
from spectrik.projects import Project
from spectrik.specs import Specification, _spec_registry
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
        _write_hcl(
            tmp_path,
            "test.hcl",
            """
            project "myproj" {
                description = "test"
            }
        """,
        )
        ws = Workspace()
        ws.load(tmp_path / "test.hcl")
        assert "myproj" in ws
        assert ws["myproj"].description == "test"

    def test_load_accepts_string_path(self, tmp_path):
        _write_hcl(
            tmp_path,
            "test.hcl",
            """
            project "myproj" {
                description = "test"
            }
        """,
        )
        ws = Workspace()
        ws.load(str(tmp_path / "test.hcl"))
        assert "myproj" in ws

    def test_load_file_with_blueprint_and_project(self, tmp_path):
        _write_hcl(
            tmp_path,
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
        ws = Workspace()
        ws.load(tmp_path / "test.hcl")
        assert len(ws["myproj"].blueprints) == 1

    def test_load_multiple_files(self, tmp_path):
        _write_hcl(
            tmp_path,
            "a.hcl",
            """
            blueprint "base" {
                ensure "widget" { color = "red" }
            }
        """,
        )
        _write_hcl(
            tmp_path,
            "b.hcl",
            """
            project "myproj" {
                use = ["base"]
            }
        """,
        )
        ws = Workspace()
        ws.load(tmp_path / "a.hcl")
        ws.load(tmp_path / "b.hcl")
        assert len(ws["myproj"].blueprints) == 1

    def test_load_duplicate_blueprint_raises(self, tmp_path):
        _write_hcl(
            tmp_path,
            "a.hcl",
            """
            blueprint "base" {
                ensure "widget" { color = "red" }
            }
        """,
        )
        _write_hcl(
            tmp_path,
            "b.hcl",
            """
            blueprint "base" {
                ensure "widget" { color = "blue" }
            }
        """,
        )
        ws = Workspace()
        ws.load(tmp_path / "a.hcl")
        with pytest.raises(ValueError, match="base"):
            ws.load(tmp_path / "b.hcl")

    def test_load_duplicate_project_raises(self, tmp_path):
        _write_hcl(
            tmp_path,
            "a.hcl",
            """
            project "myproj" { description = "first" }
        """,
        )
        _write_hcl(
            tmp_path,
            "b.hcl",
            """
            project "myproj" { description = "second" }
        """,
        )
        ws = Workspace()
        ws.load(tmp_path / "a.hcl")
        with pytest.raises(ValueError, match="myproj"):
            ws.load(tmp_path / "b.hcl")

    def test_load_blueprint_only_file(self, tmp_path):
        _write_hcl(
            tmp_path,
            "test.hcl",
            """
            blueprint "base" {
                ensure "widget" { color = "red" }
            }
        """,
        )
        ws = Workspace()
        ws.load(tmp_path / "test.hcl")
        assert len(ws) == 0  # no projects
        assert len(ws._pending_blueprints) == 1

    def test_repr_after_load(self, tmp_path):
        _write_hcl(
            tmp_path,
            "test.hcl",
            """
            blueprint "base" {}
            project "myproj" { description = "test" }
        """,
        )
        ws = Workspace()
        ws.load(tmp_path / "test.hcl")
        assert "blueprints=1" in repr(ws)
        assert "projects=1" in repr(ws)
