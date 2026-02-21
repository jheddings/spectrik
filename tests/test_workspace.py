"""Tests for spectrik.workspace."""

from __future__ import annotations

import pytest

from spectrik.context import Context
from spectrik.projects import Project
from spectrik.spec import Specification, _spec_registry
from spectrik.workspace import BlueprintRef, OperationRef, ProjectRef, Workspace


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


# -- Helpers for ref-based tests --


class TrackingSpec(Specification["Project"]):
    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def equals(self, ctx: Context[Project]) -> bool:
        return False

    def apply(self, ctx: Context[Project]) -> None:
        pass

    def remove(self, ctx: Context[Project]) -> None:
        pass


@pytest.fixture()
def _clean_registry():
    saved = _spec_registry.copy()
    _spec_registry.clear()
    _spec_registry["widget"] = TrackingSpec
    yield
    _spec_registry.clear()
    _spec_registry.update(saved)


class TestWorkspaceAdd:
    def test_add_project_ref(self):
        ws = Workspace()
        ref = ProjectRef(name="myproj", use=[], ops=[], description="test")
        ws.add(ref)
        assert "myproj" in ws
        proj = ws["myproj"]
        assert proj.name == "myproj"
        assert proj.description == "test"

    @pytest.mark.usefixtures("_clean_registry")
    def test_add_blueprint_ref(self):
        op = OperationRef(name="widget", strategy="ensure", attrs={"color": "red"})
        ref = BlueprintRef(name="base", includes=[], ops=[op])
        ws = Workspace()
        ws.add(ref)
        assert "base" in ws.blueprints

    @pytest.mark.usefixtures("_clean_registry")
    def test_add_multiple_refs(self):
        op = OperationRef(name="widget", strategy="ensure", attrs={"color": "red"})
        bp = BlueprintRef(name="base", includes=[], ops=[op])
        proj = ProjectRef(name="myproj", use=["base"], ops=[])
        ws = Workspace()
        ws.add(bp, proj)
        assert "base" in ws.blueprints
        assert "myproj" in ws

    @pytest.mark.usefixtures("_clean_registry")
    def test_add_duplicate_blueprint_raises(self):
        op = OperationRef(name="widget", strategy="ensure", attrs={"color": "red"})
        ref1 = BlueprintRef(name="base", includes=[], ops=[op])
        ref2 = BlueprintRef(name="base", includes=[], ops=[op])
        ws = Workspace()
        ws.add(ref1)
        with pytest.raises(ValueError, match="base"):
            ws.add(ref2)

    def test_add_duplicate_project_raises(self):
        ref1 = ProjectRef(name="myproj", use=[], ops=[])
        ref2 = ProjectRef(name="myproj", use=[], ops=[])
        ws = Workspace()
        ws.add(ref1)
        with pytest.raises(ValueError, match="myproj"):
            ws.add(ref2)

    @pytest.mark.usefixtures("_clean_registry")
    def test_add_unsupported_type_raises(self):
        op_ref = OperationRef(name="widget", strategy="ensure", attrs={})
        ws = Workspace()
        with pytest.raises(TypeError, match="Unsupported ref type"):
            ws.add(op_ref)

    def test_iadd_single_ref(self):
        ws = Workspace()
        ref = ProjectRef(name="myproj", use=[], ops=[])
        ws += ref
        assert "myproj" in ws

    def test_iadd_returns_self(self):
        ws = Workspace()
        ref = ProjectRef(name="myproj", use=[], ops=[])
        result = ws.__iadd__(ref)
        assert result is ws


class TestWorkspaceMapping:
    """Test Mapping protocol with refs constructed directly."""

    def test_values(self):
        ws = Workspace()
        ws.add(
            ProjectRef(name="a", use=[], ops=[], description="alpha"),
            ProjectRef(name="b", use=[], ops=[], description="beta"),
        )
        names = sorted(p.name for p in ws.values())
        assert names == ["a", "b"]

    def test_items(self):
        ws = Workspace()
        ws.add(ProjectRef(name="a", use=[], ops=[], description="alpha"))
        pairs = list(ws.items())
        assert len(pairs) == 1
        assert pairs[0][0] == "a"
        assert pairs[0][1].description == "alpha"

    def test_keys(self):
        ws = Workspace()
        ws.add(
            ProjectRef(name="a", use=[], ops=[], description="alpha"),
            ProjectRef(name="b", use=[], ops=[], description="beta"),
        )
        assert sorted(ws.keys()) == ["a", "b"]

    def test_fresh_resolution_each_access(self):
        ws = Workspace()
        ws.add(ProjectRef(name="a", use=[], ops=[], description="alpha"))
        proj1 = ws["a"]
        proj2 = ws["a"]
        assert proj1 is not proj2
        assert proj1.name == proj2.name

    def test_filter(self):
        ws = Workspace()
        ws.add(
            ProjectRef(name="a", use=[], ops=[], description="alpha"),
            ProjectRef(name="b", use=[], ops=[], description="beta"),
            ProjectRef(name="c", use=[], ops=[], description="gamma"),
        )
        result = ws.filter(["a", "c"])
        assert len(result) == 2
        assert result[0].name == "a"
        assert result[1].name == "c"

    def test_filter_skips_missing(self):
        ws = Workspace()
        ws.add(ProjectRef(name="a", use=[], ops=[], description="alpha"))
        result = ws.filter(["a", "missing"])
        assert len(result) == 1

    def test_filter_empty_names(self):
        ws = Workspace()
        ws.add(ProjectRef(name="a", use=[], ops=[], description="alpha"))
        assert ws.filter([]) == []

    def test_custom_project_type(self):
        class Custom(Project):
            repo: str = ""

        ws = Workspace(project_type=Custom)
        ref = ProjectRef(name="myproj", use=[], ops=[], attrs={"repo": "owner/repo"})
        ws.add(ref)
        proj = ws["myproj"]
        assert isinstance(proj, Custom)
        assert proj.repo == "owner/repo"
