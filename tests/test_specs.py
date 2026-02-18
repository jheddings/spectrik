"""Tests for spectrik.specs."""

from __future__ import annotations

import logging

from pydantic import BaseModel

from spectrik.context import Context
from spectrik.specs import Absent, Ensure, Present, Specification, spec


class FakeProject(BaseModel):
    name: str = "test"


# -- Concrete spec for testing --


class AlwaysEqual(Specification["FakeProject"]):
    def equals(self, ctx: Context[FakeProject]) -> bool:
        return True

    def apply(self, ctx: Context[FakeProject]) -> None:
        pass

    def remove(self, ctx: Context[FakeProject]) -> None:
        pass


class NeverEqual(Specification["FakeProject"]):
    def equals(self, ctx: Context[FakeProject]) -> bool:
        return False

    def exists(self, ctx: Context[FakeProject]) -> bool:
        return False

    def apply(self, ctx: Context[FakeProject]) -> None:
        self._applied = True

    def remove(self, ctx: Context[FakeProject]) -> None:
        self._removed = True


class ExistsButNotEqual(Specification["FakeProject"]):
    """Resource exists but is out of date."""

    def equals(self, ctx: Context[FakeProject]) -> bool:
        return False

    def exists(self, ctx: Context[FakeProject]) -> bool:
        return True

    def apply(self, ctx: Context[FakeProject]) -> None:
        self._applied = True

    def remove(self, ctx: Context[FakeProject]) -> None:
        self._removed = True


def _make_ctx(dry_run: bool = False) -> Context[FakeProject]:
    return Context(target=FakeProject(), dry_run=dry_run)


# -- Specification tests --


class TestSpecification:
    def test_exists_defaults_to_equals(self):
        s = AlwaysEqual()
        ctx = _make_ctx()
        assert s.exists(ctx) is True

    def test_exists_overridable(self):
        s = ExistsButNotEqual()
        ctx = _make_ctx()
        assert s.exists(ctx) is True
        assert s.equals(ctx) is False


# -- Present tests --


class TestPresent:
    def test_skips_when_exists(self):
        s = AlwaysEqual()
        op = Present(s)
        ctx = _make_ctx()
        op(ctx)  # should not raise

    def test_applies_when_not_exists(self):
        s = NeverEqual()
        op = Present(s)
        ctx = _make_ctx()
        op(ctx)
        assert s._applied is True

    def test_dry_run_skips_apply(self):
        s = NeverEqual()
        op = Present(s)
        ctx = _make_ctx(dry_run=True)
        op(ctx)
        assert not hasattr(s, "_applied")


# -- Ensure tests --


class TestEnsure:
    def test_skips_when_equal(self):
        s = AlwaysEqual()
        op = Ensure(s)
        ctx = _make_ctx()
        op(ctx)  # should not raise

    def test_applies_when_not_equal(self):
        s = ExistsButNotEqual()
        op = Ensure(s)
        ctx = _make_ctx()
        op(ctx)
        assert s._applied is True

    def test_dry_run_skips_apply(self):
        s = ExistsButNotEqual()
        op = Ensure(s)
        ctx = _make_ctx(dry_run=True)
        op(ctx)
        assert not hasattr(s, "_applied")


# -- Absent tests --


class TestAbsent:
    def test_removes_when_exists(self):
        s = ExistsButNotEqual()
        op = Absent(s)
        ctx = _make_ctx()
        op(ctx)
        assert s._removed is True

    def test_skips_when_not_exists(self):
        s = NeverEqual()
        op = Absent(s)
        ctx = _make_ctx()
        op(ctx)
        assert not hasattr(s, "_removed")

    def test_dry_run_skips_remove(self):
        s = ExistsButNotEqual()
        op = Absent(s)
        ctx = _make_ctx(dry_run=True)
        op(ctx)
        assert not hasattr(s, "_removed")


# -- Logging tests --


class TestSpecOpLogging:
    def test_present_logs_skip(self, caplog):
        s = AlwaysEqual()
        op = Present(s)
        with caplog.at_level(logging.DEBUG, logger="spectrik.specs"):
            op(_make_ctx())
        assert "already exists" in caplog.text

    def test_ensure_logs_skip(self, caplog):
        s = AlwaysEqual()
        op = Ensure(s)
        with caplog.at_level(logging.DEBUG, logger="spectrik.specs"):
            op(_make_ctx())
        assert "up to date" in caplog.text

    def test_absent_logs_skip(self, caplog):
        s = NeverEqual()
        op = Absent(s)
        with caplog.at_level(logging.DEBUG, logger="spectrik.specs"):
            op(_make_ctx())
        assert "not present" in caplog.text

    def test_present_logs_dry_run(self, caplog):
        s = NeverEqual()
        op = Present(s)
        with caplog.at_level(logging.INFO, logger="spectrik.specs"):
            op(_make_ctx(dry_run=True))
        assert "DRY RUN" in caplog.text

    def test_ensure_logs_dry_run(self, caplog):
        s = ExistsButNotEqual()
        op = Ensure(s)
        with caplog.at_level(logging.INFO, logger="spectrik.specs"):
            op(_make_ctx(dry_run=True))
        assert "DRY RUN" in caplog.text

    def test_absent_logs_dry_run(self, caplog):
        s = ExistsButNotEqual()
        op = Absent(s)
        with caplog.at_level(logging.INFO, logger="spectrik.specs"):
            op(_make_ctx(dry_run=True))
        assert "DRY RUN" in caplog.text


# -- @spec() decorator tests --


class TestSpecDecorator:
    def test_registers_class(self):
        from spectrik.specs import _spec_registry

        @spec("test_widget")
        class Widget(AlwaysEqual):
            pass

        assert _spec_registry["test_widget"] is Widget

    def test_returns_class_unchanged(self):
        @spec("test_gadget")
        class Gadget(AlwaysEqual):
            pass

        assert Gadget.__name__ == "Gadget"
