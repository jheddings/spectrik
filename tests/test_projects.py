"""Tests for spectrik.projects."""

from __future__ import annotations

from spectrik.blueprints import Blueprint
from spectrik.context import Context
from spectrik.projects import Project
from spectrik.specs import Ensure, Specification


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
