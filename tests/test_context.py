"""Tests for spectrik.context."""

from __future__ import annotations

from pydantic import BaseModel

from spectrik.context import Context


class FakeProject(BaseModel):
    name: str = "test"


class TestContext:
    def test_create_with_target(self):
        proj = FakeProject()
        ctx = Context(target=proj)
        assert ctx.target is proj

    def test_dry_run_defaults_false(self):
        proj = FakeProject()
        ctx = Context(target=proj)
        assert ctx.dry_run is False

    def test_dry_run_explicit_true(self):
        proj = FakeProject()
        ctx = Context(target=proj, dry_run=True)
        assert ctx.dry_run is True

    def test_target_type_preserved(self):
        proj = FakeProject(name="custom")
        ctx: Context[FakeProject] = Context(target=proj)
        assert ctx.target.name == "custom"
