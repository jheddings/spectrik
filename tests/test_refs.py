"""Tests for OperationRef, BlueprintRef, and ProjectRef."""

from __future__ import annotations

import pytest

from spectrik.context import Context
from spectrik.projects import Project, _project_registry, project
from spectrik.spec import Specification, _spec_registry
from spectrik.specop import Absent, Ensure, Present
from spectrik.workspace import BlueprintRef, OperationRef, ProjectRef, Workspace


class TrackingSpec(Specification["Project"]):
    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def equals(self, ctx: Context[Project]) -> bool:
        return False

    def apply(self, ctx: Context[Project]) -> None:
        pass

    def remove(self, ctx: Context[Project]) -> None:
        pass


@pytest.fixture(autouse=True)
def _clean_registry():
    saved_specs = _spec_registry.copy()
    _spec_registry.clear()
    _spec_registry["widget"] = TrackingSpec
    saved_projects = _project_registry.copy()
    yield
    _spec_registry.clear()
    _spec_registry.update(saved_specs)
    _project_registry.clear()
    _project_registry.update(saved_projects)


class TestOperationRef:
    def test_resolve_ensure(self):
        ref = OperationRef(name="widget", strategy="ensure", attrs={"color": "red"})
        ws = Workspace()
        result = ref.resolve(ws)
        assert isinstance(result, Ensure)
        assert isinstance(result.spec, TrackingSpec)
        assert result.spec.kwargs == {"color": "red"}

    def test_resolve_present(self):
        ref = OperationRef(name="widget", strategy="present", attrs={"size": "large"})
        ws = Workspace()
        result = ref.resolve(ws)
        assert isinstance(result, Present)
        assert isinstance(result.spec, TrackingSpec)
        assert result.spec.kwargs == {"size": "large"}

    def test_resolve_absent(self):
        ref = OperationRef(name="widget", strategy="absent", attrs={"id": "42"})
        ws = Workspace()
        result = ref.resolve(ws)
        assert isinstance(result, Absent)
        assert isinstance(result.spec, TrackingSpec)
        assert result.spec.kwargs == {"id": "42"}

    def test_resolve_unknown_spec_raises(self):
        ref = OperationRef(name="nonexistent", strategy="ensure", attrs={})
        ws = Workspace()
        with pytest.raises(ValueError, match="Unknown spec type: 'nonexistent'"):
            ref.resolve(ws)

    def test_resolve_unknown_spec_includes_source(self):
        from pathlib import Path

        source = Path("/tmp/test-config.hcl")
        ref = OperationRef(name="nonexistent", strategy="ensure", attrs={}, source=source)
        ws = Workspace()
        with pytest.raises(ValueError, match="in /tmp/test-config.hcl"):
            ref.resolve(ws)

    def test_resolve_unknown_spec_suggests_import(self):
        ref = OperationRef(name="nonexistent", strategy="ensure", attrs={})
        ws = Workspace()
        with pytest.raises(ValueError, match="ensure the module registering this spec is imported"):
            ref.resolve(ws)

    def test_resolve_unknown_strategy_raises(self):
        ref = OperationRef(name="widget", strategy="invalid", attrs={})
        ws = Workspace()
        with pytest.raises(ValueError, match="Unknown strategy"):
            ref.resolve(ws)

    def test_label_defaults_none(self):
        ref = OperationRef(name="widget", strategy="ensure", attrs={})
        assert ref.label is None

    def test_label_set(self):
        ref = OperationRef(name="widget", strategy="ensure", attrs={}, label="my-label")
        assert ref.label == "my-label"


