"""Tests for spectrik.projects."""

from __future__ import annotations

import pytest

from spectrik.blueprints import Blueprint
from spectrik.context import Context
from spectrik.projects import (
    Project,
    _collect_hooks,
    _project_registry,
    post_build,
    pre_build,
    project,
)
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


class TestLifecycleHooks:
    def test_pre_build_decorator_marks_method(self):
        class MyProject(Project):
            @pre_build
            def setup(self, ctx):
                pass

        assert getattr(MyProject.setup, "_spectrik_hook", None) == "pre_build"

    def test_post_build_decorator_marks_method(self):
        class MyProject(Project):
            @post_build
            def teardown(self, ctx):
                pass

        assert getattr(MyProject.teardown, "_spectrik_hook", None) == "post_build"

    def test_collect_hooks_finds_pre_build(self):
        class MyProject(Project):
            @pre_build
            def setup(self, ctx):
                pass

        proj = MyProject(name="test")
        hooks = _collect_hooks(proj, "pre_build")
        assert len(hooks) == 1

    def test_collect_hooks_empty_when_none(self):
        proj = Project(name="test")
        hooks = _collect_hooks(proj, "pre_build")
        assert hooks == []

    def test_collect_hooks_mro_order(self):
        """Base class hooks run before subclass hooks."""
        order = []

        class Base(Project):
            @pre_build
            def base_setup(self, ctx):
                order.append("base")

        class Child(Base):
            @pre_build
            def child_setup(self, ctx):
                order.append("child")

        proj = Child(name="test")
        hooks = _collect_hooks(proj, "pre_build")
        for h in hooks:
            h(None)
        assert order == ["base", "child"]

    def test_pre_build_runs_before_specs(self):
        order = []

        class HookedProject(Project):
            @pre_build
            def setup(self, ctx):
                order.append("pre_build")

        class OrderSpec(Specification["HookedProject"]):
            def equals(self, ctx):
                return False

            def apply(self, ctx):
                order.append("spec")

            def remove(self, ctx):
                pass

        s = OrderSpec()
        bp = Blueprint(name="bp", ops=[Ensure(s)])
        proj = HookedProject(name="test", blueprints=[bp])
        proj.build()
        assert order == ["pre_build", "spec"]

    def test_post_build_runs_after_specs(self):
        order = []

        class HookedProject(Project):
            @post_build
            def teardown(self, ctx):
                order.append("post_build")

        class OrderSpec(Specification["HookedProject"]):
            def equals(self, ctx):
                return False

            def apply(self, ctx):
                order.append("spec")

            def remove(self, ctx):
                pass

        s = OrderSpec()
        bp = Blueprint(name="bp", ops=[Ensure(s)])
        proj = HookedProject(name="test", blueprints=[bp])
        proj.build()
        assert order == ["spec", "post_build"]

    def test_pre_build_receives_context(self):
        received = {}

        class HookedProject(Project):
            @pre_build
            def setup(self, ctx):
                received["ctx"] = ctx
                received["target"] = ctx.target

        proj = HookedProject(name="test")
        proj.build()
        assert received["target"] is proj
        assert isinstance(received["ctx"], Context)

    def test_pre_build_raising_aborts_build(self):
        class HookedProject(Project):
            @pre_build
            def setup(self, ctx):
                raise RuntimeError("setup failed")

        s = TrackingSpec()
        bp = Blueprint(name="bp", ops=[Ensure(s)])
        proj = HookedProject(name="test", blueprints=[bp])
        with pytest.raises(RuntimeError, match="setup failed"):
            proj.build()
        assert s.applied is False

    def test_post_build_runs_on_pre_build_failure(self):
        cleaned_up = []

        class HookedProject(Project):
            @pre_build
            def setup(self, ctx):
                raise RuntimeError("setup failed")

            @post_build
            def teardown(self, ctx):
                cleaned_up.append(True)

        proj = HookedProject(name="test")
        with pytest.raises(RuntimeError, match="setup failed"):
            proj.build()
        assert cleaned_up == [True]

    def test_post_build_runs_on_spec_failure(self):
        cleaned_up = []

        class HookedProject(Project):
            @post_build
            def teardown(self, ctx):
                cleaned_up.append(True)

        s = FailingSpec()
        bp = Blueprint(name="bp", ops=[Ensure(s)])
        proj = HookedProject(name="test", blueprints=[bp])
        with pytest.raises(RuntimeError, match="boom"):
            proj.build()
        assert cleaned_up == [True]

    def test_multiple_pre_build_hooks(self):
        order = []

        class HookedProject(Project):
            @pre_build
            def first(self, ctx):
                order.append("first")

            @pre_build
            def second(self, ctx):
                order.append("second")

        proj = HookedProject(name="test")
        proj.build()
        assert order == ["first", "second"]

    def test_no_hooks_build_unchanged(self):
        """Projects without hooks work exactly as before."""
        s = TrackingSpec()
        bp = Blueprint(name="bp", ops=[Ensure(s)])
        proj = Project(name="test", blueprints=[bp])
        result = proj.build()
        assert result is True
        assert s.applied is True
