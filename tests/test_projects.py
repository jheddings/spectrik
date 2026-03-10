"""Tests for spectrik.projects."""

from __future__ import annotations

import pytest

from spectrik.blueprints import Blueprint
from spectrik.context import Context
from spectrik.projects import Project, _project_registry, project
from spectrik.spec import Specification
from spectrik.specop import Ensure


@pytest.fixture(autouse=True)
def _clean_project_registry():
    saved = _project_registry.copy()
    yield
    _project_registry.clear()
    _project_registry.update(saved)


class FailingSpec(Specification["Project"]):
    def equals(self, ctx: Context[Project]) -> bool:
        return False

    def apply(self, ctx: Context[Project]) -> None:
        raise RuntimeError("boom")

    def remove(self, ctx: Context[Project]) -> None:
        pass


class TrackingSpec(Specification["Project"]):
    def __init__(self):
        self.applied = False

    def equals(self, ctx: Context[Project]) -> bool:
        return False

    def apply(self, ctx: Context[Project]) -> None:
        self.applied = True
        self.received_project = ctx.target

    def remove(self, ctx: Context[Project]) -> None:
        pass


class TestProject:
    def test_create_with_name(self):
        proj = Project(name="test-proj")
        assert proj.name == "test-proj"

    def test_description_defaults_empty(self):
        proj = Project(name="test-proj")
        assert proj.description == ""

    def test_blueprints_default_empty(self):
        proj = Project(name="test-proj")
        assert proj.blueprints == []

    def test_build_executes_blueprints(self):
        s = TrackingSpec()
        bp = Blueprint(name="bp", ops=[Ensure(s)])
        proj = Project(name="test-proj", blueprints=[bp])
        proj.build()
        assert s.applied is True

    def test_build_passes_self_as_target(self):
        s = TrackingSpec()
        bp = Blueprint(name="bp", ops=[Ensure(s)])
        proj = Project(name="test-proj", blueprints=[bp])
        proj.build()
        assert s.received_project is proj

    def test_build_dry_run(self):
        s = TrackingSpec()
        bp = Blueprint(name="bp", ops=[Ensure(s)])
        proj = Project(name="test-proj", blueprints=[bp])
        proj.build(dry_run=True)
        assert s.applied is False

    def test_subclass_preserved_in_context(self):
        class CustomProject(Project):
            custom_field: str = "hello"

        s = TrackingSpec()
        bp = Blueprint(name="bp", ops=[Ensure(s)])
        proj = CustomProject(name="test-proj", blueprints=[bp])
        proj.build()
        assert isinstance(s.received_project, CustomProject)
        assert s.received_project.custom_field == "hello"

    def test_build_with_ctx(self):
        events = []
        s = TrackingSpec()
        bp = Blueprint(name="bp", ops=[Ensure(s)])
        proj = Project(name="test-proj", blueprints=[bp])
        ctx = Context(target=proj)
        ctx.on_spec_applied += lambda c, op: events.append("applied")
        proj.build(ctx=ctx)
        assert s.applied is True
        assert events == ["applied"]

    def test_build_with_ctx_preserves_dry_run(self):
        s = TrackingSpec()
        bp = Blueprint(name="bp", ops=[Ensure(s)])
        proj = Project(name="test-proj", blueprints=[bp])
        ctx = Context(target=proj, dry_run=True)
        proj.build(ctx=ctx)
        assert s.applied is False

    def test_build_returns_true(self):
        s = TrackingSpec()
        bp = Blueprint(name="bp", ops=[Ensure(s)])
        proj = Project(name="test-proj", blueprints=[bp])
        result = proj.build()
        assert result is True

    def test_build_continue_on_error(self):
        s1 = FailingSpec()
        s2 = TrackingSpec()
        bp = Blueprint(name="bp", ops=[Ensure(s1), Ensure(s2)])
        proj = Project(name="test-proj", blueprints=[bp])
        result = proj.build(continue_on_error=True)
        assert result is False
        assert s2.applied is True

    def test_build_raises_on_error_by_default(self):
        import pytest

        s = FailingSpec()
        bp = Blueprint(name="bp", ops=[Ensure(s)])
        proj = Project(name="test-proj", blueprints=[bp])
        with pytest.raises(RuntimeError, match="boom"):
            proj.build()


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