class TestBlueprintRef:
    def test_resolve_simple(self):
        op = OperationRef(name="widget", strategy="ensure", attrs={"color": "red"})
        ref = BlueprintRef(name="simple", includes=[], ops=[op])
        ws = Workspace()
        bp = ref.resolve(ws)
        assert bp.name == "simple"
        assert len(bp.ops) == 1

    def test_resolve_with_includes(self):
        base_op = OperationRef(name="widget", strategy="ensure", attrs={"color": "red"})
        base_ref = BlueprintRef(name="base", includes=[], ops=[base_op])

        ext_op = OperationRef(name="widget", strategy="present", attrs={"size": "large"})
        ext_ref = BlueprintRef(name="extended", includes=["base"], ops=[ext_op])

        ws = Workspace()
        ws.add(base_ref)
        ws.add(ext_ref)

        bp = ext_ref.resolve(ws)
        assert bp.name == "extended"
        assert len(bp.ops) == 2

    def test_resolve_circular_include_raises(self):
        ref_a = BlueprintRef(name="a", includes=["b"], ops=[])
        ref_b = BlueprintRef(name="b", includes=["a"], ops=[])

        ws = Workspace()
        ws.add(ref_a)
        ws.add(ref_b)

        with pytest.raises(ValueError, match="Circular"):
            ref_a.resolve(ws)

    def test_resolve_unknown_include_raises(self):
        ref = BlueprintRef(name="broken", includes=["missing"], ops=[])
        ws = Workspace()
        ws.add(ref)

        with pytest.raises(KeyError):
            ref.resolve(ws)

    def test_empty_blueprint(self):
        ref = BlueprintRef(name="empty", includes=[], ops=[])
        ws = Workspace()
        bp = ref.resolve(ws)
        assert bp.name == "empty"
        assert len(bp.ops) == 0

    def test_description_default(self):
        ref = BlueprintRef(name="nodesc", includes=[], ops=[])
        assert ref.description == ""

    def test_description_set(self):
        ref = BlueprintRef(name="withdesc", includes=[], ops=[], description="A blueprint")
        assert ref.description == "A blueprint"


class TestProjectRef:
    def test_resolve_simple(self):
        ref = ProjectRef(name="myproj", use=[], ops=[], description="test")
        ws = Workspace()
        project = ref.resolve(ws)
        assert project.name == "myproj"
        assert project.description == "test"
        assert isinstance(project, Project)

    def test_resolve_with_blueprint(self):
        op = OperationRef(name="widget", strategy="ensure", attrs={"color": "red"})
        bp_ref = BlueprintRef(name="base", includes=[], ops=[op])
        proj_ref = ProjectRef(name="myproj", use=["base"], ops=[])

        ws = Workspace()
        ws.add(bp_ref)
        ws.add(proj_ref)

        project = proj_ref.resolve(ws)
        assert len(project.blueprints) == 1
        assert project.blueprints[0].name == "base"

    def test_resolve_with_inline_ops(self):
        op = OperationRef(name="widget", strategy="ensure", attrs={"color": "blue"})
        ref = ProjectRef(name="myproj", use=[], ops=[op])

        ws = Workspace()
        project = ref.resolve(ws)
        assert len(project.blueprints) == 1
        assert project.blueprints[0].name == "myproj:inline"

    def test_resolve_with_custom_project_type(self):
        @project("custom")
        class Custom(Project):
            repo: str = ""

        ws = Workspace()
        ref = ProjectRef(
            name="myproj", type_name="custom", use=[], ops=[], attrs={"repo": "owner/repo"}
        )
        ws.add(ref)

        resolved = ref.resolve(ws)
        assert isinstance(resolved, Custom)
        assert resolved.repo == "owner/repo"

    def test_resolve_unknown_blueprint_raises(self):
        ref = ProjectRef(name="myproj", use=["missing"], ops=[])
        ws = Workspace()
        with pytest.raises(KeyError):
            ref.resolve(ws)

    def test_attrs_default_empty(self):
        ref = ProjectRef(name="myproj", use=[], ops=[])
        assert ref.attrs == {}

    def test_description_default(self):
        ref = ProjectRef(name="myproj", use=[], ops=[])
        assert ref.description == ""
