"""Tests for spectrik.blueprints."""

from __future__ import annotations

from pydantic import BaseModel

from spectrik.blueprints import Blueprint
from spectrik.context import Context
from spectrik.spec import Specification
from spectrik.specop import Ensure, Present


class FakeProject(BaseModel):
    name: str = "test"


class TrackingSpec(Specification["FakeProject"]):
    def __init__(self):
        self.applied = False

    def equals(self, ctx: Context[FakeProject]) -> bool:
        return False

    def apply(self, ctx: Context[FakeProject]) -> None:
        self.applied = True

    def remove(self, ctx: Context[FakeProject]) -> None:
        pass


def _make_ctx(**kwargs) -> Context[FakeProject]:
    return Context(target=FakeProject(), **kwargs)


class TestBlueprint:
    def test_create_with_name(self):
        bp = Blueprint(name="test-bp")
        assert bp.name == "test-bp"

    def test_ops_default_empty(self):
        bp = Blueprint(name="test-bp")
        assert bp.ops == []

    def test_iterable(self):
        s1 = TrackingSpec()
        s2 = TrackingSpec()
        bp = Blueprint(name="test-bp", ops=[Present(s1), Ensure(s2)])
        ops = list(bp)
        assert len(ops) == 2

    def test_build_executes_all_ops(self):
        s1 = TrackingSpec()
        s2 = TrackingSpec()
        bp = Blueprint(name="test-bp", ops=[Ensure(s1), Ensure(s2)])
        ctx = _make_ctx()
        bp.build(ctx)
        assert s1.applied is True
        assert s2.applied is True

    def test_build_dry_run(self):
        s = TrackingSpec()
        bp = Blueprint(name="test-bp", ops=[Ensure(s)])
        ctx = _make_ctx(dry_run=True)
        bp.build(ctx)
        assert s.applied is False
